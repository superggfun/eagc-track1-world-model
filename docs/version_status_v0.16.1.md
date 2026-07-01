# v0.16.1 Version Status: VirtualHome External Resources and Runtime Blocker

## Scope

v0.16.1 prepared real VirtualHome external resources and attempted a VirtualHome-only Windows smoke test.

This run did not:

- train or fine-tune models,
- call Qwen vision,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion.

## External Resources

All VirtualHome resources were kept outside the EAGC project tree.

- Repo path:
  `<external-tools>\virtualhome`
- Simulator folder:
  `<external-tools>\virtualhome_simulator`
- Windows executable:
  `<external-tools>\virtualhome_simulator\windows_exec\windows_exec.v2.3.0\VirtualHome.exe`
- Downloaded zip:
  `<external-tools>\virtualhome_simulator\windows_exec.zip`

These external resources must not be committed to git.

## Completed

- Cloned the official VirtualHome repository from `https://github.com/xavierpuigf/virtualhome.git`.
- Installed the repository dependency file from `virtualhome/requirements.txt`.
- Verified Python API import:
  `from simulation.unity_simulator import comm_unity`.
- Downloaded the official Windows executable archive from the VirtualHome README link:
  `http://virtual-home.org//release/simulator/v2.0/v2.3.0/windows_exec.zip`.
- Extracted the Windows executable.
- Verified `python_api_import_success=true`.
- Verified `simulator_executable_exists=true`.

## Dependency Note

Installing VirtualHome requirements in the user Python environment downgraded several user-site packages, including `networkx==2.3`. Pip reported compatibility warnings for packages that expect newer `networkx`, including `torch` and `scikit-image`.

For future clean runs, VirtualHome should ideally be installed in a dedicated virtual environment.

## Smoke Result

The VirtualHome-only smoke did not reach scene graph retrieval.

`outputs/virtualhome_spike/status.json` reported:

```json
{
  "success": false,
  "reason": "virtualhome_simulator_connection_timeout",
  "error_type": "TimeoutError"
}
```

The executable path exists and the process can be launched with a normal Windows environment, but the Python API did not observe the HTTP communication port opening within 60 seconds.

The smoke script records this as:

```text
virtualhome_simulator_connection_timeout
```

## Artifacts Not Generated

Because the simulator did not open the communication port:

- `scene_graph.json` was not generated.
- `program_log.json` was not generated.
- `converted_world_model.json` was not generated.
- `converted_episode_log.jsonl` was not generated.
- `frame_000.png` was not generated.

## Likely Next Step

The VirtualHome README indicates that the desktop executable may require a user to select Windowed mode and press Play. A future retry should:

1. Start `VirtualHome.exe` manually.
2. Select Windowed mode if prompted.
3. Press Play.
4. Rerun:

```powershell
$env:VIRTUALHOME_REPO_PATH="<external-tools>\virtualhome"
$env:VIRTUALHOME_SIMULATOR_PATH="<external-tools>\virtualhome_simulator\windows_exec\windows_exec.v2.3.0\VirtualHome.exe"
python tools/test_virtualhome_windows_spike.py
```

Until scene graph and program execution artifacts are generated, VirtualHome remains an optional simulator spike rather than a validated backend.


