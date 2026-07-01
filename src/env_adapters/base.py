from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class EnvAdapter(Protocol):
    """Runtime boundary used by Track 1 agent code."""

    def reset(self, episode_config: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def observe(self) -> dict[str, Any]:
        ...

    def step(self, action: dict[str, Any] | str) -> dict[str, Any]:
        ...

    def action_schema(self) -> list[dict[str, Any]]:
        ...

    def capabilities(self) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...


class BaseEnvAdapter(ABC):
    """Environment adapter contract for simulator/runtime swaps.

    `reset()` and `step()` are the legacy minimum contract used by the current
    MVP. The remaining methods freeze the v0.17.3 official-simulator-facing
    interface without forcing every existing adapter to implement capabilities
    it does not support yet.
    """

    @abstractmethod
    def reset(self, episode_config: dict[str, Any] | None = None) -> Dict[str, Any]:
        """Start an episode and return the first observation packet."""

    @abstractmethod
    def step(self, action: dict[str, Any] | str) -> Dict[str, Any]:
        """Execute one action and return an environment result packet."""

    def observe(self) -> Dict[str, Any]:
        """Return the latest observation packet, or a blocker if unsupported."""
        return _unsupported("observe")

    def get_scene_graph(self) -> Dict[str, Any]:
        """Return a simulator scene graph when the backend supports one."""
        return _unsupported("get_scene_graph")

    def capture_frame(self) -> Dict[str, Any]:
        """Capture a visual frame when the backend supports rendering."""
        return _unsupported("capture_frame")

    def execute_action(self, action: str) -> Dict[str, Any]:
        """Standard action execution entrypoint; delegates to legacy `step()`."""
        return self.step(action)

    def get_agent_state(self) -> Dict[str, Any]:
        """Return the agent state when available."""
        return _unsupported("get_agent_state")

    def action_schema(self) -> list[dict[str, Any]]:
        """Return action formats accepted by the runtime."""
        return []

    def close(self) -> None:
        """Release backend resources."""

    def capabilities(self) -> Dict[str, Any]:
        """Describe backend validation status and supported interface surface."""
        return adapter_capabilities(
            adapter_name=self.__class__.__name__,
            validated=False,
            validation_status="not_declared",
            known_blockers=["adapter has not declared capabilities"],
        )


def adapter_capabilities(
    *,
    adapter_name: str,
    validated: bool,
    validation_status: str,
    requires_rendering: bool = False,
    supports_scene_graph: bool = False,
    supports_frame_export: bool = False,
    supports_action_execution: bool = False,
    supports_online_closed_loop: bool = False,
    known_blockers: list[str] | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    packet: Dict[str, Any] = {
        "adapter_name": adapter_name,
        "validated": validated,
        "validation_status": validation_status,
        "requires_rendering": requires_rendering,
        "supports_scene_graph": supports_scene_graph,
        "supports_frame_export": supports_frame_export,
        "supports_action_execution": supports_action_execution,
        "supports_online_closed_loop": supports_online_closed_loop,
        "known_blockers": known_blockers or [],
    }
    packet.update(extra)
    return packet


def canonical_observation_packet(
    *,
    observation: str = "",
    raw_observation: dict[str, Any] | None = None,
    current_room: str | None = None,
    visible_objects: list[Any] | None = None,
    available_actions: list[Any] | None = None,
    image_path: str | None = None,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "observation": observation,
        "raw_observation": raw_observation or {},
        "current_room": current_room,
        "visible_objects": list(visible_objects or []),
        "available_actions": list(available_actions or []),
        "image_path": image_path,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }
    packet.update(extra)
    return packet


def canonical_step_result(
    *,
    success: bool,
    action: dict[str, Any] | str,
    result: str = "",
    observation_packet: dict[str, Any] | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "success": bool(success),
        "action": action,
        "result": result,
        "observation_packet": observation_packet or {},
        "error": error,
        "metadata": metadata or {},
    }
    if observation_packet and "observation" in observation_packet:
        packet.setdefault("observation", observation_packet.get("observation", ""))
    packet.update(extra)
    return packet


def _unsupported(method: str) -> Dict[str, Any]:
    return {
        "success": False,
        "reason": "unsupported_capability",
        "message": f"{method} is not supported by this adapter.",
    }
