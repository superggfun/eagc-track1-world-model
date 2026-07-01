from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clients.qwen_client import QwenClient, QwenClientError
from perception.json_utils import extract_json_from_text


OUTPUT_PATH = Path("outputs/qwen_text_smoke/status.json")


def _load_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    path = PROJECT_ROOT / "config.yaml"
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or raw_line.startswith(" "):
            continue
        if ":" not in line or line.endswith(":"):
            continue
        key, value = line.split(":", 1)
        config[key.strip()] = value.strip().strip("\"'")
    config["base_url"] = os.environ.get("QWEN_BASE_URL", config.get("base_url", "http://127.0.0.1:8000/v1"))
    config["model"] = os.environ.get("QWEN_MODEL", config.get("model", "qwen3.6-35b-nvfp4"))
    config["temperature"] = float(os.environ.get("QWEN_TEMPERATURE", config.get("temperature", "0.0")))
    config["max_tokens"] = int(os.environ.get("QWEN_MAX_TOKENS", "64"))
    return config


def main() -> int:
    config = _load_config()
    started = time.perf_counter()
    status: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "base_url": config["base_url"],
        "model": config["model"],
        "latency_seconds": None,
        "parsed_ok": False,
        "error_type": "",
        "error_message": "",
        "response_preview": "",
    }
    client = QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=0.0,
        max_tokens=min(int(config["max_tokens"]), 64),
        timeout_seconds=60,
    )
    messages = [
        {
            "role": "system",
            "content": "Return only compact JSON. No markdown.",
        },
        {
            "role": "user",
            "content": "Return exactly this JSON object with no extra text: {\"ok\": true}",
        },
    ]
    try:
        raw = client.chat_text(messages, temperature=0.0, max_tokens=64)
        status["response_preview"] = raw[:300]
        parsed = json.loads(extract_json_from_text(raw))
        status["parsed_ok"] = parsed.get("ok") is True
        status["success"] = status["parsed_ok"]
        if not status["success"]:
            status["error_message"] = f"Expected ok=true JSON, got {parsed!r}"
    except (QwenClientError, json.JSONDecodeError, ValueError) as exc:
        status["error_type"] = type(exc).__name__
        status["error_message"] = str(exc)
    finally:
        status["latency_seconds"] = round(time.perf_counter() - started, 3)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Qwen text smoke status written to {OUTPUT_PATH}")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
