from pathlib import Path
from typing import Any, Dict

from clients.qwen_client import QwenClient, QwenClientError
from env_adapters.mock_env import MockEnv
from executor.action_executor import ActionExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.replanner import Replanner
from planner.rule_planner import RulePlanner
from world_model.store import WorldModelStore


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
    env = MockEnv()
    initial = env.reset()

    logger = EpisodeLogger(OUTPUT_DIR / "episode_log.jsonl")
    store = WorldModelStore(OUTPUT_DIR / "world_model.json")
    world_model = store.initialize(initial["episode_id"])

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
    extractor = VLMExtractor(client)

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
    logger.log(
        step=1,
        event_type="world_model_update",
        observation=initial["observation"],
        model_update=extraction,
        notes="Initial extraction applied.",
    )

    planner = RulePlanner()
    plan = planner.plan(initial["task"], world_model)
    store.add_plan(plan)
    logger.log(step=2, event_type="plan", model_update=plan, notes="Initial rule plan.")

    executor = ActionExecutor(env)
    replanner = Replanner()

    for idx, action in enumerate(planner.next_actions(plan), start=3):
        result = executor.execute(action)
        logger.log(
            step=idx,
            event_type="action_result",
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )

        if not result.get("success", False):
            recovery_plan = replanner.recover(result, world_model)
            logger.log(
                step=idx + 1,
                event_type="replan",
                observation=result.get("observation", ""),
                model_update=recovery_plan,
                action=action,
                result="recovery_plan_created",
                notes="Book location marked unknown; search likely locations.",
            )
            break

    store.save()
    print(f"Demo complete. Wrote {OUTPUT_DIR / 'world_model.json'}")
    print(f"Demo complete. Wrote {OUTPUT_DIR / 'episode_log.jsonl'}")


if __name__ == "__main__":
    run_demo()
