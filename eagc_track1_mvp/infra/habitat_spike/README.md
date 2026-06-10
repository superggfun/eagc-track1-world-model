# Habitat Environment Spike

This directory documents an optional Habitat / Habitat-Sim / Habitat-Lab environment spike. It is intentionally separate from the main EAGC Track 1 LocalSim MVP and is not part of `fast`, `targeted`, `standard`, or `full` test tiers.

The spike should use a separate Python environment. Do not add Habitat dependencies to the main project `requirements.txt` unless the project later commits to a Habitat adapter.

## Recommended Separate Environment

Habitat packages are commonly easier to install in a conda or mamba environment:

```bash
conda create -n habitat python=3.9
conda activate habitat
conda install habitat-sim -c conda-forge -c aihabitat
pip install habitat-lab
```

If conda is unavailable, record that in `docs/habitat_env_spike_report.md` and avoid polluting the main project environment.

## Diagnostics

From the project root:

```bash
python tools/check_habitat_env.py
python tools/test_habitat_sim_spike.py
python tools/test_habitat_lab_spike.py
```

Expected status files:

```text
outputs/habitat_spike/habitat_env_status.json
outputs/habitat_spike/habitat_sim_status.json
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
