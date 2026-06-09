from pathlib import Path
from typing import Any, Dict

from clients.qwen_client import QwenClient, QwenClientError
from env_adapters.mock_env import MockEnv
from executor.action_executor import ActionExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.replanner import Replanner
from planner.rule_planner import RulePlanner
from world_model.action_effects import apply_action_effect, apply_exception_effect
from world_model.store import WorldModelStore
from world_model.update import apply_environment_context, update_agent_state


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"


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
    if value.replace(".", "", 1).isdigit() and value.count(".") <= 1:
        return float(value) if "." in value else int(value)
    return value


def run_demo() -> None:
    config = load_config(PROJECT_ROOT / "config.yaml")
    env = MockEnv(str(config.get("episode_id", "mock-bedroom-relocated")))
    initial = env.reset()

    logger = EpisodeLogger(OUTPUT_DIR / "episode_log.jsonl")
    store = WorldModelStore(OUTPUT_DIR / "world_model.json")
    world_model = store.initialize(initial["episode_id"])
    world_model = apply_environment_context(world_model, initial)

    logger.log(
        step=0,
        event_type="observation",
        observation=initial["observation"],
        notes=f"Task: {initial['task']}",
    )

    client = QwenClient(
        base_url=config["base_url"],
        model=config["model"],
        temperature=float(config["temperature"]),
        max_tokens=int(config["max_tokens"]),
    )
    extractor = VLMExtractor(client, debug_output_path=OUTPUT_DIR / "debug_qwen_raw.txt")

    try:
        extraction = extractor.extract(initial["observation"], initial["task"])
    except QwenClientError as exc:
        raise SystemExit(
            "\n[ERROR] Could not complete perception extraction via local vLLM.\n"
            f"{exc}\n\n"
            "Please check that vLLM is running at the configured base_url and that "
            "the configured model name is served.\n"
        ) from exc

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
    print(f"Demo complete. Wrote {OUTPUT_DIR / 'world_model.json'}")
    print(f"Demo complete. Wrote {OUTPUT_DIR / 'episode_log.jsonl'}")


if __name__ == "__main__":
    run_demo()
