from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


EXCLUDED_DIR_PARTS = {
    ".venv",
    ".venv-ai2thor",
    "__pycache__",
    ".pytest_cache",
    "outputs",
    "source_pack",
}
EXCLUDED_SUFFIXES = {".jpg", ".jpeg", ".png", ".zip"}
FORBIDDEN_MARKERS = {
    "/outputs/",
    "/.venv-ai2thor/",
    "/source_pack/",
    "/__pycache__/",
}


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    output_path = project_root / "dist" / "eagc_track1_mvp_source.zip"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tracked = subprocess.check_output(
        ["git", "-C", str(repo_root), "ls-files"],
        text=True,
        encoding="utf-8",
    ).splitlines()

    packaged = []
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in tracked:
            rel_path = Path(rel)
            if not rel_path.parts or rel_path.parts[0] != project_root.name:
                continue
            if _is_excluded(rel_path):
                continue
            abs_path = repo_root / rel_path
            if not abs_path.is_file():
                continue
            archive.write(abs_path, rel_path.as_posix())
            packaged.append(rel_path.as_posix())

    violations = _find_violations(packaged)
    if violations:
        print("Source package contains excluded paths:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Wrote {output_path}")
    print(f"Packaged tracked source files: {len(packaged)}")
    print("Verified exclusions: outputs, .venv-ai2thor, source_pack, __pycache__, zip files, and local images.")
    return 0


def _is_excluded(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
        return True
    return path.suffix.lower() in EXCLUDED_SUFFIXES


def _find_violations(paths: list[str]) -> list[str]:
    violations = []
    for path in paths:
        normalized = "/" + path.replace("\\", "/")
        if any(marker in normalized for marker in FORBIDDEN_MARKERS):
            violations.append(path)
            continue
        if Path(path).suffix.lower() in EXCLUDED_SUFFIXES:
            violations.append(path)
    return violations


if __name__ == "__main__":
    raise SystemExit(main())
