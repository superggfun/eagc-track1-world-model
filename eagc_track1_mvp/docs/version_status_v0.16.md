# v0.16 Version Status: VirtualHome Real Windows Smoke

## Goal

v0.16 attempts a VirtualHome-only Windows smoke test using a real VirtualHome Python API repository and a real Windows Unity simulator executable.

This spike does not:

- train or fine-tune any model,
- call Qwen vision,
- start a lightweight vLLM profile,
- modify, restart, delete, or manage the existing long-context Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or any other simulator.

## Expected External Resources

Both resources must live outside this EAGC project tree:

- VirtualHome repo/API:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
- VirtualHome Windows Unity simulator:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator`

Recommended setup:

```powershell
git clone https://github.com/xavierpuigf/virtualhome.git C:\Users\Alphay\Documents\ExternalTools\virtualhome
$env:VIRTUALHOME_REPO_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome"
$env:VIRTUALHOME_SIMULATOR_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\<actual_exe_name>.exe"
```

The executable, Unity assets, generated frames, videos, and simulator repository must not be committed to git.

## Smoke Criteria

A successful real VirtualHome smoke must show:

- Python API import succeeds.
- Simulator executable path exists.
- Simulator starts or accepts a connection.
- Scene graph is retrieved.
- A small household program is executed.
- `outputs/virtualhome_spike/scene_graph.json` is written.
- `outputs/virtualhome_spike/program_log.json` is written.
- `outputs/virtualhome_spike/status.json` has `success=true`.
- Converted `world_model` and `episode_log` are generated.

`frame_000.png` is optional because camera/image support depends on the available VirtualHome API and Unity build.

## Current Result

The scripts support real smoke execution and graceful blocker reporting. If the external VirtualHome repo/API or simulator executable is missing, `status.json` records the exact blocker instead of reporting success.

Latest local probe:

- External directories were created outside this repository.
- `C:\Users\Alphay\Documents\ExternalTools\virtualhome` exists but is not currently a VirtualHome repo/API checkout.
- `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator` exists but contains no Windows Unity simulator `.exe`.
- `python tools/check_virtualhome_env.py` reports `python_api_import_success=false` and `simulator_executable_exists=false`.
- `python tools/test_virtualhome_windows_spike.py` exits gracefully with `success=false` and `reason=missing_virtualhome_python_api`.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passes because the blocker is explicit.
- No scene graph, program log, converted world model, converted episode log, or frame was generated.

As of this v0.16 checkpoint, VirtualHome remains an optional simulator spike until the user-provided repo and Windows Unity executable are present and a real scene graph/program execution succeeds.
