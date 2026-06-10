from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = PROJECT_ROOT / "submission_bundle"
DEFAULT_SOURCE_ZIP = PROJECT_ROOT / "dist" / "eagc_track1_mvp_source.zip"
DEFAULT_IMAGE_NAME = "eagc-track1-agent:v0.11"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a qualification submission readiness bundle.")
    parser.add_argument("--output-dir", default=str(DEFAULT_BUNDLE_ROOT), help="Directory to write the bundle.")
    parser.add_argument("--source-zip", default=str(DEFAULT_SOURCE_ZIP), help="Prepared source zip to include.")
    parser.add_argument("--image-name", default=DEFAULT_IMAGE_NAME, help="Docker image name to describe.")
    parser.add_argument(
        "--save-docker-image",
        action="store_true",
        help="Also run docker save into the bundle. Disabled by default because the tar can be large.",
    )
    args = parser.parse_args()

    bundle_root = _resolve_path(args.output_dir)
    source_zip = _resolve_path(args.source_zip)
    image_name = str(args.image_name)

    _reset_bundle(bundle_root)
    _copy_docker_files(bundle_root, image_name)
    _copy_source_zip(bundle_root, source_zip)
    _copy_reports(bundle_root)
    _copy_disclosures(bundle_root)
    _copy_sample_outputs(bundle_root)
    _write_readme(bundle_root, image_name)
    if args.save_docker_image:
        _save_docker_image(bundle_root, image_name)
    _write_checksums(bundle_root)

    print(f"Submission bundle written to {bundle_root}")
    print("Docker image tar was not created." if not args.save_docker_image else "Docker image tar created.")
    return 0


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _reset_bundle(path: Path) -> None:
    if path.exists():
        resolved = path.resolve()
        project_root = PROJECT_ROOT.resolve()
        if project_root not in resolved.parents and resolved != project_root:
            raise SystemExit(f"Refusing to remove unexpected path: {resolved}")
        if resolved == project_root:
            raise SystemExit("Refusing to use project root as bundle output directory.")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_docker_files(bundle_root: Path, image_name: str) -> None:
    docker_dir = bundle_root / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)
    _copy_required(PROJECT_ROOT / "Dockerfile", docker_dir / "Dockerfile")
    _copy_required(PROJECT_ROOT / "docker" / "README_DOCKER.md", docker_dir / "README_DOCKER.md")
    _copy_required(PROJECT_ROOT / "docker" / "docker_run_examples.md", docker_dir / "docker_run_examples.md")
    _write_image_info(docker_dir / "image_info.txt", image_name)
    _write_docker_save_instructions(docker_dir / "docker_image_save_instructions.md", image_name)


def _copy_source_zip(bundle_root: Path, source_zip: Path) -> None:
    if not source_zip.exists():
        raise SystemExit(f"Missing source zip: {source_zip}. Run python tools/package_source.py first.")
    target_dir = bundle_root / "source"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_zip, target_dir / "eagc_track1_mvp_source.zip")


def _copy_reports(bundle_root: Path) -> None:
    reports_dir = bundle_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    _copy_required(
        PROJECT_ROOT / "submission_package" / "technical_report_draft.md",
        reports_dir / "technical_report_draft.md",
    )
    pdf_candidates = [
        PROJECT_ROOT / "submission_package" / "technical_report_draft.pdf",
        PROJECT_ROOT / "reports" / "technical_report_draft.pdf",
    ]
    for candidate in pdf_candidates:
        if candidate.exists():
            shutil.copy2(candidate, reports_dir / "technical_report_draft.pdf")
            break


def _copy_disclosures(bundle_root: Path) -> None:
    disclosures_dir = bundle_root / "disclosures"
    disclosures_dir.mkdir(parents=True, exist_ok=True)
    names = [
        "training_resource_disclosure.md",
        "reproducibility_statement.md",
        "system_limitations.md",
        "open_source_statement.md",
    ]
    for name in names:
        _copy_required(PROJECT_ROOT / "submission_package" / name, disclosures_dir / name)


def _copy_sample_outputs(bundle_root: Path) -> None:
    snapshot_root = PROJECT_ROOT / "outputs" / "demo_snapshot"
    if not snapshot_root.exists():
        raise SystemExit("Missing outputs/demo_snapshot. Run python tools/create_demo_snapshot.py first.")
    output_specs = {
        "local_sim_track1_demo": ["world_model.json", "episode_log.jsonl", "run_audit.json", "track1_score.json"],
        "visual_evidence_demo": [
            "world_model.json",
            "episode_log.jsonl",
            "run_audit.json",
            "visual_task_result.json",
        ],
    }
    for demo_name, file_names in output_specs.items():
        source_dir = snapshot_root / demo_name
        if not source_dir.exists():
            raise SystemExit(f"Missing demo snapshot directory: {source_dir}")
        target_dir = bundle_root / "sample_outputs" / demo_name
        target_dir.mkdir(parents=True, exist_ok=True)
        for file_name in file_names:
            _copy_required(source_dir / file_name, target_dir / file_name)


