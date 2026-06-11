from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pre_submission_audit"
REQUIRED_FILES = [
    "README.md",
    "Dockerfile",
    "config.yaml",
    "requirements.txt",
    "submission_package/technical_report_draft.md",
    "submission_package/training_resource_disclosure.md",
    "submission_package/reproducibility_statement.md",
    "submission_package/system_limitations.md",
    "tools/run_test_suite.py",
]
EXPECTED_TAGS = ["v0.15.2-targeted-suite-controls"]
SOURCE_ZIP = PROJECT_ROOT / "dist" / "eagc_track1_mvp_source.zip"
VIRTUALHOME_EVIDENCE_FILES = [
    "docs/version_status_v0.16.6.md",
    "docs/version_status_v0.16.7.md",
    "tools/test_virtualhome_windows_spike.py",
    "tools/test_virtualhome_multiframe_qwen_vision.py",
    "tools/compare_virtualhome_multiframe_symbolic.py",
    "validators/validate_virtualhome_multiframe_grounding.py",
    "tools/build_virtualhome_evidence_report.py",
]
VIRTUALHOME_OUTPUT_ARTIFACTS = [
    "scene_graph.json",
    "program_log.json",
    "converted_world_model.json",
    "converted_episode_log.jsonl",
    "frame_000.png",
    "task_frames",
    "multiframe_qwen_status.json",
    "episode_visual_symbolic_comparison.json",
]
RESOURCE_PROFILE_HELPERS = [
    "tools/profile_virtualhome_vllm_resources.py",
    "tools/test_virtualhome_vllm_resource_smoke.py",
]
RESOURCE_PROFILE_ARTIFACTS = [
    "virtualhome_vllm_resource_profile.json",
    "virtualhome_vllm_resource_profile.md",
    "coexistence_smoke_status.json",
]
RUNTIME_DIRS = [
    "outputs",
    "dist",
    "source_pack",
    "submission_bundle",
    "images",
    "datasets",
    "VirtualHome",
    "virtualhome",
    "ALFRED",
    "alfred_data",
]
FORBIDDEN_TRACKED_PARTS = {
    "outputs",
    "dist",
    "source_pack",
    "submission_bundle",
    "images",
    ".venv",
    ".venv-ai2thor",
    "__pycache__",
}
FORBIDDEN_TRACKED_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".mp4",
    ".avi",
    ".mov",
    ".exe",
    ".dll",
    ".unity3d",
    ".glb",
    ".ply",
    ".obj",
    ".zip",
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".gguf",
}


