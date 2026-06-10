from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "habitat_spike" / "download_status.json"
DATA_PATH = PROJECT_ROOT / "data"
SCENE_ROOT = DATA_PATH / "scene_datasets"
SCENE_SUFFIXES = {".glb", ".ply", ".obj"}


def main() -> int:
    started = time.perf_counter()
    status: dict[str, Any] = {
        "success": False,
        "uid": "habitat_test_scenes",
        "data_path": str(DATA_PATH),
        "scene_root": str(SCENE_ROOT),
        "scene_files": [],
        "scene_file_count": 0,
        "elapsed_seconds": 0.0,
        "error_type": "",
        "error_message": "",
        "command": [
            sys.executable,
            "-m",
            "habitat_sim.utils.datasets_download",
            "--uids",
            "habitat_test_scenes",
            "--data-path",
            "data/",
        ],
    }
    try:
        import habitat_sim  # noqa: F401

        DATA_PATH.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            status["command"],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
        )
        status.update(
            {
                "returncode": completed.returncode,
                "stdout_tail": _tail(completed.stdout),
                "stderr_tail": _tail(completed.stderr),
            }
        )
        scene_files = _find_scene_files()
        status["scene_files"] = [str(path) for path in scene_files]
        status["scene_file_count"] = len(scene_files)
        status["success"] = completed.returncode == 0 and bool(scene_files)
        if completed.returncode != 0:
            status["error_type"] = "DatasetDownloadFailed"
            status["error_message"] = "habitat_sim dataset downloader returned a non-zero exit code."
        elif not scene_files:
            status["error_type"] = "NoSceneFilesFound"
            status["error_message"] = "Downloader completed but no .glb/.ply/.obj files were found under data/scene_datasets/."
    except subprocess.TimeoutExpired as exc:
        status.update(
            {
                "success": False,
                "error_type": "TimeoutExpired",
                "error_message": f"Habitat test scene download exceeded {exc.timeout} seconds.",
                "stdout_tail": _tail(exc.stdout if isinstance(exc.stdout, str) else ""),
                "stderr_tail": _tail(exc.stderr if isinstance(exc.stderr, str) else ""),
            }
        )
    except Exception as exc:
        status.update(
            {
                "success": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            }
        )
    finally:
        status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"Habitat test scene download status written to {OUTPUT_PATH}")
    return 0


def _find_scene_files() -> list[Path]:
    if not SCENE_ROOT.exists():
        return []
    return sorted(
        path for path in SCENE_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in SCENE_SUFFIXES
    )


def _tail(text: str, max_chars: int = 5000) -> str:
    return text[-max_chars:] if text else ""


if __name__ == "__main__":
    raise SystemExit(main())
