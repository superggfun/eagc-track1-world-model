# v0.16.3 Version Status: VirtualHome Manual-Play Regression Suite

## Scope

v0.16.3 solidifies the VirtualHome manual-play route as an optional regression smoke.

This version does not:

- train or fine-tune models,
- call Qwen,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion.

## Validated Manual-Play Route

The known-good route is:

1. Start `VirtualHome.exe`.
2. Select Windowed mode if prompted.
3. Press Play.
4. Confirm `127.0.0.1:8080` is listening.
5. Run:

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-manual --timeout-seconds 300
```

If the port is not listening, the tier skips gracefully and does not fail the rest of the local project.

## Regression Tasks

The VirtualHome smoke now runs four fixed minimal household tasks when the scene supports the required objects:

- `walk_to_and_sit_on_sofa`
- `walk_to_and_grab_object`
- `walk_to_and_open_object`
- `place_object_on_surface`

Unsupported tasks are recorded as `unsupported_in_scene`; supported task failures are recorded and cause the smoke to fail.

Latest run:

- `task_success_count=4`
- `task_failed_count=0`
- `task_unsupported_count=0`
- `converted_object_count=440`
- `program_execution_success=true`

## Artifacts

Runtime artifacts are written under `outputs/virtualhome_spike/` and are not committed:

- `status.json`
- `scene_graph.json`
- `program_log.json`
- `converted_world_model.json`
- `converted_episode_log.jsonl`
- `manual_suite_status.json`

`frame_000.png` remains unvalidated.

## Validators

v0.16.3 adds:

```powershell
python -m validators.validate_virtualhome_converted_world_model outputs/virtualhome_spike/converted_world_model.json outputs/virtualhome_spike/converted_episode_log.jsonl
```

This checks converted world-model structure, source metadata, room/object/relation content, episode-log action/result content, and non-empty successful task logs.

## Remaining Limitations

- Automated Unity startup is still not validated.
- Frame export is not validated.
- VirtualHome remains an optional Windows simulator spike, not an official EAGC environment.
- VirtualHome dependencies were installed into the user Python environment during v0.16.1; a dedicated virtual environment is recommended if this path becomes a regular backend.

