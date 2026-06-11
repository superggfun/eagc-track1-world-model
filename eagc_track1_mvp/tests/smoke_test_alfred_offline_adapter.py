from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.check_alfred_dataset import collect_status, write_status
from tools.convert_alfred_offline import run_conversion
from validators.validate_alfred_offline_conversion import validate


def main() -> int:
    output_dir = Path("outputs/alfred_offline")
    env_status = collect_status()
    write_status(env_status)
    status = run_conversion(None, None, 1, output_dir)
    errors = validate(output_dir / "status.json")
    if errors:
        print("ALFRED offline smoke failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    if status.get("success"):
        print(f"ALFRED offline smoke converted: {status.get('selected_traj_path')}")
    else:
        print("ALFRED offline smoke passed with graceful missing-dataset status.")
        print(status.get("download_hint", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
