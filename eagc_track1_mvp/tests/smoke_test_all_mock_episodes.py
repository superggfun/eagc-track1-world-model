import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SMOKE_DIR = OUTPUT_DIR / "smoke"

sys.path.insert(0, str(PROJECT_ROOT))

from validators.validate_episode_log import validate as validate_episode_log  # noqa: E402
from validators.validate_semantic_consistency import validate as validate_semantic_consistency  # noqa: E402
from validators.validate_task_status import validate as validate_task_status  # noqa: E402
from validators.validate_world_model import validate as validate_world_model  # noqa: E402


EPISODES = [
    "mock-bedroom-relocated",
    "mock-hallway-door-locked",
    "mock-kitchen-container-unavailable",
    "mock-study-tool-substitution",
    "mock-livingroom-nominal",
]

EXCEPTION_EPISODES = {
    "mock-bedroom-relocated": "object_relocated",
    "mock-hallway-door-locked": "door_locked",
    "mock-kitchen-container-unavailable": "target_container_unavailable",
    "mock-study-tool-substitution": "tool_substitution",
}
EXPECTED_TASK_STATUS = {
    "mock-bedroom-relocated": "complete",
    "mock-hallway-door-locked": "complete",
    "mock-kitchen-container-unavailable": "blocked_recovered",
    "mock-study-tool-substitution": "complete",
    "mock-livingroom-nominal": "complete",
}


def main() -> int:
    args = parse_args()
    episodes = selected_episodes(args)
    summary_rows = []
    for episode_id in episodes:
        output_dir = SMOKE_DIR / args.mode / episode_id
        print(f"\n=== Smoke mode={args.mode} episode={episode_id} ===")
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)

        command = [
            sys.executable,
            "main.py",
            "--episode-id",
            episode_id,
            "--run-id",
            f"smoke_{args.mode}_{episode_id}",
            "--output-dir",
            str(output_dir),
        ]
        if args.mode == "mock":
            command.append("--use-mock-llm")
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            return completed.returncode

        validation = run_validators(output_dir)
        audit = _read_json(output_dir / "run_audit.json")
        world_model = _read_json(output_dir / "world_model.json")
        task_status = world_model.get("task_status", {})
        print(
            "episode_id={episode_id} task_status={status} success={success} "
            "qwen_call_count={qwen_call_count} fallback_used={fallback_used} "
            "validation={validation} output_dir={output_dir}".format(
                episode_id=episode_id,
                status=task_status.get("status"),
                success=task_status.get("success"),
                qwen_call_count=audit.get("qwen_call_count"),
                fallback_used=audit.get("fallback_used"),
                validation="passed" if validation["passed"] else "failed",
                output_dir=output_dir,
            )
        )
        summary_rows.append(
            {
                "episode_id": episode_id,
                "task_status": task_status.get("status"),
                "fallback_used": audit.get("fallback_used", False),
                "qwen_call_count": audit.get("qwen_call_count", 0),
                "latency_seconds": audit.get("latency_seconds", 0),
                "validation_status": "passed" if validation["passed"] else "failed",
                "output_dir": str(output_dir),
            }
        )
        if not validation["passed"]:
            print(json.dumps(validation, indent=2, ensure_ascii=False))
            return 1

        expectation_error = _check_recovery_expectations(episode_id, output_dir)
        if expectation_error:
            print(expectation_error)
            return 1
        task_status_error = _check_task_status(episode_id, world_model)
        if task_status_error:
            print(task_status_error)
            return 1
        strict_error = _check_strict_real(args, episode_id, audit, task_status, validation)
        if strict_error:
            print(strict_error)
            return 1

    if args.mode == "real":
        _write_real_summary_report(summary_rows)

    print(f"\nAll requested {args.mode} episode smoke tests passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mock episodes through validators.")
    parser.add_argument(
        "--mode",
        choices=["mock", "real"],
        default="mock",
        help="mock is deterministic and default; real calls local vLLM.",
    )
    parser.add_argument("--episode-id", choices=EPISODES, help="Run only one episode.")
    parser.add_argument("--all", action="store_true", help="Run all episodes.")
    parser.add_argument(
        "--strict-real",
        action="store_true",
        help="In real mode, fail if fallback/debug output/Qwen failures occur.",
    )
    return parser.parse_args()


def selected_episodes(args: argparse.Namespace) -> List[str]:
    if args.episode_id and not args.all:
        return [args.episode_id]
    return list(EPISODES)


def run_validators(output_dir: Path) -> Dict[str, Any]:
    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    checks = {
        "world_model": validate_world_model(world_model_path),
        "semantic_consistency": validate_semantic_consistency(world_model_path),
        "episode_log": validate_episode_log(episode_log_path),
        "task_status": validate_task_status(world_model_path, episode_log_path),
    }
    result = {name: {"passed": not errors, "errors": errors} for name, errors in checks.items()}
    result["passed"] = all(item["passed"] for item in result.values() if isinstance(item, dict))
    return result


def _check_recovery_expectations(episode_id: str, output_dir: Path) -> str:
    log_path = output_dir / "episode_log.jsonl"
    world_model_path = output_dir / "world_model.json"
    rows = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [row.get("event_type") for row in rows]
    if episode_id in EXCEPTION_EPISODES:
        expected_type = EXCEPTION_EPISODES[episode_id]
        world_model = _read_json(world_model_path)
        exception_types = [
            item.get("exception", {}).get("type")
            for item in world_model.get("exceptions", [])
            if isinstance(item, dict)
        ]
        if expected_type not in exception_types:
            return f"{episode_id} missing expected exception type {expected_type}."
        if "replanning" not in event_types:
            return f"{episode_id} missing replanning event."
        if not any(event in event_types for event in ["recovery_action", "recovery_complete"]):
            return f"{episode_id} missing recovery_action or recovery_complete event."
    return ""


def _check_task_status(episode_id: str, world_model: Dict[str, Any]) -> str:
    task_status = world_model.get("task_status", {})
    expected = EXPECTED_TASK_STATUS[episode_id]
    if task_status.get("status") != expected:
        return f"{episode_id} expected task_status {expected}, got {task_status.get('status')}."
    return ""


def _check_strict_real(
    args: argparse.Namespace,
    episode_id: str,
    audit: Dict[str, Any],
    task_status: Dict[str, Any],
    validation: Dict[str, Any],
) -> str:
    if args.mode != "real" or not args.strict_real:
        return ""
    expected = EXPECTED_TASK_STATUS[episode_id]
    failures = []
    if audit.get("fallback_used") is not False:
        failures.append("fallback_used must be false")
    if audit.get("debug_raw_path"):
        failures.append("debug_raw_path must be empty")
    if audit.get("qwen_call_failure_count") != 0:
        failures.append("qwen_call_failure_count must be 0")
    if task_status.get("status") != expected:
        failures.append(f"task_status must be {expected}, got {task_status.get('status')}")
    if not validation.get("passed", False):
        failures.append("validation must pass")
    if failures:
        return f"{episode_id} strict real failed: " + "; ".join(failures)
    return ""


def _write_real_summary_report(rows: List[Dict[str, Any]]) -> None:
    report_path = SMOKE_DIR / "real" / "summary_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Real smoke summary report written to {report_path}")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
