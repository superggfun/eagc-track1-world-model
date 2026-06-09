from typing import Any, Dict


def new_world_model(episode_id: str) -> Dict[str, Any]:
    return {
        "episode_id": episode_id,
        "agent_state": {
            "current_room": "unknown",
            "holding": None,
            "step": 0,
            "last_action": "",
            "mode": "initializing",
        },
        "rooms": [],
        "topology": [
            {
                "room": "unknown",
                "node_type": "room",
                "visited": False,
                "frontiers": [],
            }
        ],
        "visited_rooms": [],
        "frontiers": [],
        "objects": [],
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [],
        "plans": [],
        "exceptions": [],
        "task_status": {
            "status": "in_progress",
            "success": False,
            "reason": "",
            "evidence": [],
        },
    }
