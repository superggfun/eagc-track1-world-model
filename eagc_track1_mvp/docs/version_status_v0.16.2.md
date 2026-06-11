# v0.16.2 Version Status: VirtualHome Manual-Play Connection Smoke

## Scope

v0.16.2 validates a VirtualHome-only Windows smoke test using a manually started VirtualHome Unity executable.

This run did not:

- train or fine-tune models,
- call Qwen vision,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion.

## External Resources

External resources remain outside the EAGC project tree:

- VirtualHome repository:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
- VirtualHome Windows executable:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\windows_exec\windows_exec.v2.3.0\VirtualHome.exe`

The repository, executable, downloaded zip, Unity assets, and output artifacts are not committed.

## Manual-Play Smoke Result

The user manually opened `VirtualHome.exe`, selected Windowed mode, and pressed Play. The smoke script then detected that port `8080` was open and connected to the already-running simulator.

Result:

- Python API import: success.
- Executable path check: success.
- Existing simulator connection: success.
- Scene reset: success.
- Character add: success.
- Scene graph retrieval: success.
- Program execution: success.
- Converted world model generation: success.
- Converted episode log generation: success.
- Camera frame export: not validated.

Successful program:

```text
<char0> [Walk] <sofa> (1)
<char0> [Sit] <sofa> (1)
```

`outputs/virtualhome_spike/status.json` reported:

```json
{
  "success": true,
  "reason": "virtualhome_spike_completed",
  "existing_simulator_connection_used": true,
  "character_added": true,
  "program_execution_success": true,
  "converted_object_count": 440
}
```

## Generated Artifacts

The following artifacts were generated locally under `outputs/virtualhome_spike/`:

- `status.json`
- `scene_graph.json`
- `program_log.json`
- `converted_world_model.json`
- `converted_episode_log.jsonl`

These are runtime outputs and are intentionally not committed.

## Remaining Limitations

- Automated Windows Unity startup is still not validated.
- The smoke depends on manual interaction with the Unity launcher window.
- Camera frame export was not validated.
- VirtualHome is still an optional simulator spike, not the official EAGC runtime and not a replacement for hidden evaluation.
- VirtualHome dependencies were installed in the user Python environment during v0.16.1; future work should isolate them in a dedicated virtual environment.

