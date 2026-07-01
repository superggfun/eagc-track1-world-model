"""Centralised project-path utility.

After the flat-``src/`` migration, all modules that need the project
root should import from here instead of hard-coding ``parents[N]``.
"""

from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Walk upwards from *start* until we find ``README.md`` + ``src/``."""
    current = (start or Path(__file__)).resolve()
    for parent in [current, *current.parents]:
        if (parent / "README.md").exists() and (parent / "src").is_dir():
            return parent
    return Path.cwd().resolve()


PROJECT_ROOT: Path = find_project_root()


def project_path(*parts: str) -> Path:
    """Join *parts* to the project root."""
    return PROJECT_ROOT.joinpath(*parts)


def src_path(*parts: str) -> Path:
    """Join *parts* to ``src/``."""
    return PROJECT_ROOT.joinpath("src", *parts)
