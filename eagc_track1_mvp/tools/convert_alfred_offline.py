from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_adapters.alfred_offline_adapter import convert_traj_file
from tools.check_alfred_dataset import collect_status, write_status as write_env_status


OUTPUT_DIR = Path("outputs/alfred_offline")


def _find_traj_files(dataset_root: Path, max_samples: int) -> List[Path]:
    if not dataset_root.exists() or not dataset_root.is_dir():
        return []
    files = []
    for path in dataset_root.rglob("traj_data.json"):
        files.append(path)
        if len(files) >= max_samples:
            break
    return files


def run_conversion(traj_path: Path | None, dataset_root: Path | None, max_samples: int, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    env_status = collect_status(max_scan=max(100, max_samples))
    write_env_status(env_status)

    selected = traj_path if traj_path else None
    discovered: List[Path] = []
    if selected is None and dataset_root is not None:
        discovered = _find_traj_files(dataset_root, max_samples=max_samples)
        selected = discovered[0] if discovered else None
    if selected is None and env_status.get("selected_traj_path"):
        selected = Path(str(env_status["selected_traj_path"]))

    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "reason": "",
        "selected_traj_path": str(selected) if selected else "",
        "dataset_root": str(dataset_root) if dataset_root else "",
        "discovered_traj_paths": [str(path) for path in discovered],
        "world_model_path": "",
        "episode_log_path": "",
        "alfred_task_summary_path": "",
        "error_type": "",
        "error_message": "",
        "download_hint": "",
    }

    if selected is None or not selected.exists():
        status["reason"] = "missing_alfred_dataset"
        status["download_hint"] = env_status.get("download_hint", "Please download ALFRED dataset manually.")
        _write_status(status, output_dir)
        return status

    try:
        paths = convert_traj_file(selected, output_dir)
        status.update(
            {
                "success": True,
                "reason": "alfred_offline_conversion_complete",
                "world_model_path": str(paths["world_model"]),
                "episode_log_path": str(paths["episode_log"]),
                "alfred_task_summary_path": str(paths["summary"]),
            }
        )
    except Exception as exc:
        status["reason"] = "alfred_conversion_error"
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)

    _write_status(status, output_dir)
    return status


def _write_status(status: Dict[str, Any], output_dir: Path) -> None:
    path = output_dir / "status.json"
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ALFRED offline conversion status written to {path}")
    print(json.dumps(status, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert an ALFRED offline traj_data.json into local MVP artifacts.")
    parser.add_argument("--traj-path", default="")
    parser.add_argument("--dataset-root", default="")
    parser.add_argument("--max-samples", type=int, default=1)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    status = run_conversion(
        Path(args.traj_path) if args.traj_path else None,
        Path(args.dataset_root) if args.dataset_root else None,
        max(1, args.max_samples),
        Path(args.output_dir),
    )
    return 0 if status.get("success") or status.get("reason") == "missing_alfred_dataset" else 1


if __name__ == "__main__":
    raise SystemExit(main())
