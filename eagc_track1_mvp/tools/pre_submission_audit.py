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
        "tracked_violation_count": len(tracked_violations),
        "tracked_violations": tracked_violations,
        "technical_report_build_status": pdf_status,
        "notes": [
            "Ignored runtime outputs/dist/submission bundles are warnings, not failures.",
            "Tracked datasets, images, executables, scene assets, model weights, or zip files are failures.",
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
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