def main() -> int:
    report = build_report()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "audit_report.json"
    md_path = OUTPUT_DIR / "audit_report.md"
    report["audit_report_json"] = str(json_path)
    report["audit_report_md"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(f"Pre-submission audit written to {json_path}")
    print(f"Pre-submission audit written to {md_path}")
    if report["failures"]:
        print("Pre-submission audit failed:")
        for failure in report["failures"]:
            print(f"- {failure}")
        return 1
    print("Pre-submission audit passed with warnings only." if report["warnings"] else "Pre-submission audit passed.")
    return 0


def build_report() -> Dict[str, Any]:
    tracked = _git_lines(["ls-files"])
    dirty = _git_lines(["status", "--short"])
    tags = set(_git_lines(["tag", "--list"]))
    latest_reports = sorted((PROJECT_ROOT / "outputs" / "test_suite_reports").glob("*_report.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    failures: List[str] = []
    warnings: List[str] = []

    required_status = []
    for rel in REQUIRED_FILES:
        path = PROJECT_ROOT / rel
        exists = path.exists()
        required_status.append({"path": rel, "exists": exists})
        if not exists:
            failures.append(f"Missing required file: {rel}")

    if not SOURCE_ZIP.exists():
        warnings.append("Source package is missing; run python tools/package_source.py.")

    for tag in EXPECTED_TAGS:
        if tag not in tags:
            failures.append(f"Missing expected git tag: {tag}")

    if dirty:
        warnings.append("Git working tree is dirty; review dirty_files before final submission.")

    tracked_violations = _tracked_violations(tracked)
    for violation in tracked_violations:
        failures.append(f"Forbidden tracked artifact: {violation}")

    runtime_dirs = []
    for rel in RUNTIME_DIRS:
        path = PROJECT_ROOT / rel
        exists = path.exists()
        runtime_dirs.append({"path": rel, "exists": exists})
        if exists:
            warnings.append(f"Runtime/artifact directory exists locally and should remain ignored: {rel}")

    virtualhome_evidence = _virtualhome_evidence_status()
    if not any(item["exists"] for item in virtualhome_evidence["version_docs"]):
        warnings.append("VirtualHome v0.16.6/v0.16.7 status docs are missing.")
    for item in virtualhome_evidence["required_code"]:
        if not item["exists"]:
            warnings.append(f"VirtualHome evidence helper is missing: {item['path']}")
    if virtualhome_evidence["output_dir_exists"]:
        warnings.append("VirtualHome evidence outputs exist locally and should remain ignored by git.")
    else:
        warnings.append("VirtualHome evidence outputs are not present locally; this is allowed for source-only submission checks.")

    resource_profile = _resource_profile_status()
    for item in resource_profile["helpers"]:
        if not item["exists"]:
            warnings.append(f"Resource profile helper is missing: {item['path']}")
    if not all(item["exists"] for item in resource_profile["artifacts"]):
        warnings.append("One or more resource profile runtime artifacts are missing; run python tools/run_test_suite.py --tier targeted-resource-profile if needed.")

    pdf_status_path = PROJECT_ROOT / "submission_bundle" / "reports" / "technical_report_build_status.json"
    pdf_status: Dict[str, Any] = {}
    if pdf_status_path.exists():
        try:
            pdf_status = json.loads(pdf_status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append("technical_report_build_status.json exists but is not valid JSON.")
    else:
        warnings.append("Technical report PDF/HTML build status not found; run python tools/build_report_pdf.py if needed.")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "success": not failures,
        "failures": failures,
        "warnings": warnings,
        "required_files": required_status,
        "source_package": {"path": str(SOURCE_ZIP), "exists": SOURCE_ZIP.exists()},
        "latest_test_suite_report": str(latest_reports[0]) if latest_reports else "",
        "dirty_files": dirty,
        "expected_tags": [{"tag": tag, "exists": tag in tags} for tag in EXPECTED_TAGS],
        "runtime_dirs": runtime_dirs,
        "virtualhome_evidence": virtualhome_evidence,
        "resource_profile": resource_profile,
        "tracked_violation_count": len(tracked_violations),
        "tracked_violations": tracked_violations,
        "technical_report_build_status": pdf_status,
        "notes": [
            "Ignored runtime outputs/dist/submission bundles are warnings, not failures.",
            "Tracked datasets, images, executables, scene assets, model weights, or zip files are failures.",
        ],
    }


def _virtualhome_evidence_status() -> Dict[str, Any]:
    version_docs = []
    required_code = []
    for rel in VIRTUALHOME_EVIDENCE_FILES:
        item = {"path": rel, "exists": (PROJECT_ROOT / rel).exists()}
        if rel.startswith("docs/version_status"):
            version_docs.append(item)
        else:
            required_code.append(item)

    output_dir = PROJECT_ROOT / "outputs" / "virtualhome_spike"
    output_artifacts = []
    for rel in VIRTUALHOME_OUTPUT_ARTIFACTS:
        path = output_dir / rel
        output_artifacts.append(
            {
                "path": f"outputs/virtualhome_spike/{rel}",
                "exists": path.exists(),
                "kind": "directory" if path.is_dir() else "file",
            }
        )
    return {
        "description": "VirtualHome evidence artifacts are optional runtime outputs. Presence is recorded for audit, but outputs must stay untracked.",
        "version_docs": version_docs,
        "required_code": required_code,
        "output_dir_exists": output_dir.exists(),
        "output_artifacts": output_artifacts,
    }


def _resource_profile_status() -> Dict[str, Any]:
    output_dir = PROJECT_ROOT / "outputs" / "resource_profile"
    return {
        "description": "Resource profile artifacts are optional runtime outputs. Presence is recorded for audit, but outputs must stay untracked.",
        "helpers": [{"path": rel, "exists": (PROJECT_ROOT / rel).exists()} for rel in RESOURCE_PROFILE_HELPERS],
        "output_dir_exists": output_dir.exists(),
        "artifacts": [
            {
                "path": f"outputs/resource_profile/{rel}",
                "exists": (output_dir / rel).exists(),
            }
            for rel in RESOURCE_PROFILE_ARTIFACTS
        ],
    }


def _tracked_violations(tracked: List[str]) -> List[str]:
    violations: List[str] = []
    for rel in tracked:
        rel_path = Path(rel)
        if rel_path.parts and rel_path.parts[0] == PROJECT_ROOT.name:
            parts = set(rel_path.parts[1:])
            suffix = rel_path.suffix.lower()
            normalized = rel_path.as_posix().lower()
            is_allowed_fixture = normalized.endswith("tests/fixtures/alfred/sample_traj_data.json")
            if is_allowed_fixture:
                continue
            if parts & FORBIDDEN_TRACKED_PARTS or suffix in FORBIDDEN_TRACKED_SUFFIXES:
                violations.append(rel)
            if "alfred" in normalized and "tests/fixtures/alfred/" not in normalized and suffix == ".json":
                violations.append(rel)
            if "traj_data.json" in normalized and "tests/fixtures/alfred/" not in normalized:
                violations.append(rel)
    return sorted(set(violations))


def _git_lines(args: List[str]) -> List[str]:
    try:
        output = subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return []
    return [line for line in output.splitlines() if line.strip()]


def _markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Pre-Submission Audit Report",
        "",
        f"- success: `{report['success']}`",
        f"- timestamp: `{report['timestamp']}`",
        f"- project_root: `{report['project_root']}`",
        f"- latest_test_suite_report: `{report['latest_test_suite_report']}`",
        "",
        "## Failures",
        "",
    ]
    failures = report.get("failures", [])
    lines.extend([f"- {item}" for item in failures] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings", [])
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    lines.extend(["", "## Required Files", "", "| file | exists |", "|---|---:|"])
    for item in report.get("required_files", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.extend(["", "## Dirty Files", ""])
    dirty = report.get("dirty_files", [])
    lines.extend([f"- `{item}`" for item in dirty] or ["- none"])
    lines.extend(["", "## Tracked Artifact Violations", ""])
    violations = report.get("tracked_violations", [])
    lines.extend([f"- `{item}`" for item in violations] or ["- none"])
    lines.extend(["", "## VirtualHome Evidence", ""])
    vh = report.get("virtualhome_evidence", {})
    lines.append(vh.get("description", ""))
    lines.extend(["", "### Version Docs", "", "| file | exists |", "|---|---:|"])
    for item in vh.get("version_docs", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.extend(["", "### Evidence Helpers", "", "| file | exists |", "|---|---:|"])
    for item in vh.get("required_code", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.extend(["", "### Local Runtime Artifacts", "", "| artifact | exists |", "|---|---:|"])
    for item in vh.get("output_artifacts", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.extend(["", "## Resource Profile", ""])
    rp = report.get("resource_profile", {})
    lines.append(rp.get("description", ""))
    lines.extend(["", "### Helpers", "", "| file | exists |", "|---|---:|"])
    for item in rp.get("helpers", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.extend(["", "### Local Runtime Artifacts", "", "| artifact | exists |", "|---|---:|"])
    for item in rp.get("artifacts", []):
        lines.append(f"| `{item['path']}` | `{item['exists']}` |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
