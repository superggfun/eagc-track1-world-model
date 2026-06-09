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
from validators.validate_no_hidden_spec_leakage import validate as validate_no_hidden_spec_leakage
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_track1_procedure import validate as validate_track1_procedure
from validators.validate_world_model import validate as validate_world_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Run randomized LocalSim robustness evaluation.")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--end-seed", type=int)
    parser.add_argument("--num-episodes", type=int, default=20)
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="easy")
    parser.add_argument("--strict-leakage-check", action="store_true")
    args = parser.parse_args()

    root = PROJECT_ROOT / "outputs" / "robustness" / "local_sim_random" / args.difficulty / args.mode
    root.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    end_seed = args.end_seed if args.end_seed is not None else args.start_seed + args.num_episodes - 1
    seeds = list(range(args.start_seed, end_seed + 1))

    for seed in seeds:
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
        result = _collect_result(seed, output_dir, completed.returncode, completed.stdout, completed.stderr, args.strict_leakage_check)
        results.append(result)
        print(
            "seed={seed} status={status} expected={expected} score={score} "
            "exception={exception} leakage={leakage_check} validation={validation} output_dir={output_dir}".format(**result)
        )

    summary = _build_summary(len(seeds), args.mode, args.difficulty, results)
    (root / "summary_report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (root / "summary_report.md").write_text(_render_markdown(summary), encoding="utf-8")
    print(f"\nRandom LocalSim summary written to {root / 'summary_report.json'}")
    print(f"Random LocalSim summary written to {root / 'summary_report.md'}")
    print(f"success_rate={summary['success_rate']:.3f} failed_count={summary['failed_count']}")
    threshold = 0.85 if args.difficulty == "easy" else 0.6
    passed = summary["success_rate"] >= threshold and summary["leakage_check_passed"]
    return 0 if passed else 1


def _collect_result(seed: int, output_dir: Path, returncode: int, stdout: str, stderr: str, strict_leakage_check: bool) -> Dict[str, Any]:
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
        leakage_errors = validate_no_hidden_spec_leakage(world_model_path, audit_path, episode_log_path)
        if leakage_errors and strict_leakage_check:
            validation_errors.append(f"no_hidden_spec_leakage: {leakage_errors}")
    else:
        validation_errors.append("Missing required output artifacts.")
        leakage_errors = ["Missing required output artifacts."]

    task_status = str(world_model.get("task_status", {}).get("status") or "failed")
    validation = "passed" if returncode == 0 and not validation_errors else "failed"
    hidden_spec = spec.get("hidden_spec", {}) if isinstance(spec.get("hidden_spec"), dict) else {}
    exception_type = str(audit.get("controlled_exception_type") or hidden_spec.get("controlled_exception", {}).get("type") or spec.get("controlled_exception", {}).get("type") or "")
    expected = str(audit.get("expected_task_status") or hidden_spec.get("expected_task_status") or spec.get("expected_task_status") or "")
    recoverable = bool(audit.get("recoverable", hidden_spec.get("recoverable", True)))
    accepted_failure = bool(audit.get("accepted_failure")) or (not recoverable and task_status in {"failed", "blocked_recovered", "in_progress"})
    result = {
        "seed": seed,
        "status": task_status if validation == "passed" else "failed",
        "expected": expected,
        "accepted_failure": accepted_failure,
        "recoverable": recoverable,
        "template": str(spec.get("template") or spec.get("public_env_config", {}).get("template") or ""),
        "score": float(audit.get("track1_total_score") or score.get("total_score") or 0.0),
        "exception": exception_type,
        "validation": validation,
        "leakage_check": "passed" if not leakage_errors else "failed",
        "leakage_errors": leakage_errors,
        "output_dir": str(output_dir),
        "steps": int(audit.get("total_steps_used") or 0),
        "recovery_steps": int(audit.get("recovery_steps_used") or 0),
        "qwen_calls": int(audit.get("qwen_call_count") or 0),
        "latency_seconds": float(audit.get("latency_seconds") or 0.0),
        "fallback_used": bool(audit.get("fallback_used", False)),
        "failure_reason": "; ".join(validation_errors) or (stderr.strip() or stdout.strip() if returncode != 0 else ""),
    }
    if validation != "passed" or (task_status not in {"complete", "blocked_recovered"} and not accepted_failure):
        _write_failure_case(output_dir, result, stdout, stderr, world_model, audit, spec, rows)
    return result


def _build_summary(num_episodes: int, mode: str, difficulty: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    complete = [item for item in results if item["status"] == "complete"]
    blocked = [item for item in results if item["status"] == "blocked_recovered"]
    accepted = [item for item in results if item.get("accepted_failure")]
    successes = complete + blocked + accepted
    failures = [item for item in results if item not in successes]
    recoverable_items = [item for item in results if item.get("recoverable", True)]
    recoverable_successes = [item for item in recoverable_items if item["status"] in {"complete", "blocked_recovered"}]
    per_exception: Dict[str, Dict[str, Any]] = {}
    per_template: Dict[str, Dict[str, Any]] = {}
    for item in results:
        key = item.get("exception") or "none"
        _bump_stats(per_exception, key, item)
        _bump_stats(per_template, item.get("template") or "unknown", item)
    top_failure_reasons: Dict[str, int] = {}
    for item in failures:
        reason = str(item.get("failure_reason") or "unknown failure")
        reason = reason[:240]
        top_failure_reasons[reason] = top_failure_reasons.get(reason, 0) + 1
    return {
        "mode": mode,
        "difficulty": difficulty,
        "num_episodes": num_episodes,
        "complete_count": len(complete),
        "blocked_recovered_count": len(blocked),
        "accepted_failure_count": len(accepted),
        "failed_count": len(failures),
        "success_rate": round(len(successes) / num_episodes if num_episodes else 0.0, 4),
        "recoverable_success_rate": round(len(recoverable_successes) / len(recoverable_items) if recoverable_items else 0.0, 4),
        "blocked_recovered_rate": round(len(blocked) / num_episodes if num_episodes else 0.0, 4),
        "average_local_heuristic_score": round(_avg([item["score"] for item in results]), 4),
        "average_steps": round(_avg([item["steps"] for item in results]), 4),
        "average_recovery_steps": round(_avg([item["recovery_steps"] for item in results]), 4),
        "average_qwen_calls": round(_avg([item["qwen_calls"] for item in results]), 4),
        "average_latency_seconds": round(_avg([item["latency_seconds"] for item in results]), 4),
        "fallback_used_count": sum(1 for item in results if item.get("fallback_used")),
        "leakage_check_passed": all(item.get("leakage_check") == "passed" for item in results),
        "failures": failures,
        "per_template_stats": per_template,
        "per_exception_type_stats": per_exception,
        "top_failure_reasons": top_failure_reasons,
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
        f"- accepted_failure_count: {summary['accepted_failure_count']}",
        f"- failed_count: {summary['failed_count']}",
        f"- success_rate: {summary['success_rate']}",
        f"- recoverable_success_rate: {summary['recoverable_success_rate']}",
        f"- average_local_heuristic_score: {summary['average_local_heuristic_score']}",
        f"- average_steps: {summary['average_steps']}",
        f"- average_recovery_steps: {summary['average_recovery_steps']}",
        f"- average_qwen_calls: {summary['average_qwen_calls']}",
        f"- average_latency_seconds: {summary['average_latency_seconds']}",
        f"- fallback_used_count: {summary['fallback_used_count']}",
        f"- leakage_check_passed: {summary['leakage_check_passed']}",
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


def _bump_stats(target: Dict[str, Dict[str, Any]], key: str, item: Dict[str, Any]) -> None:
    stats = target.setdefault(
        key,
        {"count": 0, "complete": 0, "blocked_recovered": 0, "accepted_failure": 0, "failed": 0},
    )
    stats["count"] += 1
    if item.get("accepted_failure"):
        stats["accepted_failure"] += 1
    elif item["status"] in {"complete", "blocked_recovered"}:
        stats[item["status"]] += 1
    else:
        stats["failed"] += 1


if __name__ == "__main__":
    raise SystemExit(main())
