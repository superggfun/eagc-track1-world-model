from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env_adapters.registry import list_adapters

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "adapter_capabilities"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    adapters = list_adapters()
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "adapter_count": len(adapters),
        "adapters": adapters,
        "notes": [
            "This registry reports capabilities only; it does not start simulators.",
            "Validated backends are LocalSim and VirtualHome. ALFRED offline is validated only for a synthetic fixture.",
            "AI2-THOR, Habitat, and ProcTHOR remain reserved adapter targets, not validated backends.",
        ],
    }
    json_path = OUTPUT_DIR / "adapter_capabilities.json"
    md_path = OUTPUT_DIR / "adapter_capabilities.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(f"Adapter capabilities written to {json_path}")
    print(f"Adapter capabilities written to {md_path}")
    for adapter in adapters:
        print(
            f"{adapter['adapter_name']}: validated={adapter['validated']} "
            f"status={adapter['validation_status']} blockers={adapter['known_blockers']}"
        )
    return 0


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Environment Adapter Capabilities",
        "",
        f"- timestamp: `{report['timestamp']}`",
        f"- adapter_count: `{report['adapter_count']}`",
        "",
        "| adapter | validated | status | scene graph | frame export | actions | online closed loop | blockers |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for item in report["adapters"]:
        lines.append(
            "| `{adapter_name}` | `{validated}` | `{validation_status}` | `{supports_scene_graph}` | "
            "`{supports_frame_export}` | `{supports_action_execution}` | `{supports_online_closed_loop}` | {blockers} |".format(
                blockers=", ".join(f"`{value}`" for value in item.get("known_blockers", [])) or "none",
                **item,
            )
        )
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report.get("notes", []))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
