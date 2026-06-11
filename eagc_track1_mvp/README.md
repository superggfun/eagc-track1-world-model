# EAGC Track 1 MVP

Minimal runnable Python MVP for EAGC 2026 Track 1. It uses a mock text-only environment and a replaceable adapter layout until an official EAGC runtime/API/schema is available.

Current version: v0.16.1 VirtualHome external resources and runtime blocker.

Current stable tag: `v0.16-virtualhome-real-smoke-blocker`

Current status:

- LocalSim Track 1 MVP
- Official-style Track1 procedure runner
- Visual-local hybrid prototype with evidence reporting
- Real Qwen3.6 vLLM integration
- ALFRED offline adapter with synthetic fixture conversion
- VirtualHome external repo/API and Windows executable prepared; runtime connection still blocked
- Docker/source package readiness
- No training yet
- Official EAGC runtime, ProcTHOR, Habitat, AI2-THOR, successful VirtualHome scene-graph/program execution, and real ALFRED dataset conversion are not validated yet

The demo loop:

1. `MockEnv` emits a bedroom observation.
2. `QwenClient` calls a local OpenAI-compatible vLLM endpoint.
3. `VLMExtractor` extracts objects, states, relations, affordances, and uncertainty.
4. `WorldModelStore` updates and writes `outputs/world_model.json`.
5. `RulePlanner` creates subgoals and actions.
6. `ActionExecutor` simulates action execution.
7. `Replanner` creates a recovery plan when an execution exception occurs.
8. `EpisodeLogger` writes `outputs/episode_log.jsonl`.
9. `validators/` checks output structure and auditability.

## Pre-Submission Package

The pre-submission readiness materials are in `submission_package/`:

- `README_submission.md`
- `technical_report_draft.md`
- `training_resource_disclosure.md`
- `reproducibility_statement.md`
- `system_limitations.md`
- `demo_commands.md`
- `checklist.md`

This package is for qualification-submission preparation, teacher review, and technical report drafting. It does not claim official EAGC results. LocalSim remains a self-built local environment, visual-local hybrid remains symbolic, and no model training has been performed.

Run the pre-submission audit after packaging:

```powershell
python tools/pre_submission_audit.py
```

The audit writes `outputs/pre_submission_audit/audit_report.json` and `.md`, checks key submission documents, reports dirty git state, verifies that `v0.15.2-targeted-suite-controls` exists, and warns about ignored runtime artifact directories such as `outputs/`, `dist/`, `submission_bundle/`, and local datasets.

## Requirements

- Windows
- Python 3.10+
- A local vLLM OpenAI-compatible server already running at `http://127.0.0.1:8000/v1`
- Served model name: `qwen3.6-35b-nvfp4`

This project does not start, stop, restart, or manage the vLLM Docker container.

## Install

```powershell
cd "C:\Users\Alphay\Documents\New project\eagc_track1_mvp"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure

Edit `config.yaml` if your local endpoint or model name changes:

```yaml
base_url: http://127.0.0.1:8000/v1
model: qwen3.6-35b-nvfp4
temperature: 0.2
max_tokens: 2048
episode_id: mock-bedroom-relocated
use_mock_llm: false
output_dir: outputs
oracle_metadata_mode: false
alfred:
  dataset_root: ""
  sample_traj_path: ""
track1_budgets:
  exploration_steps: 12
  planning_steps: 3
  execution_steps: 50
  max_recovery_steps: 8
```

The client currently supports text-only chat completions through:

```text
POST /chat/completions
```

v0.5 also adds a minimal OpenAI-compatible vision chat path using a local image encoded as a base64 data URL.

## Run

```powershell
python main.py
```

Run a specific episode:

```powershell
python main.py --episode-id mock-bedroom-relocated
python main.py --episode-id mock-door-locked
```

Demo command recipes are collected in:

```powershell
docs/demo_commands.md
```

Run with validators after the episode:

```powershell
python main.py --episode-id mock-bedroom-relocated --validate
```

Use an explicit run id or output directory:

```powershell
python main.py --episode-id mock-bedroom-relocated --run-id demo001
python main.py --episode-id mock-bedroom-relocated --output-dir outputs/custom/demo001
```

Without `--output-dir`, each run writes to an isolated directory:

```text
outputs/runs/<timestamp>_<episode_id>/
```

For compatibility, latest copies are also written to:

```text
outputs/world_model.json
outputs/episode_log.jsonl
outputs/run_audit.json
```

Run without calling vLLM, using deterministic mock LLM extraction:

```powershell
python main.py --episode-id mock-bedroom-relocated --validate --use-mock-llm
```

Run the vision smoke episode with a local image:

```powershell
python main.py --vision --image-path assets/test_images/bedroom.png --validate
```

If `assets/test_images/bedroom.png` does not exist, place a local bedroom scene image there or pass another local path with `--image-path`.

Run the AI2-THOR simulator smoke episode:

```powershell
python main.py --env ai2thor --scene FloorPlan1 --validate
```

Run a local multi-image visual sequence:

```powershell
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --validate
python -m validators.validate_visual_sequence outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python tests/smoke_test_visual_sequence.py --image-dir assets/test_sequences/bedroom_sequence --max-frames 3
```

Run the visual-local hybrid prototype:

```powershell
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --visual-local-hybrid --visual-task "Find the laptop." --validate
python -m validators.validate_visual_local_hybrid outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python -m validators.validate_visual_task_evidence outputs/visual_task_result.json outputs/run_audit.json
python tests/smoke_test_visual_local_hybrid.py --image-dir assets/test_sequences/bedroom_sequence --max-frames 3
```

Create a reproducible demo snapshot:

```powershell
python tools/create_demo_snapshot.py
```

Generate the technical report and source package:

```powershell
python tools/generate_project_report.py
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
```

Run the LocalSim Track 1 MVP environment:

```powershell
python main.py --env local_sim --episode-id local-explore-book-relocated --max-steps 50 --validate
python main.py --env local_sim --episode-id local-door-locked-route --max-steps 50 --validate
python main.py --env local_sim --episode-id local-container-unavailable --max-steps 50 --validate
python main.py --env local_sim --episode-id local-tool-substitution --max-steps 50 --validate
```

Run the official-style Track 1 procedure on LocalSim:

```powershell
python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

