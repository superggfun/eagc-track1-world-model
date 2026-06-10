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

Docker smoke tier:

```powershell
python tools/run_test_suite.py --tier docker-smoke
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

Note: this is the current report generator output path and uses a legacy filename from the first technical-report milestone. The current submission-facing technical report draft is `submission_package/technical_report_draft.md`, and `tools/build_report_pdf.py` writes HTML/PDF-status artifacts under `submission_bundle/reports/`.

## Source Package Generation

```powershell
python tools/package_source.py
```

Expected output:

- `dist/eagc_track1_mvp_source.zip`

The package is generated from git-tracked source files and excludes outputs, local images, `.venv-ai2thor`, `source_pack`, zip files, and `__pycache__`.

Clean source package check:

```powershell
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
```

## Docker Reproducibility

The Docker image packages only the local agent code. It does not include Qwen3.6-35B-A3B-NVFP4 model weights.

Build:

```powershell
docker build -t eagc-track1-agent:v0.11 .
```

Mock-only Docker smoke:

```powershell
docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke
```

Windows Docker Desktop host vLLM example:

```powershell
docker run --rm -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.11 python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

Linux host-network example:

```bash
docker run --rm --network host -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.11 python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

## Visual Test Images

Visual sequence and visual-local hybrid smoke tests require local images named like:

```text
assets/test_sequences/bedroom_sequence/frame_000.jpg
assets/test_sequences/bedroom_sequence/frame_001.jpg
assets/test_sequences/bedroom_sequence/frame_002.jpg
```

These images are local resources and are intentionally not committed.
