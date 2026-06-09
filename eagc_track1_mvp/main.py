import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from clients.mock_llm_client import MockLLMClient
from clients.qwen_client import QwenClient, QwenClientError
from env_adapters.mock_env import MockEnv
from executor.action_executor import ActionExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.replanner import Replanner
from planner.rule_planner import RulePlanner
from task_evaluator.task_evaluator import evaluate_task_status
from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_world_model import validate as validate_world_model
from world_model.action_effects import apply_action_effect, apply_exception_effect
from world_model.store import WorldModelStore
from world_model.update import apply_environment_context, update_agent_state


PROJECT_ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split(":", 1)
        config[key.strip()] = _parse_scalar(value.strip())
    return config


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value.replace(".", "", 1).isdigit() and value.count(".") <= 1:
        return float(value) if "." in value else int(value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the EAGC Track 1 MVP demo.")
    parser.add_argument("--episode-id", help="Mock episode id. Defaults to config.yaml episode_id.")
    parser.add_argument("--run-id", help="Stable run id for output directory naming.")
    parser.add_argument("--output-dir", help="Directory for this run's artifacts.")
    parser.add_argument("--validate", action="store_true", help="Run validators after the episode.")
    parser.add_argument("--use-mock-llm", action="store_true", help="Use deterministic mock LLM instead of vLLM.")
    return parser.parse_args()


def run_demo(args: argparse.Namespace | None = None) -> Dict[str, Any]:
    args = args or argparse.Namespace(
        episode_id=None,
        run_id=None,
        output_dir=None,
        validate=False,
        use_mock_llm=False,
    )
    config = load_config(PROJECT_ROOT / "config.yaml")
    output_root = _resolve_output_path(str(config.get("output_dir", "outputs")))

    episode_id = args.episode_id or str(config.get("episode_id", "mock-bedroom-relocated"))
    use_mock_llm = bool(args.use_mock_llm or config.get("use_mock_llm", False))
    max_recovery_steps = int(config.get("max_recovery_steps", 6))
    started_wall = datetime.now(timezone.utc)
    started = time.perf_counter()
    run_id = args.run_id or _default_run_id(started_wall)
    output_dir = _select_output_dir(args.output_dir, output_root, run_id, episode_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    audit_path = output_dir / "run_audit.json"
    qwen_calls_path = output_dir / "qwen_calls.jsonl"
    validation_status: Dict[str, Any] | str = "not_requested"
    client: QwenClient | MockLLMClient | None = None

    try:
        env = MockEnv(episode_id)
        initial = env.reset()

        logger = EpisodeLogger(episode_log_path)
        store = WorldModelStore(world_model_path)
        world_model = store.initialize(initial["episode_id"])
        world_model = apply_environment_context(world_model, initial)

        logger.log(
            step=0,
            event_type="observation",
            observation=initial["observation"],
            notes=f"Task: {initial['task']}",
        )

        if use_mock_llm:
            client = MockLLMClient(model="deterministic-mock-llm", base_url="mock://local")
        else:
            client = QwenClient(
                base_url=str(config["base_url"]),
                model=str(config["model"]),
                temperature=float(config["temperature"]),
                max_tokens=int(config["max_tokens"]),
                audit_path=qwen_calls_path,
            )
        extractor = VLMExtractor(client, debug_output_path=output_dir / "debug_qwen_raw.txt")

        extraction = extractor.extract(initial["observation"], initial["task"])
        world_model = store.update_from_extraction(extraction)
        world_model = apply_environment_context(world_model, initial)
        logger.log(
            step=1,
            event_type="perception",
            observation=initial["observation"],
            model_update=extraction,
            notes="Text-only perception extraction completed.",
        )
        logger.log(
            step=2,
            event_type="world_model_update",
            observation=initial["observation"],
            model_update=extraction,
            notes="Initial extraction applied.",
        )

        planner = RulePlanner()
        plan = planner.plan(initial["task"], world_model)
        update_agent_state(world_model, step=3, last_action="", mode="planning")
        store.add_plan(plan)
        logger.log(step=3, event_type="planning", model_update=plan, notes="Initial rule plan.")

        executor = ActionExecutor(env)
        replanner = Replanner()

        step = 4
        plan_actions = planner.next_actions(plan)
        for action_index, action in enumerate(plan_actions):
            result = executor.execute(action)
            if result.get("success", False):
                apply_action_effect(world_model, action, result, step)
            update_agent_state(
                world_model,
                step=step,
                last_action=action,
                mode="executing" if result.get("success", False) else "exception",
                result=result.get("result", ""),
            )
            logger.log(
                step=step,
                event_type="action",
                observation=result.get("observation", ""),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            step += 1

            if not result.get("success", False):
                apply_exception_effect(world_model, result, step)
                logger.log(
                    step=step,
                    event_type="execution_exception",
                    observation=result.get("observation", ""),
                    model_update=result.get("exception", {}),
                    action=action,
                    result=result.get("result", ""),
                    notes=result.get("message", ""),
                )
                step += 1
                recovery_plan = replanner.recover(result, world_model)
                update_agent_state(world_model, step=step, last_action=action, mode="replanning")
                logger.log(
                    step=step,
                    event_type="replanning",
                    observation=result.get("observation", ""),
                    model_update=recovery_plan,
                    action=action,
                    result="recovery_plan_created",
                    notes="Exception handled; recovery plan created.",
                )
                step += 1
                step, recovery_complete = execute_recovery_plan(
                    recovery_plan=recovery_plan,
                    executor=executor,
                    world_model=world_model,
                    logger=logger,
                    start_step=step,
                    max_recovery_steps=max_recovery_steps,
                )
                if recovery_complete:
                    current_status = update_task_status(world_model, initial["task"], initial["episode_id"])
                    if current_status["status"] not in {"complete", "blocked_recovered"}:
                        step = execute_resume_actions(
                            actions=plan_actions[action_index + 1 :],
                            executor=executor,
                            world_model=world_model,
                            logger=logger,
                            start_step=step,
                        )
                break

        final_status = update_task_status(world_model, initial["task"], initial["episode_id"])
        logger.log(
            step=step,
            event_type="task_status",
            model_update=world_model["task_status"],
            result=final_status["status"],
            notes=final_status["reason"],
        )
        store.save()
        if args.validate:
            validation_status = run_validators(world_model_path, episode_log_path)

        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=initial["episode_id"],
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=extractor.fallback_used,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status=validation_status,
        )
        write_run_audit(audit_path, audit)
        write_latest_artifacts(output_root, world_model_path, episode_log_path, audit_path)
        print(f"Demo complete. Wrote {world_model_path}")
        print(f"Demo complete. Wrote {episode_log_path}")
        print(f"Run audit written to {audit_path}")
        if args.validate and isinstance(validation_status, dict) and not validation_status.get("passed", False):
            raise SystemExit(1)
        return audit
    except QwenClientError as exc:
        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=episode_id,
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=False,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status={"status": "not_run", "reason": "qwen_client_error"},
        )
        audit["error_message"] = str(exc)
        write_run_audit(audit_path, audit)
        raise SystemExit(
            "\n[ERROR] Could not complete perception extraction via local vLLM.\n"
            f"{exc}\n\n"
            "Please check that vLLM is running at the configured base_url and that "
            "the configured model name is served.\n"
        ) from exc


def run_validators(world_model_path: Path, episode_log_path: Path) -> Dict[str, Any]:
    checks = {
        "world_model": validate_world_model(world_model_path),
        "semantic_consistency": validate_semantic_consistency(world_model_path),
        "episode_log": validate_episode_log(episode_log_path),
        "task_status": validate_task_status(world_model_path, episode_log_path),
    }
    status = {
        name: {"passed": not errors, "errors": errors}
        for name, errors in checks.items()
    }
    status["passed"] = all(item["passed"] for item in status.values() if isinstance(item, dict))
    for name, item in status.items():
        if isinstance(item, dict):
            print(f"Validation {name}: {'passed' if item['passed'] else 'failed'}")
            for error in item["errors"]:
                print(f"- {error}")
    return status


def execute_recovery_plan(
    recovery_plan: Dict[str, Any],
    executor: ActionExecutor,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
    start_step: int,
    max_recovery_steps: int,
) -> tuple[int, bool]:
    step = start_step
    actions = list(recovery_plan.get("actions", []))[:max_recovery_steps]
    for action in actions:
        result = executor.execute(action)
        if result.get("success", False):
            apply_action_effect(world_model, action, result, step)
        update_agent_state(
            world_model,
            step=step,
            last_action=action,
            mode="recovering" if result.get("success", False) else "recovery_failed",
            result=result.get("result", ""),
        )
        logger.log(
            step=step,
            event_type="recovery_action",
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        step += 1
        if not result.get("success", False):
            logger.log(
                step=step,
                event_type="recovery_failed",
                observation=result.get("observation", ""),
                model_update=result.get("exception", {}),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            update_agent_state(world_model, step=step, last_action=action, mode="recovery_failed")
            return step + 1, False

    logger.log(
        step=step,
        event_type="recovery_complete",
        model_update=recovery_plan,
        result="success",
        notes=f"Executed {len(actions)} recovery actions.",
    )
    update_agent_state(world_model, step=step, last_action="", mode="recovery_complete")
    return step + 1, True


def execute_resume_actions(
    actions: list[str],
    executor: ActionExecutor,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
    start_step: int,
) -> int:
    step = start_step
    for action in actions:
        result = executor.execute(action)
        if result.get("success", False):
            apply_action_effect(world_model, action, result, step)
        update_agent_state(
            world_model,
            step=step,
            last_action=action,
            mode="resuming" if result.get("success", False) else "resume_failed",
            result=result.get("result", ""),
        )
        logger.log(
            step=step,
            event_type="resume_action",
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        step += 1
        if not result.get("success", False):
            logger.log(
                step=step,
                event_type="resume_failed",
                observation=result.get("observation", ""),
                model_update=result.get("exception", {}),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            update_agent_state(world_model, step=step, last_action=action, mode="resume_failed")
            return step + 1
    return step


def update_task_status(world_model: Dict[str, Any], task: str, episode_id: str) -> Dict[str, Any]:
    evaluated = evaluate_task_status(task, world_model, episode_id)
    status = {
        "status": evaluated["task_status"],
        "success": evaluated["success"],
        "reason": evaluated["reason"],
        "evidence": evaluated["evidence"],
    }
    world_model["task_status"] = status
    return status


def build_run_audit(
    config: Dict[str, Any],
    run_id: str,
    episode_id: str,
    output_dir: Path,
    use_mock_llm: bool,
    started_wall: datetime,
    latency_seconds: float,
    client: QwenClient | MockLLMClient | None,
    fallback_used: bool,
    debug_raw_path: Path,
    world_model_path: Path,
    episode_log_path: Path,
    validation_status: Dict[str, Any] | str,
) -> Dict[str, Any]:
    ended = datetime.now(timezone.utc)
    qwen_call_count = 0 if use_mock_llm or client is None else client.call_count
    qwen_success_count = 0 if use_mock_llm or client is None else client.success_count
    qwen_failure_count = 0 if use_mock_llm or client is None else client.failure_count
    return {
        "run_id": run_id,
        "episode_id": episode_id,
        "output_dir": str(output_dir),
        "model": "deterministic-mock-llm" if use_mock_llm else config.get("model"),
        "base_url": "mock://local" if use_mock_llm else config.get("base_url"),
        "use_mock_llm": use_mock_llm,
        "start_time": started_wall.isoformat(),
        "end_time": ended.isoformat(),
        "latency_seconds": round(latency_seconds, 6),
        "qwen_call_count": qwen_call_count,
        "qwen_call_success_count": qwen_success_count,
        "qwen_call_failure_count": qwen_failure_count,
        "fallback_used": fallback_used,
        "debug_raw_path": str(debug_raw_path) if debug_raw_path.exists() else "",
        "world_model_path": str(world_model_path),
        "episode_log_path": str(episode_log_path),
        "validation_status": validation_status,
    }


def write_run_audit(path: Path, audit: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")


def write_latest_artifacts(output_root: Path, world_model_path: Path, episode_log_path: Path, audit_path: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for source, name in [
        (world_model_path, "world_model.json"),
        (episode_log_path, "episode_log.jsonl"),
        (audit_path, "run_audit.json"),
    ]:
        if source.exists():
            shutil.copy2(source, output_root / name)


def _resolve_output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _select_output_dir(output_dir_arg: str | None, output_root: Path, run_id: str, episode_id: str) -> Path:
    if output_dir_arg:
        return _resolve_output_path(output_dir_arg)
    return output_root / "runs" / f"{run_id}_{episode_id}"


def _default_run_id(started_wall: datetime) -> str:
    return started_wall.strftime("%Y%m%dT%H%M%S%fZ")


if __name__ == "__main__":
    run_demo(parse_args())
