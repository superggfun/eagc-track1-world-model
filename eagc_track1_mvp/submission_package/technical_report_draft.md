# Technical Report Draft

## Project Overview

This project builds a local MVP and evaluation baseline for EAGC 2026 Track 1. The goal is to test the full agent loop before the official runtime/API/schema is available: exploration, observation extraction, world-model construction, task planning, closed-loop execution, exception recovery, structured logging, reproducible evaluation, and report generation.

The current system uses a self-built LocalSim environment and a visual-local hybrid smoke path. It uses local Qwen3.6-35B-A3B-NVFP4 inference through a vLLM OpenAI-compatible endpoint. No model training or fine-tuning has been performed.

## Track 1 Task Interpretation

Track 1 is interpreted as an embodied-agent style procedure:

1. Explore an environment from partial observations.
2. Build and maintain a structured world model.
3. Receive a task.
4. Plan actions from the world model.
5. Execute actions in a closed loop.
6. Detect exceptions and replan.
7. Report task status, evidence, logs, and audit metadata.

Because the official runtime is not yet available, LocalSim is used as a local development and evaluation platform. The system is designed so adapters can be replaced later.

## System Architecture

Main modules:

- `env_adapters/`: mock, visual sequence, LocalSim, and experimental AI2-THOR adapters.
- `clients/`: local OpenAI-compatible Qwen/vLLM client and mock client.
- `perception/`: prompt templates and extraction logic for text and vision observations.
- `world_model/`: schema, store, update helpers, consistency logic, and action effects.
- `planner/`: action ontology, rule planner, and replanner.
- `executor/`: simulated action executor and symbolic visual executor.
- `task_evaluator/`: LocalSim task evaluation and visual task evaluation.
- `track1_runner/`: Track 1 procedure runner for exploration, task reception, execution, and recovery.
- `validators/`: structure, semantic, log, visual, LocalSim, leakage, and procedure validators.
- `scoring/`: local heuristic score for debugging only.
- `tests/`: smoke tests, robustness tests, and visual sequence tests.
- `tools/`: report generation, replay, source packaging, and demo snapshot generation.

## World Model Design

The world model is saved as `world_model.json`. Key fields include:

- `episode_id`
- `agent_state`
- `rooms`
- `topology`
- `visited_rooms`
- `frontiers`
- `objects`
- `relations`
- `states`
- `affordances`
- `uncertainty`
- `plans`
- `exceptions`
- `task_status`

Objects use structured locations with room, region, support, status, and confidence. Relations include subject, relation, object, status, confidence, and observed step. When an object location changes, old location relations become stale rather than being deleted.

## Planning And Replanning

Planning is rule-based and uses a controlled action ontology. Qwen is used for observation extraction, not direct action control. The planner generates actions such as:

- `explore(room)`
- `navigate_to(target)`
- `search(region)`
- `pick_up(object)`
- `place_on(object, target)`
- `place_in(object, container)`
- `unlock(object)`
- `use_tool(tool, target)`

The replanner handles observed exceptions by adding recovery plans and preserving evidence in the world model.

## Exception Recovery

LocalSim supports controlled exception classes:

- object relocation
- door locked
- target container unavailable
- tool substitution

Observed exceptions are written to `world_model.exceptions` and `episode_log.jsonl`. Recovery plans are added to `world_model.plans`. For example, a locked door can trigger search for a key, pick up key, unlock door, open door, and resume the original task.

## Visual-Local Hybrid Module

The visual-local hybrid path processes local multi-frame image sequences:

1. `VisualSequenceEnv` reads frames from a local directory.
2. `VLMExtractor` calls Qwen vision extraction for each frame.
3. The world model is updated incrementally.
4. A visual task is received after the visual world model is built.
5. `RulePlanner.plan_visual(...)` creates symbolic query actions.
6. `SymbolicVisualExecutor` answers from the world model without claiming physical manipulation.

This module is a local smoke test for vision-to-world-model-to-task-answering. It is not ProcTHOR, AI2-THOR, or official runtime integration.

## Evidence And Uncertainty Reporting

Visual task evaluation writes `visual_task_result.json`. The result includes:

- `status`
- `success`
- `answer`
- `confidence`
- `supporting_evidence`
- `contradicting_evidence`
- `missing_evidence`
- `evidence_summary`
- `queried_entities`
- `queried_relations`

Complete example:

- Task: `Find the laptop.`
- Expected result: complete if a matching laptop object exists with sufficient confidence.

Uncertain example:

- Task: `Is the laptop on the chair?`
- Expected behavior: complete only if an explicit active `laptop on chair` relation exists. If both objects exist but the relation is missing or stale, the result is uncertain with missing evidence.

This conservative behavior prevents uncertain visual relations from being reported as success.

## Local Evaluation Results

Current gates include:

- `fast`: source compile and mock smoke tests, plus visual-local hybrid smoke when local frames are available.
- `targeted`: fast tier, fixed LocalSim, Track 1 procedure smoke, seed replay, and seed robustness.
- `standard`: real mock smoke, fixed LocalSim, Track 1 procedure, easy randomized mock batch, visual sequence smoke, and report generation.

The latest v0.10.2 gate completed:

- targeted: passed.
- standard: passed.
- visual-local hybrid smoke: passed.
- source package exclusion check: passed.

These are local MVP results, not official EAGC scores.

## Current Limitations

- LocalSim is self-built and simpler than official or realistic simulators.
- No official runtime/API/schema is integrated yet.
- AI2-THOR/ProcTHOR remains blocked by platform/runtime issues.
- Visual-local hybrid tasks are symbolic queries, not physical interaction.
- No model training, fine-tuning, or student model distillation has been performed.
- No full-scale benchmark has been run.
- Performance profiling and optimization are not complete.

## Future Work

- Prepare a final Docker/runtime story when competition requirements stabilize.
- Retry ProcTHOR/AI2-THOR or another simulator path in a stable Linux/Docker environment.
- Expand randomized LocalSim difficulty and failure replay coverage.
- Add richer multi-frame visual tasks and evidence summaries.
- Add profiling for latency, Qwen call counts, and memory pressure.
- Consider training or distillation only after data and evaluation are stable.
