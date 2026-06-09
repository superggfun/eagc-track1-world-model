import argparse
import json
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
from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
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
    parser.add_argument("--validate", action="store_true", help="Run validators after the episode.")
    parser.add_argument("--use-mock-llm", action="store_true", help="Use deterministic mock LLM instead of vLLM.")
    return parser.parse_args()


def run_demo(args: argparse.Namespace | None = None) -> Dict[str, Any]:
    args = args or argparse.Namespace(episode_id=None, validate=False, use_mock_llm=False)
    config = load_config(PROJECT_ROOT / "config.yaml")
    output_dir = _resolve_output_dir(str(config.get("output_dir", "outputs")))
    output_dir.mkdir(parents=True, exist_ok=True)

    episode_id = args.episode_id or str(config.get("episode_id", "mock-bedroom-relocated"))
    use_mock_llm = bool(args.use_mock_llm or config.get("use_mock_llm", False))
    started_wall = datetime.now(timezone.utc)
    started = time.perf_counter()

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
        for action in planner.next_actions(plan):
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
                break

        store.save()
        if args.validate:
            validation_status = run_validators(world_model_path, episode_log_path)

        audit = build_run_audit(
            config=config,
            episode_id=initial["episode_id"],
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status=validation_status,
        )
        write_run_audit(audit_path, audit)
        print(f"Demo complete. Wrote {world_model_path}")
        print(f"Demo complete. Wrote {episode_log_path}")
        print(f"Run audit written to {audit_path}")
        if args.validate and isinstance(validation_status, dict) and not validation_status.get("passed", False):
            raise SystemExit(1)
        return audit
    except QwenClientError as exc:
        audit = build_run_audit(
            config=config,
            episode_id=episode_id,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
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


def build_run_audit(
    config: Dict[str, Any],
    episode_id: str,
    use_mock_llm: bool,
    started_wall: datetime,
    latency_seconds: float,
    client: QwenClient | MockLLMClient | None,
    world_model_path: Path,
    episode_log_path: Path,
    validation_status: Dict[str, Any] | str,
) -> Dict[str, Any]:
    ended = datetime.now(timezone.utc)
    qwen_call_count = 0 if use_mock_llm or client is None else client.call_count
    qwen_success_count = 0 if use_mock_llm or client is None else client.success_count
    qwen_failure_count = 0 if use_mock_llm or client is None else client.failure_count
    return {
        "episode_id": episode_id,
        "model": "deterministic-mock-llm" if use_mock_llm else config.get("model"),
        "base_url": "mock://local" if use_mock_llm else config.get("base_url"),
        "use_mock_llm": use_mock_llm,
        "start_time": started_wall.isoformat(),
        "end_time": ended.isoformat(),
        "latency_seconds": round(latency_seconds, 6),
        "qwen_call_count": qwen_call_count,
        "qwen_call_success_count": qwen_success_count,
        "qwen_call_failure_count": qwen_failure_count,
        "world_model_path": str(world_model_path),
        "episode_log_path": str(episode_log_path),
        "validation_status": validation_status,
    }


def write_run_audit(path: Path, audit: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_output_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    run_demo(parse_args())
