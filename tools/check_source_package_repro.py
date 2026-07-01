from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPRO_ROOT = PROJECT_ROOT / "dist" / "repro_check"
REPORT_PATH = PROJECT_ROOT / "dist" / "repro_check_report.json"
FORBIDDEN_DIRS = {
    "outputs",
    "dist",
    "source_pack",
    "submission_bundle",
    ".venv",
    ".venv-ai2thor",
    "__pycache__",
    ".pytest_cache",
    "build",
}
FORBIDDEN_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".zip", ".pyc", ".pyo"}
ALLOWED_IMAGE_FIXTURES = {
    "assets/test_sequences/bedroom_sequence/frame_000.png",
    "assets/test_sequences/bedroom_sequence/frame_001.png",
    "assets/test_sequences/bedroom_sequence/frame_002.png",
}
ALLOWED_IMAGE_PREFIXES = {
    "assets/test_sequences/virtualhome_exploration/frames/frame_",
}
REQUIRED_FILES = [
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-report.txt",
    "requirements-optional-sim.txt",
    "main.py",
    "sitecustomize.py",
    "config.yaml",
    "Dockerfile",
    "docker/README_DOCKER.md",
    "docker/docker_run_examples.md",
    "tools/run_test_suite.py",
    "submission_package/README_submission.md",
    "submission_package/training_resource_disclosure.md",
    "submission_package/reproducibility_statement.md",
    "submission_package/system_limitations.md",
    "assets/test_sequences/bedroom_sequence/frame_000.png",
    "assets/test_sequences/bedroom_sequence/frame_001.png",
    "assets/test_sequences/bedroom_sequence/frame_002.png",
    "assets/test_sequences/virtualhome_exploration/frame_manifest.json",
    "assets/test_sequences/virtualhome_exploration/frames/frame_000.jpg",
    "assets/test_sequences/virtualhome_exploration/frames/frame_011.jpg",
]
SOURCE_DIRS = [
    "src",
    "tools",
    "tests",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source package reproducibility in a clean directory.")
    parser.add_argument("--zip-path", default="dist/source.zip")
    args = parser.parse_args()

    zip_path = _resolve_project_path(args.zip_path)
    report: dict[str, Any] = {
        "zip_path": str(zip_path),
        "extract_dir": str(REPRO_ROOT),
        "passed": False,
        "checks": {},
        "commands": [],
    }
    try:
        if not zip_path.exists():
            raise CheckError(f"Missing source zip: {zip_path}")
        _reset_repro_dir()
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            report["zip_entry_count"] = len(names)
            report["checks"]["zip_forbidden_paths"] = _forbidden_paths(names)
            if report["checks"]["zip_forbidden_paths"]:
                raise CheckError("Source zip contains forbidden paths.")
            archive.extractall(REPRO_ROOT)

        project_dir = _find_extracted_project_dir(REPRO_ROOT)
        report["project_dir"] = str(project_dir)
        extracted_paths = _relative_files_and_dirs(project_dir)
        report["checks"]["extracted_forbidden_paths"] = _forbidden_paths(extracted_paths)
        if report["checks"]["extracted_forbidden_paths"]:
            raise CheckError("Extracted source contains forbidden paths.")

        missing = [path for path in REQUIRED_FILES if not (project_dir / path).exists()]
        report["checks"]["required_files_missing"] = missing
        if missing:
            raise CheckError("Extracted source is missing required files.")

        report["commands"].append(_run([sys.executable, "-m", "compileall", *SOURCE_DIRS], project_dir))
        report["commands"].append(_run([sys.executable, "tools/run_test_suite.py", "--tier", "fast"], project_dir))
        failed = [command for command in report["commands"] if command["returncode"] != 0]
        if failed:
            raise CheckError("One or more reproducibility commands failed.")

        report["passed"] = True
        return 0
    except CheckError as exc:
        report["error"] = str(exc)
        return 1
    finally:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Repro check report written to {REPORT_PATH}")
        if report.get("passed"):
            print("Source package reproducibility check passed.")
        else:
            print(f"Source package reproducibility check failed: {report.get('error', 'unknown error')}")


class CheckError(Exception):
    pass


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _reset_repro_dir() -> None:
    if REPRO_ROOT.exists():
        resolved = REPRO_ROOT.resolve()
        dist_root = (PROJECT_ROOT / "dist").resolve()
        if dist_root not in resolved.parents:
            raise CheckError(f"Refusing to remove unexpected path: {resolved}")
        shutil.rmtree(REPRO_ROOT)
    REPRO_ROOT.mkdir(parents=True, exist_ok=True)


def _find_extracted_project_dir(root: Path) -> Path:
    direct = root / PROJECT_ROOT.name
    if direct.exists() and direct.is_dir():
        return direct
    candidates = [path for path in root.iterdir() if path.is_dir() and (path / "main.py").exists()]
    if len(candidates) == 1:
        return candidates[0]
    if (root / "main.py").exists():
        return root
    raise CheckError("Could not locate extracted project directory.")


def _relative_files_and_dirs(root: Path) -> list[str]:
    paths = []
    for path in root.rglob("*"):
        paths.append(path.relative_to(root).as_posix() + ("/" if path.is_dir() else ""))
    return paths


def _forbidden_paths(paths: list[str]) -> list[str]:
    violations = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/").strip("/")
        if _is_allowed_image(path):
            continue
        if path.startswith("assets/images/unused/"):
            violations.append(raw_path)
            continue
        parts = [part for part in path.split("/") if part]
        if any(part in FORBIDDEN_DIRS for part in parts):
            violations.append(raw_path)
            continue
        if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(raw_path)
    return violations


def _is_allowed_image(path: str) -> bool:
    return path in ALLOWED_IMAGE_FIXTURES or any(path.startswith(prefix) for prefix in ALLOWED_IMAGE_PREFIXES)


def _run(command: list[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    print(f"\n$ {' '.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout_tail = _tail(completed.stdout)
    stderr_tail = _tail(completed.stderr)
    if stdout_tail:
        print(stdout_tail)
    if stderr_tail:
        print(stderr_tail, file=sys.stderr)
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "latency_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


def _tail(text: str, max_lines: int = 80) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


if __name__ == "__main__":
    raise SystemExit(main())
