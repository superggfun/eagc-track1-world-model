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
$env:VIRTUALHOME_REPO_PATH = "C:\Users\Alphay\Documents\ExternalTools\virtualhome"
$env:VIRTUALHOME_SIMULATOR_PATH = "C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\<actual_exe_name>.exe"
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
python tools/check_local_gpu_runtime.py
```

Optional lightweight vLLM endpoint check:

```powershell
python tools/check_vllm_endpoint.py --base-url http://127.0.0.1:8000/v1
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
- VirtualHome-only simulator execution did not start because the Python API and executable path are missing.
- `scene_graph.json` was not generated.
- `program_log.json` was not generated.
- No camera frame was saved.

Current `status.json` reason:

```text
missing_virtualhome_python_api
```

Latest v0.14.3 local probe on 2026-06-11:

- Common local repository locations were checked:
  - `C:\Users\Alphay\Documents\VirtualHome`
  - `C:\Users\Alphay\Documents\virtualhome`
  - `C:\Users\Alphay\Downloads\virtualhome`
  - `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
- No local VirtualHome repository exposing `simulation.unity_simulator.comm_unity` was found.
- `VIRTUALHOME_REPO_PATH` is not configured to a usable repository.
- No Windows VirtualHome Unity simulator `.exe` was found under the recommended external simulator folder.
- `VIRTUALHOME_SIMULATOR_PATH` and `config.yaml` `virtualhome.simulator_path` are still empty.
- `python tools/setup_virtualhome_hint.py` now writes `outputs/virtualhome_spike/setup_hint.json` with candidate repo paths, candidate simulator paths, and exact PowerShell environment variable examples.
- `python tools/check_virtualhome_env.py` still reports `missing_virtualhome_python_api`.
- `python tools/test_virtualhome_windows_spike.py` still exits gracefully with `success=false` and `reason=missing_virtualhome_python_api`.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passes because the missing dependency is explicit and auditable.
- Since the simulator did not start, no real `scene_graph.json`, `program_log.json`, `frame_000.png`, `converted_world_model.json`, or `converted_episode_log.jsonl` was generated in this run.

Current v0.14.3 readiness assessment:

- Repo path configured: no.
- Simulator path configured: no.
- Python API import: no.
- Executable exists: no.
- Scene graph acquired: no.
- Action program executed: no.
- Converted world model / episode log generated: no.
- Recommendation: do not enter v0.14.4 VirtualHome to world-model integration until a local VirtualHome repo and Windows Unity simulator executable are provided outside this EAGC project tree.

v0.15.3 refresh:

- VirtualHome remains diagnostics/setup-readiness only.
- No real Windows executable smoke has succeeded.
- No VirtualHome scene graph, program log, frame, or converted world model should be described as validated.
- VirtualHome is not included in fast, targeted, standard, or full submission gates.

Local RTX 5090 runtime note:

- The workstation has one RTX 5090 32GB GPU.
- `python tools/check_local_gpu_runtime.py` recorded approximately 31,768 MiB used and 420 MiB free during the latest probe.
- The original long-context vLLM profile can leave very little free VRAM and should not be used for VirtualHome coexistence testing.
- `python tools/check_local_gpu_runtime.py` records the current GPU and process state to `outputs/local_runtime_check/gpu_status.txt`.
- If a coexistence test is attempted later, use a separate lightweight vLLM profile with a shorter context and lower memory utilization. See `docs/local_vllm_lightweight_profile.md`.
- If memory remains insufficient, use time-sliced operation: run VirtualHome first to generate scene graph/log/frame artifacts, then run Qwen/vLLM post-processing afterward.

VirtualHome + vLLM coexistence status:

- Not run in the latest probe because VirtualHome-only smoke did not reach simulator startup.
- The original 262K-context vLLM container should not be used for coexistence testing.
- A future coexistence test should first validate VirtualHome-only, then use `python tools/check_vllm_endpoint.py --base-url ...` and `python tools/test_virtualhome_vllm_coexistence.py` with a lightweight endpoint.

Required user-provided artifacts before a real smoke can run:

1. A local VirtualHome repository or installed Python API exposing `simulation.unity_simulator.comm_unity`.
2. A Windows VirtualHome Unity simulator executable path, provided via `VIRTUALHOME_SIMULATOR_PATH` or `config.yaml`.

Do not commit the executable, Unity assets, frames, videos, or other large simulator artifacts.

v0.16 real-smoke preparation:

- External directories are expected outside this repository:
  - `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
  - `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator`
- If the repository is missing, manually clone it outside the EAGC project:

```powershell
git clone https://github.com/xavierpuigf/virtualhome.git C:\Users\Alphay\Documents\ExternalTools\virtualhome
```

