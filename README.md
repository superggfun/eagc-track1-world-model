# EAGC Track 1 World Model Prototype

This repository contains a local MVP and evaluation baseline for EAGC 2026 Track 1.

Main project directory: [`./eagc_track1_mvp`](./eagc_track1_mvp)

Final stable tag: `v0.17.6-final-submission-refresh-maze-anti-loop`

## What This Repo Contains

- LocalSim Track 1 MVP for exploration, world-model updates, planning, closed-loop execution, and exception recovery.
- VirtualHome real simulator evidence pipeline with manual-play scene graph, action-program, frame export, and visual grounding support.
- Qwen/vLLM text and vision grounding through a local OpenAI-compatible endpoint.
- MazeSim topology and anti-loop stress tests for synthetic exploration, dead-end recovery, blocked-edge replanning, and graceful unreachable-goal termination.
- ALFRED offline synthetic fixture adapter for stable conversion testing.
- Docker/source package readiness tooling.
- Submission package, technical report draft, reproducibility notes, limitations, and demo commands.

## What Is Not Claimed

- No official EAGC runtime validation yet.
- No hidden evaluation validation yet.
- No AI2-THOR / Habitat / ProcTHOR runtime validation.
- No model training or fine-tuning.
- LocalSim and MazeSim results are local synthetic baselines, not official scores.

## Quick Links

- [Project README](./eagc_track1_mvp/README.md)
- [Submission package](./eagc_track1_mvp/submission_package/)
- [Documentation](./eagc_track1_mvp/docs/)
- [Test suite runner](./eagc_track1_mvp/tools/run_test_suite.py)
