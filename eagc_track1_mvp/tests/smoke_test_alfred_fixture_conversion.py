from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_adapters.alfred_offline_adapter import convert_traj_file
from validators.validate_alfred_offline_conversion import validate


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "alfred" / "sample_traj_data.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "alfred_fixture"


def main() -> int:
    if not FIXTURE_PATH.exists():
        print(f"Missing ALFRED synthetic fixture: {FIXTURE_PATH}")
        return 1
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.get("fixture_type") != "synthetic_alfred_like":
        print("Fixture must be explicitly marked fixture_type=synthetic_alfred_like.")
        return 1

    paths = convert_traj_file(FIXTURE_PATH, OUTPUT_DIR)
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "reason": "alfred_fixture_conversion_complete",
        "fixture_type": fixture.get("fixture_type"),
        "selected_traj_path": str(FIXTURE_PATH),
        "world_model_path": str(paths["world_model"]),
        "episode_log_path": str(paths["episode_log"]),
        "alfred_task_summary_path": str(paths["summary"]),
        "download_hint": "",
    }
    (OUTPUT_DIR / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    errors = validate(OUTPUT_DIR / "status.json")
    world_model = json.loads(paths["world_model"].read_text(encoding="utf-8"))
    episode_lines = [line for line in paths["episode_log"].read_text(encoding="utf-8").splitlines() if line.strip()]
    event_types = {json.loads(line).get("event_type") for line in episode_lines}
    if world_model.get("source") != "alfred_offline":
        errors.append("world_model.source must be alfred_offline.")
    if not world_model.get("task"):
        errors.append("world_model.task must be non-empty.")
    if not ({"subgoal_loaded", "action_loaded"} & event_types):
        errors.append("episode_log must include subgoal_loaded or action_loaded.")
    if not world_model.get("objects") and not world_model.get("uncertainty"):
        errors.append("world_model must include objects or uncertainty.")

    if errors:
        print("ALFRED fixture conversion smoke failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("ALFRED fixture conversion smoke passed.")
    print(f"fixture_type={fixture.get('fixture_type')}")
    print(f"task={world_model.get('task')}")
    print(f"object_count={len(world_model.get('objects', []))}")
    print(f"event_count={len(episode_lines)}")
    print(f"output_dir={OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
