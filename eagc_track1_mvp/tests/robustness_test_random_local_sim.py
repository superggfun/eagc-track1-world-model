import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_random_local_sim_run import validate as validate_random_local_sim_run
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_track1_procedure import validate as validate_track1_procedure
from validators.validate_world_model import validate as validate_world_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Run randomized LocalSim robustness evaluation.")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--num-episodes", type=int, default=20)
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="easy")
    args = parser.parse_args()

    root = PROJECT_ROOT / "outputs" / "robustness" / "local_sim_random" / args.difficulty
    root.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    for seed in range(1, args.num_episodes + 1):
        output_dir = root / f"seed_{seed:04d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        for artifact in ["world_model.json", "episode_log.jsonl", "run_audit.json", "track1_score.json", "generated_episode_spec.json", "failure_case.json"]:
            path = output_dir / artifact
            if path.exists():
                path.unlink()

        cmd = [
            sys.executable,
            "main.py",
            "--env",
            "local_sim_random",
            "--seed",
            str(seed),
            "--difficulty",
            args.difficulty,
            "--track1-procedure",
            "--output-dir",
            str(output_dir),
            "--validate",
        ]
        if args.mode == "mock":
            cmd.append("--use-mock-llm")
        completed = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True)
        result = _collect_result(seed, output_dir, completed.returncode, completed.stdout, completed.stderr)
        results.append(result)
        print(
            "seed={seed} status={status} expected={expected} score={score} "
            "exception={exception} validation={validation} output_dir={output_dir}".format(**result)
        )

    summary = _build_summary(args.num_episodes, args.mode, args.difficulty, results)
    (root / "summary_report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "summary_report.md").write_text(_render_markdown(summary), encoding="utf-8")
    print(f"\nRandom LocalSim summary written to {root / 'summary_report.json'}")
    print(f"Random LocalSim summary written to {root / 'summary_report.md'}")
    print(f"success_rate={summary['success_rate']:.3f} failed_count={summary['failed_count']}")
    return 0 if summary["success_rate"] >= 0.7 else 1


def _collect_result(seed: int, output_dir: Path, returncode: int, stdout: str, stderr: str) -> Dict[str, Any]:
    world_model_path = output_dir / "world_model.json"
    audit_path = output_dir / "run_audit.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    spec_path = output_dir / "generated_episode_spec.json"
    score_path = output_dir / "track1_score.json"

    world_model = _read_json_if_exists(world_model_path)
    audit = _read_json_if_exists(audit_path)
    spec = _read_json_if_exists(spec_path)
    score = _read_json_if_exists(score_path)
    rows = _read_jsonl_if_exists(episode_log_path)

    validation_errors: List[str] = []
    if all(path.exists() for path in [world_model_path, audit_path, episode_log_path]):
        for name, errors in {
            "world_model": validate_world_model(world_model_path),
            "semantic": validate_semantic_consistency(world_model_path),
            "episode_log": validate_episode_log(episode_log_path),
            "task_status": validate_task_status(world_model_path, episode_log_path),
            "track1_procedure": validate_track1_procedure(world_model_path, audit_path, episode_log_path),
            "random_local_sim": validate_random_local_sim_run(world_model_path, audit_path, episode_log_path),
        }.items():
            if errors:
                validation_errors.append(f"{name}: {errors}")
    else:
        validation_errors.append("Missing required output artifacts.")

    task_status = str(world_model.get("task_status", {}).get("status") or "failed")
    validation = "passed" if returncode == 0 and not validation_errors else "failed"
    exception_type = str(audit.get("controlled_exception_type") or spec.get("controlled_exception", {}).get("type") or "")
    result = {
        "seed": seed,
        "status": task_status if validation == "passed" else "failed",
        "expected": str(audit.get("expected_task_status") or spec.get("expected_task_status") or ""),
        "score": float(audit.get("track1_total_score") or score.get("total_score") or 0.0),
        "exception": exception_type,
        "validation": validation,
        "output_dir": str(output_dir),
        "steps": int(audit.get("total_steps_used") or 0),
        "recovery_steps": int(audit.get("recovery_steps_used") or 0),
        "failure_reason": "; ".join(validation_errors) or (stderr.strip() or stdout.strip() if returncode != 0 else ""),
    }
    if validation != "passed" or task_status not in {"complete", "blocked_recovered"}:
        _write_failure_case(output_dir, result, stdout, stderr, world_model, audit, spec, rows)
    return result


def _build_summary(num_episodes: int, mode: str, difficulty: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    complete = [item for item in results if item["status"] == "complete"]
    blocked = [item for item in results if item["status"] == "blocked_recovered"]
    successes = complete + blocked
    failures = [item for item in results if item not in successes]
    per_exception: Dict[str, Dict[str, Any]] = {}
    for item in results:
        key = item.get("exception") or "none"
        stats = per_exception.setdefault(key, {"count": 0, "complete": 0, "blocked_recovered": 0, "failed": 0})
        stats["count"] += 1
        if item["status"] in stats:
            stats[item["status"]] += 1
        else:
            stats["failed"] += 1
    return {
        "mode": mode,
        "difficulty": difficulty,
        "num_episodes": num_episodes,
        "complete_count": len(complete),
        "blocked_recovered_count": len(blocked),
        "failed_count": len(failures),
        "success_rate": round(len(successes) / num_episodes if num_episodes else 0.0, 4),
        "blocked_recovered_rate": round(len(blocked) / num_episodes if num_episodes else 0.0, 4),
        "average_local_heuristic_score": round(_avg([item["score"] for item in results]), 4),
        "average_steps": round(_avg([item["steps"] for item in results]), 4),
        "average_recovery_steps": round(_avg([item["recovery_steps"] for item in results]), 4),
        "failures": failures,
        "per_exception_type": per_exception,
        "results": results,
    }


def _write_failure_case(
    output_dir: Path,
    result: Dict[str, Any],
    stdout: str,
    stderr: str,
    world_model: Dict[str, Any],
    audit: Dict[str, Any],
    spec: Dict[str, Any],
    rows: List[Dict[str, Any]],
) -> None:
    payload = {
        "result": result,
        "stdout": stdout,
        "stderr": stderr,
        "generated_episode_spec": spec,
        "world_model": world_model,
        "run_audit": audit,
        "episode_log_tail": rows[-20:],
    }
    (output_dir / "failure_case.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _render_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Random LocalSim Robustness Summary",
        "",
        f"- mode: `{summary['mode']}`",
        f"- difficulty: `{summary['difficulty']}`",
        f"- num_episodes: {summary['num_episodes']}",
        f"- complete_count: {summary['complete_count']}",
        f"- blocked_recovered_count: {summary['blocked_recovered_count']}",
        f"- failed_count: {summary['failed_count']}",
        f"- success_rate: {summary['success_rate']}",
        f"- average_local_heuristic_score: {summary['average_local_heuristic_score']}",
        f"- average_steps: {summary['average_steps']}",
        f"- average_recovery_steps: {summary['average_recovery_steps']}",
        "",
        "## Failures",
        "",
    ]
    if not summary["failures"]:
        lines.append("No failures.")
    else:
        for item in summary["failures"]:
            lines.append(f"- seed {item['seed']}: {item['failure_reason']} ({item['output_dir']})")
    return "\n".join(lines) + "\n"


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl_if_exists(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