This mode separates exploration, task reception, planning, execution/recovery, and final evaluation. The task is hidden during exploration and is only written into the world model after `exploration_end`.

Run a generated hidden-style LocalSim episode:

```powershell
python main.py --env local_sim_random --seed 1 --difficulty easy --track1-procedure --validate
```

Run randomized LocalSim robustness evaluation:

```powershell
python tests/robustness_test_random_local_sim.py --mode mock --num-episodes 100 --difficulty easy --strict-leakage-check
python tests/robustness_test_random_local_sim.py --mode real --num-episodes 20 --difficulty easy --strict-leakage-check
python tests/robustness_test_random_local_sim.py --mode real --num-episodes 10 --difficulty medium --strict-leakage-check --episode-timeout-seconds 600 --max-qwen-calls-per-episode 40
python tests/robustness_test_random_local_sim.py --mode real --num-episodes 50 --difficulty medium --strict-leakage-check --episode-timeout-seconds 600 --max-qwen-calls-per-episode 40
```

The 50-episode real medium run is intended as an optional overnight stress test, not a normal development commit gate.

Run tiered test suites:

```powershell
python tools/run_test_suite.py --tier fast
python tools/run_test_suite.py --list-tiers
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-vision --timeout-seconds 600
python tools/run_test_suite.py --tier targeted-local-sim --timeout-seconds 600
python tools/run_test_suite.py --tier targeted-track1 --timeout-seconds 600
python tools/run_test_suite.py --tier targeted --timeout-seconds 900 --continue-on-failure
python tools/run_test_suite.py --tier standard
python tools/run_test_suite.py --tier full
```

The fast tier is deterministic and does not call real Qwen, real vision, external simulators, local images, or real ALFRED data. It compiles source directories, runs mock-only smoke tests, and converts a tiny synthetic ALFRED-like fixture.

The compile step is equivalent to:

```powershell
python -m compileall clients env_adapters perception world_model planner executor logging_utils validators task_evaluator track1_runner scoring diagnostics dataset_adapters tools tests
```

Targeted tests are decomposed:

- `targeted-text`: minimal real Qwen text endpoint smoke, no vision.
- `targeted-vision`: real Qwen vision visual-local hybrid smoke.
- `targeted-local-sim`: fixed LocalSim real episodes.
- `targeted-track1`: official-style Track1ProcedureRunner real smoke.
- `targeted`: aggregate of the four targeted smoke groups.

Each command records elapsed time and status under `outputs/test_suite_reports/`. Use `--timeout-seconds` to prevent a long test from hanging the suite and `--continue-on-failure` when you want a complete report across all targeted groups. Run `standard` or `full` only when explicitly requested; `full` is a stress test.

Replay a single randomized LocalSim seed with diagnostics:

```powershell
python tools/replay_random_local_sim_failure.py --seed 6 --difficulty medium --mode real
python tools/replay_random_local_sim_failure.py --seed 6 --difficulty medium --mode mock
```

Sequence frames should be local files named in deterministic order:

```text
assets/test_sequences/bedroom_sequence/frame_000.png
assets/test_sequences/bedroom_sequence/frame_001.png
assets/test_sequences/bedroom_sequence/frame_002.png
```

The project does not download sequence images.

Expected outputs:

```text
outputs/world_model.json
outputs/episode_log.jsonl
outputs/run_audit.json
```

If the vLLM call fails, the program exits with a clear error containing the endpoint URL, model name, and request exception.

If Qwen returns malformed JSON, the raw model output is saved to:

```text
outputs/debug_qwen_raw.txt
```

The demo then uses a minimal fallback extraction so the full pipeline can still produce auditable outputs.

## Validators

Run validators from the project directory:

