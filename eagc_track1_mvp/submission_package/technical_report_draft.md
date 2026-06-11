# Technical Report Draft

## Abstract

This project develops a local MVP and evaluation baseline for EAGC 2026 Track 1. The system demonstrates an auditable agent loop for exploration, world-model construction, task planning, closed-loop execution, exception recovery, visual evidence reporting, and reproducible local evaluation. The current implementation does not rely on an official EAGC runtime/API/schema, because those interfaces have not yet been released. Instead, it uses a self-built LocalSim environment and local visual sequence smoke tests to validate system behavior before official integration.

The inference path uses a local Qwen3.6-35B-A3B-NVFP4 model served through an OpenAI-compatible vLLM endpoint. No model training, fine-tuning, distillation, or online model API calls are used in the validated local runs.

Current readiness state as of v0.16.7: LocalSim, the official-style Track1 procedure runner, visual-local hybrid evidence reporting, Docker/source packaging, ALFRED synthetic fixture conversion, and VirtualHome manual-play evidence smoke are prepared. Official EAGC runtime, hidden evaluation environments, real ProcTHOR/Habitat/AI2-THOR execution, fully automated VirtualHome startup, real ALFRED dataset conversion, and model training remain unvalidated.

v0.17 resource audit status: the validated VirtualHome evidence path works with the existing long-context Qwen/vLLM endpoint. The resource snapshot recorded an RTX 5090 with 32607 MiB total memory, 31674 MiB used, and 514 MiB free; `openclaw-vllm` was running on `127.0.0.1:8000`; VirtualHome manual-play was listening on `127.0.0.1:8080`; Qwen text smoke latency was about 0.141 seconds; VirtualHome frame vision smoke latency was about 0.696 seconds; multi-frame grounding averaged about 2.722 seconds per frame. No container changes were made, and lightweight vLLM remains a documented fallback only.

## Method Overview

The system separates perception, memory, planning, execution, evaluation, and auditing:

1. Environment adapters provide text or image observations.
2. Qwen or a deterministic mock LLM extracts structured observation facts.
3. The world model is updated incrementally with objects, relations, states, topology, uncertainty, and exceptions.
4. Rule-based planners generate actions from the world model rather than letting the LLM directly control execution.
5. Executors simulate or symbolically evaluate actions.
6. Replanners recover from controlled exceptions.
7. Validators check schema, semantic consistency, episode logs, leakage, visual evidence, and task status.
8. Run audits and reports preserve reproducibility metadata.

This design keeps the core agent logic replaceable when official Track 1 adapters become available.

## Backend-Agnostic Adapter Interface

v0.17.3 freezes a small environment adapter interface so the agent can remain backend-agnostic. The interface covers `reset`, `observe`, `get_scene_graph`, `capture_frame`, `execute_action`, `get_agent_state`, `close`, and `capabilities`.

The `capabilities()` schema records whether a backend is validated, whether it requires rendering, whether it supports scene graph retrieval, frame export, action execution, and online closed-loop operation, plus known blockers. `tools/list_env_adapters.py` writes a static capability report without starting heavy simulators.

Current capability status:

- LocalSim: validated local Track 1 MVP backend.
- VirtualHome: validated manual-play Windows backend; manual Play is required.
- ALFRED offline: validated for the synthetic fixture only; real dataset conversion is not validated.
- AI2-THOR: reserved but not validated; Windows/WSL/cloud rendering stack remains unresolved.
- Habitat: reserved but not validated; EGL/Vulkan/headless rendering remains unresolved.
- ProcTHOR: reserved but not validated; depends on AI2-THOR/ProcTHOR runtime availability.

The reserved adapters do not import heavy dependencies during registry listing and do not fake simulator success. If called before real validation, they return explicit blocker packets.

## System Architecture

Main modules:

- `env_adapters/`: mock, visual sequence, LocalSim, validated VirtualHome conversion path, official-adapter placeholder, adapter capability registry, and reserved AI2-THOR/Habitat/ProcTHOR targets.
- `dataset_adapters/`: optional offline public dataset conversion paths such as ALFRED trajectory parsing.
- `clients/`: OpenAI-compatible Qwen/vLLM client and deterministic mock client.
- `perception/`: prompt templates, JSON extraction, text observation extraction, and vision observation extraction.
- `world_model/`: schema, store, update helpers, action effects, consistency logic, and visibility updates.
- `planner/`: action ontology, rule planner, and replanner.
- `executor/`: simulated action executor and symbolic visual executor.
- `task_evaluator/`: LocalSim task evaluation and visual task evidence evaluation.
- `track1_runner/`: official-style local procedure runner for exploration, task reception, execution, and recovery.
- `validators/`: structural, semantic, log, LocalSim, Track 1 procedure, leakage, visual sequence, and visual evidence validators.
- `scoring/`: local heuristic score for debugging only.
- `diagnostics/`: failure diagnosis and replay support.
- `tools/`: test suite runner, report generation, source packaging, Docker checks, demo snapshot generation, and submission bundle generation.

The Docker package builds a lightweight agent image and expects external model service access through environment variables. Qwen model weights are not included in the image.

## Public Dataset Alignment

An optional ALFRED offline trajectory adapter is prepared as a public household-task alignment path. It reads local `traj_data.json` files when the user has manually provided ALFRED data, extracts task instructions, high-level subgoals, low-level actions, object mentions, and scene metadata, then writes approximate `world_model.json`, `episode_log.jsonl`, and `alfred_task_summary.json` artifacts.

This path does not launch AI2-THOR, does not render frames, does not execute actions online, and does not train a model. ALFRED data is not redistributed with this project.

The included fixture `tests/fixtures/alfred/sample_traj_data.json` is explicitly synthetic (`fixture_type = synthetic_alfred_like`). It validates conversion logic only and is not benchmark evidence or real ALFRED data.

## Test Suite Status

The test suite is decomposed to keep development checks bounded:

- `fast`: deterministic; compiles source, runs mock-only smoke, and converts the synthetic ALFRED fixture. It does not call real Qwen, real vision, external simulators, local images, or real ALFRED data.
- `targeted-text`: minimal real Qwen text endpoint smoke.
- `targeted-vision`: real Qwen vision smoke for visual-local hybrid tasks.
- `targeted-local-sim`: LocalSim real smoke; latest observed runtime is approximately 283 seconds.
- `targeted-track1`: official-style Track1 procedure smoke.
- `standard` and `full`: longer checks for packaging and robustness; these are not routine edit gates.

Each `tools/run_test_suite.py` run writes JSON and Markdown reports under `outputs/test_suite_reports/`.

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

Objects use structured locations with `room`, `region`, `support`, `status`, and `confidence`. Relations include `subject`, `relation`, `object`, `status`, `confidence`, and observed step metadata. When an object moves or is picked up, old active location relations are marked `stale` rather than being deleted. This preserves historical evidence while preventing contradictory active state.

The update layer uses entity-aware upsert rules:

- objects by `id` or normalized name
- relations by `subject + relation + object`
- states by `entity + attribute`
- affordances by object/action sets
- uncertainty as append/merge records

## Track 1 Procedure

The local Track 1 procedure has three phases:

1. Exploration phase: the agent observes partial environment state, visits rooms, discovers frontiers, and builds topology.
2. Task reception and planning phase: the task is introduced after exploration, and the planner generates a task-specific plan from the current world model.
3. Execution and recovery phase: the executor applies actions, detects failures, records exceptions, triggers replanning, and resumes remaining work when possible.

LocalSim observations are partially observable. The agent does not receive hidden success conditions, generated episode specs, or controlled exception configuration during the run.

## Planning And Replanning

Planning is rule-based and uses an explicit action ontology. Representative actions include:

- `explore(room)`
- `navigate_to(target)`
- `search(region)`
- `pick_up(object)`
- `place_on(object, target)`
- `place_in(object, container)`
- `open(object)`
- `unlock(object)`
- `substitute_tool(old_tool, new_tool)`
- `use_tool(tool, target)`

Qwen is used for observation extraction, not direct action selection. This keeps action control auditable and makes planner failures easier to diagnose.

The replanner handles observed exceptions by adding recovery plans and preserving evidence in the world model. Recovery actions are executed in a closed loop rather than merely logged.

## Exception Recovery

LocalSim supports controlled exception classes:

- object relocation
- door locked
- target container unavailable
- tool substitution

Observed exceptions are written to `world_model.exceptions` and `episode_log.jsonl`. Recovery plans are added to `world_model.plans`. Examples:

- If an object is relocated, the old relation becomes stale, the object location becomes uncertain, likely locations are searched, and the plan resumes after pickup.
- If a door is locked, the agent searches for an unlocking object, picks it up, unlocks and opens the door, then enters the target room before completing the task.
- If a container is unavailable, a fallback target can produce a `blocked_recovered` status rather than a false completion.
- If a required tool is unavailable, a valid substitute can be selected and used when supported by the environment state.

## Visual-Local Hybrid Module

The visual-local hybrid path processes local multi-frame image sequences:

1. `VisualSequenceEnv` reads frames from a local image directory.
2. `VLMExtractor` calls Qwen vision extraction for each frame.
3. The world model is updated incrementally across frames.
4. Object persistence, visibility decay, not-currently-observed records, and stale/active relation updates are maintained.
5. A visual task is received after visual world-model construction.
6. `RulePlanner.plan_visual(...)` creates symbolic query actions.
7. `SymbolicVisualExecutor` answers from the world model without claiming physical manipulation.

This module validates vision-to-world-model-to-task-answering behavior. It is not ProcTHOR, AI2-THOR, or official runtime integration.

## Evidence And Uncertainty Reporting

Visual task evaluation writes `visual_task_result.json`. The result schema includes:

- `task`
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

Complete visual tasks require explicit supporting evidence. Relation tasks require explicit active relations. For example, `Is the laptop on the chair?` is only complete if an active `laptop on chair` relation exists. If the laptop and chair are both present but the relation is missing, stale, or contradicted, the result is `uncertain`.

This conservative behavior prevents uncertain visual relations from being reported as success.

## VirtualHome Evidence Pipeline

VirtualHome is now validated as an optional Windows-friendly simulator evidence path using manual Play mode. The simulator is launched outside the project, the user presses Play, and the project connects to `127.0.0.1:8080`.

Validated VirtualHome results:

- Manual-play Windows VirtualHome simulator connection succeeded.
- Scene graph extraction succeeded.
- Four fixed household program tasks executed successfully.
- `converted_world_model.json` and `converted_episode_log.jsonl` were generated from simulator state and program logs.
- Camera frame export succeeded at 640x480.
- Five selected task frames were exported for episode-level evidence.
- Single-frame Qwen vision comparison succeeded using the already-running local Qwen/vLLM endpoint.
- Episode-level multi-frame Qwen vision grounding processed 5/5 frames.
- Average Qwen vision latency in the latest multi-frame smoke was about 2.8 seconds per frame.

The comparison is evidence-driven. Visual objects are matched approximately against simulator symbolic scene graph and converted world-model objects. Scene graph-only objects are treated as not visible in the selected camera frame(s), not as Qwen errors. Unmatched visual objects are recorded as warnings rather than hard failures. Single-frame and selected multi-frame observations are not expected to cover all symbolic simulator objects.

VirtualHome artifacts such as exported frames, raw Qwen responses, and `outputs/virtualhome_spike/` reports are runtime diagnostics and are not redistributed in git.

## Local Evaluation

Current local gates include:

