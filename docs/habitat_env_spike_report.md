# Habitat Environment Spike Report

This document records the v0.13 Habitat / Habitat-Sim / Habitat-Lab environment spike.

Scope:

- This is an optional environment diagnostic spike.
- This is not a full Habitat adapter.
- This does not modify the EAGC agent main system logic.
- This does not train models.
- This does not debug AI2-THOR or ProcTHOR.
- This does not modify, restart, or manage the local Qwen vLLM Docker container.
- Habitat diagnostics are not included in `fast`, `targeted`, `standard`, or `full` test tiers.

## Current Machine Environment

Environment details are collected by:

```powershell
python tools/check_habitat_env.py
```

The status file is written to:

```text
outputs/habitat_spike/habitat_env_status.json
```

Observed fields include:

- OS and Python version
- Windows / WSL / Docker detection
- CUDA / `nvidia-smi` availability
- `habitat_sim` import status
- `habitat` / Habitat-Lab import status
- common data directory availability
- `HABITAT_SIM_LOG` and `MAGNUM_LOG`

Observed on 2026-06-10 from the active Windows project environment:

- OS: Windows 10.0.26200, AMD64.
- Python: 3.11.1 at `C:\Program Files\Python\Python311\python.exe`.
- GPU: NVIDIA GeForce RTX 5090 visible through `nvidia-smi`.
- CUDA compiler: `nvcc` available, CUDA 12.8.
- WSL/Docker: not used for this Habitat spike run.
- Habitat environment variables: `HABITAT_SIM_LOG` and `MAGNUM_LOG` not set.
- `habitat_sim`: not installed in the active Python environment.
- Habitat-Lab `habitat`: not installed in the active Python environment.
- Local scene/data directories: `data/`, `data/scene_datasets/`, `data/datasets/`, and `habitat-lab/data/` are missing.

## Installation Strategy

Habitat dependencies are not added to the main project `requirements.txt`.

Recommended separate environment:

```bash
conda create -n habitat python=3.9 cmake=3.14.0
conda activate habitat
conda install habitat-sim withbullet headless -c conda-forge -c aihabitat
# Optional later, only after Habitat-Sim is available:
pip install habitat-lab
```

If conda/mamba is unavailable, use a separate venv only for diagnostics and record any installation limitations.

## Diagnostic Commands

Run the main project regression first:

```powershell
python -m compileall .
python tools/run_test_suite.py --tier fast
```

Then run Habitat diagnostics:

```powershell
python tools/check_habitat_env.py
python tools/download_habitat_test_scenes.py
python tools/test_habitat_sim_spike.py
python tools/test_habitat_lab_spike.py
```

If a local scene is available:

```powershell
python tools/test_habitat_sim_spike.py --scene-path data/scene_datasets/example.glb
```

## v0.13.1 Separate Environment Attempt

The v0.13.1 follow-up used a separate conda environment rather than the main project Python environment.

Commands attempted:

```powershell
conda create -n habitat python=3.9 cmake=3.14.0 -y
conda install -n habitat habitat-sim withbullet headless -c conda-forge -c aihabitat -y
conda run -n habitat python tools/check_habitat_env.py
conda run -n habitat python tools/download_habitat_test_scenes.py
conda run -n habitat python tools/test_habitat_sim_spike.py
```

Observed results on 2026-06-10:

- `conda` is available: `conda 25.11.1`.
- `mamba` is not available.
- The isolated `habitat` conda environment was created successfully at `<conda-envs>\habitat`.
- Python inside the isolated environment is `3.9.25`.
- Installing `habitat-sim` from `conda-forge` / `aihabitat` on Windows `win-64` failed with `PackagesNotFoundError`.
- `nvidia-smi` is available and reports NVIDIA GeForce RTX 5090.
- `nvcc` is available and reports CUDA 12.8.
- `habitat_sim` is not importable inside the isolated environment.
- Habitat-Lab `habitat` is not importable inside the isolated environment.
- `habitat_test_scenes` download did not run because `habitat_sim` is missing.
- No scene files were found under `data/scene_datasets/`.
- The minimal sim spike wrote a graceful failure status with `reason="missing_scene_assets"`.
- No RGB observation was generated.
- No simple simulator action was executed.

Important failure excerpt:

```text
PackagesNotFoundError: The following packages are not available from current channels:
  - habitat-sim
Platform: win-64
Current channels:
  - conda-forge
  - aihabitat
  - defaults
```