```powershell
python -m validators.validate_world_model outputs/world_model.json
python -m validators.validate_semantic_consistency outputs/world_model.json
python -m validators.validate_episode_log outputs/episode_log.jsonl
python -m validators.validate_vision_extraction outputs/world_model.json outputs/run_audit.json
python -m validators.validate_ai2thor_smoke outputs/world_model.json outputs/run_audit.json
python -m validators.validate_visual_sequence outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python -m validators.validate_local_sim_run outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python -m validators.validate_track1_procedure outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python -m validators.validate_random_local_sim_run outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python -m validators.validate_no_hidden_spec_leakage outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
```

The world model validator checks required top-level fields, object identity fields, unique object IDs, plans, and structured exception recovery records.

The semantic consistency validator checks relation endpoints, structured locations, stale relations after relocation, topology, agent state, action ontology compliance, and recovery plan linkage.

The episode log validator checks JSONL validity, required fields, increasing steps, audit event coverage, and recovery after a failed `pick_up(book)`.

Run all mock episodes with:

```powershell
python tests/smoke_test_all_mock_episodes.py
```

By default, the smoke test uses deterministic mock LLM mode, so it does not call vLLM:

```powershell
python tests/smoke_test_all_mock_episodes.py
```

Run the same smoke coverage against the real local vLLM:

```powershell
python tests/smoke_test_all_mock_episodes.py --mode real
python tests/smoke_test_all_mock_episodes.py --mode real --episode-id mock-bedroom-relocated
python tests/smoke_test_all_mock_episodes.py --mode real --all
python tests/smoke_test_all_mock_episodes.py --mode real --all --strict-real
```

Run a direct Qwen vision smoke call:

```powershell
python tools/test_qwen_vision_call.py --image-path assets/test_images/bedroom.png
```

Run an AI2-THOR adapter smoke call:

```powershell
pip install ai2thor
python tools/test_ai2thor_adapter.py --scene FloorPlan1
```

Run the optional VirtualHome Windows spike:

```powershell
python tools/check_local_gpu_runtime.py
python tools/check_gpu_budget.py
python tools/setup_virtualhome_hint.py
python tools/check_virtualhome_env.py
python tools/test_virtualhome_windows_spike.py
python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json
```

VirtualHome is a Windows-friendly household activity simulator candidate for scene graph, action program, and optional visual-frame smoke tests. It is a complementary route after AI2-THOR/Habitat local rendering blockers, not a claim that VirtualHome fully replaces ProcTHOR, Habitat, AI2-THOR, or the official EAGC runtime.

For a real VirtualHome Windows executable smoke, place the VirtualHome repo and simulator outside this project tree, then set:

```powershell
# If the repo is not present yet, clone it outside this project:
git clone https://github.com/xavierpuigf/virtualhome.git C:\Users\Alphay\Documents\ExternalTools\virtualhome
$env:VIRTUALHOME_REPO_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome"
$env:VIRTUALHOME_SIMULATOR_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\<actual_exe_name>.exe"
```

Do not commit the VirtualHome repository, Unity executable, Unity assets, generated frames, videos, or other simulator artifacts.

If you want to test a separate lightweight vLLM profile for sharing GPU memory with VirtualHome, review the dry-run first:

```powershell
scripts/start_vllm_qwen36_vh_lite.ps1
```

Only after reviewing the inferred image/mount plan, start the separate container:

```powershell
scripts/start_vllm_qwen36_vh_lite.ps1 -ForceRun
python tools/check_vllm_endpoint.py --base-url http://127.0.0.1:8001/v1
scripts/stop_vllm_qwen36_vh_lite.ps1
```

These scripts use a separate container name, `eagc-vllm-qwen36-vh-lite`, and host port `8001`. They do not delete or modify the original vLLM container. See:

```text
docs/vllm_virtualhome_gpu_budget.md
docs/local_vllm_lightweight_profile.md
docs/virtualhome_windows_spike_report.md
```

## ALFRED Offline Adapter

The optional ALFRED offline adapter parses public `traj_data.json` files without launching AI2-THOR. It is intended for public household task trajectory alignment in reports and diagnostics, not online closed-loop simulator evaluation.

It supports two validation modes:

1. Synthetic fixture conversion for stable fast-tier testing: `tests/fixtures/alfred/sample_traj_data.json`.
2. Real ALFRED dataset conversion when the user manually provides a local ALFRED path.

The synthetic fixture is explicitly marked `fixture_type="synthetic_alfred_like"` and is not real ALFRED data or benchmark evidence.

Set one of:

```powershell
$env:ALFRED_DATASET_ROOT="C:\path\to\ALFRED"
$env:ALFRED_SAMPLE_TRAJ_PATH="C:\path\to\traj_data.json"
```

Then run:

```powershell
python tools/check_alfred_dataset.py
python tests/smoke_test_alfred_fixture_conversion.py
python tools/convert_alfred_offline.py --traj-path C:\path\to\traj_data.json
python -m validators.validate_alfred_offline_conversion outputs/alfred_offline/status.json
```

