from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_PATH = Path("reports/v0.8.4_technical_report.md")
SUMMARY_CANDIDATES = {
    "easy mock": Path("outputs/robustness/local_sim_random/easy/mock/summary_report.json"),
    "easy real": Path("outputs/robustness/local_sim_random/easy/real/summary_report.json"),
    "medium real": Path("outputs/robustness/local_sim_random/medium/real/summary_report.json"),
    "medium latest": Path("outputs/robustness/local_sim_random/medium/summary_report.json"),
}


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    report_path = project_root / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)

    summaries = {
        label: _read_summary(project_root / rel_path)
        for label, rel_path in SUMMARY_CANDIDATES.items()
    }
    report_path.write_text(_render_report(project_root, summaries), encoding="utf-8")
    print(f"Wrote {report_path}")
    return 0


def _read_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"could not read {path}: {exc}"}


def _git(project_root: Path, *args: str) -> str:
    repo_root = project_root.parent
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "not available"


def _value(summary: dict[str, Any] | None, key: str) -> Any:
    if not summary:
        return "not available"
    return summary.get(key, "not available")


def _summary_table(summaries: dict[str, dict[str, Any] | None]) -> str:
    columns = [
        "success_rate",
        "complete_count",
        "blocked_recovered_count",
        "accepted_failure_count",
        "failed_count",
        "average_local_heuristic_score",
        "fallback_used_count",
        "hidden_spec_leakage_detected",
        "average_qwen_calls",
        "average_latency_seconds",
    ]
    header = "| Run | " + " | ".join(columns) + " |"
    sep = "|---" * (len(columns) + 1) + "|"
    rows = [header, sep]
    for label, summary in summaries.items():
        values = [str(_value(summary, key)) for key in columns]
        rows.append("| " + label + " | " + " | ".join(values) + " |")
    return "\n".join(rows)


def _render_report(project_root: Path, summaries: dict[str, dict[str, Any] | None]) -> str:
    commit = _git(project_root, "rev-parse", "--short", "HEAD")
    tag = _git(project_root, "describe", "--tags", "--always")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"""# v0.8.4 Technical Report: EAGC Track 1 LocalSim MVP

Generated: {generated_at}

Git commit: `{commit}`

Git tag/describe: `{tag}`

## 1. Project Overview

This project is an EAGC Track 1 LocalSim MVP. The goal is to provide a local baseline for exploration, world-model construction, task planning, closed-loop execution, and exception recovery.

The current system does not depend on an official EAGC runtime/API/schema. It does not train models. It uses a local Qwen3.6 vLLM service for inference and a self-built LocalSim environment for controlled Track 1-style evaluation.

## 2. System Architecture

- `LocalSimEnv / LocalSimGenerator`: local simulator and randomized hidden-style episode generator with public and hidden spec separation.
- `Track1ProcedureRunner`: exploration, task reception/planning, execution, recovery, and local score orchestration.
- `QwenClient / VLMExtractor`: OpenAI-compatible local vLLM calls and structured extraction from text or image observations.
- `WorldModelStore`: persistent `world_model.json` updates and isolated run outputs.
- `RulePlanner / Replanner`: action-ontology-based planning and exception recovery.
- `TaskEvaluator`: local status evaluation for complete, in-progress, failed, and blocked-recovered outcomes.
- `Validators`: structure, semantic consistency, leakage, episode log, LocalSim, Track 1 procedure, and vision checks.
- `Scoring`: local heuristic score for debugging and comparison only.
- `Robustness tests`: randomized easy/medium LocalSim batches with runtime guardrails.
- `Diagnostics / Replay`: seed replay and failure root-cause summaries.

## 3. Track 1 Procedure

The procedure is organized into three phases:

- Exploration phase: the agent explores from partial observations and uses visible frontiers instead of hard-coded room routes.
- Task reception and planning phase: the task is received after exploration, then the planner creates action sequences from the world model.
- Execution and recovery phase: actions are executed in the environment; exceptions trigger replanning and recovery actions before task evaluation.

## 4. World Model Schema

Key `world_model.json` fields:

- `rooms`: discovered rooms.
- `topology`: discovered topology nodes and frontiers.
- `visited_rooms`: rooms actually visited by the agent.
- `frontiers`: currently known reachable or explorable targets.
- `objects`: object identity, category, location, state, and confidence.
- `relations`: active, stale, inferred, or uncertain object relations.
- `states`: entity attributes such as lock state, availability, held-by, and open/closed status.
- `affordances`: object/action capability hints.
- `uncertainty`: unknowns, not-currently-visible objects, and recovery uncertainty.
- `plans`: original plans and replanning/recovery plans.
- `exceptions`: observed execution exceptions and recovery plans.
- `task_status`: local evaluator status.

## 5. Evaluation Setup

Evaluation uses fixed LocalSim episodes and randomized hidden-style LocalSim episodes. Randomized runs split data into `public_env_config` for agent-visible setup and `hidden_spec` for evaluator-only success conditions, expected status, hidden relocation targets, and controlled exceptions.

Difficulty levels:

- `easy`: sanity check for generator, planner, validator, and scoring.
- `medium`: robustness check with harder locations, locked routes, unavailable targets, tool candidates, distractors, and limited unrecoverable cases.

Anti-leakage validators check that hidden specs do not appear in prompts, logs, or world model state. `local_heuristic_score` is not an official EAGC score.

## 6. Results

{_summary_table(summaries)}

Standard gate status for v0.8.3 was passing. The latest medium real summary above is the most recent stored robustness result available under `outputs/robustness`.

Default development checks use the fast tier:

```powershell
python tools/run_test_suite.py --tier fast
```

The compile step is intentionally limited to source directories:

```powershell
python -m compileall clients env_adapters perception world_model planner executor logging_utils validators task_evaluator track1_runner scoring diagnostics tools tests
```

`standard` and `full` tiers call longer real-Qwen or stress runs and should be executed only when explicitly requested.

## 7. Failure Replay Case

The seed 6 medium case previously exposed a recoverable `door_locked` failure. The original failure involved a locked door plus a mismatch between the target room route and object location. The root cause was that the planner could try to reach the task target before collecting the required object, leaving the task in progress after door recovery.

The repair makes the runner and replanner first open the route to the target room when needed, then fetch the object from its current room, and finally return to the placement target. The replay tool is:

```powershell
python tools/replay_random_local_sim_failure.py --seed 6 --difficulty medium --mode real
```

## 8. Limitations

- LocalSim is a self-built environment, not an official EAGC runtime or official test.
- ProcTHOR and AI2-THOR are not integrated into the stable path.
- Vision currently has only a single-image smoke test.
- Qwen is not trained or fine-tuned; it is used only for local inference.
- LocalSim is simpler than realistic embodied simulation environments.
- `local_heuristic_score` is a local debugging metric, not an official score.

## 9. Next Steps

- v0.9: multi-frame visual sequence world-model updates.
- v1.0: ProcTHOR / AI2-THOR retry using Docker/Linux or another stable rendering setup.
- v1.1: failure-driven planner improvement.
- v1.2: possible training or distillation only after data and evaluation stabilize.
- v1.3: performance profiling.
"""


if __name__ == "__main__":
    raise SystemExit(main())
