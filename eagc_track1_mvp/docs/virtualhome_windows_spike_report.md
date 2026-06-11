# VirtualHome Windows Spike Report

This document records the optional VirtualHome Windows simulator spike. It is not part of the stable EAGC agent gate and does not replace ProcTHOR, Habitat, AI2-THOR, or an official Track 1 runtime.

## Scope

Goals:

- Check whether a VirtualHome Windows Unity executable is available on the current machine.
- Check whether the VirtualHome Python API can be imported.
- If available, start or connect to the simulator, reset a scene, get a scene graph, and execute a tiny household program.
- Save spike artifacts under `outputs/virtualhome_spike/`.
- Convert scene graph / program log artifacts into approximate `world_model` and `episode_log` files.
- Gracefully fail when the executable or API is missing.

Non-goals:

- No model training.
- No modification of the main agent architecture.
- No claim that VirtualHome is a full substitute for ProcTHOR or official EAGC runtime.
- No deletion or reconfiguration of the existing vLLM Docker container.

## Configuration

`config.yaml` contains optional VirtualHome fields:

```yaml
virtualhome:
  simulator_path: ""
  port: 8080
  default_scene: 0
  camera_mode: "FIRST_PERSON"
```

Environment variables can override the simulator path and port:

```powershell
$env:VIRTUALHOME_REPO_PATH = "C:\path\to\VirtualHome"
$env:VIRTUALHOME_SIMULATOR_PATH = "C:\path\to\VirtualHome.exe"
$env:VIRTUALHOME_PORT = "8080"
```

`VIRTUALHOME_REPO_PATH` is optional but recommended when the VirtualHome Python API is available from a local clone rather than an installed package. The spike scripts add this repository path to `sys.path` for the current process only; they do not modify `requirements.txt` and do not install packages automatically.

## Commands

Environment probe:

```powershell
python tools/setup_virtualhome_hint.py
python tools/check_virtualhome_env.py
```

Spike run:

```powershell
python tools/test_virtualhome_windows_spike.py
```

Validation:

```powershell
python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json
```

GPU budget:

```powershell
python tools/check_gpu_budget.py
```

Optional lightweight vLLM endpoint check:

```powershell
python tools/test_vllm_lite_endpoint.py
```

## Expected Artifacts

Always expected after the environment/spike commands:

```text
outputs/virtualhome_spike/env_status.json
outputs/virtualhome_spike/status.json
```

Expected only when VirtualHome runs successfully:

```text
outputs/virtualhome_spike/scene_graph.json
outputs/virtualhome_spike/program_log.json
outputs/virtualhome_spike/converted_world_model.json
outputs/virtualhome_spike/converted_episode_log.jsonl
outputs/virtualhome_spike/frame_000.png
```

`frame_000.png` is optional and depends on VirtualHome camera support and API availability.

## Current Status

The spike scripts are implemented with graceful failure behavior. If VirtualHome is not installed or the Unity executable path is missing, `status.json` records:

```json
{
  "success": false,
  "reason": "missing_virtualhome_executable"
}
```

or another explicit not-ready reason. This is considered a valid optional-spike outcome and should not break the main LocalSim / visual-local MVP.

Latest local probe on 2026-06-11:

- `python tools/check_virtualhome_env.py` completed and wrote `outputs/virtualhome_spike/env_status.json`.
- VirtualHome Python API import is not currently available.
- `VIRTUALHOME_REPO_PATH` is not set to a usable VirtualHome clone.
- `VIRTUALHOME_SIMULATOR_PATH` / `virtualhome.simulator_path` is not set, so the Windows Unity simulator executable is also missing.
- `python tools/test_virtualhome_windows_spike.py` completed gracefully and wrote `outputs/virtualhome_spike/status.json`.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passed because the missing API/executable state is reported explicitly rather than faked as success.
- `python tools/setup_virtualhome_hint.py` provides manual setup hints and does not download large files.

Current `status.json` reason:

```text
missing_virtualhome_python_api
```

Required user-provided artifacts before a real smoke can run:

1. A local VirtualHome repository or installed Python API exposing `simulation.unity_simulator.comm_unity`.
2. A Windows VirtualHome Unity simulator executable path, provided via `VIRTUALHOME_SIMULATOR_PATH` or `config.yaml`.

Do not commit the executable, Unity assets, frames, videos, or other large simulator artifacts.

## Assessment Criteria

VirtualHome becomes a useful Windows-friendly household simulator candidate if:

- the Windows Unity executable launches reliably,
- scene graph extraction works,
- simple household programs execute,
- optional camera frames can be saved,
- generated scene graph / frame artifacts can be converted into the existing world model and visual pipeline.

Until those conditions are met, VirtualHome remains an optional simulator spike rather than a main backend.

VirtualHome is still only a Windows-friendly household activity simulator candidate. It is useful to explore scene graphs, household programs, and possible visual frames, but this project does not claim it fully replaces ProcTHOR, Habitat, AI2-THOR, or the future official EAGC Track 1 runtime.
