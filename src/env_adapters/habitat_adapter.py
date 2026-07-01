from __future__ import annotations

from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter, adapter_capabilities


class HabitatAdapter(BaseEnvAdapter):
    """Reserved Habitat adapter stub.

    This file intentionally does not import habitat-sim or habitat-lab. The
    current project records Habitat as an unvalidated public-simulator target
    until EGL/Vulkan/headless rendering is resolved in a separate environment.
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.error_message = "Habitat adapter is reserved but not validated."

    def reset(self) -> Dict[str, Any]:
        return _blocker("habitat_reset_not_validated")

    def step(self, action: str) -> Dict[str, Any]:
        packet = _blocker("habitat_action_execution_not_validated")
        packet["action"] = action
        return packet

    def capabilities(self) -> Dict[str, Any]:
        return adapter_capabilities(
            adapter_name="habitat",
            validated=False,
            validation_status="reserved_not_validated",
            requires_rendering=True,
            supports_scene_graph=False,
            supports_frame_export=True,
            supports_action_execution=False,
            supports_online_closed_loop=False,
            known_blockers=["EGL/Vulkan/headless rendering unresolved"],
        )


def _blocker(reason: str) -> Dict[str, Any]:
    return {
        "success": False,
        "reason": reason,
        "message": "Habitat is a reserved adapter target and has not been validated for this submission baseline.",
    }