If no local ALFRED data is present, the checker and converter exit gracefully with `reason="missing_alfred_dataset"`. ALFRED data is not downloaded automatically, not redistributed, and must not be committed to git. See `docs/alfred_offline_adapter_report.md`.

Run all LocalSim Track 1 episodes:

```powershell
python tests/smoke_test_local_sim_episodes.py --mode real
python tests/smoke_test_local_sim_episodes.py --mode mock
```

Run all official-style Track 1 procedure episodes:

```powershell
python tests/smoke_test_track1_procedure.py --mode real
python tests/smoke_test_track1_procedure.py --mode mock
```

Package tracked source files only:

```powershell
python tools/package_source.py
```

The source package excludes local virtual environments, generated outputs, image assets, `source_pack/`, Python caches, and zip artifacts.

The mock smoke test runs all five mock episodes, validates each output, and archives per-episode artifacts under `outputs/smoke/`.
It also prints and checks each episode's final `task_status`.

## Run Audit

Each `main.py` run writes:

```text
outputs/run_audit.json
```

It records the episode id, model, base URL, mock LLM flag, run timing, Qwen call counts, output paths, and validation status.

For `--track1-procedure`, it also records phase budgets, phase step usage, `phase_budget_exceeded`, `track1_score_path`, and `track1_total_score`. This is a local heuristic debugging score, not an official EAGC score. The local score is written to:

```text
outputs/track1_score.json
```

Real vLLM calls are appended to:

```text
outputs/qwen_calls.jsonl
```

Each line records timestamp, model, base URL, prompt character count, a short prompt summary, decoding settings, latency, success, and error message. Full prompts are not logged.

## Mock Episodes

Select the active scenario with `episode_id` in `config.yaml`.

- `mock-bedroom-relocated`: object relocated; `pick_up(book)` fails and triggers a search recovery plan.
- `mock-hallway-door-locked`: door locked; `open(door)` fails and triggers key search.
- `mock-kitchen-container-unavailable`: target container unavailable; `place_on(cup, drawer)` fails.
- `mock-study-tool-substitution`: tool substitution; missing screwdriver leads to using a coin.
- `mock-livingroom-nominal`: nominal move task with no simulated failure.

The default scenario is `mock-bedroom-relocated`.

## v0.3 Architecture Notes

The architecture remains intentionally small:

- `clients/`: local OpenAI-compatible vLLM client.
- `env_adapters/`: environment interface plus mock and future official adapters.
- `perception/`: prompt construction, raw JSON extraction, fallback extraction, and normalization.
- `world_model/`: schema creation, updates, and persistence.
- `planner/`: deterministic baseline planning and exception recovery planning.
- `planner/action_schema.py`: shared action ontology used by planners and semantic validators.
- `executor/`: action execution shim over the environment adapter.
- `logging_utils/`: append-only JSONL episode audit log.
- `validators/`: format, semantic consistency, and episode log validation.

The v0.3 world model uses structured locations:

```json
{
  "room": "bedroom",
  "region": "bed_area",
  "support": "bed",
  "status": "known",
  "confidence": 0.9
}
```

Relations include `status`, `confidence`, and `observed_at_step`. When an object is relocated and its location becomes unknown, previous active location relations such as `book on bed` are retained as evidence but marked `stale`.

Allowed planner actions are:

```text
locate(object)
navigate_to(target)
search(region)
pick_up(object)
place_on(object, target)
open(object)
close(object)
unlock(object)
substitute_tool(old_tool, new_tool)
wait()
```

## v0.3.1 Notes

v0.3.1 replaces generic list merging with entity-aware upserts for objects, states, relations, and affordances. Successful actions now update world-model effects, including held objects, placement relations, open/close state, and lock state. Execution exceptions also write queryable state updates, such as locked doors, unavailable containers, and tool substitution records.

Generated output files are ignored by `.gitignore`; `outputs/.gitkeep` keeps the output directory in the repository.

## v0.4 Notes

v0.4 adds CLI controls, deterministic mock LLM mode, Qwen call audit logging, and per-run audit summaries. The default behavior still calls the configured local vLLM unless `use_mock_llm: true` or `--use-mock-llm` is set.

## v0.4.1 Notes

v0.4.1 executes recovery plans after replanning instead of stopping at plan generation. Recovery actions are logged as `recovery_action`, followed by `recovery_complete` or `recovery_failed`.

Action effects now stale old active location relations before `pick_up` and `place_on`, clear stale `held_by=agent` state after placement, and keep `agent_state.holding` consistent with `agent_hand` support.

Semantic and episode-log validators now check closed-loop recovery execution, single active location relation per object, location support consistency, and generic failure-to-replanning behavior.

## v0.4.2 Notes

v0.4.2 adds `TaskEvaluator`, writes `task_status` into `world_model.json`, and distinguishes completed tasks from fallback recovery such as `blocked_recovered` for unavailable containers.

After recovery completes, `main.py` evaluates the task. If the task is still in progress, it resumes the original plan actions after the failed action. For example, the door-locked episode unlocks and opens the door, then resumes `navigate_to(next_room)`.

