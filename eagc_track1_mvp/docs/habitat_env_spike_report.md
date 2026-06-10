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
- The isolated `habitat` conda environment was created successfully at `C:\Users\Alphay\.conda\envs\habitat`.
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

## Latest Results

| Check | Result | Notes |
|---|---|---|
| Separate conda env | created | `habitat` env exists and uses Python 3.9.25. |
| `habitat-sim` install | failed | No `win-64` package was available from configured conda channels. |
| `habitat_sim` import | failed gracefully | `ModuleNotFoundError: No module named 'habitat_sim'` in `outputs/habitat_spike/habitat_env_status.json`. |
| Habitat-Lab `habitat` import | failed gracefully | `ModuleNotFoundError: No module named 'habitat'` in env status. |
| `habitat_test_scenes` download | failed gracefully | Blocked because `habitat_sim` is unavailable. |
| Scene assets | missing | No `data/scene_datasets/` directory and no `.glb` / `.ply` / `.obj` scene files found. |
| Minimal scene load | not attempted | Blocked before simulator creation because no package and no scene asset are available. |
| RGB observation | not available | No simulator was created; `rgb.png` was not generated. |
| Simple action | not available | No simulator was created, so no action step was executed. |

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
3. No local Habitat scene assets are present under `data/scene_datasets/`.
4. Because the package and scene prerequisites are missing, RGB/depth observation and action stepping were not evaluated.

## Recommendation

Habitat is not yet validated on this machine because the Windows conda route did not provide a usable `habitat-sim` package and no test scene assets were downloaded. Unlike the AI2-THOR spike, this run did not reach a renderer crash or Unity hang; it stopped cleanly at missing prerequisites.

Recommended next steps:

1. Retry Habitat in a separate WSL2/native Linux/remote Linux GPU conda environment rather than Windows `win-64`.
2. Install `habitat-sim` there using the official Habitat-Sim channel guidance.
3. Download the lightweight `habitat_test_scenes` into the ignored local `data/` directory:

   ```bash
   python tools/download_habitat_test_scenes.py
   ```

4. Add a minimal legal scene asset under `data/scene_datasets/` or pass it with `--scene-path`.
5. Re-run:

   ```powershell
   python tools/check_habitat_env.py
   python tools/test_habitat_sim_spike.py --scene-path data/scene_datasets/<scene>.glb
   python tools/test_habitat_lab_spike.py
   ```

6. If `habitat_sim` can save `rgb.png` and execute a simple action, proceed to a small Habitat adapter smoke test.
7. If Habitat install/rendering remains blocked locally, use a remote/native Linux GPU host.

Do not add Habitat to `requirements.txt`, the main Docker image, or the standard test tiers until the minimal sim spike succeeds.

Current direction assessment:

- Habitat remains a plausible public simulator direction, but this Windows machine has not yet reached the rendering layer.
- The most likely viable next route is WSL2 or native/remote Linux GPU with conda packages and official test scenes.
- For near-term EAGC Track 1 work, keep LocalSim and visual-local hybrid as the stable baseline.
- `data/`, scene files, and generated outputs are ignored and must not be committed.
