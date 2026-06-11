from __future__ import annotations

from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter, adapter_capabilities


class ProcThorAdapter(BaseEnvAdapter):
    """Reserved ProcTHOR adapter stub.

    ProcTHOR depends on the AI2-THOR/ProcTHOR runtime path, which remains
    unvalidated in this project. This stub exposes capabilities without
    importing or initializing any heavy simulator dependency.
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.error_message = "ProcTHOR adapter is reserved but not validated."

    def reset(self) -> Dict[str, Any]:
        return _blocker("procthor_reset_not_validated")

    def step(self, action: str) -> Dict[str, Any]:
        packet = _blocker("procthor_action_execution_not_validated")
        packet["action"] = action
        return packet

    def capabilities(self) -> Dict[str, Any]:
        return adapter_capabilities(
            adapter_name="procthor",
            validated=False,
            validation_status="reserved_not_validated",
            requires_rendering=True,
            supports_scene_graph=False,
            supports_frame_export=True,
            supports_action_execution=False,
            supports_online_closed_loop=False,
            known_blockers=["depends on AI2-THOR/ProcTHOR runtime availability"],
        )


def _blocker(reason: str) -> Dict[str, Any]:
    return {
        "success": False,
        "reason": reason,
        "message": "ProcTHOR is a reserved adapter target and has not been validated for this submission baseline.",
    }