`MockEnv` is now stateful: it tracks holding, object availability and locations, door lock/open state, drawer availability, and current room. This makes invalid actions fail instead of succeeding unconditionally.

The action ontology now includes:

```text
use_tool(tool, target)
enter(room)
```

## v0.4.3 Notes

v0.4.3 isolates run outputs under `outputs/runs/` by default and records `run_id`, `output_dir`, `fallback_used`, `debug_raw_path`, and Qwen call counts in `run_audit.json`.

The smoke test now writes each episode to `outputs/smoke/<mode>/<episode_id>/`, runs validators through imported Python functions, and supports targeted real-vLLM checks.

If Qwen returns malformed JSON, the raw output is saved as `debug_qwen_raw.txt` in that run directory. The pipeline can still use fallback extraction, but `run_audit.json` records `fallback_used: true`.

## v0.5 Notes

v0.5 adds a minimal vision interface smoke test:

- `QwenClient.chat_vision(image_path, prompt)` sends text plus `image_url` content to the same OpenAI-compatible chat completions endpoint.
- `tools/test_qwen_vision_call.py` tests a raw vision call and writes `outputs/vision_smoke/qwen_vision_response.json` plus `outputs/vision_smoke/qwen_vision_raw.txt`.
- `VisualMockEnv` provides `visual-bedroom-smoke`, which passes `{text, image_path}` into `VLMExtractor`.
- `main.py --vision --image-path ... --validate` reuses the same world model, planner, executor, task evaluator, and validators.
- `run_audit.json` records `vision_mode`, image metadata, and vision call/parse status.
- `qwen_response_summary.json` records `input_mode: "vision"` for vision extraction.

This is not a ProcTHOR adapter and does not train or modify any model. It is only a static local-image interface smoke test that keeps the official runtime adapter boundary unchanged.

## v0.6 Notes

v0.6 adds a deterministic LocalSim Track 1 MVP environment:

- `env_adapters/local_sim_env.py` provides a local multi-room simulator with bedroom, hallway, kitchen, and living_room topology.
- LocalSim tracks agent room, holding state, visited rooms, known frontiers, object states, visibility, pickup/open/container availability, and controlled exceptions.
- LocalSim episodes cover object relocation, locked-door route recovery, unavailable container fallback, and tool substitution.
- `main.py --env local_sim --episode-id ... --max-steps 50 --validate` runs the same extraction, world-model update, planner, executor, replanner, task evaluator, logging, and validators as the mock/vision paths.
- `validators/validate_local_sim_run.py` checks LocalSim audit fields, topology, visited/frontier records, task status, event coverage, and recovery execution.
- `tests/smoke_test_local_sim_episodes.py --mode real` runs all LocalSim episodes against the configured local vLLM. `--mode mock` uses deterministic mock LLM extraction for fast logic checks.

Expected LocalSim statuses:

```text
local-explore-book-relocated      -> complete
local-door-locked-route           -> complete
local-container-unavailable       -> blocked_recovered
local-tool-substitution           -> complete
```

The v0.6 mainline is LocalSimEnv. It does not depend on AI2-THOR, ProcTHOR, or an official EAGC runtime/API.

## v0.7 Notes

v0.7 adds `Track1ProcedureRunner`, an official-style local Track 1 procedure runner:

- `track1_runner/procedure_runner.py` runs `exploration_start -> exploration_end -> task_received -> planning -> execution_start -> task_evaluation`.
- Exploration uses only `explore`, `navigate_to`, and `search` actions, and LocalSim hides the natural-language task until task reception.
- `config.yaml` includes `track1_budgets` for exploration, planning, execution, and recovery step budgets.
- `scoring/track1_score.py` writes `track1_score.json` with a 100-point local heuristic score over task completion, world-model quality, exception recovery, efficiency, and robustness/safety. It is not an official EAGC score.
- `validators/validate_track1_procedure.py` checks phase order, task leakage, exploration action constraints, required audit fields, and score file validity.
- `tests/smoke_test_track1_procedure.py --mode real` runs all LocalSim episodes through the procedure runner.

This is an official-style local procedure, not the official EAGC runtime/API. `official_adapter.py` remains a reserved interface stub.

## v0.8 Notes

v0.8 adds randomized hidden-style LocalSim robustness evaluation:

- `env_adapters/local_sim_generator.py` creates deterministic generated LocalSim specs from `seed` and `difficulty`.
- `main.py --env local_sim_random --seed N --difficulty easy --track1-procedure --validate` saves `generated_episode_spec.json` and runs the same Track 1 procedure runner.
- Generated specs include rooms, topology, doors, objects, object locations, task text, controlled exception, expected task status, and success condition.
- `TaskEvaluator` now prefers `success_condition` from the generated spec before falling back to fixed episode rules.
- `validators/validate_random_local_sim_run.py` checks generated-spec auditability, expected status, exception recovery evidence, legal visited rooms, topology, and non-teleport placement.
- `tests/robustness_test_random_local_sim.py` runs seed batches and writes `summary_report.json`, `summary_report.md`, and `failure_case.json` for failed cases.

