from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.check_virtualhome_env import collect_status


OUTPUT_PATH = Path("outputs/virtualhome_spike/setup_hint.json")


def _candidate_repo_paths() -> List[Path]:
    candidates = []
    env_path = os.environ.get("VIRTUALHOME_REPO_PATH")
    if env_path:
        candidates.append(Path(env_path))
    roots = [
        Path.cwd(),
        Path.cwd().parent,
        Path.home(),
        Path.home() / "Documents",
        Path.home() / "Downloads",
    ]
    names = ["VirtualHome", "virtualhome", "virtual-home"]
    for root in roots:
        for name in names:
            candidates.append(root / name)
    seen = set()
    unique: List[Path] = []
    for candidate in candidates:
        value = str(candidate)
        if value not in seen:
            unique.append(candidate)
            seen.add(value)
    return unique


def _repo_has_api(path: Path) -> bool:
    return any(
        (path / relative).exists()
        for relative in [
            Path("simulation/unity_simulator/comm_unity.py"),
            Path("virtualhome/simulation/unity_simulator/comm_unity.py"),
        ]
    )


def build_hint() -> Dict[str, Any]:
    env_status = collect_status()
    candidate_repos = [
        {
            "path": str(path),
            "exists": path.exists(),
            "looks_like_virtualhome_repo": path.exists() and _repo_has_api(path),
        }
        for path in _candidate_repo_paths()
    ]
    likely_repos = [item for item in candidate_repos if item["looks_like_virtualhome_repo"]]

    hints: List[str] = []
    if not env_status.get("virtualhome_api_available"):
        hints.append(
            "VirtualHome Python API is not importable. If you already cloned VirtualHome, set "
            "VIRTUALHOME_REPO_PATH to that repository. Otherwise clone/download it manually and "
            "install it in a separate environment or use editable install from that repo."
        )
    if not env_status.get("virtualhome_simulator_path"):
        hints.append(
            "VirtualHome Windows Unity executable path is not configured. Download the Windows "
            "Unity simulator executable manually and set VIRTUALHOME_SIMULATOR_PATH to the .exe path."
        )
    elif not env_status.get("simulator_executable_exists"):
        hints.append("Configured VirtualHome simulator path does not exist; verify the .exe path.")
    hints.append("Do not commit the VirtualHome executable, Unity assets, videos, images, or large scene files.")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env_status": env_status,
        "candidate_repositories": candidate_repos,
        "likely_repositories": likely_repos,
        "manual_install_hint": [
            "$env:VIRTUALHOME_REPO_PATH = 'C:\\path\\to\\VirtualHome'",
            "$env:VIRTUALHOME_SIMULATOR_PATH = 'C:\\path\\to\\VirtualHome.exe'",
            "python tools/check_virtualhome_env.py",
            "python tools/test_virtualhome_windows_spike.py",
        ],
        "hints": hints,
        "success": bool(env_status.get("success")),
    }


def main() -> int:
    hint = build_hint()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(hint, indent=2), encoding="utf-8")
    print(f"VirtualHome setup hint written to {OUTPUT_PATH}")
    for message in hint["hints"]:
        print(f"- {message}")
    if hint["likely_repositories"]:
        print("Likely VirtualHome repositories:")
        for item in hint["likely_repositories"]:
            print(f"- {item['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
