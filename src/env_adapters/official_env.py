from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from env_adapters.base import BaseEnvAdapter, adapter_capabilities


OFFICIAL_ENV_VARS = [
    "EAGC_OFFICIAL_MODE",
    "EAGC_ENV_HOST",
    "EAGC_ENV_PORT",
    "EAGC_EPISODE_ID",
    "EAGC_CONFIG_PATH",
    "EAGC_OUTPUT_DIR",
    "EAGC_ACTION_SCHEMA_PATH",
]


class OfficialRuntimeUnavailable(RuntimeError):
    """Raised when official runtime configuration or wiring is unavailable."""


@dataclass(frozen=True)
class OfficialRuntimeConfig:
    mode: str = ""
    host: str = ""
    port: str = ""
    episode_id: str = ""
    config_path: str = ""
    output_dir: str = ""
    action_schema_path: str = ""

    @classmethod
    def from_env_and_overrides(
        cls,
        *,
        episode_id: str | None = None,
        output_dir: str | Path | None = None,
        config_path: str | Path | None = None,
        action_schema_path: str | Path | None = None,
        mode: str | None = None,
        host: str | None = None,
        port: str | int | None = None,
    ) -> "OfficialRuntimeConfig":
        return cls(
            mode=str(mode if mode is not None else os.environ.get("EAGC_OFFICIAL_MODE", "")).strip(),
            host=str(host if host is not None else os.environ.get("EAGC_ENV_HOST", "")).strip(),
            port=str(port if port is not None else os.environ.get("EAGC_ENV_PORT", "")).strip(),
            episode_id=str(episode_id if episode_id is not None else os.environ.get("EAGC_EPISODE_ID", "")).strip(),
            config_path=str(config_path if config_path is not None else os.environ.get("EAGC_CONFIG_PATH", "")).strip(),
            output_dir=str(output_dir if output_dir is not None else os.environ.get("EAGC_OUTPUT_DIR", "")).strip(),
            action_schema_path=str(
                action_schema_path
                if action_schema_path is not None
                else os.environ.get("EAGC_ACTION_SCHEMA_PATH", "")
            ).strip(),
        )

    def has_runtime_hint(self) -> bool:
        return bool(self.mode or self.host or self.config_path)

    def redacted(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "host_configured": bool(self.host),
            "port_configured": bool(self.port),
            "episode_id_configured": bool(self.episode_id),
            "config_path_configured": bool(self.config_path),
            "output_dir_configured": bool(self.output_dir),
            "action_schema_path_configured": bool(self.action_schema_path),
        }


class OfficialEnvAdapter(BaseEnvAdapter):
    """Fail-closed placeholder for the future official EAGC Track 1 runtime."""

    def __init__(
        self,
        *,
        episode_id: str | None = None,
        output_dir: str | Path | None = None,
        config_path: str | Path | None = None,
        action_schema_path: str | Path | None = None,
        mode: str | None = None,
        host: str | None = None,
        port: str | int | None = None,
    ) -> None:
        self.config = OfficialRuntimeConfig.from_env_and_overrides(
            episode_id=episode_id,
            output_dir=output_dir,
            config_path=config_path,
            action_schema_path=action_schema_path,
            mode=mode,
            host=host,
            port=port,
        )
        self._action_schema = _load_action_schema(self.config.action_schema_path)

        if not self.config.has_runtime_hint():
            raise OfficialRuntimeUnavailable(
                "Official EAGC runtime is not configured. Set EAGC_OFFICIAL_MODE "
                "with the released SDK/RPC/socket/HTTP details, or pass the matching "
                "official runner config. Official mode never falls back to LocalSim."
            )

        raise OfficialRuntimeUnavailable(
            "Official runtime configuration was detected, but concrete official API wiring "
            "has not been released/implemented yet. Add the SDK/RPC/socket/HTTP observe() "
            "and step() calls in src/env_adapters/official_env.py only."
        )

    def reset(self, episode_config: dict[str, Any] | None = None) -> dict[str, Any]:
        del episode_config
        raise OfficialRuntimeUnavailable("OfficialEnvAdapter.reset() requires official runtime wiring.")

    def observe(self) -> dict[str, Any]:
        raise OfficialRuntimeUnavailable("OfficialEnvAdapter.observe() requires official runtime wiring.")

    def step(self, action: dict[str, Any] | str) -> dict[str, Any]:
        del action
        raise OfficialRuntimeUnavailable("OfficialEnvAdapter.step() requires official runtime wiring.")

    def action_schema(self) -> list[dict[str, Any]]:
        return list(self._action_schema)

    def capabilities(self) -> dict[str, Any]:
        return official_capabilities(config=self.config.redacted())


def official_capabilities(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return adapter_capabilities(
        adapter_name="official",
        validated=False,
        validation_status="stub_until_official_runtime_release",
        requires_rendering=False,
        supports_scene_graph=False,
        supports_frame_export=False,
        supports_action_execution=True,
        supports_online_closed_loop=True,
        known_blockers=["official runtime/API has not been released or wired"],
        name="official",
        status="stub_until_official_runtime_release",
        supports_hidden_runtime=True,
        supports_observe_step_loop=True,
        uses_hidden_ground_truth=False,
        requires_internet=False,
        config=config or {},
    )


def _load_action_schema(path_value: str) -> list[dict[str, Any]]:
    if not path_value:
        return []
    path = Path(path_value)
    if not path.exists():
        raise OfficialRuntimeUnavailable(f"EAGC_ACTION_SCHEMA_PATH does not exist: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OfficialRuntimeUnavailable(f"EAGC_ACTION_SCHEMA_PATH is not valid JSON: {exc}") from exc
    if isinstance(payload, dict):
        candidate = payload.get("actions") or payload.get("action_schema") or payload.get("schema")
    else:
        candidate = payload
    if not isinstance(candidate, list):
        raise OfficialRuntimeUnavailable("EAGC_ACTION_SCHEMA_PATH must contain a list or an object with actions.")
    schema: list[dict[str, Any]] = []
    for item in candidate:
        if isinstance(item, dict):
            schema.append(dict(item))
        elif isinstance(item, str):
            schema.append({"name": item})
    return schema


OfficialAdapter = OfficialEnvAdapter