This is hidden-style local robustness evaluation, not an official EAGC benchmark or official score.

## v0.8.1 Notes

v0.8.1 separates agent-visible runtime data from evaluator-only generated specs:

- Generated episode specs now contain `public_env_config` and `hidden_spec`.
- `LocalSimEnv` may hold `hidden_spec` internally, but observations, Qwen prompts, episode logs, and world-model updates do not expose `success_condition`, `expected_task_status`, or raw `controlled_exception`.
- `TaskEvaluator` receives evaluator-only context from the runner instead of reading hidden success conditions from the world model.
- `validators/validate_no_hidden_spec_leakage.py` audits world model, episode log, Qwen call summaries, and Qwen response summaries for hidden spec leakage.
- Medium difficulty adds more varied object placement, distractors, non-adjacent relocation targets, blocked routes, candidate substitutes, and a small number of accepted unrecoverable cases.
- Robustness summaries now include accepted failures, recoverable success rate, average Qwen calls, average latency, fallback count, leakage status, per-template stats, per-exception stats, and top failure reasons.

Local standards for this MVP:

- easy 100 mock episodes: verifies the generator, planner, validators, and local heuristic scoring
- easy 20 real episodes: verifies Qwen stability on easy randomized runs
- medium 10 real episodes: quick robustness exposure for harder randomized runs
- medium 50 real episodes: optional overnight stress test, not required for v0.8.1 submission
- easy threshold: `complete + blocked_recovered >= 85%`
- medium threshold: `complete + blocked_recovered + accepted_failure >= 60%`
- `fallback_used_count` should ideally be 0
- leakage checks must pass for every generated run

These are local hidden-style checks for robustness. They are not official EAGC evaluation results.

## v0.8.2 Notes

v0.8.2 adds targeted replay and repair for a recoverable medium `door_locked` failure:

- `tools/replay_random_local_sim_failure.py` reruns one generated seed and saves `generated_episode_spec.json`, `public_env_config.json`, `hidden_spec_debug.json`, output artifacts, and `failure_diagnosis.json`.
- `diagnostics/diagnose_episode_failure.py` classifies common route/recovery failures such as `door_unlocked_but_not_entered`, `key_found_but_not_used`, `opened_door_but_original_plan_not_resumed`, and `recovery_plan_incomplete`.
- `RulePlanner` now keeps the post-recovery route for tasks like 鈥済o to kitchen and place cup on counter鈥? open/verify the room route, navigate to the object, pick it up, return to the target room, and place it.
- `Replanner` uses explicit `required_key` metadata for locked doors when available.
- `Track1ProcedureRunner` can synthesize a missing `navigate_to(target_room)` after door recovery if a failure occurred on a route action.
- `TaskEvaluator` distinguishes 鈥渄oor opened鈥?from 鈥渢arget room entered鈥? an open door alone is still `in_progress`.
- Random robustness summaries use `leakage_check_passed` and `hidden_spec_leakage_detected` to avoid ambiguous `leakage=true` wording.

## v0.8.3 Notes

v0.8.3 adds test runtime guardrails and makes Track 1 exploration frontier-based:

- `tests/robustness_test_random_local_sim.py` supports `--episode-timeout-seconds` and `--max-qwen-calls-per-episode`.
- Robustness summaries include timeout/budget counts, max episode latency, max Qwen calls, slowest seed, and highest Qwen-call seed.
- `tools/run_test_suite.py` provides `fast`, `targeted`, `standard`, and `full` test tiers.
- `Track1ProcedureRunner` chooses exploration actions from observed frontiers/topology instead of hardcoded room names.
- `validators/validate_track1_procedure.py` checks that exploration `navigate_to(room)` actions come from observed frontiers or discovered topology.

## v0.8.4 Notes

v0.8.4 adds a technical report and demo package:

- `reports/v0.8.4_technical_report.md` summarizes the project overview, architecture, Track 1 procedure, world-model schema, evaluation setup, results, limitations, and next steps.
- `reports/architecture_overview.md`, `reports/experiment_summary.md`, and `reports/limitations_and_next_steps.md` provide shorter reference docs.
- `docs/demo_commands.md` lists fast, targeted, standard, random LocalSim, Track 1 procedure, and vision smoke demo commands.
- `tools/generate_project_report.py` reads existing robustness summaries and git metadata, then regenerates the v0.8.4 technical report.

Generate the report with:

```powershell
python tools/generate_project_report.py
```

## v0.7.1 Notes

v0.7.1 tightens LocalSim realism without changing the overall architecture:

- LocalSim observations are partially observable. The environment keeps the full internal topology, but observations only expose visited rooms and currently visible frontiers.
- World-model topology updates are merged by room instead of overwritten by the latest observation.
- LocalSim no longer allows teleport placement. `place_on` and `place_in` fail if the target object is not in the current room.
- Navigation action effects distinguish rooms, objects, and doors so `visited_rooms` contains only actual rooms.
- LocalSim and Track 1 procedure validators check visited-room integrity, placement reachability, partial-observability leakage, and exploration actions that depend on task-specific targets.
- `tools/package_source.py` creates `dist/eagc_track1_mvp_source.zip` from git tracked source files only.

