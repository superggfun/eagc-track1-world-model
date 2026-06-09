from typing import Any, Dict


def new_world_model(episode_id: str) -> Dict[str, Any]:
    return {
        "episode_id": episode_id,
        "agent_state": {},
        "rooms": [],
        "topology": [],
        "objects": [],
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [],
        "plans": [],
        "exceptions": [],
    }
