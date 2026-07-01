from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness.validate_outputs import validate_output_dir
from validators.validate_maze_outputs import validate_detailed as validate_maze_outputs_detailed
from validators.validate_virtualhome_exploration import validate_detailed as validate_virtualhome_exploration_detailed


DEFAULT_BUNDLE_ROOT = PROJECT_ROOT / "submission_bundle"
DEFAULT_SOURCE_ZIP = PROJECT_ROOT / "dist" / "source.zip"
DEFAULT_IMAGE_NAME = "eagc-track1-agent:v0.17.6"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a qualification submission readiness bundle.")
    parser.add_argument("--output-dir", default=str(DEFAULT_BUNDLE_ROOT))
    parser.add_argument("--source-zip", default=str(DEFAULT_SOURCE_ZIP))
    parser.add_argument("--image-name", default=DEFAULT_IMAGE_NAME)
    parser.add_argument("--save-docker-image", action="store_true")
    parser.add_argument(
        "--allow-mock-virtualhome-sample",
        action="store_true",
        help="Deprecated development flag; mock VirtualHome output is copied only to optional diagnostics.",
    )
    parser.add_argument(
        "--require-virtualhome-final",
        action="store_true",
        help="Fail bundle generation unless validated continuous closed-loop VirtualHome final evidence is present.",
    )
    args = parser.parse_args()
    bundle_root = _resolve_path(args.output_dir)
    source_zip = _resolve_path(args.source_zip)
    _reset_bundle(bundle_root)
    _copy_docker_files(bundle_root)
    _copy_source_zip(bundle_root, source_zip)
    _copy_reports(bundle_root)
    _copy_disclosures(bundle_root)
    _copy_sample_outputs(
        bundle_root,
        allow_mock_virtualhome_sample=bool(args.allow_mock_virtualhome_sample),
        require_virtualhome_final=bool(args.require_virtualhome_final),
    )
    if args.save_docker_image:
        _save_docker_image(bundle_root, str(args.image_name))
    _write_checksums(bundle_root)
    print(f"Submission bundle written to {bundle_root}")
    print("Top-level bundle directories: sample_outputs, reports, disclosures, checksums, source, docker.")
    return 0


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _reset_bundle(path: Path) -> None:
    if path.exists():
        resolved = path.resolve()
        project_root = PROJECT_ROOT.resolve()
        if resolved == project_root or project_root not in resolved.parents:
            raise SystemExit(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_docker_files(bundle_root: Path) -> None:
    docker_dir = bundle_root / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)
    _copy_required(PROJECT_ROOT / "Dockerfile", docker_dir / "Dockerfile")
    _copy_required(PROJECT_ROOT / "docker" / "README_DOCKER.md", docker_dir / "README_DOCKER.md")
    _copy_required(PROJECT_ROOT / "docker" / "docker_run_examples.md", docker_dir / "docker_run_examples.md")
    (docker_dir / "README_IMAGE_TAR.md").write_text(
        "Docker image tar is not included; rebuild from the root Dockerfile.\n",
        encoding="utf-8",
    )


def _copy_source_zip(bundle_root: Path, source_zip: Path) -> None:
    if not source_zip.exists():
        raise SystemExit(f"Missing source zip: {source_zip}. Run python tools/package_source.py first.")
    target_dir = bundle_root / "source"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_zip, target_dir / "source.zip")


def _copy_reports(bundle_root: Path) -> None:
    reports_dir = bundle_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    _copy_required(PROJECT_ROOT / "submission_package" / "technical_report.md", reports_dir / "technical_report.md")
    html_candidates = [
        PROJECT_ROOT / "submission_package" / "technical_report.html",
        PROJECT_ROOT / "reports" / "technical_report.html",
        PROJECT_ROOT / "submission_bundle" / "reports" / "technical_report.html",
    ]
    html_included = False
    for candidate in html_candidates:
        if candidate.exists():
            shutil.copy2(candidate, reports_dir / "technical_report.html")
            html_included = True
            break
    pdf_candidates = [
        PROJECT_ROOT / "submission_package" / "technical_report.pdf",
        PROJECT_ROOT / "reports" / "technical_report.pdf",
        PROJECT_ROOT / "submission_bundle" / "reports" / "technical_report.pdf",
    ]
    for candidate in pdf_candidates:
        if candidate.exists():
            shutil.copy2(candidate, reports_dir / "technical_report.pdf")
            _write_technical_report_status(
                reports_dir / "technical_report_build_status.json",
                pdf_included=True,
                html_included=html_included,
            )
            break
    else:
        _write_technical_report_status(
            reports_dir / "technical_report_build_status.json",
            pdf_included=False,
            html_included=html_included,
        )
    metrics_path = PROJECT_ROOT / "reports" / "report_metrics.json"
    if metrics_path.exists():
        shutil.copy2(metrics_path, reports_dir / "report_metrics.json")