## AI2-THOR Experimental Notes

The repository keeps an experimental AI2-THOR simulator adapter smoke test:

- `env_adapters/ai2thor_adapter.py` starts an `ai2thor.controller.Controller`, captures one RGB frame, and saves simulator metadata.
- `tools/test_ai2thor_adapter.py --scene FloorPlan1` verifies that AI2-THOR can start on the local machine and writes `outputs/ai2thor_smoke/frame.png` plus `outputs/ai2thor_smoke/metadata.json`.
- `main.py --env ai2thor --scene FloorPlan1 --validate` captures a simulator frame, sends it through the existing Qwen vision extraction path, updates the world model, and runs validators.
- `run_audit.json` records simulator frame path, metadata path, scene, AI2-THOR startup status, and any simulator error message.
- `validators/validate_ai2thor_smoke.py` checks the saved frame, metadata, AI2-THOR audit fields, episode log, and non-empty world-model objects.

Install AI2-THOR only when you want to run the simulator smoke:

```powershell
pip install ai2thor
```

`oracle_metadata_mode: false` is the default. In this mode, world-model extraction should come from Qwen vision, not directly from simulator metadata. Setting `oracle_metadata_mode: true` may write `debug_oracle_objects.json` for development comparison, debugging, or training-data analysis, but oracle metadata should not be treated as a final official evaluation dependency.

Windows native and WSL2 CloudRendering checks did not pass in the current local setup, so AI2-THOR remains experimental and no `v0.6-ai2thor` tag is used. Future work can handle AI2-THOR separately in a suitable Docker/Ubuntu graphics environment.

## v0.9 Notes

v0.9 adds a local multi-frame visual sequence world-model update path:

- `VisualSequenceEnv` reads `frame_*.png`, `frame_*.jpg`, `frame_*.jpeg`, or `frame_*.webp` from a local directory in filename order.
- `main.py --env visual_sequence --image-dir ... --max-frames N --validate` calls Qwen vision once per frame.
- Each frame incrementally updates the same world model; it does not reinitialize or overwrite prior state.
- Same-name or same-id objects persist across frames and update `last_observed_step`.
- If a new frame moves an object to a new active location relation, prior active location relations for that object become `stale`.
- Objects not visible in the current frame are retained and marked with `visibility=not_observed_current_frame`; uncertainty records note that the object was not visible instead of deleting it.
- Simple confidence decay lowers location confidence when an object is not observed in the current frame.
- `run_audit.json` records `env=visual_sequence`, `image_dir`, `processed_frames`, `frame_paths`, Qwen call counts, fallback use, and vision parse status.
- `validators/validate_visual_sequence.py` checks multi-frame processing, log coverage, object persistence, duplicate ids, stale/active relation consistency, and run audit fields.
- `tests/smoke_test_visual_sequence.py` runs the visual sequence path and validator when local test images are present.

You need to provide local test images under `assets/test_sequences/bedroom_sequence/` or another directory. This is still a local smoke test over static images, not an official runtime, not ProcTHOR, not AI2-THOR, and not a training setup.

## v0.9.1 Notes

v0.9.1 finalizes the real-image visual sequence smoke validation:

- The local validation used three Pexels bedroom-sequence images named `frame_000.jpg`, `frame_001.jpg`, and `frame_002.jpg`.
- The images are local test resources only and are ignored by git; do not submit them as source.
- Latest validation summary: `processed_frames=3`, `qwen_call_count=3`, `fallback_used=False`, `vision_parse_success=True`, `object_count=15`, `relation_count=23`.
- Object and relation counts can vary slightly across real Qwen vision runs; the validator focuses on structured extraction, frame accounting, object persistence, not-visible retention, and stale/active relation consistency.
- The run validated object persistence across frames, `not_observed_current_frame` visibility records, and stale/active relation updates.
- `tests/smoke_test_visual_sequence.py` can be run directly from the project root without setting `PYTHONPATH`.
- This remains a local visual sequence smoke test, not an official environment, not ProcTHOR/AI2-THOR, and not model training.

Local non-source artifacts that should stay out of git include:

- `assets/test_sequences/bedroom_sequence/frame_*.jpg`
- `assets/test_sequences/bedroom_sequence/frame_*.png`
- `pexels-readymade-4008334.jpg`
- `source_pack/`
- `outputs/`

## v0.10 Notes

v0.10 adds a visual-local hybrid Track 1 prototype:

- It first builds a world model from the local multi-frame visual sequence.
- After visual exploration, it receives a simple visual task such as `Find the laptop.` or `Is the laptop on the chair?`.
- `RulePlanner.plan_visual(...)` generates lightweight symbolic actions such as `locate(object)`, `answer_location(object)`, and `answer_relation(subject, relation, object)`.
- `SymbolicVisualExecutor` performs plan-level checks against the visual world model. It does not call a physical environment step and does not pretend that `pick_up` or `place_on` succeeded.
- `visual_task_evaluator.py` supports find-object, identify-location, relation-query, and near-relation tasks.
- `run_audit.json` records `visual_local_hybrid`, `visual_task`, `visual_task_status`, `symbolic_action_count`, `unsupported_physical_action_count`, and `evidence_count`.

