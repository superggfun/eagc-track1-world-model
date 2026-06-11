from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "outputs" / "test_suite_reports"
GUARDRAILS = ["--episode-timeout-seconds", "600", "--max-qwen-calls-per-episode", "40"]
SOURCE_DIRS = [
    "clients",
    "env_adapters",
    "perception",
    "world_model",
    "planner",
    "executor",
    "logging_utils",
    "validators",
    "task_evaluator",
    "track1_runner",
    "scoring",
    "diagnostics",
    "dataset_adapters",
    "tools",
    "tests",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tiered EAGC Track 1 local test suites.")
    parser.add_argument(
        "--tier",
        choices=list(_tier_descriptions().keys()),
        help="Test tier to run. Use --list-tiers to inspect available tiers.",
    )
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="medium")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--list-tiers", action="store_true")
    args = parser.parse_args()

    if args.list_tiers:
        _print_tiers()
        return 0
    if not args.tier:
        parser.error("--tier is required unless --list-tiers is used")

    commands = _commands(args.tier, args.seed, args.difficulty)
    report = _run_commands(
        tier=args.tier,
        commands=commands,
        timeout_seconds=args.timeout_seconds,
        continue_on_failure=args.continue_on_failure,
    )
    _write_report(report)
    if report["success"]:
        print(f"\nTest suite tier {args.tier!r} passed.")
        return 0
    print(f"\nTest suite tier {args.tier!r} failed. Report: {report['report_json_path']}")
    return 1


def _commands(tier: str, seed: int, difficulty: str) -> List[List[str]]:
    py = sys.executable
    compileall = [py, "-m", "compileall", *SOURCE_DIRS]
    smoke_mock = [py, "tests/smoke_test_all_mock_episodes.py", "--mode", "mock", "--all"]
    smoke_real = [py, "tests/smoke_test_all_mock_episodes.py", "--mode", "real", "--all", "--strict-real"]
    qwen_text = [py, "tools/test_qwen_text_call.py"]
    local_sim = [py, "tests/smoke_test_local_sim_episodes.py", "--mode", "real"]
    track1 = [py, "tests/smoke_test_track1_procedure.py", "--mode", "real"]
    alfred_fixture = [py, "tests/smoke_test_alfred_fixture_conversion.py"]
    visual_local_hybrid = [
        py,
        "tests/smoke_test_visual_local_hybrid.py",
        "--image-dir",
        "assets/test_sequences/bedroom_sequence",
        "--max-frames",
        "3",
    ]
    visual_sequence = [
        py,
        "tests/smoke_test_visual_sequence.py",
        "--image-dir",
        "assets/test_sequences/bedroom_sequence",
        "--max-frames",
        "3",
    ]
    generate_report = [py, "tools/generate_project_report.py"]
    package_source = [py, "tools/package_source.py"]
    check_source_package = [py, "tools/check_source_package_repro.py", "--zip-path", "dist/eagc_track1_mvp_source.zip"]
    demo_snapshot = [py, "tools/create_demo_snapshot.py"]
    docker_smoke = [py, "tools/docker_smoke_check.py"]
    virtualhome_manual = [py, "tools/run_virtualhome_manual_suite.py"]
    targeted_replay = [
        py,
        "tools/replay_random_local_sim_failure.py",
        "--seed",
        str(seed),
        "--difficulty",
        difficulty,
        "--mode",
        "real",
    ]
    targeted_robustness = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--start-seed",
        str(seed),
        "--end-seed",
        str(seed),
        "--difficulty",
        difficulty,
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy20_mock = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "mock",
        "--num-episodes",
        "20",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy20_real = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "20",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    medium5 = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "5",
        "--difficulty",
        "medium",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    easy100_mock = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "mock",
        "--num-episodes",
        "100",
        "--difficulty",
        "easy",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]
    medium10_real = [
        py,
        "tests/robustness_test_random_local_sim.py",
        "--mode",
        "real",
        "--num-episodes",
        "10",
        "--difficulty",
        "medium",
        "--strict-leakage-check",
        *GUARDRAILS,
    ]

    tier_commands = {
        "fast": [compileall, smoke_mock, alfred_fixture],
        "targeted-text": [qwen_text],
        "targeted-vision": [visual_local_hybrid],
        "targeted-local-sim": [local_sim],
        "targeted-track1": [track1],
        "targeted-virtualhome-manual": [virtualhome_manual],
        "targeted": [qwen_text, visual_local_hybrid, local_sim, track1],
        "standard": [
            compileall,
            smoke_real,
            visual_local_hybrid,
            local_sim,
            track1,
            easy20_mock,
            visual_sequence,
            generate_report,
            demo_snapshot,
            package_source,
            check_source_package,
        ],
        "full": [
            compileall,
            smoke_real,
            visual_local_hybrid,
            local_sim,
            track1,
            targeted_replay,
            targeted_robustness,
            easy100_mock,
            easy20_real,
            medium5,
            medium10_real,
        ],
        "docker-smoke": [compileall, docker_smoke, smoke_mock],
    }
    return tier_commands[tier]


