from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from env_adapters.visual_sequence_env import VisualSequenceEnv
from executor.symbolic_visual_executor import SymbolicVisualExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.rule_planner import RulePlanner
from task_evaluator.visual_task_evaluator import evaluate_visual_task
from world_model.store import WorldModelStore
from world_model.update import apply_environment_context, apply_frame_visibility, update_agent_state


class VisualLocalHybridRunner:
    """Build a visual world model, then run symbolic planning/evaluation on it."""

    def __init__(
        self,
        env: VisualSequenceEnv,
        extractor: VLMExtractor,
        store: WorldModelStore,
        logger: EpisodeLogger,
        output_dir: Path,
    ) -> None:
        self.env = env
        self.extractor = extractor
        self.store = store
        self.logger = logger
        self.output_dir = output_dir

    def run(self, initial: Dict[str, Any], task: str) -> Dict[str, Any]:
        world_model = self.store.world_model
        packet = initial
        processed_frames: list[str] = []
        step = 1
        frame_index = 0

        while True:
            observation = packet["observation"]
            if frame_index > 0:
                self.logger.log(
                    step=step,
                    event_type="observation",
                    observation=_render_observation(observation),
                    notes=f"Visual sequence frame {frame_index}.",
                )
                step += 1
            extraction = self.extractor.extract(observation, packet["task"])
            world_model = self.store.update_from_extraction(extraction)
            apply_environment_context(world_model, packet)
            observed_names = _extraction_object_names(extraction)
            apply_frame_visibility(world_model, observed_names, frame_index)
            update_agent_state(world_model, step=step, last_action="", mode="visual_exploration")
            processed_frames.append(str(observation["image_path"]))

            self.logger.log(
                step=step,
                event_type="perception",
                observation=_render_observation(observation),
                model_update=extraction,
                notes=f"Visual hybrid extraction completed for frame {frame_index}.",
            )
            step += 1
            self.logger.log(
                step=step,
                event_type="world_model_update",
                observation=_render_observation(observation),
                model_update={
                    "frame_index": frame_index,
                    "observed_objects": observed_names,
                    "world_model_object_count": len(world_model.get("objects", [])),
                    "world_model_relation_count": len(world_model.get("relations", [])),
                },
                notes=f"Visual hybrid world model updated for frame {frame_index}.",
            )
            step += 1

            result = self.env.step("next_frame")
            if not result.get("success"):
                break
            packet = result["observation"]
            frame_index += 1

        self.logger.log(
            step=step,
            event_type="visual_world_model_built",
            model_update={
                "processed_frames": processed_frames,
                "object_count": len(world_model.get("objects", [])),
                "relation_count": len(world_model.get("relations", [])),
            },
            notes="Visual exploration phase completed.",
        )
        step += 1

        self.logger.log(step=step, event_type="task_received", observation=task, notes="Visual task received.")
        step += 1

        planner = RulePlanner()
        plan = planner.plan_visual(task, world_model)
        self.store.add_plan(plan)
        update_agent_state(world_model, step=step, last_action="", mode="visual_planning")
        self.logger.log(step=step, event_type="planning", model_update=plan, notes="Visual-local symbolic plan.")
        step += 1

        executor = SymbolicVisualExecutor(world_model, task)
        last_answer = ""
        last_evidence: list[str] = []
        for action in plan.get("actions", []):
            result = executor.execute(str(action))
            update_agent_state(world_model, step=step, last_action=str(action), mode="symbolic_visual_execution")
            if result.get("answer"):
                last_answer = str(result["answer"])
            if result.get("evidence"):
                last_evidence = list(result["evidence"])
            self.logger.log(
                step=step,
                event_type="symbolic_action",
                model_update={"answer": result.get("answer", ""), "evidence": result.get("evidence", [])},
                action=str(action),
                result=str(result.get("result", "")),
                notes=str(result.get("message", "")),
            )
            step += 1
            if str(action).startswith(("answer_location(", "answer_relation(")):
                self.logger.log(
                    step=step,
                    event_type="answer",
                    model_update={"answer": result.get("answer", ""), "evidence": result.get("evidence", [])},
                    action=str(action),
                    result=str(result.get("result", "")),
                    notes="Symbolic visual answer emitted.",
                )
                step += 1

        task_status = evaluate_visual_task(task, world_model)
        if last_answer and not task_status.get("answer"):
            task_status["answer"] = last_answer
        if last_evidence and not task_status.get("evidence"):
            task_status["evidence"] = last_evidence
        world_model["task_status"] = task_status
        self.logger.log(
            step=step,
            event_type="task_status",
            model_update=task_status,
            result=str(task_status.get("status", "")),
            notes=str(task_status.get("answer") or task_status.get("reason", "")),
        )
        self.store.save()

        return {
            "world_model": world_model,
            "processed_frames": processed_frames,
            "plan": plan,
            "task_status": task_status,
            "symbolic_action_count": executor.symbolic_action_count,
            "unsupported_physical_action_count": executor.unsupported_physical_action_count,
            "evidence_count": len(task_status.get("evidence", [])),
        }


def _render_observation(observation: Any) -> str:
    import json

    if isinstance(observation, str):
        return observation
    return json.dumps(observation, ensure_ascii=False)


def _extraction_object_names(extraction: Dict[str, Any]) -> list[str]:
    names = []
    for obj in extraction.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or obj.get("id")
        if name:
            names.append(str(name))
    return names