## v0.10.1 Notes

v0.10.1 upgrades visual task evaluation from a simple status result to evidence-based explanation:

- Each visual task result is saved to `visual_task_result.json`.
- The result includes `status`, `success`, `answer`, `confidence`, `supporting_evidence`, `contradicting_evidence`, `missing_evidence`, `evidence_summary`, `queried_entities`, and `queried_relations`.
- `complete` requires supporting evidence; the system does not mark a visual task complete without evidence.
- Relation queries such as `Is the laptop on the chair?` require an explicit active relation in the world model. If both objects exist but the active relation is missing, the result is `uncertain`.
- `uncertain` is a conservative visual judgment, not a program failure. It reports what evidence is present, what evidence is missing, and whether any contradictory relation was observed.
- `run_audit.json` records `visual_task_result_path`, `visual_task_confidence`, `supporting_evidence_count`, `contradicting_evidence_count`, and `missing_evidence_count`.
- `validators/validate_visual_task_evidence.py` checks that the result schema and evidence counts are valid.

## v0.10.2 Notes

v0.10.2 packages the current project as a more reproducible stage demo:

- `tools/run_test_suite.py` supports `fast`, `targeted`, `standard`, and `full` tiers.
- `tools/create_demo_snapshot.py` creates `outputs/demo_snapshot/` with a LocalSim Track 1 demo and a visual evidence demo.
- `tools/package_source.py` creates `dist/eagc_track1_mvp_source.zip` from git-tracked source files only and verifies that outputs, local images, `.venv-ai2thor`, `source_pack`, zip files, and `__pycache__` are excluded.
- `tools/check_source_package_repro.py` extracts the source zip into `dist/repro_check/`, verifies required files and exclusions, then compiles source directories and runs `python tools/run_test_suite.py --tier fast` in the clean extracted project.
- `docs/submission_readiness_checklist.md` summarizes current artifacts, dependencies, hardware, training disclosure, and known limitations.
- The project remains a local MVP. LocalSim results are not official EAGC results, visual-local hybrid is symbolic, and no model training is performed.

## v0.10.4 Notes

v0.10.4 adds a clean source package reproducibility check:

```powershell
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
```

The check confirms that the source archive excludes runtime outputs, local images, `dist/`, `source_pack/`, `.venv-ai2thor/`, and `__pycache__/`, then verifies that the extracted source can compile and run the fast test tier.
- `validators/validate_visual_local_hybrid.py` checks task ordering, symbolic answer coverage, plans, task status, and that no physical action is reported as successful.

This is still a local prototype that connects visual world-model construction to planning and task evaluation. It is not real physical execution, not ProcTHOR/AI2-THOR, not the official EAGC runtime, and not model training.

## v0.11 Docker Notes

v0.11 adds Docker submission-readiness packaging for the executable local agent:

- `Dockerfile` builds a Python 3.11 slim image with the inference client, world-model update modules, planner/replanner, task evaluator, validators, diagnostics, and demo/test commands.
- The Docker image does **not** include Qwen3.6-35B-A3B-NVFP4 model weights.
- Runtime model access is configured through `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_TEMPERATURE`, and `QWEN_MAX_TOKENS`, which override `config.yaml`.
- `tools/run_test_suite.py --tier docker-smoke` runs a mock-only container smoke check that does not require real Qwen, local images, AI2-THOR, or ProcTHOR.
- `tools/check_docker_context.py` verifies that Docker build context rules exclude outputs, dist, source packs, local images, zip files, virtual environments, and caches.

Build and run mock-only smoke:

```powershell
docker build -t eagc-track1-agent:v0.11 .
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
```

Run against host vLLM on Windows Docker Desktop:

```powershell
docker run --rm -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.11 python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

See `docker/README_DOCKER.md` and `docker/docker_run_examples.md` for more details.

## v0.11.1 Bundle Notes

v0.11.1 adds a qualification submission readiness bundle builder:

```powershell
python tools/create_submission_bundle.py
```

The generated `submission_bundle/` includes Docker instructions, the prepared source zip, report/disclosure documents, sample `world_model.json` and `episode_log.jsonl` outputs, and SHA256 checksums. It is a local upload-preparation artifact and is ignored by git.

## Adapter Layout

- `env_adapters/base.py`: stable adapter interface
- `env_adapters/mock_env.py`: current local demo environment
- `env_adapters/official_adapter.py`: placeholder for a future official EAGC runtime adapter

The rest of the pipeline depends on `BaseEnvAdapter`, so the official adapter can replace `MockEnv` without rewriting planning, execution, or logging.

The official EAGC runtime/API is still not integrated. `official_adapter.py` is a reserved interface stub until the official runtime, API, and schema are available.