- `fast`: deterministic source-directory compile, mock smoke tests, and synthetic ALFRED fixture conversion; it does not call real Qwen, real vision, local images, or external simulators.
- `targeted-text`: minimal real Qwen text endpoint smoke.
- `targeted-vision`: real Qwen vision smoke for visual-local hybrid tasks.
- `targeted-local-sim`: fixed LocalSim real smoke.
- `targeted-track1`: official-style Track1 procedure smoke.
- `targeted-virtualhome-*`: optional manual-play VirtualHome evidence tiers.
- `standard`: real mock smoke, fixed LocalSim, Track 1 procedure, easy randomized mock batch, visual sequence smoke, and report generation.
- `docker-smoke`: source-directory compile, Docker smoke check, and mock-only smoke tests inside the agent container.

Recent validated status:

- Docker image `eagc-track1-agent:v0.11` built successfully.
- Docker mock smoke passed.
- Docker container accessed host vLLM through `host.docker.internal` and completed a real LocalSim Track 1 command.
- Source zip clean reproducibility check passed.
- Submission bundle generation passed.
- VirtualHome manual-play evidence smoke passed through scene graph extraction, 4/4 household task execution, frame export, single-frame Qwen vision comparison, and 5/5 multi-frame Qwen grounding.

These are local MVP results, not official EAGC scores.

## Compute Budget

Local development and evaluation were performed on a Windows workstation with an RTX 5090 32GB GPU. Real Qwen inference was served by a local vLLM service at an OpenAI-compatible endpoint. The agent code itself is lightweight Python and can run in a slim Docker image; heavy model inference is external to the agent container.

No training compute has been used. All model calls are inference calls.

The v0.17 resource profile recorded high VRAM residency from the existing long-context vLLM profile, but the current VirtualHome evidence smoke still completed successfully without starting lightweight vLLM. The current recommendation is to keep the existing endpoint for this smoke pipeline and consider a separate lightweight endpoint only if longer episodes, additional frames, or concurrent workloads become unstable and the user explicitly allows it.

## Training Resource Disclosure Summary

No model training, fine-tuning, reinforcement learning, or distillation has been performed. The system uses local Qwen3.6-35B-A3B-NVFP4 inference through vLLM. LocalSim is self-built for development and evaluation. Local visual images are used only for smoke testing. Qwen model weights are not redistributed in the source package, Docker image, or submission bundle.

## Failure Analysis

The project includes replay and diagnosis tooling for local failures. One medium-difficulty LocalSim case previously failed around a locked-door route because the recovery sequence opened/unlocked the door but did not reliably resume entry and final task completion. The fix strengthened recovery planning, task evaluation, and route resumption. The replay tool records task, exception type, executed actions, failed actions, replanning actions, and likely root cause.

Known failure categories tracked by diagnostics include:

- door unlocked but target room not entered
- key found but not used
- opened door but original plan not resumed
- navigated to object instead of room
- target room not reached
- recovery plan incomplete
- stale world-model state

## Reproducibility

Core commands:

```powershell
python tools/run_test_suite.py --tier fast
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
python tools/create_demo_snapshot.py
python tools/create_submission_bundle.py
```

Docker commands:

```powershell
docker build -t eagc-track1-agent:v0.11 .
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
```

Docker with external vLLM on Windows Docker Desktop:

```powershell
docker run --rm -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.11 python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

The final official submission format remains pending organizer clarification.

## Limitations

- LocalSim is self-built and is not official hidden evaluation.
- `local_heuristic_score` is a local debugging metric, not an official score.
- No official EAGC runtime/API/schema is integrated yet.
- AI2-THOR/ProcTHOR remains blocked by platform/runtime issues and is not part of the stable path.
- Visual-local hybrid tasks are symbolic world-model queries, not physical robot interaction.
- No model training, fine-tuning, or student model distillation has been performed.
- No full benchmark-scale official evaluation has been run.
- Docker packaging excludes model weights and depends on external endpoint configuration.
- Model weight packaging, endpoint rules, volume mount policy, registry upload policy, and qualification submission portal are pending organizer clarification.
