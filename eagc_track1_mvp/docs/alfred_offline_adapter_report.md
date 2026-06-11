# ALFRED Offline Adapter Report

This document records the optional ALFRED offline trajectory adapter spike. It does not run AI2-THOR.

The adapter has two validation modes:

1. A tiny synthetic ALFRED-like fixture for deterministic fast-tier conversion tests.
2. Real ALFRED dataset conversion when the user manually provides local data.

## Goal

The goal is to parse public ALFRED offline task / trajectory files and convert them into this project's auditable artifacts:

- `world_model.json`
- `episode_log.jsonl`
- `alfred_task_summary.json`

This gives the project a public household-task alignment path without depending on simulator rendering.

## Why ALFRED Offline

ALFRED provides household task language instructions, high-level subgoals, low-level action sequences, object targets, and scene/floorplan metadata. These are useful for comparing the local MVP's world-model, task-planning, and action-summary format against a public embodied-task dataset.

## Scope

This adapter only parses offline `traj_data.json` files. It does not:

- launch AI2-THOR,
- render frames,
- execute actions online,
- train or fine-tune any model,
- redistribute ALFRED data.

Offline conversion cannot replace online closed-loop simulation. It is a dataset-alignment and reporting tool.

## Data Directory Requirements

Set either:

```powershell
$env:ALFRED_DATASET_ROOT="C:\path\to\ALFRED"
```

or:

```powershell
$env:ALFRED_SAMPLE_TRAJ_PATH="C:\path\to\traj_data.json"
```

The scripts also check:

- `data/alfred/`
- `datasets/alfred/`
- `C:\Users\Alphay\Documents\Datasets\ALFRED`
- `C:\Users\Alphay\Downloads\ALFRED`

ALFRED data should stay outside git. The project ignores common local ALFRED/data paths.

## Commands

Synthetic fixture conversion:

```powershell
python tests/smoke_test_alfred_fixture_conversion.py
```

Check local data:

```powershell
python tools/check_alfred_dataset.py
```

Convert one sample:

```powershell
python tools/convert_alfred_offline.py --traj-path C:\path\to\traj_data.json
```

or:

```powershell
python tools/convert_alfred_offline.py --dataset-root C:\path\to\ALFRED --max-samples 1
```

Validate:

```powershell
python -m validators.validate_alfred_offline_conversion outputs/alfred_offline/status.json
```

Optional smoke:

```powershell
python tests/smoke_test_alfred_offline_adapter.py
```

## Current Status

The v0.15.1 adapter, checker, converter, validator, synthetic fixture smoke test, real-data graceful smoke test, and documentation are prepared.

v0.15.3 status:

- Synthetic fixture conversion is part of the deterministic fast tier.
- Real ALFRED dataset conversion is supported by CLI but has not been validated locally because no real ALFRED data path is configured.
- The adapter remains an offline converter only and does not run AI2-THOR.

The synthetic fixture is located at:

```text
tests/fixtures/alfred/sample_traj_data.json
```

It contains `fixture_type = "synthetic_alfred_like"` and is not real ALFRED data. It only proves that the adapter can parse an ALFRED-like task/instruction/subgoal/action structure and produce project artifacts.

If no local ALFRED data is present, the expected status is:

```json
{
  "success": false,
  "reason": "missing_alfred_dataset"
}
```

That is a graceful optional-spike result, not a main-system failure.

## Conversion Result

When a `traj_data.json` file is available, the converter extracts:

- task instruction,
- scene/floorplan id when present,
- high-level subgoals,
- low-level actions,
- object names mentioned in action arguments or PDDL params,
- approximate affordances,
- uncertainty explaining that offline files may not expose full visual state.

The resulting `world_model.json` includes `source = "alfred_offline"`.

## Limitations

- Offline conversion does not verify whether actions succeed in a simulator.
- Object locations and relations are approximate unless explicitly available in the trajectory.
- No RGB frames or metadata are produced.
- It cannot replace online closed-loop simulation or official EAGC runtime evaluation.
