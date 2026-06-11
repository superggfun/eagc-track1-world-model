from __future__ import annotations

from importlib import import_module
from typing import Any, Dict

from env_adapters.base import adapter_capabilities


ADAPTER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "local_sim": adapter_capabilities(
        adapter_name="local_sim",
        validated=True,
        validation_status="validated_local_track1_mvp_backend",
        requires_rendering=False,
        supports_scene_graph=True,
        supports_frame_export=False,
        supports_action_execution=True,
        supports_online_closed_loop=True,
        known_blockers=[],
    ),
    "virtualhome": adapter_capabilities(
        adapter_name="virtualhome",
        validated=True,
        validation_status="validated_manual_play_windows_backend",
        requires_rendering=True,
        supports_scene_graph=True,
        supports_frame_export=True,
        supports_action_execution=True,
        supports_online_closed_loop=True,
        known_blockers=["manual_play_required"],
        manual_play_required=True,
    ),
    "alfred_offline": adapter_capabilities(
        adapter_name="alfred_offline",
        validated=True,
        validation_status="validated_synthetic_fixture_only",
        requires_rendering=False,
        supports_scene_graph=False,
        supports_frame_export=False,
        supports_action_execution=False,
        supports_online_closed_loop=False,
        known_blockers=["real ALFRED dataset conversion has not been validated"],
        real_dataset_validated=False,
    ),
    "ai2thor": adapter_capabilities(
        adapter_name="ai2thor",
        validated=False,
        validation_status="reserved_not_validated",
        requires_rendering=True,
        supports_scene_graph=True,
        supports_frame_export=True,
        supports_action_execution=False,
        supports_online_closed_loop=False,
        known_blockers=["Windows/WSL/cloud rendering stack unresolved"],
    ),
    "habitat": adapter_capabilities(
        adapter_name="habitat",
        validated=False,
        validation_status="reserved_not_validated",
        requires_rendering=True,
        supports_scene_graph=False,
        supports_frame_export=True,
        supports_action_execution=False,
        supports_online_closed_loop=False,
        known_blockers=["EGL/Vulkan/headless rendering unresolved"],
    ),
    "procthor": adapter_capabilities(
        adapter_name="procthor",
        validated=False,
        validation_status="reserved_not_validated",
        requires_rendering=True,
        supports_scene_graph=False,
        supports_frame_export=True,
        supports_action_execution=False,
        supports_online_closed_loop=False,
        known_blockers=["depends on AI2-THOR/ProcTHOR runtime availability"],
    ),
}


ADAPTER_CLASS_PATHS = {
    "local_sim": ("env_adapters.local_sim_env", "LocalSimEnv"),
    "ai2thor": ("env_adapters.ai2thor_adapter", "AI2ThorAdapter"),
    "habitat": ("env_adapters.habitat_adapter", "HabitatAdapter"),
    "procthor": ("env_adapters.procthor_adapter", "ProcThorAdapter"),
}


def list_adapters() -> list[Dict[str, Any]]:
    """Return static adapter capabilities without starting simulators."""
    return [ADAPTER_CAPABILITIES[name] for name in sorted(ADAPTER_CAPABILITIES)]


def get_adapter(name: str) -> Any:
    """Return an adapter class for runtime-backed adapters.

    The function imports only the requested adapter module. It does not create
    simulator controllers or download dependencies.
    """
    normalized = name.strip().lower().replace("-", "_")
    if normalized not in ADAPTER_CLASS_PATHS:
        raise KeyError(f"No instantiable adapter registered for {name!r}.")
    module_name, class_name = ADAPTER_CLASS_PATHS[normalized]
    module = import_module(module_name)
    return getattr(module, class_name)


def capabilities_for(name: str) -> Dict[str, Any]:
    normalized = name.strip().lower().replace("-", "_")
    if normalized not in ADAPTER_CAPABILITIES:
        raise KeyError(f"Unknown adapter: {name!r}")
    return ADAPTER_CAPABILITIES[normalized]
