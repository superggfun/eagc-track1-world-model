from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "dist" / "docker_context_check_report.json"
REQUIRED_FILES = [
    "Dockerfile",
    ".dockerignore",
    "docker/.dockerignore",
    "docker/README_DOCKER.md",
    "docker/docker_run_examples.md",
]
REQUIRED_IGNORE_PATTERNS = [
    "outputs/",
    "dist/",
    "source_pack/",
    ".venv*/",
    "__pycache__/",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.zip",
    ".git/",
]
FORBIDDEN_EXISTING_PATHS = [
    "outputs",
    "dist",
    "source_pack",
    ".venv-ai2thor",
    ".venv",
    "pexels-readymade-4008334.jpg",
]
FORBIDDEN_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".zip"}


def main() -> int:
    report: dict[str, Any] = {
        "passed": False,
        "required_files_missing": [],
        "required_ignore_patterns_missing": [],
        "forbidden_unignored_paths": [],
    }
    try:
        report["required_files_missing"] = [path for path in REQUIRED_FILES if not (PROJECT_ROOT / path).exists()]
        if report["required_files_missing"]:
            raise CheckError("Required Docker files are missing.")

        patterns = _load_patterns(PROJECT_ROOT / ".dockerignore")
        report["required_ignore_patterns_missing"] = [
            pattern for pattern in REQUIRED_IGNORE_PATTERNS if pattern not in patterns
        ]
        if report["required_ignore_patterns_missing"]:
            raise CheckError("Root .dockerignore is missing required patterns.")

        violations = _find_forbidden_unignored_paths(patterns)
        report["forbidden_unignored_paths"] = violations
        if violations:
            raise CheckError("Forbidden paths are not excluded by .dockerignore.")

        report["passed"] = True
        print("Docker context check passed.")
        return 0
    except CheckError as exc:
        report["error"] = str(exc)
        print(f"Docker context check failed: {exc}")
        return 1
    finally:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Docker context report written to {REPORT_PATH}")


class CheckError(Exception):
    pass


def _load_patterns(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _find_forbidden_unignored_paths(patterns: list[str]) -> list[str]:
    violations = []
    candidates: list[Path] = []
    for rel in FORBIDDEN_EXISTING_PATHS:
        path = PROJECT_ROOT / rel
        if path.exists():
            candidates.append(path)
    for root, dirnames, filenames in os.walk(PROJECT_ROOT, topdown=True, onerror=lambda exc: None):
        root_path = Path(root)
        rel_root = root_path.relative_to(PROJECT_ROOT).as_posix()
        if rel_root == ".":
            rel_root = ""
        pruned = []
        for dirname in dirnames:
            child_rel = f"{rel_root}/{dirname}".strip("/")
            child_path = root_path / dirname
            if _is_ignored(child_rel, True, patterns):
                candidates.append(child_path)
            else:
                pruned.append(dirname)
        dirnames[:] = pruned
        for filename in filenames:
            child_path = root_path / filename
            child_rel = f"{rel_root}/{filename}".strip("/")
            if child_path.suffix.lower() in FORBIDDEN_SUFFIXES or "__pycache__" in child_path.parts:
                candidates.append(child_path)

    seen: set[str] = set()
    for path in candidates:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        if not _is_ignored(rel, path.is_dir(), patterns):
            violations.append(rel + ("/" if path.is_dir() else ""))
    return violations


def _is_ignored(rel: str, is_dir: bool, patterns: list[str]) -> bool:
    rel_dir = rel + ("/" if is_dir and not rel.endswith("/") else "")
    parts = rel.split("/")
    for pattern in patterns:
        normalized = pattern.strip("/")
        if pattern.endswith("/") and (rel_dir == pattern or rel.startswith(normalized + "/")):
            return True
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, normalized):
            return True
        if any(fnmatch.fnmatch(part, normalized) for part in parts):
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