def _copy_disclosures(bundle_root: Path) -> None:
    disclosures_dir = bundle_root / "disclosures"
    disclosures_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "training_resource_disclosure.md",
        "reproducibility_statement.md",
        "system_limitations.md",
        "open_source_statement.md",
    ]:
        _copy_required(PROJECT_ROOT / "submission_package" / name, disclosures_dir / name)


def _copy_sample_outputs(
    bundle_root: Path,
    *,
    allow_mock_virtualhome_sample: bool,
    require_virtualhome_final: bool,
) -> None:
    snapshot_root = PROJECT_ROOT / "outputs" / "demo_snapshot"
    specs: list[dict[str, Any]] = [
        {
            "name": "local_sim_track1_demo",
            "source_dir": snapshot_root / "local_sim_track1_demo",
            "mode": "track1",
            "required": ["world_model.json", "episode_log.jsonl", "run_audit.json", "harness_result.json", "track1_score.json"],
            "optional": [],
            "validator": lambda source_dir: _validate_harness_output(source_dir, "track1"),
            "copy_tree": False,
            "missing_hint": "Run python tools/create_demo_snapshot.py first.",
        },
        {
            "name": "visual_evidence_demo",
            "source_dir": snapshot_root / "visual_evidence_demo",
            "mode": "visual",
            "required": ["world_model.json", "episode_log.jsonl", "run_audit.json", "harness_result.json", "visual_task_result.json"],
            "optional": ["qwen_response_summary.json"],
            "validator": lambda source_dir: _validate_harness_output(source_dir, "visual"),
            "copy_tree": False,
            "missing_hint": "Run python tools/create_demo_snapshot.py first.",
        },
        {
            "name": "maze_stress",
            "source_dir": PROJECT_ROOT / "outputs" / "maze_stress",
            "mode": "maze_stress",
            "required": [
                "world_model.json",
                "episode_log.jsonl",
                "run_audit.json",
                "maze_metrics.json",
                "status.json",
                "reference_maze.json",
                "comparison_report.json",
            ],
            "optional": [],
            "validator": _validate_maze_stress_output,
            "copy_tree": True,
            "missing_hint": "Run python tools/run_maze_stress_test.py --episode generated_grid_maze --difficulty medium first.",
        },
        {
            "name": "maze_anti_loop",
            "source_dir": PROJECT_ROOT / "outputs" / "maze_anti_loop",
            "mode": "maze_anti_loop",
            "required": [
                "world_model.json",
                "episode_log.jsonl",
                "run_audit.json",
                "maze_metrics.json",
                "status.json",
                "reference_maze.json",
                "comparison_report.json",
                "anti_loop_report.md",
            ],
            "optional": [],
            "validator": _validate_maze_anti_loop_output,
            "copy_tree": True,
            "missing_hint": "Run python tools/run_maze_anti_loop_test.py --episode all first.",
        },
    ]
    manifest: dict[str, Any] = {"sample_outputs": {}, "optional_diagnostics": {}}
    for spec in specs:
        source_dir = Path(spec["source_dir"])
        name = str(spec["name"])
        if not source_dir.exists():
            raise SystemExit(f"Missing sample output directory: {source_dir}. {spec['missing_hint']}")
        _assert_required(source_dir, list(spec["required"]))
        validator: Callable[[Path], dict[str, Any]] = spec["validator"]
        validation = validator(source_dir)
        if not validation["passed"]:
            raise SystemExit(f"Sample output validation failed for {name}:\n{json.dumps(validation, ensure_ascii=False, indent=2)}")
        target_dir = bundle_root / "sample_outputs" / name
        if spec["copy_tree"]:
            copied = _copy_output_tree(source_dir, target_dir)
            missing_optional: list[str] = []
        else:
            copied, missing_optional = _copy_file_set(source_dir, target_dir, list(spec["required"]), list(spec["optional"]))
        manifest["sample_outputs"][name] = {
            "mode": spec["mode"],
            "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
            "copied": copied,
            "missing_optional": missing_optional,
            "validation": validation,
        }
        audit_path = source_dir / "run_audit.json"
        if audit_path.exists():
            audit = _read_json(audit_path)
            if audit.get("evidence_level"):
                manifest["sample_outputs"][name]["evidence_level"] = audit.get("evidence_level")
    _copy_virtualhome_if_final(
        bundle_root,
        manifest,
        require_virtualhome_final=require_virtualhome_final,
        allow_mock_virtualhome_sample=allow_mock_virtualhome_sample,
    )
    _copy_virtualhome_optional_diagnostics(bundle_root, manifest)
    manifest["official_runtime_adapter"] = {
        "placeholder_implemented": True,
        "hidden_evaluation_results_included": False,
        "reason": "Official runtime/API is not available in this local build.",
        "integration_boundary": [
            "src/env_adapters/official_env.py",
            "src/executor/action_translator.py",
            "src/harness/run_official.py",
        ],
    }
    manifest_path = bundle_root / "sample_outputs" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_harness_output(source_dir: Path, mode: str) -> dict[str, Any]:
    summary = validate_output_dir(source_dir, mode)
    return {"passed": bool(summary.get("passed")), "details": summary}


