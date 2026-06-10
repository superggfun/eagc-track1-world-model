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
conda create -n habitat python=3.9
conda activate habitat
conda install habitat-sim -c conda-forge -c aihabitat
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
python tools/test_habitat_sim_spike.py
python tools/test_habitat_lab_spike.py
```

If a local scene is available:

```powershell
python tools/test_habitat_sim_spike.py --scene-path data/scene_datasets/example.glb
```

## Latest Results

| Check | Result | Notes |
|---|---|---|
| `habitat_sim` import | failed gracefully | `ModuleNotFoundError: No module named 'habitat_sim'` in `outputs/habitat_spike/habitat_env_status.json`. |
| Habitat-Lab `habitat` import | failed gracefully | `ModuleNotFoundError: No module named 'habitat'` in both env and lab status files. |
| Scene assets | missing | No `data/scene_datasets/` directory and no `.glb` / `.ply` / `.obj` scene files found. |
| Minimal scene load | not attempted | Blocked before simulator creation because no scene asset is available. |
| RGB observation | not available | No simulator was created; `rgb.png` was not generated. |
| Simple action | not available | No simulator was created, so no action step was executed. |

Generated status files:

```text
outputs/habitat_spike/habitat_env_status.json
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

1. Habitat packages are not installed in the active project Python environment.
2. No local Habitat scene assets are present under `data/scene_datasets/`.
3. Because the above prerequisites are missing, RGB/depth observation and action stepping were not evaluated.

## Recommendation

Habitat is not yet validated on this machine because the active environment lacks both packages and scene assets. Unlike the AI2-THOR spike, this run did not reach a renderer crash or Unity hang; it stopped cleanly at missing prerequisites.

Recommended next steps:

1. Install Habitat in a separate conda/mamba environment, preferably WSL2 or native Linux rather than the main Windows project environment.
2. Add a minimal legal scene asset under `data/scene_datasets/` or pass it with `--scene-path`.
3. Re-run:

   ```powershell
   python tools/check_habitat_env.py
   python tools/test_habitat_sim_spike.py --scene-path data/scene_datasets/<scene>.glb
   python tools/test_habitat_lab_spike.py
   ```

4. If `habitat_sim` can save `rgb.png` and execute a simple action, proceed to a small Habitat adapter smoke test.
5. If Habitat install/rendering is blocked locally, use a remote/native Linux GPU host.

Current direction assessment:

- Habitat remains a plausible public simulator direction, but it requires separate environment setup and scene assets before it can be compared fairly with AI2-THOR.
- For near-term EAGC Track 1 work, keep LocalSim and visual-local hybrid as the stable baseline.
- Do not add Habitat to `requirements.txt` or the standard test tiers until the minimal sim spike succeeds.
