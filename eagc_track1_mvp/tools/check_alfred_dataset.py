from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


OUTPUT_PATH = Path("outputs/alfred_offline/env_status.json")


def _config_value(section: str, key: str) -> str:
    config_path = Path("config.yaml")
    if not config_path.exists():
        return ""
    current_section = ""
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1]
            continue
        if current_section == section and line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def candidate_roots() -> List[Path]:
    values = [
        os.environ.get("ALFRED_DATASET_ROOT", ""),
        _config_value("alfred", "dataset_root"),
        "data/alfred",
        "datasets/alfred",
        str(Path.home() / "Documents" / "Datasets" / "ALFRED"),
        str(Path.home() / "Downloads" / "ALFRED"),
    ]
    return _unique_paths([Path(value) for value in values if value])


def candidate_sample_paths() -> List[Path]:
    values = [
        os.environ.get("ALFRED_SAMPLE_TRAJ_PATH", ""),
        _config_value("alfred", "sample_traj_path"),
    ]
    return _unique_paths([Path(value) for value in values if value])


def collect_status(max_scan: int = 100) -> Dict[str, Any]:
    sample_candidates = candidate_sample_paths()
    root_candidates = candidate_roots()
    traj_files: List[Path] = []
    for sample in sample_candidates:
        if sample.exists() and sample.is_file():
            traj_files.append(sample)
    for root in root_candidates:
        if root.exists() and root.is_dir():
            for path in root.rglob("traj_data.json"):
                traj_files.append(path)
                if len(traj_files) >= max_scan:
                    break
        if len(traj_files) >= max_scan:
            break

    json_candidates = _json_candidates(root_candidates, max_scan)
    selected = _unique_paths(traj_files)[0] if traj_files else None
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": bool(selected),
        "reason": "alfred_dataset_found" if selected else "missing_alfred_dataset",
        "selected_traj_path": str(selected) if selected else "",
        "traj_data_count": len(_unique_paths(traj_files)),
        "traj_data_paths": [str(path) for path in _unique_paths(traj_files)[:20]],
        "json_candidate_count": len(json_candidates),
        "json_candidates": [str(path) for path in json_candidates[:20]],
        "candidate_roots": [{"path": str(path), "exists": path.exists()} for path in root_candidates],
        "candidate_sample_paths": [{"path": str(path), "exists": path.exists()} for path in sample_candidates],
        "download_hint": "",
    }
    if not selected:
        status["download_hint"] = (
            "Please download ALFRED dataset manually and set ALFRED_DATASET_ROOT or ALFRED_SAMPLE_TRAJ_PATH. "
            "Do not commit ALFRED data into git."
        )
    return status


def write_status(status: Dict[str, Any], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_candidates(roots: List[Path], max_scan: int) -> List[Path]:
    candidates: List[Path] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*.json"):
            if path.name == "traj_data.json" or _looks_like_task_json(path):
                candidates.append(path)
            if len(candidates) >= max_scan:
                return _unique_paths(candidates)
    return _unique_paths(candidates)


def _looks_like_task_json(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
    except OSError:
        return False
    return any(token in text for token in ["instruction", "task_desc", "high_pddl", "low_actions", "plan"])


def _unique_paths(paths: List[Path]) -> List[Path]:
    seen: set[str] = set()
    unique: List[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for a local ALFRED offline dataset or sample trajectory.")
    parser.add_argument("--max-scan", type=int, default=100)
    args = parser.parse_args()
    status = collect_status(max_scan=args.max_scan)
    write_status(status)
    print(f"ALFRED dataset status written to {OUTPUT_PATH}")
    if status["success"]:
        print(f"ALFRED sample trajectory found: {status['selected_traj_path']}")
    else:
        print(f"ALFRED dataset not ready: {status['reason']}")
        print(status["download_hint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