def _validate_maze_stress_output(source_dir: Path) -> dict[str, Any]:
    summary = validate_maze_outputs_detailed(source_dir, recursive=True)
    return {"passed": not summary["errors"], "errors": summary["errors"], "warnings": summary["warnings"]}


def _validate_maze_anti_loop_output(source_dir: Path) -> dict[str, Any]:
    summary = validate_maze_outputs_detailed(source_dir, recursive=True)
    return {"passed": not summary["errors"], "errors": summary["errors"], "warnings": summary["warnings"]}


def _validate_virtualhome_exploration_output(source_dir: Path, *, final_submission: bool) -> dict[str, Any]:
    summary = validate_virtualhome_exploration_detailed(source_dir, final_submission=final_submission)
    return {"passed": not summary["errors"], "errors": summary["errors"], "warnings": summary["warnings"]}


VIRTUALHOME_REQUIRED_FILES = [
    "world_model.json",
    "reference_world_model.json",
    "comparison_report.json",
    "episode_log.jsonl",
    "run_audit.json",
    "visual_task_result.json",
    "frame_manifest.json",
    "coverage_report.json",
    "dedup_report.json",
    "virtualhome_exploration_report.md",
]


def _copy_virtualhome_if_final(
    bundle_root: Path,
    manifest: dict[str, Any],
    *,
    require_virtualhome_final: bool,
    allow_mock_virtualhome_sample: bool,
) -> None:
    candidates = [
        PROJECT_ROOT / "outputs" / "virtualhome_continuous",
        PROJECT_ROOT / "outputs" / "virtualhome_exploration",
        PROJECT_ROOT / "outputs" / "virtualhome_mock_replay",
    ]
    existing_candidates = [candidate for candidate in candidates if candidate.exists()]
    source_dir = next(
        (
            candidate
            for candidate in existing_candidates
            if all((candidate / rel).exists() for rel in VIRTUALHOME_REQUIRED_FILES)
        ),
        existing_candidates[0] if existing_candidates else None,
    )
    if source_dir is None:
        reason = "No validated continuous closed-loop VirtualHome + VLM evidence available in this build."
        manifest["virtualhome_final_evidence"] = {"included": False, "reason": reason}
        if require_virtualhome_final:
            raise SystemExit(reason)
        return

    missing = [rel for rel in VIRTUALHOME_REQUIRED_FILES if not (source_dir / rel).exists()]
    if missing:
        reason = f"VirtualHome output is incomplete and was not copied as final evidence: missing {missing}."
        manifest["virtualhome_final_evidence"] = {"included": False, "source": source_dir.relative_to(PROJECT_ROOT).as_posix(), "reason": reason}
        if require_virtualhome_final:
            raise SystemExit(reason)
        return

    final_validation = _validate_virtualhome_exploration_output(source_dir, final_submission=True)
    if final_validation["passed"]:
        _assert_virtualhome_final_evidence(source_dir, allow_mock_virtualhome_sample=False)
        target_dir = bundle_root / "sample_outputs" / "virtualhome_exploration"
        copied = _copy_output_tree(source_dir, target_dir)
        audit = _read_json(source_dir / "run_audit.json")
        manifest["sample_outputs"]["virtualhome_exploration"] = {
            "mode": "virtualhome_exploration",
            "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
            "copied": copied,
            "missing_optional": [],
            "validation": final_validation,
            "evidence_level": audit.get("evidence_level"),
            "prediction_input_mode": audit.get("prediction_input_mode"),
            "final_vlm_required": True,
        }
        manifest["virtualhome_final_evidence"] = {
            "included": True,
            "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
            "evidence_level": audit.get("evidence_level"),
        }
        return

    reason = "No validated continuous closed-loop VirtualHome + VLM evidence available in this build."
    if final_validation["errors"]:
        reason = f"{reason} Final validation errors: {'; '.join(final_validation['errors'][:5])}"
    manifest["virtualhome_final_evidence"] = {
        "included": False,
        "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
        "reason": reason,
        "validation": final_validation,
    }
    if require_virtualhome_final:
        raise SystemExit(reason)

    diagnostic_validation = _validate_virtualhome_exploration_output(source_dir, final_submission=False)
    if diagnostic_validation["passed"] or allow_mock_virtualhome_sample:
        target_dir = bundle_root / "optional_diagnostics" / "virtualhome_mock_replay"
        copied = _copy_output_tree(source_dir, target_dir)
        audit = _read_json(source_dir / "run_audit.json")
        manifest["optional_diagnostics"]["virtualhome_mock_replay"] = {
            "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
            "copied": copied,
            "validation": diagnostic_validation,
            "evidence_level": audit.get("evidence_level"),
            "prediction_input_mode": audit.get("prediction_input_mode"),
            "not_final_evidence": True,
        }


