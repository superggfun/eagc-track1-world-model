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

from tools.check_virtualhome_env import candidate_repo_paths, candidate_simulator_paths, collect_status, repo_has_api


OUTPUT_PATH = Path("outputs/virtualhome_spike/setup_hint.json")


def _candidate_repo_paths() -> List[Path]:
    return candidate_repo_paths()


def _repo_has_api(path: Path) -> bool:
    return repo_has_api(path)


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
    simulator_candidates = [
        {
            "path": str(path),
            "exists": path.exists(),
            "is_executable_candidate": path.exists() and path.is_file() and path.suffix.lower() == ".exe",
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        }
        for path in candidate_simulator_paths()
    ]
    likely_simulators = [item for item in simulator_candidates if item["is_executable_candidate"]]

    hints: List[str] = []
    if not env_status.get("virtualhome_api_available"):
        hints.append(
            "VirtualHome Python API is not importable. If you already cloned VirtualHome, set "
            "VIRTUALHOME_REPO_PATH to that repository. Otherwise clone/download it manually and "
            "install it in a separate environment or use editable install from that repo."
        )
        hints.append(
            "Recommended manual clone command: git clone https://github.com/xavierpuigf/virtualhome.git "
            "C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome"
        )
    if not env_status.get("virtualhome_simulator_path"):
        hints.append(
            "VirtualHome Windows Unity executable path is not configured. Download the Windows "
            "Unity simulator executable manually and set VIRTUALHOME_SIMULATOR_PATH to the .exe path."
        )
    elif not env_status.get("simulator_executable_exists"):
        hints.append("Configured VirtualHome simulator path does not exist; verify the .exe path.")
    if not likely_repos:
        hints.append("Recommended repo location: C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome")
    if not likely_simulators:
        hints.append("Recommended simulator folder: C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome_simulator\\")
    hints.append("Do not commit the VirtualHome executable, Unity assets, videos, images, or large scene files.")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env_status": env_status,
        "candidate_repositories": candidate_repos,
        "likely_repositories": likely_repos,
        "candidate_simulators": simulator_candidates,
        "likely_simulators": likely_simulators,
        "manual_install_hint": [
            "git clone https://github.com/xavierpuigf/virtualhome.git C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome",
            '$env:VIRTUALHOME_REPO_PATH="C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome"',
            '$env:VIRTUALHOME_SIMULATOR_PATH="C:\\Users\\Alphay\\Documents\\ExternalTools\\virtualhome_simulator\\<actual_exe_name>.exe"',
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
    else:
        print("No local VirtualHome repository with simulation/unity_simulator/comm_unity.py was found.")
    if hint["likely_simulators"]:
        print("Likely VirtualHome simulator executables:")
        for item in hint["likely_simulators"]:
            print(f"- {item['path']}")
    else:
        print("No VirtualHome Windows simulator .exe candidate was found.")
    print("PowerShell setup example:")
    for command in hint["manual_install_hint"][:3]:
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
