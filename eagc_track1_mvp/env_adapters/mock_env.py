from typing import Any, Dict, List

from env_adapters.base import BaseEnvAdapter
from planner.action_schema import parse_action


MOCK_EPISODES: Dict[str, Dict[str, Any]] = {
    "mock-bedroom-relocated": {
        "room": "bedroom",
        "frontiers": [{"target": "door", "status": "closed", "confidence": 0.8}],
        "visible_objects": ["bed", "pillow", "book", "lamp", "chair", "door"],
        "object_hints": {
            "bed": {"region": "bed_area", "support": "", "confidence": 0.95, "category": "furniture"},
            "pillow": {"region": "bed_area", "support": "bed", "confidence": 0.9},
            "book": {"region": "bed_area", "support": "bed", "confidence": 0.9, "category": "object"},
            "lamp": {"region": "bedside_area", "support": "bedside_surface", "confidence": 0.8},
            "chair": {"region": "bed_area", "support": "", "confidence": 0.9, "category": "furniture"},
            "door": {"region": "exit", "support": "", "confidence": 0.9, "category": "door"},
        },
        "task": "Find the book and place it on the chair.",
        "observation": (
            "Room: bedroom. Visible objects: bed, pillow, book, lamp, chair, door. "
            "The book is initially on the bed near the pillow. The chair is beside the bed. "
            "The lamp is on a small bedside surface. The door is closed. "
            "Task: Find the book and place it on the chair."
        ),
        "fail_action": "pick_up(book)",
        "exception": {
            "type": "object_relocated",
            "object": "book",
            "state": "location unknown",
        },
        "failure_message": "Attempted pick_up(book), but the book is no longer on the bed.",
        "failure_observation": (
            "The agent reaches toward the bed to pick up the book, but the book is not "
            "there anymore. The bed, pillow, lamp, chair, and door remain visible."
        ),
    },
    "mock-hallway-door-locked": {
        "room": "hallway",
        "frontiers": [{"target": "door", "status": "locked", "confidence": 0.85}],
        "visible_objects": ["door", "key_hook", "mat", "console_table"],
        "object_hints": {
            "door": {"region": "exit", "support": "", "confidence": 0.9, "category": "door"},
            "key_hook": {"region": "wall", "support": "", "confidence": 0.8},
            "mat": {"region": "floor", "support": "floor", "confidence": 0.8},
            "console_table": {"region": "entry_area", "support": "", "confidence": 0.8},
        },
        "task": "Open the hallway door and enter the next room.",
        "observation": (
            "Room: hallway. Visible objects: door, key_hook, mat, console_table. "
            "The hallway door is closed. The key hook is empty. "
            "Task: Open the hallway door and enter the next room."
        ),
        "fail_action": "open(door)",
        "exception": {"type": "door_locked", "object": "door", "state": "locked"},
        "failure_message": "Attempted open(door), but the door is locked.",
        "failure_observation": "The door handle turns slightly, but the latch does not release.",
    },
    "mock-kitchen-container-unavailable": {
        "room": "kitchen",
        "frontiers": [{"target": "drawer", "status": "jammed", "confidence": 0.8}],
        "visible_objects": ["cup", "drawer", "counter", "sink"],
        "object_hints": {
            "cup": {"region": "counter_area", "support": "counter", "confidence": 0.9, "category": "object"},
            "drawer": {"region": "cabinet_area", "support": "", "confidence": 0.85, "category": "container"},
            "counter": {"region": "counter_area", "support": "", "confidence": 0.9, "category": "surface"},
            "sink": {"region": "sink_area", "support": "", "confidence": 0.8},
        },
        "task": "Place the cup in the drawer.",
        "observation": (
            "Room: kitchen. Visible objects: cup, drawer, counter, sink. "
            "The cup is on the counter. The drawer is visibly jammed. "
            "Task: Place the cup in the drawer."
        ),
        "fail_action": "place_in(cup, drawer)",
        "exception": {
            "type": "target_container_unavailable",
            "object": "drawer",
            "state": "jammed",
        },
        "failure_message": "Attempted place_in(cup, drawer), but the drawer is jammed.",
        "failure_observation": "The drawer cannot be opened far enough to receive the cup.",
    },
    "mock-study-tool-substitution": {
        "room": "study",
        "frontiers": [{"target": "desk", "status": "searchable", "confidence": 0.85}],
        "visible_objects": ["loose_screw", "coin", "desk", "lamp"],
        "object_hints": {
            "loose_screw": {"region": "desk_area", "support": "desk", "confidence": 0.75},
            "coin": {"region": "desk_area", "support": "desk", "confidence": 0.85, "category": "object"},
            "screwdriver": {
                "region": "",
                "support": "",
                "confidence": 0.0,
                "category": "tool",
                "status": "unknown",
                "state": "unavailable",
            },
            "desk": {"region": "desk_area", "support": "", "confidence": 0.9, "category": "furniture"},
            "lamp": {"region": "desk_area", "support": "desk", "confidence": 0.8},
        },
        "task": "Tighten the loose screw with a suitable tool.",
        "observation": (
            "Room: study. Visible objects: loose_screw, coin, desk, lamp. "
            "No screwdriver is visible. A coin is on the desk and may fit the screw slot. "
            "Task: Tighten the loose screw with a suitable tool."
        ),
        "fail_action": "pick_up(screwdriver)",
        "exception": {
            "type": "tool_substitution",
            "object": "screwdriver",
            "state": "unavailable",
            "substitute": "coin",
        },
        "failure_message": "Attempted pick_up(screwdriver), but no screwdriver is available.",
        "failure_observation": "The screwdriver is absent, while the coin remains visible on the desk.",
    },
    "mock-livingroom-nominal": {
        "room": "living_room",
        "frontiers": [{"target": "coffee_table", "status": "clear", "confidence": 0.9}],
        "visible_objects": ["remote", "sofa", "coffee_table", "basket"],
        "object_hints": {
            "remote": {"region": "sofa_area", "support": "sofa", "confidence": 0.9, "category": "object"},
            "sofa": {"region": "sofa_area", "support": "", "confidence": 0.9, "category": "furniture"},
            "coffee_table": {"region": "center_area", "support": "", "confidence": 0.9, "category": "furniture"},
            "basket": {"region": "corner", "support": "floor", "confidence": 0.75},
        },
        "task": "Move the remote to the coffee table.",
        "observation": (
            "Room: living_room. Visible objects: remote, sofa, coffee_table, basket. "
            "The remote is on the sofa. The coffee table is clear. "
            "Task: Move the remote to the coffee table."
        ),
        "fail_action": "",
        "exception": {},
        "failure_message": "",
        "failure_observation": "",
    },
}

