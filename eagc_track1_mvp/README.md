# EAGC Track 1 MVP

Minimal runnable Python MVP for EAGC 2026 Track 1. It uses a mock text-only environment and a replaceable adapter layout until an official EAGC runtime/API/schema is available.

Current version: v0.3.1 semantic correctness fixes.

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
```

The client currently supports text-only chat completions through:

```text
POST /chat/completions
```

## Run

```powershell
python main.py
```

Expected outputs:

```text
outputs/world_model.json
outputs/episode_log.jsonl
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
```

The world model validator checks required top-level fields, object identity fields, unique object IDs, plans, and structured exception recovery records.

The semantic consistency validator checks relation endpoints, structured locations, stale relations after relocation, topology, agent state, action ontology compliance, and recovery plan linkage.

The episode log validator checks JSONL validity, required fields, increasing steps, audit event coverage, and recovery after a failed `pick_up(book)`.

Run all mock episodes with:

```powershell
python tests/smoke_test_all_mock_episodes.py
```

The smoke test runs all five mock episodes, validates each output, and archives per-episode artifacts under `outputs/smoke/`.

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

## Adapter Layout

- `env_adapters/base.py`: stable adapter interface
- `env_adapters/mock_env.py`: current local demo environment
- `env_adapters/official_adapter.py`: placeholder for a future official EAGC runtime adapter

The rest of the pipeline depends on `BaseEnvAdapter`, so the official adapter can replace `MockEnv` without rewriting planning, execution, or logging.

The official EAGC runtime/API is still not integrated. `official_adapter.py` is a reserved interface stub until the official runtime, API, and schema are available.