Generated status files:

```text
outputs/habitat_spike/habitat_env_status.json
outputs/habitat_spike/download_status.json
outputs/habitat_spike/status.json
outputs/habitat_spike/habitat_sim_status.json
```

The scripts behaved as intended: failure was recorded as structured JSON instead of being treated as a fake pass.

## v0.13.2 WSL2 Attempt

The v0.13.2 follow-up attempted to move the Habitat-Sim test-scene smoke from Windows `win-64` to WSL2 Ubuntu / Linux.

Commands run from Windows PowerShell:

```powershell
wsl -l -v
wsl bash -lc "uname -a"
wsl bash -lc "nvidia-smi"
wsl bash -lc "command -v conda || true; command -v mamba || true"
```

Observed WSL2 environment:

- WSL distribution: `Ubuntu-24.04`
- WSL version: `2`
- Kernel: `6.6.87.2-microsoft-standard-WSL2`
- Architecture: `x86_64`
- GPU visibility: `nvidia-smi` works inside WSL2 and reports NVIDIA GeForce RTX 5090.
- WSL display variables: `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`.
- `conda`: not available in WSL2.
- `mamba`: not available in WSL2.

Because conda/mamba is unavailable in WSL2, no Habitat conda environment was created. The main project Python environment was not modified. To keep the spike auditable, the diagnostic scripts were run with WSL's default Python:

```bash
cd "<repo-root>"
python3 tools/check_habitat_env.py
python3 tools/download_habitat_test_scenes.py
python3 tools/test_habitat_sim_spike.py
```

Observed WSL2 diagnostic results:

- Python: `3.12.3` at `/usr/bin/python3`.
- `habitat_sim`: not importable.
- Habitat-Lab `habitat`: not importable.
- `nvcc`: not available in WSL2 default PATH.
- `data/scene_datasets/`: missing.
- `habitat_test_scenes`: not downloaded because `habitat_sim` is missing.
- RGB observation: not generated.
- Simple simulator action: not executed.

Generated WSL2 status files:

```text
outputs/habitat_spike/habitat_env_status.json
outputs/habitat_spike/download_status.json
outputs/habitat_spike/status.json
```

The WSL2 attempt therefore did not reach the Habitat rendering layer. The immediate blocker is missing conda/mamba in WSL2, not a Habitat renderer crash.

## v0.13.3 WSL2 Miniforge / Habitat-Sim RGB Smoke

The v0.13.3 follow-up installed Miniforge/Mamba inside WSL2 and retried Habitat-Sim on Linux `x86_64`.

Commands executed:

```powershell
wsl bash -lc "curl -L --fail -o /tmp/Miniforge3-Linux-x86_64.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
wsl bash -lc "bash /tmp/Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3"
wsl bash -lc "source ~/miniforge3/etc/profile.d/conda.sh && mamba create -n habitat python=3.9 cmake=3.14.0 -y"
wsl bash -lc "source ~/miniforge3/etc/profile.d/conda.sh && conda activate habitat && mamba install habitat-sim withbullet headless -c conda-forge -c aihabitat -y"
```

Observed installation results:

- Miniforge installed successfully under `~/miniforge3`.
- `mamba` is available from the Miniforge base environment.
- The isolated `habitat` environment was created successfully.
- `habitat-sim` installed successfully from `aihabitat` / `conda-forge`.
- Installed Habitat-Sim version: `0.3.3`.
- Initial import failed because `libOpenGL.so.0` was missing.
- Installing `libopengl` into the isolated conda environment fixed the import:

  ```bash
  mamba install -y -c conda-forge libopengl
  ```