def _run_commands(
    tier: str,
    commands: List[List[str]],
    timeout_seconds: int,
    continue_on_failure: bool,
) -> Dict[str, object]:
    started = datetime.now(timezone.utc)
    report: Dict[str, object] = {
        "tier": tier,
        "start_time": started.isoformat(),
        "end_time": "",
        "elapsed_seconds": 0.0,
        "timeout_seconds": timeout_seconds,
        "continue_on_failure": continue_on_failure,
        "success": True,
        "commands": [],
        "report_json_path": "",
        "report_md_path": "",
    }
    overall_start = time.perf_counter()
    command_reports: List[Dict[str, object]] = []
    for command in commands:
        command_text = " ".join(command)
        print(f"\n$ {command_text}", flush=True)
        command_started = datetime.now(timezone.utc)
        timer = time.perf_counter()
        row: Dict[str, object] = {
            "command": command_text,
            "argv": command,
            "start_time": command_started.isoformat(),
            "end_time": "",
            "elapsed_seconds": 0.0,
            "returncode": None,
            "status": "running",
            "timeout": False,
        }
        try:
            completed = subprocess.run(command, cwd=PROJECT_ROOT, timeout=timeout_seconds)
            row["returncode"] = completed.returncode
            row["status"] = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            row["returncode"] = None
            row["status"] = "timeout"
            row["timeout"] = True
            print(f"Command timed out after {timeout_seconds}s: {command_text}")
        finally:
            row["elapsed_seconds"] = round(time.perf_counter() - timer, 3)
            row["end_time"] = datetime.now(timezone.utc).isoformat()
            command_reports.append(row)

        if row["status"] != "passed":
            report["success"] = False
            if not continue_on_failure:
                break
    report["commands"] = command_reports
    report["end_time"] = datetime.now(timezone.utc).isoformat()
    report["elapsed_seconds"] = round(time.perf_counter() - overall_start, 3)
    return report


def _write_report(report: Dict[str, object]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tier = str(report["tier"]).replace("/", "_")
    json_path = REPORT_DIR / f"{timestamp}_{tier}_report.json"
    md_path = REPORT_DIR / f"{timestamp}_{tier}_report.md"
    report["report_json_path"] = str(json_path)
    report["report_md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_report_markdown(report), encoding="utf-8")
    print(f"\nTest suite report written to {json_path}")
    print(f"Test suite report written to {md_path}")


def _report_markdown(report: Dict[str, object]) -> str:
    lines = [
        f"# Test Suite Report: {report['tier']}",
        "",
        f"- success: `{report['success']}`",
        f"- start_time: `{report['start_time']}`",
        f"- end_time: `{report['end_time']}`",
        f"- elapsed_seconds: `{report['elapsed_seconds']}`",
        f"- timeout_seconds: `{report['timeout_seconds']}`",
        f"- continue_on_failure: `{report['continue_on_failure']}`",
        "",
        "| status | timeout | elapsed_seconds | command |",
        "|---|---:|---:|---|",
    ]
    for item in report.get("commands", []):
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).replace("|", "\\|")
        lines.append(
            f"| {item.get('status')} | {item.get('timeout')} | {item.get('elapsed_seconds')} | `{command}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _tier_descriptions() -> Dict[str, str]:
    return {
        "fast": "Deterministic sanity check: compile source dirs, mock-only smoke, ALFRED synthetic fixture.",
        "targeted-text": "Minimal real Qwen text chat smoke; no vision and no long batch.",
        "targeted-vision": "Visual-local hybrid smoke using real Qwen vision.",
        "targeted-local-sim": "Fixed LocalSim episodes with real Qwen text extraction.",
        "targeted-track1": "Official-style Track1ProcedureRunner real smoke.",
        "targeted-virtualhome-manual": "Optional VirtualHome manual-play smoke; skips if 127.0.0.1:8080 is not listening.",
        "targeted": "Aggregate targeted smoke: text, vision, LocalSim, Track1 procedure.",
        "standard": "Longer gate: targeted-style coverage plus report/source/demo packaging.",
        "full": "Optional stress suite with longer robustness batches.",
        "docker-smoke": "Mock-only container-safe smoke.",
    }


def _print_tiers() -> None:
    print("Available tiers:")
    for tier, description in _tier_descriptions().items():
        print(f"\n{tier}: {description}")
        for command in _commands(tier, seed=6, difficulty="medium"):
            print(f"  - {' '.join(command)}")


if __name__ == "__main__":
    raise SystemExit(main())