EPISODE_ALIASES = {
    "mock-door-locked": "mock-hallway-door-locked",
}


class MockEnv(BaseEnvAdapter):
    """Text-only indoor scenes used until the official EAGC runtime exists."""

    def __init__(self, episode_id: str = "mock-bedroom-relocated") -> None:
        episode_id = EPISODE_ALIASES.get(episode_id, episode_id)
        if episode_id not in MOCK_EPISODES:
            available = ", ".join(sorted(MOCK_EPISODES))
            raise ValueError(f"Unknown mock episode_id={episode_id!r}. Available: {available}")
        self.episode_id = episode_id
        self.episode = MOCK_EPISODES[episode_id]
        self.step_count = 0
        self.failed_once = False
        self.holding: str | None = None
        self.object_available: Dict[str, bool] = {}
        self.object_locations: Dict[str, str] = {}
        self.current_room = self.episode["room"]
        self.door_locked = episode_id == "mock-hallway-door-locked"
        self.door_open = False
        self.drawer_available = episode_id != "mock-kitchen-container-unavailable"

    def reset(self) -> Dict[str, Any]:
        self.step_count = 0
        self.failed_once = False
        self.holding = None
        self.current_room = self.episode["room"]
        self.door_locked = self.episode_id == "mock-hallway-door-locked"
        self.door_open = False
        self.drawer_available = self.episode_id != "mock-kitchen-container-unavailable"
        self.object_available = {
            name: self.episode["object_hints"].get(name, {}).get("status") != "unknown"
            for name in self.episode["object_hints"]
        }
        for name in self.episode["visible_objects"]:
            self.object_available[name] = True
        self.object_locations = {
            name: self.episode["object_hints"].get(name, {}).get("support", "")
            for name in self.episode["object_hints"]
        }
        return {
            "episode_id": self.episode_id,
            "task": self.episode["task"],
            "observation": self.episode["observation"],
            "current_room": self.episode["room"],
            "room": self.episode["room"],
            "topology": [
                {
                    "room": self.episode["room"],
                    "node_type": "room",
                    "visited": True,
                    "frontiers": list(self.episode["frontiers"]),
                }
            ],
            "object_hints": dict(self.episode["object_hints"]),
            "visible_objects": list(self.episode["visible_objects"]),
        }

    def step(self, action: str) -> Dict[str, Any]:
        self.step_count += 1
        action_name, args = parse_action(action)

        if action_name in {"locate", "search"}:
            return self._handle_locate_or_search(action, args)
        if action_name == "pick_up" and len(args) == 1:
            return self._handle_pick_up(action, args[0])
        if action_name == "place_on" and len(args) == 2:
            return self._handle_place_on(action, args[0], args[1])
        if action_name == "place_in" and len(args) == 2:
            return self._handle_place_on(action, args[0], args[1])
        if action_name == "open" and len(args) == 1:
            return self._handle_open(action, args[0])
        if action_name == "unlock" and len(args) == 1:
            return self._handle_unlock(action, args[0])
        if action_name == "navigate_to" and len(args) == 1:
            return self._handle_navigate(action, args[0])
        if action_name == "enter" and len(args) == 1:
            return self._handle_navigate(action, args[0])
        if action_name == "substitute_tool" and len(args) == 2:
            return self._success(action, f"Substituted {args[0]} with {args[1]}.")
        if action_name == "use_tool" and len(args) == 2:
            return self._handle_use_tool(action, args[0], args[1])
        if action_name == "wait":
            return self._success(action, "Waited and kept the scene stable.")
        return self._success(action, f"Executed {action}.")

    def _handle_locate_or_search(self, action: str, args: List[str]) -> Dict[str, Any]:
        if self.episode_id == "mock-bedroom-relocated" and args:
            self.object_available["book"] = True
            self.object_locations["book"] = args[0]
        return self._success(action, f"Executed {action}.")

    def _handle_pick_up(self, action: str, obj: str) -> Dict[str, Any]:
        if self.episode_id == "mock-bedroom-relocated" and obj == "book" and not self.failed_once:
            self.failed_once = True
            self.object_available["book"] = False
            return self._failure()
        if self.episode_id == "mock-study-tool-substitution" and obj == "screwdriver":
            self.failed_once = True
            return self._failure()
        if not self.object_available.get(obj, False):
            return self._failure_message(action, f"Attempted {action}, but {obj} is not available.")
        self.holding = obj
        self.object_locations[obj] = "agent_hand"
        return self._success(action, f"Executed {action}.")

    def _handle_place_on(self, action: str, obj: str, target: str) -> Dict[str, Any]:
        if target == "drawer" and not self.drawer_available:
            self.failed_once = True
            return self._failure()
        if self.holding != obj:
            return self._failure_message(action, f"Attempted {action}, but the agent is not holding {obj}.")
        self.holding = None
        self.object_locations[obj] = target
        return self._success(action, f"Executed {action}.")

    def _handle_open(self, action: str, obj: str) -> Dict[str, Any]:
        if obj == "door" and self.door_locked:
            self.failed_once = True
            return self._failure()
        if obj == "door":
            self.door_open = True
        return self._success(action, f"Executed {action}.")

    def _handle_unlock(self, action: str, obj: str) -> Dict[str, Any]:
        if obj == "door":
            self.door_locked = False
        return self._success(action, f"Executed {action}.")

    def _handle_navigate(self, action: str, target: str) -> Dict[str, Any]:
        if target == "next_room" and not self.door_open:
            return self._failure_message(action, "Cannot navigate to next_room because the door is not open.")
        self.current_room = target
        return self._success(action, f"Executed {action}.")

    def _handle_use_tool(self, action: str, tool: str, target: str) -> Dict[str, Any]:
        if self.holding != tool:
            return self._failure_message(action, f"Attempted {action}, but the agent is not holding {tool}.")
        return self._success(action, f"Executed {action}.")

    def _success(self, action: str, message: str) -> Dict[str, Any]:
        return {
            "success": True,
            "result": "success",
            "message": message,
            "observation": self.episode["observation"],
        }

    def _failure(self) -> Dict[str, Any]:
        return {
            "success": False,
            "result": "failure",
            "message": self.episode["failure_message"],
            "exception": dict(self.episode["exception"]),
            "observation": self.episode["failure_observation"],
        }

    def _failure_message(self, action: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "result": "failure",
            "message": message,
            "exception": {"type": "constraint_violation", "object": action, "state": "blocked"},
            "observation": self.episode["observation"],
        }
