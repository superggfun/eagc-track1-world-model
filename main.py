"""Thin root wrapper that adds src/ to path and re-exports entrypoints.main."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from entrypoints.main import *  # noqa: E402, F403

if __name__ == "__main__":
    raise SystemExit(main())