Validation commands:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate habitat
python tools/check_habitat_env.py
python tools/download_habitat_test_scenes.py
python tools/test_habitat_sim_spike.py
```

Observed diagnostic results:

- `tools/check_habitat_env.py`: `habitat_sim` import succeeded, version `0.3.3`.
- Habitat-Lab `habitat` is still not installed; this is expected because this spike only targets Habitat-Sim.
- `nvidia-smi` is available inside WSL2.
- `habitat_test_scenes` downloaded successfully.
- Scene files found:
  - `apartment_1.glb`
  - `skokloster-castle.glb`
  - `van-gogh-room.glb`
  - `van-gogh-room.mesh.ply`
- The downloader wrapper now skips repeated downloads when scene files already exist, avoiding Habitat-Sim's interactive replacement prompt.
- The RGB smoke selected `apartment_1.glb`.
- Habitat-Sim reached the headless EGL context creation step but failed before rendering:

  ```text
  Platform::WindowlessEglApplication::tryCreateContext(): unable to find CUDA device 0 among 1 EGL devices in total
  WindowlessContext: Unable to create windowless context
  ```

- `outputs/habitat_spike/status.json` was written by the parent process with:
  - `success=false`
  - `error_type=WorkerProcessFailed`
  - `reason=worker_process_failed`
  - `rgb_saved=false`
  - `action_step_success=false`

Script robustness changes:

- `tools/test_habitat_sim_spike.py` now runs Habitat-Sim in a worker subprocess by default.
- If the C++/EGL layer exits the worker before Python can catch an exception, the parent process still writes `status.json`.
- The smoke script now attempts a minimal action step and records `action_step_success`, `rgb_step_path`, and `step_frame_shape` when rendering succeeds.
- `tools/download_habitat_test_scenes.py` now follows symlinks and scans both `data/scene_datasets/` and `data/versioned_data/`.

The v0.13.3 result is therefore a partial success: Habitat-Sim installation and official test-scene acquisition work in WSL2, but RGB rendering is still blocked by WSL2 headless EGL / CUDA device mapping.

## Remote RTX 4090 Linux Smoke

On 2026-06-11, a remote RTX 4090 Linux host was used for an additional public simulator smoke test.

Remote machine summary:

- OS: Ubuntu 22.04.4 LTS.
- Kernel: `5.19.0-50-generic`.
- GPU: NVIDIA GeForce RTX 4090.
- NVIDIA driver / CUDA from `nvidia-smi`: `550.144.03` / CUDA `12.4`.
- Docker: not available on the remote PATH.
- `nvcc`: not available on the remote PATH.
- Python: system `python3` is available; plain `python` was initially absent before Miniforge.
- Results archive: `outputs/remote_simulator_results.tar.gz` locally, ignored by git.

Habitat-Sim setup on the remote host:

- Miniforge was installed under `/root/miniforge3`.
- A separate conda environment `habitat` was created.
- `habitat-sim` installed successfully from `aihabitat` / `conda-forge`.
- `habitat_sim` imports successfully, version `0.3.3`.
- `nvidia-smi` is available from inside the Habitat environment.
- `libEGL` was required in addition to the base Habitat-Sim package stack.
- Official `habitat_test_scenes` were made available under ignored `data/` paths.

Remote Habitat-Sim smoke result:

- `habitat_test_scenes` available: yes.
- Scene file count: 8.
- Selected scene: `apartment_1.glb`.
- RGB smoke success: no.
- `rgb.png` saved: no.
- Action step success: no.
- Failure reason:

  ```text
  Platform::WindowlessEglApplication::tryCreateContext(): cannot get default EGL display: EGL_BAD_PARAMETER
  WindowlessContext: Unable to create windowless context
  ```

Conclusion:

- Remote Ubuntu RTX 4090 validates Habitat-Sim install/import and test-scene availability.
- Remote Ubuntu RTX 4090 Habitat-Sim RGB smoke did not succeed.
- The remaining blocker is renderer/EGL configuration, not Python package installation.
- As with AI2-THOR, `nvidia-smi` confirms CUDA compute visibility, but that does not guarantee headless EGL rendering or NVIDIA graphics ICD availability.

## Latest Results

| Check | Result | Notes |
|---|---|---|
| Separate conda env | created | `habitat` env exists and uses Python 3.9.25. |
| `habitat-sim` install | failed | No `win-64` package was available from configured conda channels. |
| WSL2 Ubuntu | available | `Ubuntu-24.04` is running as WSL2 and can see the RTX 5090 through `nvidia-smi`. |
| WSL2 Miniforge/Mamba | installed | Miniforge installed under `~/miniforge3`; mamba available. |
| WSL2 `habitat` env | created | Python 3.9 conda env created outside the main project environment. |
| WSL2 `habitat-sim` install | succeeded | `habitat_sim` import succeeded after adding `libopengl`; version `0.3.3`. |
| Habitat-Lab `habitat` import | not installed | Expected for this spike; Habitat-Lab was not required. |
| `habitat_test_scenes` download | succeeded | Scene files are present under ignored `data/` paths. |
| Scene assets | available | Test scenes include `apartment_1.glb`, `skokloster-castle.glb`, and `van-gogh-room.glb`. |
| Minimal scene load | failed in renderer | Worker reached EGL context creation and failed with CUDA/EGL device mapping error. |
| RGB observation | failed | `rgb.png` was not generated. |
| Simple action | failed | No action frame was generated because renderer initialization failed. |
| Remote RTX 4090 Habitat install/import | succeeded | Ubuntu 22.04 remote host imports `habitat_sim 0.3.3`. |
| Remote RTX 4090 test scenes | available | Official lightweight scenes are present under ignored `data/` paths. |
| Remote RTX 4090 RGB smoke | failed in renderer | Headless EGL failed with `EGL_BAD_PARAMETER`; no `rgb.png` was generated. |

Generated status files:

```text
outputs/habitat_spike/habitat_env_status.json
outputs/habitat_spike/download_status.json
outputs/habitat_spike/status.json
outputs/habitat_spike/habitat_sim_status.json
outputs/habitat_spike/habitat_lab_status.json
```

## Failure Reasons

Common expected failure modes:

- `habitat_sim` is not installed in the active Python environment.
- Habitat-Lab is not installed in the active Python environment.
- No local scene assets exist under `data/scene_datasets/`.
- GPU or graphics backend is unavailable.
- Habitat package versions are incompatible with the active Python version.

Observed failure reasons in this run:

1. Habitat packages are not installed in the active project Python environment, by design.
2. The isolated Windows conda environment could be created, but `habitat-sim` was unavailable for `win-64` from the configured channels.
3. WSL2 Ubuntu is available and GPU-visible.
4. WSL2 Miniforge/Mamba and `habitat-sim` installation now work.
5. Official lightweight scene assets are present under ignored `data/` paths.
6. RGB/depth observation and action stepping are blocked by WSL2 headless EGL / CUDA device mapping:

   ```text
   Platform::WindowlessEglApplication::tryCreateContext(): unable to find CUDA device 0 among 1 EGL devices in total
   WindowlessContext: Unable to create windowless context
   ```
7. On the remote RTX 4090 Ubuntu host, install/import and scene availability succeed, but headless EGL still fails:

   ```text
   Platform::WindowlessEglApplication::tryCreateContext(): cannot get default EGL display: EGL_BAD_PARAMETER
   WindowlessContext: Unable to create windowless context
   ```

## Recommendation

Habitat is not yet fully validated. The Windows conda route did not provide a usable `habitat-sim` package. The WSL2 route installs and imports Habitat-Sim and downloads official test scenes, but headless RGB rendering fails at EGL context creation. The remote RTX 4090 Ubuntu route also installs/imports Habitat-Sim and has test scenes available, but RGB rendering fails at headless EGL display creation. CUDA compute visibility is therefore not sufficient evidence that the simulator rendering stack is ready.

Recommended next steps:

1. Treat WSL2 Habitat-Sim as partially validated: install/import/data acquisition work; rendering does not yet.
2. For the next rendering attempt, test one of:
   - WSL2 EGL device configuration / `EGL_DEVICE_ID` style environment controls.
   - Remote/native Linux EGL/OpenGL package configuration.
   - A Docker GPU route with known-good EGL/OpenGL libraries.
3. Re-run:

   ```powershell
   python tools/check_habitat_env.py
   python tools/download_habitat_test_scenes.py
   python tools/test_habitat_sim_spike.py
   ```

4. If `habitat_sim` can save `rgb.png` and execute a simple action, proceed to a small Habitat adapter smoke test.
5. If WSL2 rendering remains blocked locally, use a remote/native Linux GPU host.

Do not add Habitat to `requirements.txt`, the main Docker image, or the standard test tiers until the minimal sim spike succeeds.

Current direction assessment:

- Habitat remains a plausible public simulator direction, but this Windows machine has not yet reached the rendering layer.
- WSL2 has now reached the rendering layer and fails specifically at headless EGL context creation.
- Remote Ubuntu RTX 4090 has also reached the rendering layer and fails specifically at headless EGL context creation.
- The most likely viable next route is a simulator-ready Ubuntu image, a native Linux GPU host with NVIDIA EGL/OpenGL/Vulkan ICDs correctly exposed, or a Docker GPU image with known-good headless rendering support.
- For near-term EAGC Track 1 work, keep LocalSim and visual-local hybrid as the stable baseline.
- `data/`, scene files, and generated outputs are ignored and must not be committed.

