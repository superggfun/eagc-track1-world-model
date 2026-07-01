from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "final_submission"
REQUIRED_TAG = "v0.17.1-final-submission-dry-run"
EXPECTED_HANDOFF_TAG = "v0.17.2-final-submission-handoff"

FORBIDDEN_DIR_PARTS = {
    "outputs",
    "dist",
    "submission_bundle",
    "source_pack",
    "images",
    "datasets",
    ".venv",
    ".venv-ai2thor",
    "__pycache__",
}
FORBIDDEN_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".mp4",
    ".avi",
    ".mov",
    ".zip",
    ".exe",
    ".dll",
    ".unity3d",
    ".safetensors",
    ".bin",
    ".gguf",
    ".pt",
    ".pth",
}
FORBIDDEN_NAME_MARKERS = {
    "virtualhome.exe",
    "windows_exec.zip",
    "debug_qwen_raw",
    "qwen_response_summary.json",
    "raw_qwen",
}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    json_path = OUTPUT_DIR / "github_push_readiness.json"
    md_path = OUTPUT_DIR / "github_push_readiness.md"
    report["report_json"] = str(json_path)
    report["report_md"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(f"GitHub push readiness written to {json_path}")
    print(f"GitHub push readiness written to {md_path}")
    if report["failures"]:
        print("GitHub push readiness failed:")
        for failure in report["failures"]:
            print(f"- {failure}")
        return 1
    print("GitHub push readiness passed with warnings only." if report["warnings"] else "GitHub push readiness passed.")
    return 0


def build_report() -> dict[str, Any]:
    dirty = _git_lines(["status", "--short"])
    tracked = _git_lines(["ls-files"])
    tags = set(_git_lines(["tag", "--list"]))
    remotes = _git_lines(["remote", "-v"])
    branch = _git_scalar(["branch", "--show-current"])
    head = _git_scalar(["rev-parse", "--short", "HEAD"])

    failures: list[str] = []
    warnings: list[str] = []
    tracked_violations = _tracked_violations(tracked)
    if tracked_violations:
        failures.extend(f"Forbidden tracked artifact: {item}" for item in tracked_violations)
    if dirty:
        warnings.append("Working tree is dirty; commit intended source/document changes before pushing.")
    if not remotes:
        warnings.append("No git remote is configured. Add origin before pushing to GitHub.")
    if REQUIRED_TAG not in tags:
        failures.append(f"Missing required baseline tag: {REQUIRED_TAG}")
    if EXPECTED_HANDOFF_TAG not in tags:
        warnings.append(f"Expected handoff tag is not present yet: {EXPECTED_HANDOFF_TAG}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "success": not failures,
        "failures": failures,
        "warnings": warnings,
        "branch": branch,
        "head": head,
        "remote_origin_exists": any(line.startswith("origin\t") for line in remotes),
        "remotes": remotes,
        "required_tags": [
            {"tag": REQUIRED_TAG, "exists": REQUIRED_TAG in tags},
            {"tag": EXPECTED_HANDOFF_TAG, "exists": EXPECTED_HANDOFF_TAG in tags},
        ],
        "dirty_files": dirty,
        "tracked_violation_count": len(tracked_violations),
        "tracked_violations": tracked_violations,
        "notes": [
            "Ignored outputs, dist, submission_bundle, and local simulator/model artifacts may exist locally.",
            "This check fails only when those artifacts are tracked by git.",
            "The v0.17.2 tag is expected to be missing before the handoff commit is created.",
        ],
    }


def _tracked_violations(tracked: list[str]) -> list[str]:
    violations: list[str] = []
    for rel in tracked:
        path = Path(rel)
        parts = list(path.parts)
        if parts and parts[0] == PROJECT_ROOT.name:
            parts = parts[1:]
        part_set = {part.lower() for part in parts}
        normalized = "/".join(parts).lower()
        suffix = Path(normalized).suffix
        if normalized == "outputs/.gitkeep":
            continue
        if part_set & FORBIDDEN_DIR_PARTS:
            violations.append(rel)
            continue
        if suffix in FORBIDDEN_SUFFIXES:
            if normalized == "tests/fixtures/alfred/sample_traj_data.json":
                continue
            violations.append(rel)
            continue
        if any(marker in normalized for marker in FORBIDDEN_NAME_MARKERS):
            violations.append(rel)
            continue
        if "alfred" in normalized and "tests/fixtures/alfred/" not in normalized and suffix == ".json":
            violations.append(rel)
    return sorted(set(violations))


def _git_lines(args: list[str]) -> list[str]:
    try:
        output = subprocess.check_output(["git", *args], cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return []
    return [line for line in output.splitlines() if line.strip()]


def _git_scalar(args: list[str]) -> str:
    lines = _git_lines(args)
    return lines[0] if lines else ""


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GitHub Push Readiness",
        "",
        f"- success: `{report['success']}`",
        f"- timestamp: `{report['timestamp']}`",
        f"- branch: `{report['branch']}`",
        f"- head: `{report['head']}`",
        f"- remote_origin_exists: `{report['remote_origin_exists']}`",
        "",
        "## Tags",
        "",
        "| tag | exists |",
        "|---|---:|",
    ]
    for item in report.get("required_tags", []):
        lines.append(f"| `{item['tag']}` | `{item['exists']}` |")
    lines.extend(["", "## Failures", ""])
    lines.extend([f"- {item}" for item in report.get("failures", [])] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report.get("warnings", [])] or ["- none"])
    lines.extend(["", "## Dirty Files", ""])
    lines.extend([f"- `{item}`" for item in report.get("dirty_files", [])] or ["- none"])
    lines.extend(["", "## Tracked Artifact Violations", ""])
    lines.extend([f"- `{item}`" for item in report.get("tracked_violations", [])] or ["- none"])
    lines.extend(["", "## Remotes", ""])
    lines.extend([f"- `{item}`" for item in report.get("remotes", [])] or ["- none"])
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
