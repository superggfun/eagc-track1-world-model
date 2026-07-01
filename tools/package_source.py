from __future__ import annotations

import json
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "dist" / "source.zip"

INCLUDE_DIRS = [
    "src",
    "tests",
    "tools",
    "assets",
    "docs",
    "submission_package",
    "docker",
    "scripts",
    "reports",
]
INCLUDE_FILES = [
    ".dockerignore",
    ".gitignore",
    "README.md",
    "Dockerfile",
    "main.py",
    "sitecustomize.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements-report.txt",
    "requirements-optional-sim.txt",
    "SUBMISSION_VERSION.txt",
    "config.yaml",
]

EXCLUDED_DIR_PARTS = {
    ".git",
    ".venv",
    ".venv-ai2thor",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "outputs",
    "submission_bundle",
    "source_pack",
}
EXCLUDED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".zip", ".pyc", ".pyo"}
GMAIL_SAFE_ARCHIVE_SUFFIX_RENAMES = {
    ".ps1": ".ps1.txt",
}
ALLOWED_IMAGE_FIXTURES = {
    "assets/test_sequences/bedroom_sequence/frame_000.png",
    "assets/test_sequences/bedroom_sequence/frame_001.png",
    "assets/test_sequences/bedroom_sequence/frame_002.png",
}
ALLOWED_IMAGE_PREFIXES = {
    "assets/test_sequences/virtualhome_exploration/frames/frame_",
}
FORBIDDEN_MARKERS = {
    "/outputs/",
    "/.venv-ai2thor/",
    "/dist/",
    "/source_pack/",
    "/submission_bundle/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/build/",
}


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    missing = _missing_expected_paths()
    candidates = sorted(_iter_source_files(), key=lambda path: path.as_posix())
    packaged: list[str] = []
    with zipfile.ZipFile(OUTPUT_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        renamed_entries: dict[str, str] = {}
        for abs_path in candidates:
            rel_path = abs_path.relative_to(PROJECT_ROOT)
            if _is_excluded(rel_path):
                continue
            archive_name = _archive_name(rel_path)
            archive.write(abs_path, archive_name)
            packaged.append(archive_name)
            if archive_name != rel_path.as_posix():
                renamed_entries[rel_path.as_posix()] = archive_name
        manifest = {
            "layout": "flat-src",
            "included_count": len(packaged),
            "included_roots": INCLUDE_DIRS,
            "included_files": INCLUDE_FILES,
            "missing_expected_paths": missing,
            "excluded": sorted(EXCLUDED_DIR_PARTS),
            "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
            "allowed_image_fixtures": sorted(ALLOWED_IMAGE_FIXTURES),
            "allowed_image_prefixes": sorted(ALLOWED_IMAGE_PREFIXES),
            "gmail_safe_archive_suffix_renames": renamed_entries,
        }
        archive.writestr("source_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        packaged.append("source_manifest.json")
    violations = _find_violations(packaged)
    if violations:
        print("Source package contains excluded paths:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Packaged source files: {len(packaged)}")
    if missing:
        print("Missing optional/expected paths recorded in source_manifest.json:")
        for path in missing:
            print(f"- {path}")
    print(
        "Verified exclusions: outputs, dist, submission_bundle, caches, virtualenvs, zip files, "
        "and local images except the synthetic visual fixtures and selected VirtualHome replay keyframes."
    )
    return 0


def _iter_source_files() -> set[Path]:
    files: set[Path] = set()
    for rel in INCLUDE_FILES:
        path = PROJECT_ROOT / rel
        if path.is_file():
            files.add(path)
    for rel in INCLUDE_DIRS:
        root = PROJECT_ROOT / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                files.add(path)
    return files


def _missing_expected_paths() -> list[str]:
    return [rel for rel in [*INCLUDE_FILES, *INCLUDE_DIRS] if not (PROJECT_ROOT / rel).exists()]


def _is_excluded(path: Path) -> bool:
    posix = path.as_posix()
    if _is_allowed_image(posix):
        return False
    if set(path.parts) & EXCLUDED_DIR_PARTS:
        return True
    if any(part.endswith(".egg-info") for part in path.parts):
        return True
    if posix.startswith("assets/images/unused/"):
        return True
    return path.suffix.lower() in EXCLUDED_SUFFIXES


def _archive_name(path: Path) -> str:
    posix = path.as_posix()
    replacement = GMAIL_SAFE_ARCHIVE_SUFFIX_RENAMES.get(path.suffix.lower())
    if not replacement:
        return posix
    return posix[: -len(path.suffix)] + replacement


def _find_violations(paths: list[str]) -> list[str]:
    violations = []
    for path in paths:
        normalized = "/" + path.replace("\\", "/")
        if any(marker in normalized for marker in FORBIDDEN_MARKERS):
            violations.append(path)
            continue
        suffix = Path(path).suffix.lower()
        if suffix in EXCLUDED_SUFFIXES and not _is_allowed_image(path):
            violations.append(path)
    return violations


def _is_allowed_image(path: str) -> bool:
    return path in ALLOWED_IMAGE_FIXTURES or any(path.startswith(prefix) for prefix in ALLOWED_IMAGE_PREFIXES)


if __name__ == "__main__":
    raise SystemExit(main())
