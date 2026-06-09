# EAGC Track 1 MVP

Minimal runnable Python MVP for EAGC 2026 Track 1. It uses a mock text-only environment and a replaceable adapter layout until an official EAGC runtime/API/schema is available.

Current version: v0.6 LocalSim Track 1 MVP environment.

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
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-steps 3 --validate
```

Run the LocalSim Track 1 MVP environment:

```powershell
python main.py --env local_sim --episode-id local-explore-book-relocated --max-steps 50 --validate
python main.py --env local_sim --episode-id local-door-locked-route --max-steps 50 --validate
python main.py --env local_sim --episode-id local-container-unavailable --max-steps 50 --validate
python main.py --env local_sim --episode-id local-tool-substitution --max-steps 50 --validate
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

Run all LocalSim Track 1 episodes:

```powershell
python tests/smoke_test_local_sim_episodes.py --mode real
python tests/smoke_test_local_sim_episodes.py --mode mock
```

The mock smoke test runs all five mock episodes, validates each output, and archives per-episode artifacts under `outputs/smoke/`.
It also prints and checks each episode's final `task_status`.

## Run Audit

Each `main.py` run writes:

```text
outputs/run_audit.json
```

It records the episode id, model, base URL, mock LLM flag, run timing, Qwen call counts, output paths, and validation status.

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

## v0.5.1 Notes

v0.5.1 adds a local multi-image visual sequence smoke path:

- `VisualSequenceEnv` reads `frame_*.png`, `frame_*.jpg`, `frame_*.jpeg`, or `frame_*.webp` from a local directory in filename order.
- `main.py --env visual_sequence --image-dir ... --max-steps N --validate` calls Qwen vision once per frame.
- Each frame incrementally updates the same world model; it does not reinitialize or overwrite prior state.
- If a new frame moves an object to a new active location relation, prior active location relations for that object become `stale`.
- Objects not visible in the current frame are retained and marked with `visibility=not_observed_current_frame`; uncertainty records note that the object was not visible instead of deleting it.
- `run_audit.json` records `frame_count`, `image_dir`, and `processed_frames`.
- `validators/validate_visual_sequence.py` checks multi-frame processing, log coverage, non-empty objects, and active location relation consistency.

This is still a local smoke test over static images, not an official runtime or training setup.

## Adapter Layout

- `env_adapters/base.py`: stable adapter interface
- `env_adapters/mock_env.py`: current local demo environment
- `env_adapters/official_adapter.py`: placeholder for a future official EAGC runtime adapter

The rest of the pipeline depends on `BaseEnvAdapter`, so the official adapter can replace `MockEnv` without rewriting planning, execution, or logging.

The official EAGC runtime/API is still not integrated. `official_adapter.py` is a reserved interface stub until the official runtime, API, and schema are available.