- If the Windows Unity simulator executable is missing, download it manually according to the official VirtualHome documentation and set:

```powershell
$env:VIRTUALHOME_REPO_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome"
$env:VIRTUALHOME_SIMULATOR_PATH="C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\<actual_exe_name>.exe"
```

- The v0.16 smoke remains VirtualHome-only: it does not call Qwen, does not start lightweight vLLM, and does not modify the existing long-context vLLM Docker container.
- A successful real smoke must produce `scene_graph.json`, `program_log.json`, and converted world-model artifacts. If the repo/API or executable is missing, the scripts must report a blocker in `status.json` rather than fabricate success.

Latest v0.16 local probe on 2026-06-11:

- External directories were created outside the EAGC project:
  - `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
  - `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator`
- `C:\Users\Alphay\Documents\ExternalTools\virtualhome` exists, but it is currently empty or otherwise not a VirtualHome repository exposing `simulation/unity_simulator/comm_unity.py`.
- `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator` exists, but no Windows Unity simulator `.exe` was found.
- `python tools/setup_virtualhome_hint.py` completed and now prints the external clone command and PowerShell environment variable examples.
- `python tools/check_virtualhome_env.py` completed and wrote `outputs/virtualhome_spike/env_status.json`.
- `python_api_import_success=false`.
- `simulator_executable_exists=false`.
- `python tools/test_virtualhome_windows_spike.py` completed gracefully with `success=false` and `reason=missing_virtualhome_python_api`.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passed because the missing dependency is explicit and auditable.
- The simulator did not start.
- Scene graph acquired: no.
- Action program executed: no.
- Converted world model / episode log generated: no.
- Frame saved: no.
- Recommendation: provide the real VirtualHome repo/API and Windows Unity executable outside the project tree before retrying real smoke.

Latest v0.16.1 local probe on 2026-06-11:

- The official VirtualHome repository was cloned outside the EAGC project:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome`
- The repository exposes `virtualhome/simulation/unity_simulator/comm_unity.py`.
- VirtualHome dependencies were installed from `virtualhome/requirements.txt`.
- Python API import succeeded:
  `from simulation.unity_simulator import comm_unity`
- The official Windows simulator archive was downloaded from the VirtualHome README link:
  `http://virtual-home.org//release/simulator/v2.0/v2.3.0/windows_exec.zip`
