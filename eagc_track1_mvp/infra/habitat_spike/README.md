# Habitat Environment Spike

This directory documents an optional Habitat / Habitat-Sim / Habitat-Lab environment spike. It is intentionally separate from the main EAGC Track 1 LocalSim MVP and is not part of `fast`, `targeted`, `standard`, or `full` test tiers.

The spike should use a separate Python environment. Do not add Habitat dependencies to the main project `requirements.txt` unless the project later commits to a Habitat adapter.

## Recommended Separate Environment

Habitat packages are commonly easier to install in a conda or mamba environment:

```bash
conda create -n habitat python=3.9 cmake=3.14.0
conda activate habitat
conda install habitat-sim withbullet headless -c conda-forge -c aihabitat
```

If Habitat-Lab is needed for a later spike:

```bash
pip install habitat-lab
```

If conda is unavailable, record that in `docs/habitat_env_spike_report.md` and avoid polluting the main project environment. Do not install Habitat packages into the main EAGC project Python environment.

## Diagnostics

From the project root:

```bash
python tools/check_habitat_env.py
python tools/download_habitat_test_scenes.py
python tools/test_habitat_sim_spike.py
python tools/test_habitat_lab_spike.py
```

Expected status files:

```text
outputs/habitat_spike/habitat_env_status.json
outputs/habitat_spike/download_status.json
outputs/habitat_spike/status.json
outputs/habitat_spike/habitat_lab_status.json
```

The scripts are diagnostic. Missing packages or missing scene assets should be reported as structured `success=false` status rather than treated as a fake pass.

## Scene Assets

`tools/test_habitat_sim_spike.py` looks for scene files under:

```text
data/scene_datasets/
```

Supported minimal scene suffixes:

- `.glb`
- `.ply`
- `.obj`

Do not download large datasets automatically from these scripts.

The only dataset helper added for this spike downloads the official lightweight Habitat test scenes:

```bash
python tools/download_habitat_test_scenes.py
```

Internally this runs:

```bash
python -m habitat_sim.utils.datasets_download --uids habitat_test_scenes --data-path data/
```

The downloaded `data/` directory is ignored by git.