def _copy_virtualhome_optional_diagnostics(bundle_root: Path, manifest: dict[str, Any]) -> None:
    optional_manifest = manifest.setdefault("optional_diagnostics", {})
    _copy_one_virtualhome_diagnostic(
        bundle_root,
        optional_manifest,
        name="virtualhome_mock_replay",
        candidates=[PROJECT_ROOT / "outputs" / "virtualhome_mock_replay"],
        final_submission=False,
    )
    _copy_one_virtualhome_diagnostic(
        bundle_root,
        optional_manifest,
        name="virtualhome_partial_live",
        candidates=[
            PROJECT_ROOT / "outputs" / "virtualhome_partial_live",
            PROJECT_ROOT / "outputs" / "virtualhome_live_attach_check",
        ],
        final_submission=False,
        allow_failure_only=True,
    )


def _copy_one_virtualhome_diagnostic(
    bundle_root: Path,
    optional_manifest: dict[str, Any],
    *,
    name: str,
    candidates: list[Path],
    final_submission: bool,
    allow_failure_only: bool = False,
) -> None:
    source_dir = next((candidate for candidate in candidates if candidate.exists() and any(candidate.iterdir())), None)
    if source_dir is None:
        optional_manifest[name] = {"included": False, "reason": "diagnostic output directory was not present"}
        return

    has_full_artifacts = all((source_dir / rel).exists() for rel in VIRTUALHOME_REQUIRED_FILES)
    if has_full_artifacts:
        validation = _validate_virtualhome_exploration_output(source_dir, final_submission=final_submission)
    elif allow_failure_only and ((source_dir / "live_connection_error.json").exists() or (source_dir / "harness_result.json").exists()):
        validation = {
            "passed": False,
            "errors": [],
            "warnings": ["failure-only or partial live diagnostic; not final evidence"],
        }
    else:
        optional_manifest[name] = {
            "included": False,
            "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
            "reason": "diagnostic output was incomplete",
        }
        return

    target_dir = bundle_root / "optional_diagnostics" / name
    copied = _copy_output_tree(source_dir, target_dir)
    audit: dict[str, Any] = {}
    if (source_dir / "run_audit.json").exists():
        audit = _read_json(source_dir / "run_audit.json")
    elif (source_dir / "live_connection_error.json").exists():
        audit = _read_json(source_dir / "live_connection_error.json")
    optional_manifest[name] = {
        "included": True,
        "source": source_dir.relative_to(PROJECT_ROOT).as_posix(),
        "copied": copied,
        "validation": validation,
        "evidence_level": audit.get("evidence_level"),
        "prediction_input_mode": audit.get("prediction_input_mode"),
        "not_final_evidence": True,
    }