- The archive was extracted outside the EAGC project under:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator`
- The selected executable is:
  `C:\Users\Alphay\Documents\ExternalTools\virtualhome_simulator\windows_exec\windows_exec.v2.3.0\VirtualHome.exe`
- `python tools/check_virtualhome_env.py` completed with:
  - `python_api_import_success=true`
  - `simulator_executable_exists=true`
- `python tools/test_virtualhome_windows_spike.py` reached runtime launch/connection but did not retrieve a scene graph.
- The project smoke script works around a Windows launcher issue in the upstream VirtualHome API, where the launcher uses an empty environment and raises WinError 87. With a normal inherited environment, the executable process can be launched.
- The launched executable did not open the API HTTP port within 60 seconds.
- Final `status.json` reason:

```text
virtualhome_simulator_connection_timeout
```

- Manual start hint recorded in `status.json`: start `VirtualHome.exe` manually, choose Windowed mode if prompted, press Play, then rerun the smoke.
- Scene graph acquired: no.
- Program log generated: no.
- Converted world model / episode log generated: no.
- Frame saved: no.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passed because this runtime blocker is explicit and auditable.

Dependency warning:

- Installing VirtualHome requirements in the user Python environment downgraded `networkx` to `2.3`.
- Pip reported compatibility warnings for packages expecting newer `networkx`, including `torch` and `scikit-image`.
- Future work should isolate VirtualHome in a dedicated virtual environment if it becomes more than a one-off simulator spike.

Latest v0.16.2 manual-play probe on 2026-06-11:

- User manually started `VirtualHome.exe`, selected Windowed mode, and pressed Play.
- Port `8080` was detected as listening before the smoke run.
- The smoke script connected to the already-running simulator instead of launching a second process.
- `python tools/check_virtualhome_env.py` passed.
- `python tools/test_virtualhome_windows_spike.py` completed successfully.
- `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json` passed.
- Scene graph saved: yes.
- Program log saved: yes.
- Simple household program executed successfully:

```text
<char0> [Walk] <sofa> (1)
<char0> [Sit] <sofa> (1)
```

- Converted world model saved: yes.
- Converted episode log saved: yes.
- Converted object count: 440.
- Frame saved: no. Camera frame export remains optional and was not validated in this run.
- The real VirtualHome smoke is now validated in manual-play mode, but automated simulator startup is still not validated.

Latest v0.16.3 manual-play regression probe on 2026-06-11:

- The manual-play route was promoted to an optional test suite tier:
  `python tools/run_test_suite.py --tier targeted-virtualhome-manual`
- The tier first checks whether `127.0.0.1:8080` is listening.
- If the port is not listening, the tier writes `outputs/virtualhome_spike/manual_suite_status.json`, reports `virtualhome_manual_play_port_not_open`, and exits as a graceful skip.
- If the port is listening, it runs:
  - `python tools/check_virtualhome_env.py`
  - `python tools/test_virtualhome_windows_spike.py`
  - `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json`
  - `python -m validators.validate_virtualhome_converted_world_model outputs/virtualhome_spike/converted_world_model.json outputs/virtualhome_spike/converted_episode_log.jsonl`
- The smoke now runs four fixed household tasks:
  - `walk_to_and_sit_on_sofa`
  - `walk_to_and_grab_object`
  - `walk_to_and_open_object`
  - `place_object_on_surface`
- Latest run result:
  - task success count: 4
  - task failed count: 0
  - task unsupported count: 0
  - converted object count: 440
  - scene graph saved: yes
  - program log saved: yes
  - converted world model saved: yes
  - converted episode log saved: yes
  - frame saved: no
- The converted world-model quality validator checks non-empty objects, rooms or uncertainty, relations, source, episode id, and episode log action/result content.
- VirtualHome is now validated as a manual-play Windows simulator smoke, but it is still not an automated backend and still does not replace official EAGC runtime validation.

Latest v0.16.4 frame export and visual-symbolic evidence probe on 2026-06-11:

- The frame path is now an optional manual-play tier:
  `python tools/run_test_suite.py --tier targeted-virtualhome-frame`
- The tier first checks whether `127.0.0.1:8080` is listening.
- If the port is not listening, it writes `outputs/virtualhome_spike/frame_suite_status.json`, reports `virtualhome_manual_play_port_not_open`, and exits as a graceful skip.
- If the port is listening, it runs:
  - `python tools/test_virtualhome_windows_spike.py --export-frame`
  - `python -m validators.validate_virtualhome_spike outputs/virtualhome_spike/status.json`
  - `python -m validators.validate_virtualhome_converted_world_model outputs/virtualhome_spike/converted_world_model.json outputs/virtualhome_spike/converted_episode_log.jsonl`
  - `python -m validators.validate_virtualhome_frame_export outputs/virtualhome_spike/frame_export_status.json`
  - `python tools/build_virtualhome_evidence_report.py`
- Frame export uses the documented VirtualHome camera API:
  - `camera_count()`
  - `camera_image([camera_index], mode="normal", image_width=640, image_height=480)`
- Runtime artifacts:
  - `outputs/virtualhome_spike/frame_000.png` if frame export succeeds
  - `outputs/virtualhome_spike/frame_export_status.json`
  - `outputs/virtualhome_spike/visual_symbolic_evidence_report.json`
  - `outputs/virtualhome_spike/visual_symbolic_evidence_report.md`
- Latest run result:
  - frame export: success
  - frame dimensions: 640x480
  - camera index: 86 of 87 cameras
  - task success count: 4
  - task failed count: 0
  - scene graph object count: 444
  - scene graph relation count: 932
  - converted world-model object count: 440
  - converted world-model relation count: 932
- The evidence report compares symbolic state and optional visual observation metadata:
  - scene graph object/relation counts
  - converted world-model object/relation counts
  - executed/successful task counts
  - frame availability and dimensions if available
- v0.16.4 still does not call Qwen vision, does not start lightweight vLLM, and does not perform official EAGC runtime validation.
- If frame export fails, the failure is captured as `virtualhome_frame_api_unavailable`, `virtualhome_camera_not_configured`, `virtualhome_frame_export_timeout`, or `virtualhome_frame_export_unsupported`; the existing scene graph/program pipeline remains valid.

## Assessment Criteria

VirtualHome becomes a useful Windows-friendly household simulator candidate if:

- the Windows Unity executable launches reliably,
- scene graph extraction works,
- simple household programs execute,
- optional camera frames can be saved,
- generated scene graph / frame artifacts can be converted into the existing world model and visual pipeline.

Until those conditions are met, VirtualHome remains an optional simulator spike rather than a main backend.

VirtualHome is still only a Windows-friendly household activity simulator candidate. It is useful to explore scene graphs, household programs, and possible visual frames, but this project does not claim it fully replaces ProcTHOR, Habitat, AI2-THOR, or the future official EAGC Track 1 runtime.
