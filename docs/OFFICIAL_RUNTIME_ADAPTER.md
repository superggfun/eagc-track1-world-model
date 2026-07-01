# Official Runtime Adapter

LocalSim, MazeSim, visual evidence, and VirtualHome diagnostics are local evidence environments. They are not the official hidden evaluator.

The future official runtime should be integrated through `src/env_adapters/official_env.py`. The core Track 1 pipeline expects the adapter to provide:

- `reset(episode_config=None) -> dict`
- `observe() -> dict`
- `step(action) -> dict`
- `action_schema() -> list[dict]`
- `capabilities() -> dict`
- `close() -> None`

Canonical observations may include `observation`, `raw_observation`, `current_room`, `visible_objects`, `available_actions`, `image_path`, `timestamp`, and `metadata`. Missing optional fields are handled gracefully.

Canonical step results may include `success`, `action`, `result`, `observation_packet`, `error`, and `metadata`.

Official mode is fail-closed in this repository. If the official runtime is not configured or the released SDK/RPC/socket/HTTP wiring has not been implemented, `OfficialEnvAdapter` raises a clear runtime error and never falls back to LocalSim.

Expected environment variables:

- `EAGC_EPISODE_ID`
- `EAGC_OUTPUT_DIR`
- `EAGC_CONFIG_PATH`
- `EAGC_ENV_HOST`
- `EAGC_ENV_PORT`
- `EAGC_OFFICIAL_MODE`
- `EAGC_ACTION_SCHEMA_PATH`

Required outputs from an official run are the same agent artifacts:

- `world_model.json`
- `episode_log.jsonl`
- `run_audit.json`
- `harness_result.json`
- `track1_score.json` when the Track 1 procedure runner produces a local score artifact

The official adapter must not use hidden ground truth, reference maps, or hidden task specification files for generation. It should only consume public runtime APIs such as observation, available action schema, action execution results, and local frame/observation payloads provided by the official runtime.

Action translation is isolated in `src/executor/action_translator.py`. If the official runtime uses a different action format, update that translator or adapter-specific schema handling. Unsupported actions must fail as invalid actions so the planner/recovery path can handle them; the adapter must not invent unlisted actions.

When the official API is released, concrete work should be limited to:

- adding official SDK/RPC/socket/HTTP calls in `src/env_adapters/official_env.py`
- updating action translation/schema handling if needed
- setting official runner configuration

The world model update logic, planner core, Track1ProcedureRunner, episode logger, audit builder, validators, and submission bundle format should not need a rewrite.
