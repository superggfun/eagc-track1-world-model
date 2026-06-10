# Reproducibility Statement

## Environment Assumptions

- Operating system: Windows local development environment.
- Python: 3.10+ recommended.
- Local vLLM server: already running before tests.
- vLLM endpoint: `http://127.0.0.1:8000/v1`.
- Model identifier: `qwen3.6-35b-nvfp4`.
- The project does not start, stop, restart, or manage the vLLM Docker container.

## Installation

```powershell
cd "C:\Users\Alphay\Documents\New project\eagc_track1_mvp"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Test Commands

Fast tier:

```powershell
python tools/run_test_suite.py --tier fast
```

Targeted tier:

```powershell
python tools/run_test_suite.py --tier targeted
```

Standard tier:

```powershell
python tools/run_test_suite.py --tier standard
```

Full tier is available but not required for this readiness package:

```powershell
python tools/run_test_suite.py --tier full
```

## Demo Snapshot Reproduction

```powershell
python tools/create_demo_snapshot.py
```

Expected output:

- `outputs/demo_snapshot/local_sim_track1_demo/`
- `outputs/demo_snapshot/visual_evidence_demo/`
- `outputs/demo_snapshot/README_demo.md`

## Report Generation

```powershell
python tools/generate_project_report.py
```

Expected output:

- `reports/v0.8.4_technical_report.md`

## Source Package Generation

```powershell
python tools/package_source.py
```

Expected output:

- `dist/eagc_track1_mvp_source.zip`

The package is generated from git-tracked source files and excludes outputs, local images, `.venv-ai2thor`, `source_pack`, zip files, and `__pycache__`.

## Visual Test Images

Visual sequence and visual-local hybrid smoke tests require local images named like:

```text
assets/test_sequences/bedroom_sequence/frame_000.jpg
assets/test_sequences/bedroom_sequence/frame_001.jpg
assets/test_sequences/bedroom_sequence/frame_002.jpg
```

These images are local resources and are intentionally not committed.
