from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from diagnostics.diagnose_episode_failure import diagnose_failure
from env_adapters.local_sim_generator import generate_random_local_sim_episode


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay one randomized LocalSim episode and diagnose failures.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="medium")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "outputs" / "replay" / "local_sim_random" / args.difficulty / args.mode / f"seed_{args.seed:04d}"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = generate_random_local_sim_episode(args.seed, args.difficulty)
    _write_json(output_dir / "generated_episode_spec.json", spec)
    _write_json(output_dir / "public_env_config.json", spec.get("public_env_config", {}))
    _write_json(output_dir / "hidden_spec_debug.json", spec.get("hidden_spec", {}))

    cmd = [
        sys.executable,
        "main.py",
        "--env",
        "local_sim_random",
        "--seed",
        str(args.seed),
        "--difficulty",
        args.difficulty,
        "--track1-procedure",
        "--validate",
        "--output-dir",
        str(output_dir),
    ]
    if args.mode == "mock":
        cmd.append("--use-mock-llm")
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True)

    world_model = _read_json(output_dir / "world_model.json")
    run_audit = _read_json(output_dir / "run_audit.json")
    generated = _read_json(output_dir / "generated_episode_spec.json") or spec
    rows = _read_jsonl(output_dir / "episode_log.jsonl")
    diagnosis = diagnose_failure(world_model, rows, run_audit, generated)
    _write_json(output_dir / "failure_diagnosis.json", diagnosis)

    report = _build_report(spec, world_model, run_audit, rows, diagnosis, completed)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return completed.returncode


def _build_report(
    spec: Dict[str, Any],
    world_model: Dict[str, Any],
    run_audit: Dict[str, Any],
    rows: List[Dict[str, Any]],
    diagnosis: Dict[str, Any],
    completed: subprocess.CompletedProcess[str],
) -> Dict[str, Any]:
    hidden = spec.get("hidden_spec", {})
    if not isinstance(hidden, dict):
        hidden = {}
    controlled = hidden.get("controlled_exception", {})
    if not isinstance(controlled, dict):
        controlled = {}
    task_status = world_model.get("task_status", {})
    if not isinstance(task_status, dict):
        task_status = {}
    return {
        "task": spec.get("task", ""),
        "controlled_exception_type": controlled.get("type", ""),
        "expected_task_status": hidden.get("expected_task_status", ""),
        "final_task_status": task_status.get("status", ""),
        "final_task_reason": task_status.get("reason", ""),
        "final_agent_room": world_model.get("agent_state", {}).get("current_room", ""),
        "locked_door_object": controlled.get("object", "") if controlled.get("type") == "door_locked" else "",
        "key_tool_availability": _key_tool_availability(world_model),
        "executed_actions": [row.get("action") for row in rows if row.get("action")],
        "failed_actions": [
            {
                "event_type": row.get("event_type", ""),
                "action": row.get("action", ""),
                "notes": row.get("notes", ""),
            }
            for row in rows
            if row.get("result") == "failure"
        ],
        "replanning_actions": _replanning_actions(rows),
        "remaining_original_actions": _remaining_original_actions(world_model, rows),
        "why_task_stayed_in_progress": task_status.get("reason", ""),
        "diagnosis": diagnosis,
        "returncode": completed.returncode,
        "stdout_tail": "\n".join(completed.stdout.splitlines()[-12:]),
        "stderr_tail": "\n".join(completed.stderr.splitlines()[-12:]),
        "output_dir": str(Path(run_audit.get("output_dir") or "")),
    }


def _key_tool_availability(world_model: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name in ["key", "coin", "screwdriver"]:
        obj = _find_object(world_model, name)
        result[name] = {
            "known": bool(obj),
            "state": obj.get("state", "") if obj else "",
            "room": obj.get("location", {}).get("room", "") if obj and isinstance(obj.get("location"), dict) else "",
            "support": obj.get("location", {}).get("support", "") if obj and isinstance(obj.get("location"), dict) else "",
        }
    return result


def _replanning_actions(rows: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    for row in rows:
        if row.get("event_type") == "replanning":
            update = row.get("model_update", {})
            if isinstance(update, dict):
                actions.extend(str(action) for action in update.get("actions", []))
    return actions


def _remaining_original_actions(world_model: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    plans = [plan for plan in world_model.get("plans", []) if isinstance(plan, dict) and plan.get("planner") == "RulePlanner"]
    original = list(plans[0].get("actions", [])) if plans else []
    executed = [str(row.get("action")) for row in rows if row.get("action")]
    remaining = list(original)
    for action in executed:
        if remaining and action == remaining[0]:
            remaining.pop(0)
    return remaining


def _find_object(world_model: Dict[str, Any], name: str) -> Dict[str, Any] | None:
    for obj in world_model.get("objects", []):
        if isinstance(obj, dict) and (obj.get("name") == name or obj.get("id") == name):
            return obj
    return None


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

