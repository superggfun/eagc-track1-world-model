# EAGC Track 1 MVP

Minimal runnable Python MVP for EAGC 2026 Track 1. It uses a mock text-only environment and a replaceable adapter layout until an official EAGC runtime/API/schema is available.

The demo loop:

1. `MockEnv` emits a bedroom observation.
2. `QwenClient` calls a local OpenAI-compatible vLLM endpoint.
3. `VLMExtractor` extracts objects, states, relations, affordances, and uncertainty.
4. `WorldModelStore` updates and writes `outputs/world_model.json`.
5. `RulePlanner` creates subgoals and actions.
6. `ActionExecutor` simulates action execution.
7. `Replanner` creates a recovery plan when `pick_up(book)` fails.
8. `EpisodeLogger` writes `outputs/episode_log.jsonl`.

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

## Mock Scenario

- Room: `bedroom`
- Visible objects: `bed`, `pillow`, `book`, `lamp`, `chair`, `door`
- Task: `Find the book and place it on the chair.`
- Simulated exception: the first `pick_up(book)` fails because the book is no longer on the bed.
- Recovery: the replanner marks the book location as unknown and generates a search plan for likely nearby locations.

## Adapter Layout

- `env_adapters/base.py`: stable adapter interface
- `env_adapters/mock_env.py`: current local demo environment
- `env_adapters/official_adapter.py`: placeholder for a future official EAGC runtime adapter

The rest of the pipeline depends on `BaseEnvAdapter`, so the official adapter can replace `MockEnv` without rewriting planning, execution, or logging.
