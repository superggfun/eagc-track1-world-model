from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseEnvAdapter(ABC):
    """Environment adapter contract for simulator/runtime swaps.

    `reset()` and `step()` are the legacy minimum contract used by the current
    MVP. The remaining methods freeze the v0.17.3 official-simulator-facing
    interface without forcing every existing adapter to implement capabilities
    it does not support yet.
    """

    @abstractmethod
    def reset(self) -> Dict[str, Any]:
        """Start an episode and return the first observation packet."""

    @abstractmethod
    def step(self, action: str) -> Dict[str, Any]:
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


def _unsupported(method: str) -> Dict[str, Any]:
    return {
        "success": False,
        "reason": "unsupported_capability",
        "message": f"{method} is not supported by this adapter.",
    }
