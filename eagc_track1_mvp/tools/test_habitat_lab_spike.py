from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "habitat_lab_status.json"
    status = _run_lab_probe()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print(f"Habitat-Lab spike status written to {status_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Habitat-Lab availability probe.")
    parser.add_argument("--output-dir", default="outputs/habitat_spike")
    return parser.parse_args()


def _run_lab_probe() -> dict[str, Any]:
    started = time.perf_counter()
    status: dict[str, Any] = {
        "success": False,
        "habitat_importable": False,
        "habitat_version": None,
        "config_api_available": False,
        "candidate_config_paths": [],
        "dataset_dirs": [],
        "elapsed_seconds": 0.0,
        "reason": "",
        "error_type": "",
        "error_message": "",
    }
    try:
        import habitat

        status["habitat_importable"] = True
        status["habitat_version"] = getattr(habitat, "__version__", None)
        status["config_api_available"] = _has_config_api()
        status["candidate_config_paths"] = _candidate_config_paths()
        status["dataset_dirs"] = _dataset_dirs()
        if not status["candidate_config_paths"]:
            status.update(
                {
                    "success": False,
                    "reason": "missing_habitat_lab_config",
                    "error_message": "Habitat-Lab import succeeded, but no local benchmark/config YAML was found.",
                }
            )
        elif not any(item["exists"] for item in status["dataset_dirs"]):
            status.update(
                {
                    "success": False,
                    "reason": "missing_habitat_lab_dataset",
                    "error_message": "Habitat-Lab config files exist, but common dataset directories are missing.",
                }
            )
        else:
            status.update(
                {
                    "success": True,
                    "reason": "",
                    "error_message": "Habitat-Lab appears importable and local config/data candidates exist.",
                }
            )
    except Exception as exc:
        status.update(
            {
                "success": False,
                "reason": "habitat_lab_import_failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-5000:],
            }
        )
    finally:
        status["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return status


def _has_config_api() -> bool:
    try:
        import habitat.config  # noqa: F401

        return True
    except Exception:
        return False


def _candidate_config_paths() -> list[str]:
    roots = [
        PROJECT_ROOT / "habitat-lab" / "habitat-lab" / "habitat" / "config",
        PROJECT_ROOT / "habitat-lab" / "habitat" / "config",
        PROJECT_ROOT / "configs",
        PROJECT_ROOT / "data",
    ]
    candidates: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.rglob("*.yaml")):
            candidates.append(str(item))
            if len(candidates) >= 20:
                return candidates
    return candidates


def _dataset_dirs() -> list[dict[str, Any]]:
    candidates = [
        PROJECT_ROOT / "data" / "datasets",
        PROJECT_ROOT / "data" / "scene_datasets",
        PROJECT_ROOT / "habitat-lab" / "data",
    ]
    return [{"path": str(path), "exists": path.exists(), "is_dir": path.is_dir()} for path in candidates]


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