def _write_image_info(path: Path, image_name: str) -> None:
    info = _docker_image_info(image_name)
    lines = [
        f"image name: {image_name}",
        f"image id: {info.get('id', 'not available')}",
        f"image size bytes: {info.get('size', 'not available')}",
        "",
        "build command:",
        "docker build -t eagc-track1-agent:v0.11 .",
        "",
        "docker-smoke command:",
        "docker run --rm eagc-track1-agent:v0.11 python tools/run_test_suite.py --tier docker-smoke",
        "",
        "real LocalSim command:",
        (
            "docker run --rm -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 "
            "-e QWEN_MODEL=qwen3.6-35b-nvfp4 eagc-track1-agent:v0.11 "
            "python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate"
        ),
        "",
        "note: model weights are not included in the image.",
        "note: Qwen endpoint is configured by QWEN_BASE_URL and QWEN_MODEL.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _docker_image_info(image_name: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", image_name],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    if not payload:
        return {}
    item = payload[0]
    return {"id": item.get("Id"), "size": item.get("Size"), "created": item.get("Created")}


def _write_docker_save_instructions(path: Path, image_name: str) -> None:
    tar_name = image_name.replace(":", "-").replace("/", "-") + ".tar"
    text = f"""# Docker Image Save Instructions

The submission bundle builder does not save the Docker image by default because the tar file may be large.

To save the current image manually:

```bash
docker save -o {tar_name} {image_name}
```

To load it later:

```bash
docker load -i {tar_name}
```

The saved image contains the agent code and Python dependencies, but not Qwen model weights.
"""
    path.write_text(text, encoding="utf-8")


def _save_docker_image(bundle_root: Path, image_name: str) -> None:
    tar_name = image_name.replace(":", "-").replace("/", "-") + ".tar"
    target = bundle_root / "docker" / tar_name
    command = ["docker", "save", "-o", str(target), image_name]
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _write_readme(bundle_root: Path, image_name: str) -> None:
    text = f"""# EAGC Track 1 Qualification Submission Readiness Bundle

This bundle is a pre-submission package for the current local EAGC Track 1 MVP.

## What Is Included

- Docker packaging instructions for `{image_name}`.
- Docker image metadata and save/load instructions.
- Source package: `source/eagc_track1_mvp_source.zip`.
- Technical report draft.
- Training/resource disclosure, reproducibility statement, system limitations, and open-source statement.
- Sample LocalSim Track 1 outputs: `sample_outputs/local_sim_track1_demo/`.
- Sample visual evidence outputs: `sample_outputs/visual_evidence_demo/`.
- SHA256 checksums under `checksums/SHA256SUMS.txt`.

## How To Run Docker Smoke

```bash
docker run --rm {image_name} python tools/run_test_suite.py --tier docker-smoke
```

## How To Run With External vLLM Endpoint

Windows Docker Desktop example:

```bash
docker run --rm -e QWEN_BASE_URL=http://host.docker.internal:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 {image_name} python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

Linux host-network example:

```bash
docker run --rm --network host -e QWEN_BASE_URL=http://127.0.0.1:8000/v1 -e QWEN_MODEL=qwen3.6-35b-nvfp4 {image_name} python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

## Sample Outputs

- `sample_outputs/local_sim_track1_demo/world_model.json`
- `sample_outputs/local_sim_track1_demo/episode_log.jsonl`
- `sample_outputs/local_sim_track1_demo/run_audit.json`
- `sample_outputs/local_sim_track1_demo/track1_score.json`
- `sample_outputs/visual_evidence_demo/world_model.json`
- `sample_outputs/visual_evidence_demo/episode_log.jsonl`
- `sample_outputs/visual_evidence_demo/run_audit.json`
- `sample_outputs/visual_evidence_demo/visual_task_result.json`

## What Is Not Included

- Qwen model weights.
- Any redistributed Qwen model checkpoint or model archive.
- Official EAGC runtime/API.
- ProcTHOR or AI2-THOR validated runtime.
- Training outputs or fine-tuned models.
- Local visual test images.

## Known Limitations

LocalSim is a self-built local environment, not official hidden evaluation. The visual-local hybrid path is symbolic and does not perform physical manipulation. The local heuristic score is not an official score.

## Pending Organizer Clarification

- Whether qualification submission requires Docker image tar, Dockerfile/source, or registry URL.
- Whether model weights must be included, mounted, or served externally.
- Whether external vLLM endpoints are allowed or whether model volumes must be mounted into the agent container.
- Official qualification submission portal and final runtime schema.
"""
    (bundle_root / "README_SUBMISSION.md").write_text(text, encoding="utf-8")


def _write_checksums(bundle_root: Path) -> None:
    checksums_dir = bundle_root / "checksums"
    checksums_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for path in sorted(bundle_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_root).as_posix()
        if rel == "checksums/SHA256SUMS.txt":
            continue
        entries.append(f"{_sha256(path)}  {rel}")
    (checksums_dir / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_required(source: Path, target: Path) -> None:
    if not source.exists():
        raise SystemExit(f"Missing required file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