def _assert_virtualhome_final_evidence(source_dir: Path, *, allow_mock_virtualhome_sample: bool) -> None:
    audit = _read_json(source_dir / "run_audit.json")
    required = {
        "evidence_level": "closed_loop_final_evidence",
        "world_model_source": "visual_observation_pipeline",
        "capture_mode": "continuous_episode",
        "continuous_closed_loop": True,
        "virtualhome_live_run": True,
        "live_runtime_connected": True,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
    }
    errors = [f"run_audit.{key} must be {expected!r}, got {audit.get(key)!r}" for key, expected in required.items() if audit.get(key) != expected]
    mode = str(audit.get("prediction_input_mode") or "")
    if mode != "vlm_frame_extraction" and not allow_mock_virtualhome_sample:
        errors.append(
            "VirtualHome final evidence is not VLM-based. Re-run with --prediction-input-mode vlm_frame_extraction "
            "or pass an explicit dev override."
        )
    if audit.get("synthetic_capture") is True and not allow_mock_virtualhome_sample:
        errors.append("VirtualHome final evidence has synthetic_capture=true. Use real VirtualHome/exported keyframes for final bundle.")
    if audit.get("mock_extraction") is True and not allow_mock_virtualhome_sample:
        errors.append("VirtualHome final evidence has mock_extraction=true. Use a real VLM extraction run for final bundle.")
    if audit.get("virtualhome_live_run") is True and audit.get("live_runtime_connected") is not True:
        errors.append("VirtualHome live evidence is missing live_runtime_connected=true.")
    if errors:
        raise SystemExit("VirtualHome final evidence check failed:\n- " + "\n- ".join(errors))


def _assert_required(source_dir: Path, required: list[str]) -> None:
    missing = [rel for rel in required if not (source_dir / rel).exists()]
    if missing:
        raise SystemExit(f"Missing required files in {source_dir}: {missing}")


def _copy_file_set(source_dir: Path, target_dir: Path, required: list[str], optional: list[str]) -> tuple[list[str], list[str]]:
    copied: list[str] = []
    missing_optional: list[str] = []
    for rel in required:
        _copy_required(source_dir / rel, target_dir / rel)
        copied.append(rel)
    for rel in optional:
        source = source_dir / rel
        if source.exists():
            shutil.copy2(source, target_dir / rel)
            copied.append(rel)
        else:
            missing_optional.append(rel)
    return copied, missing_optional


def _copy_output_tree(source_dir: Path, target_dir: Path) -> list[str]:
    copied: list[str] = []
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file() or _is_ignored_output_file(source):
            continue
        rel = source.relative_to(source_dir)
        target = target_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(rel.as_posix())
    return copied


def _is_ignored_output_file(path: Path) -> bool:
    return "__pycache__" in path.parts or ".pytest_cache" in path.parts or path.suffix.lower() in {".pyc", ".pyo", ".zip"}


def _write_technical_report_status(path: Path, pdf_included: bool, html_included: bool) -> None:
    status = {
        "source": "submission_package/technical_report.md",
        "technical_report_markdown": "reports/technical_report.md",
        "technical_report_html": "reports/technical_report.html" if html_included else "",
        "technical_report_pdf": "reports/technical_report.pdf" if pdf_included else "",
        "html_included": html_included,
        "pdf_included": pdf_included,
        "manual_export_required": not pdf_included,
        "manual_export_steps": [
            "Open submission_bundle/reports/technical_report.html in a browser, or open submission_package/technical_report.md.",
            "Use Print / Save as PDF.",
            "Place the exported file at submission_bundle/reports/technical_report.pdf.",
        ]
        if not pdf_included
        else [],
    }
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_docker_image(bundle_root: Path, image_name: str) -> None:
    tar_name = image_name.replace(":", "-").replace("/", "-") + ".tar"
    target = bundle_root / "source" / tar_name
    command = ["docker", "save", "-o", str(target), image_name]
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Missing required JSON file: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON file {path}: {exc}") from None
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
