from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from env_adapters.local_sim_env import LocalSimEnv
from executor.action_executor import ActionExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.replanner import Replanner
from planner.rule_planner import RulePlanner
from scoring.track1_score import compute_track1_score, write_track1_score
from task_evaluator.task_evaluator import evaluate_task_status
from world_model.action_effects import apply_action_effect, apply_exception_effect
from world_model.store import WorldModelStore
from world_model.update import apply_environment_context, update_agent_state


DEFAULT_BUDGETS = {
    "exploration_steps": 12,
    "planning_steps": 3,
    "execution_steps": 50,
    "max_recovery_steps": 8,
}


class Track1ProcedureRunner:
    """Official-style local Track 1 runner with explicit phases and budgets."""

    def __init__(
        self,
        env: LocalSimEnv,
        extractor: VLMExtractor,
        store: WorldModelStore,
        logger: EpisodeLogger,
        output_dir: Path,
        budgets: Dict[str, Any] | None = None,
        evaluator_context: Dict[str, Any] | None = None,
    ) -> None:
        self.env = env
        self.extractor = extractor
        self.store = store
        self.logger = logger
        self.output_dir = output_dir
        self.budgets = {**DEFAULT_BUDGETS, **(budgets or {})}
        self.executor = ActionExecutor(env)
        self.planner = RulePlanner()
        self.replanner = Replanner()
        self.step = 0
        self.exploration_steps_used = 0
        self.planning_steps_used = 0
        self.execution_steps_used = 0
        self.recovery_steps_used = 0
        self.phase_budget_exceeded = False
        self.task = ""
        self.plan: Dict[str, Any] = {}
        self.evaluator_context = evaluator_context or {}

    def run_episode(self, episode_id: str) -> Dict[str, Any]:
        del episode_id
        initial = self.env.reset(reveal_task=False)
        world_model = self.store.initialize(initial["episode_id"])
        world_model["procedure_mode"] = "track1_official_style"
        world_model = apply_environment_context(world_model, initial)
        self._refresh_discovery_fields(world_model)

        self.exploration_phase(initial)
        self.task_reception_phase()
        self.planning_phase()
        self.execution_phase()
        self.final_evaluation()
        self.store.save()

        rows = _read_rows(self.logger.output_path)
        audit_updates = self.audit_updates()
        score_path = self.output_dir / "track1_score.json"
        score = compute_track1_score(world_model, rows, audit_updates, validation_status="not_requested")
        write_track1_score(score_path, score)
        audit_updates["track1_score_path"] = str(score_path)
        audit_updates["track1_total_score"] = score["total_score"]
        return {
            "initial": initial,
            "world_model": world_model,
            "audit_updates": audit_updates,
            "track1_score": score,
            "track1_score_path": score_path,
        }

    def exploration_phase(self, initial: Dict[str, Any]) -> None:
        self.logger.log(
            step=self.step,
            event_type="exploration_start",
            observation=_render_observation(initial.get("observation", "")),
            notes="Track 1 exploration phase started with task hidden.",
        )
        self.step += 1
        self._perceive(initial, "Explore the environment and map rooms, objects, topology, and frontiers.")

        for action in self._exploration_actions(initial):
            if self.exploration_steps_used >= int(self.budgets["exploration_steps"]):
                self.phase_budget_exceeded = True
                break
            result = self.executor.execute(action)
            self.exploration_steps_used += 1
            if result.get("success", False):
                apply_action_effect(self.store.world_model, action, result, self.step)
            update_agent_state(
                self.store.world_model,
                step=self.step,
                last_action=action,
                mode="exploring" if result.get("success", False) else "exploration_blocked",
                result=result.get("result", ""),
            )
            self.logger.log(
                step=self.step,
                event_type="exploration_action",
                observation=result.get("observation", ""),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            self.step += 1
            packet = result.get("observation_packet")
            if isinstance(packet, dict):
                self._perceive(packet, "Explore the environment and map rooms, objects, topology, and frontiers.")

        self._refresh_discovery_fields(self.store.world_model)
        self.logger.log(
            step=self.step,
            event_type="exploration_end",
            model_update={
                "visited_rooms": self.store.world_model.get("visited_rooms", []),
                "frontiers": self.store.world_model.get("frontiers", []),
            },
            notes="Track 1 exploration phase ended before task reception.",
        )
        self.step += 1

    def task_reception_phase(self) -> None:
        packet = self.env.reveal_task()
        self.task = str(packet.get("task", ""))
        self.store.world_model["task"] = self.task
        self.store.world_model["task_received_after_exploration"] = True
        apply_environment_context(self.store.world_model, packet)
        self.logger.log(
            step=self.step,
            event_type="task_received",
            observation=_render_observation(packet.get("observation", "")),
            model_update={"task": self.task},
            result="task_received",
            notes="Natural-language task revealed after exploration.",
        )
        self.step += 1

    def planning_phase(self) -> None:
        self.plan = self.planner.plan(self.task, self.store.world_model)
        self.planning_steps_used = 1
        if self.planning_steps_used > int(self.budgets["planning_steps"]):
            self.phase_budget_exceeded = True
        update_agent_state(self.store.world_model, step=self.step, last_action="", mode="planning")
        self.store.add_plan(self.plan)
        self.logger.log(
            step=self.step,
            event_type="planning",
            model_update=self.plan,
            result="plan_created",
            notes="RulePlanner created task plan from current world model and received task.",
        )
        self.step += 1

    def execution_phase(self) -> None:
        self.logger.log(
            step=self.step,
            event_type="execution_start",
            model_update=self.plan,
            notes="Execution and recovery phase started.",
        )
        self.step += 1

        actions = self.planner.next_actions(self.plan)
        for action_index, action in enumerate(actions):
            if self.execution_steps_used >= int(self.budgets["execution_steps"]):
                self.phase_budget_exceeded = True
                break
            result = self._execute_action(action, event_type="action", mode="executing")
            if not result.get("success", False):
                self._handle_failure(result, action, actions[action_index + 1 :])
                break

    def final_evaluation(self) -> None:
        evaluated = evaluate_task_status(
            self.task,
            self.store.world_model,
            self.store.world_model["episode_id"],
            evaluator_context=self.evaluator_context,
        )
        status = {
            "status": evaluated["task_status"],
            "success": evaluated["success"],
            "reason": evaluated["reason"],
            "evidence": evaluated["evidence"],
        }
        self.store.world_model["task_status"] = status
        self.logger.log(
            step=self.step,
            event_type="task_status",
            model_update=status,
            result=status["status"],
            notes=status["reason"],
        )
        self.step += 1
        self.logger.log(
            step=self.step,
            event_type="task_evaluation",
            model_update=status,
            result=status["status"],
            notes=status["reason"],
        )
        self.step += 1

    def audit_updates(self) -> Dict[str, Any]:
        total_steps = (
            self.exploration_steps_used
            + self.planning_steps_used
            + self.execution_steps_used
            + self.recovery_steps_used
        )
        return {
            "track1_procedure": True,
            "track1_budgets": dict(self.budgets),
            "exploration_steps_used": self.exploration_steps_used,
            "planning_steps_used": self.planning_steps_used,
            "execution_steps_used": self.execution_steps_used,
            "recovery_steps_used": self.recovery_steps_used,
            "total_steps_used": total_steps,
            "phase_budget_exceeded": self.phase_budget_exceeded,
        }

    def _handle_failure(self, result: Dict[str, Any], action: str, remaining_actions: List[str]) -> None:
        apply_exception_effect(self.store.world_model, result, self.step)
        self.logger.log(
            step=self.step,
            event_type="execution_exception",
            observation=result.get("observation", ""),
            model_update=result.get("exception", {}),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        self.step += 1

        recovery_plan = self.replanner.recover(result, self.store.world_model)
        update_agent_state(self.store.world_model, step=self.step, last_action=action, mode="replanning")
        self.logger.log(
            step=self.step,
            event_type="replanning",
            observation=result.get("observation", ""),
            model_update=recovery_plan,
            action=action,
            result="recovery_plan_created",
            notes="Exception handled; recovery plan created.",
        )
        self.step += 1

        recovery_complete = self._execute_recovery_actions(recovery_plan)
        if not recovery_complete:
            return
        remaining_actions = self._door_route_continuation(result, action, remaining_actions)
        current = evaluate_task_status(
            self.task,
            self.store.world_model,
            self.store.world_model["episode_id"],
            evaluator_context=self.evaluator_context,
        )
        if current["task_status"] in {"complete", "blocked_recovered"}:
            return
        for resume_action in remaining_actions:
            if self.execution_steps_used >= int(self.budgets["execution_steps"]):
                self.phase_budget_exceeded = True
                return
            resumed = self._execute_action(resume_action, event_type="resume_action", mode="resuming")
            if not resumed.get("success", False):
                self.logger.log(
                    step=self.step,
                    event_type="resume_failed",
                    observation=resumed.get("observation", ""),
                    model_update=resumed.get("exception", {}),
                    action=resume_action,
                    result=resumed.get("result", ""),
                    notes=resumed.get("message", ""),
                )
                self.step += 1
                return

    def _door_route_continuation(
        self,
        failure: Dict[str, Any],
        failed_action: str,
        remaining_actions: List[str],
    ) -> List[str]:
        exception = failure.get("exception", {})
        if not isinstance(exception, dict) or exception.get("type") != "door_locked":
            return remaining_actions
        target_room = self._target_room_after_door_failure(failed_action, exception)
        if not target_room:
            return remaining_actions
        current_room = self.store.world_model.get("agent_state", {}).get("current_room")
        action = f"navigate_to({target_room})"
        if current_room == target_room or action in remaining_actions:
            return remaining_actions
        return [action, *remaining_actions]

    def _target_room_after_door_failure(self, failed_action: str, exception: Dict[str, Any]) -> str:
        if failed_action.startswith("navigate_to(") and failed_action.endswith(")"):
            target = failed_action.removeprefix("navigate_to(").removesuffix(")")
            if target in {"bedroom", "hallway", "kitchen", "living_room"}:
                return target
        condition = self.evaluator_context.get("success_condition", {})
        if isinstance(condition, dict) and condition.get("room"):
            return str(condition["room"])
        door = str(exception.get("object") or "")
        if door == "kitchen_door":
            return "kitchen"
        if door == "living_room_door":
            return "living_room"
        if door == "bedroom_door":
            return "bedroom"
        return ""

    def _execute_recovery_actions(self, recovery_plan: Dict[str, Any]) -> bool:
        max_recovery = int(self.budgets["max_recovery_steps"])
        for action in list(recovery_plan.get("actions", []))[:max_recovery]:
            if self.recovery_steps_used >= max_recovery:
                self.phase_budget_exceeded = True
                return False
            result = self._execute_action(action, event_type="recovery_action", mode="recovering", recovery=True)
            if not result.get("success", False):
                self.logger.log(
                    step=self.step,
                    event_type="recovery_failed",
                    observation=result.get("observation", ""),
                    model_update=result.get("exception", {}),
                    action=action,
                    result=result.get("result", ""),
                    notes=result.get("message", ""),
                )
                self.step += 1
                return False
        self.logger.log(
            step=self.step,
            event_type="recovery_complete",
            model_update=recovery_plan,
            result="success",
            notes="Recovery plan actions completed.",
        )
        self.step += 1
        return True

    def _execute_action(
        self,
        action: str,
        event_type: str,
        mode: str,
        recovery: bool = False,
    ) -> Dict[str, Any]:
        result = self.executor.execute(action)
        if recovery:
            self.recovery_steps_used += 1
        else:
            self.execution_steps_used += 1
        if result.get("success", False):
            apply_action_effect(self.store.world_model, action, result, self.step)
        update_agent_state(
            self.store.world_model,
            step=self.step,
            last_action=action,
            mode=mode if result.get("success", False) else "exception",
            result=result.get("result", ""),
        )
        self.logger.log(
            step=self.step,
            event_type=event_type,
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        self.step += 1
        packet = result.get("observation_packet")
        if isinstance(packet, dict):
            self._perceive(packet, self.task or "Explore the environment.")
        return result

    def _perceive(self, packet: Dict[str, Any], task: str) -> None:
        observation = packet.get("observation", "")
        extraction = self.extractor.extract(observation, task)
        self.store.update_from_extraction(extraction)
        apply_environment_context(self.store.world_model, packet)
        self._refresh_discovery_fields(self.store.world_model)
        self.logger.log(
            step=self.step,
            event_type="perception",
            observation=_render_observation(observation),
            model_update=extraction,
            notes="Procedure perception extraction completed.",
        )
        self.step += 1
        self.logger.log(
            step=self.step,
            event_type="world_model_update",
            observation=_render_observation(observation),
            model_update={
                "visited_rooms": self.store.world_model.get("visited_rooms", []),
                "frontiers": self.store.world_model.get("frontiers", []),
                "objects": self.store.world_model.get("objects", []),
            },
            notes="Procedure world model updated.",
        )
        self.step += 1

    def _exploration_actions(self, initial: Dict[str, Any]) -> List[str]:
        current = str(initial.get("current_room", ""))
        actions = [f"explore({current})", "search(visible_area)"]
        if current != "hallway":
            actions.extend(["navigate_to(hallway)", "explore(hallway)", "search(visible_area)"])
        if current not in {"living_room", "kitchen"}:
            actions.extend(["navigate_to(living_room)", "explore(living_room)"])
        return actions

    def _refresh_discovery_fields(self, world_model: Dict[str, Any]) -> None:
        visited = world_model.get("visited_rooms", [])
        if isinstance(visited, list):
            world_model["discovered_rooms"] = list(dict.fromkeys(visited))
        objects = [
            obj.get("name") or obj.get("id")
            for obj in world_model.get("objects", [])
            if isinstance(obj, dict) and (obj.get("name") or obj.get("id"))
        ]
        world_model["discovered_objects"] = list(dict.fromkeys(objects))


def _render_observation(observation: Any) -> str:
    if isinstance(observation, str):
        return observation
    return json.dumps(observation, ensure_ascii=False)


def _read_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
