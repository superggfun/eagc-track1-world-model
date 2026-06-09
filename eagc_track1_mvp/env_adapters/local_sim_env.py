from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from env_adapters.base import BaseEnvAdapter
from planner.action_schema import parse_action


LOCAL_SIM_EPISODES: Dict[str, Dict[str, Any]] = {
    "local-explore-book-relocated": {
        "task": "Find the book and place it on the chair.",
        "start_room": "bedroom",
        "expected_status": "complete",
    },
    "local-door-locked-route": {
        "task": "Go from bedroom to kitchen and place the cup on the counter.",
        "start_room": "bedroom",
        "expected_status": "complete",
    },
    "local-container-unavailable": {
        "task": "Place the cup in the drawer.",
        "start_room": "kitchen",
        "expected_status": "blocked_recovered",
    },
    "local-tool-substitution": {
        "task": "Tighten the loose screw with a suitable tool.",
        "start_room": "living_room",
        "expected_status": "complete",
    },
}


TOPOLOGY = {
    "bedroom": ["hallway"],
    "hallway": ["bedroom", "kitchen", "living_room"],
    "kitchen": ["hallway"],
    "living_room": ["hallway"],
}


DOOR_BY_ROOM = {
    "bedroom": "bedroom_door",
    "kitchen": "kitchen_door",
    "living_room": "living_room_door",
}


DOORS = {
    "bedroom_door": {"connects": ("bedroom", "hallway"), "locked": False, "open": True},
    "kitchen_door": {"connects": ("hallway", "kitchen"), "locked": False, "open": False},
    "living_room_door": {"connects": ("hallway", "living_room"), "locked": False, "open": True},
}


def _initial_objects() -> Dict[str, Dict[str, Any]]:
    return {
        "bed": {
            "category": "furniture",
            "room": "bedroom",
            "region": "bed_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "book": {
            "category": "object",
            "room": "bedroom",
            "region": "bed_area",
            "support": "bed",
            "visible": True,
            "pickupable": True,
            "available": True,
        },
        "chair": {
            "category": "furniture",
            "room": "bedroom",
            "region": "bed_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "lamp": {
            "category": "object",
            "room": "bedroom",
            "region": "bedside_area",
            "support": "bedside_table",
            "visible": True,
            "pickupable": False,
        },
        "cup": {
            "category": "object",
            "room": "kitchen",
            "region": "counter_area",
            "support": "counter",
            "visible": True,
            "pickupable": True,
            "available": True,
        },
        "drawer": {
            "category": "container",
            "room": "kitchen",
            "region": "cabinet_area",
            "support": "",
            "visible": True,
            "pickupable": False,
            "openable": True,
            "container": True,
            "available": True,
        },
        "counter": {
            "category": "surface",
            "room": "kitchen",
            "region": "counter_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "key": {
            "category": "object",
            "room": "hallway",
            "region": "key_hook",
            "support": "key_hook",
            "visible": True,
            "pickupable": True,
            "available": True,
        },
        "key_hook": {
            "category": "surface",
            "room": "hallway",
            "region": "wall",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "tool": {
            "category": "tool",
            "room": "living_room",
            "region": "tool_area",
            "support": "side_table",
            "visible": True,
            "pickupable": True,
            "available": True,
        },
        "screwdriver": {
            "category": "tool",
            "room": "living_room",
            "region": "tool_area",
            "support": "side_table",
            "visible": True,
            "pickupable": True,
            "available": False,
        },
        "coin": {
            "category": "object",
            "room": "living_room",
            "region": "table_area",
            "support": "side_table",
            "visible": True,
            "pickupable": True,
            "available": True,
        },
        "loose_screw": {
            "category": "object",
            "room": "living_room",
            "region": "repair_area",
            "support": "wall_plate",
            "visible": True,
            "pickupable": False,
            "available": True,
            "state": "loose",
        },
        "bedside_table": {
            "category": "surface",
            "room": "bedroom",
            "region": "bedside_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "side_table": {
            "category": "surface",
            "room": "living_room",
            "region": "table_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
        "wall_plate": {
            "category": "surface",
            "room": "living_room",
            "region": "repair_area",
            "support": "",
            "visible": True,
            "pickupable": False,
        },
    }


class LocalSimEnv(BaseEnvAdapter):
    """Deterministic local simulator for Track 1 closed-loop smoke tests."""

    def __init__(self, episode_id: str = "local-explore-book-relocated", episode_spec: Dict[str, Any] | None = None) -> None:
        if episode_spec is None and episode_id not in LOCAL_SIM_EPISODES:
            available = ", ".join(sorted(LOCAL_SIM_EPISODES))
            raise ValueError(f"Unknown local_sim episode_id={episode_id!r}. Available: {available}")
        self.episode_id = episode_id
        self.episode_spec = deepcopy(episode_spec) if episode_spec else None
        self.episode = self._episode_from_spec(self.episode_spec) if self.episode_spec else LOCAL_SIM_EPISODES[episode_id]
        self.task = str(self.episode["task"])
        self.step_count = 0
        self.current_room = str(self.episode["start_room"])
        self.holding: str | None = None
        self.visited_rooms: set[str] = set()
        self.known_frontiers: set[str] = set()
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.doors: Dict[str, Dict[str, Any]] = {}
        self.last_action_result: Dict[str, Any] = {}
        self.book_relocated = False
        self.generated_relocation_done = False
        self.task_visible = True

    @classmethod
    def from_generated_episode(cls, episode_spec: Dict[str, Any]) -> "LocalSimEnv":
        return cls(str(episode_spec.get("episode_id", "random-local-sim-seed-0000")), episode_spec=episode_spec)

    def reset(self, reveal_task: bool = True) -> Dict[str, Any]:
        self.step_count = 0
        self.current_room = str(self.episode["start_room"])
        self.holding = None
        self.visited_rooms = {self.current_room}
        self.known_frontiers = set(TOPOLOGY[self.current_room])
        self.objects = _initial_objects()
        self.doors = deepcopy(DOORS)
        self.last_action_result = {}
        self.book_relocated = False
        self.generated_relocation_done = False
        self.task_visible = reveal_task

        if self.episode_spec:
            self.objects = {
                name: dict(value)
                for name, value in self.episode_spec.get("objects", _initial_objects()).items()
                if isinstance(value, dict)
            }
            self.doors = deepcopy(self.episode_spec.get("doors", DOORS))

        if self.episode_id == "local-door-locked-route":
            self.doors["kitchen_door"]["locked"] = True
            self.doors["kitchen_door"]["open"] = False
        if self.episode_id == "local-container-unavailable":
            self.objects["drawer"]["available"] = False
            self.objects["drawer"]["state"] = "unavailable"
        return self.observe()

    def reveal_task(self) -> Dict[str, Any]:
        self.task_visible = True
        return self.observe()

    def observe(self, reveal_task: bool | None = None) -> Dict[str, Any]:
        if reveal_task is not None:
            self.task_visible = reveal_task
        visible_objects = self._visible_object_names()
        visible_frontiers = self._visible_frontiers()
        text = self._render_text(visible_objects, visible_frontiers)
        task = self.task if self.task_visible else ""
        return {
            "episode_id": self.episode_id,
            "task": task,
            "observation": text,
            "text": text,
            "source": "local_sim",
            "agent_state": self._agent_state(),
            "current_room": self.current_room,
            "room": self.current_room,
            "visible_objects": visible_objects,
            "visible_rooms": [self.current_room],
            "visible_frontiers": visible_frontiers,
            "topology": self._partial_topology_nodes(),
            "object_hints": self._object_hints(visible_objects),
            "last_action_result": dict(self.last_action_result),
            "success_condition": deepcopy(self.episode_spec.get("success_condition", {})) if self.episode_spec else {},
            "expected_task_status": self.episode_spec.get("expected_task_status", "") if self.episode_spec else "",
            "controlled_exception": deepcopy(self.episode_spec.get("controlled_exception", {})) if self.episode_spec else {},
            "generated_episode": bool(self.episode_spec),
        }

    def step(self, action: str) -> Dict[str, Any]:
        self.step_count += 1
        name, args = parse_action(action)
        if name == "explore" and len(args) == 1:
            result = self._explore(args[0], action)
        elif name == "navigate_to" and len(args) == 1:
            result = self._navigate_to(args[0], action)
        elif name in {"locate", "search"} and len(args) == 1:
            result = self._search(args[0], action)
        elif name == "open" and len(args) == 1:
            result = self._open(args[0], action)
        elif name == "unlock" and len(args) == 1:
            result = self._unlock(args[0], action)
        elif name == "pick_up" and len(args) == 1:
            result = self._pick_up(args[0], action)
        elif name == "place_on" and len(args) == 2:
            result = self._place(args[0], args[1], "on", action)
        elif name == "place_in" and len(args) == 2:
            result = self._place(args[0], args[1], "inside", action)
        elif name == "substitute_tool" and len(args) == 2:
            result = self._substitute_tool(args[0], args[1], action)
        elif name == "use_tool" and len(args) == 2:
            result = self._use_tool(args[0], args[1], action)
        elif name == "wait":
            result = self._success(action, "Waited and kept the local simulator state stable.")
        else:
            result = self._failure(
                action,
                "unsupported_action",
                action,
                f"LocalSim does not support action {action}.",
            )
        result["observation"] = self.observe()["observation"]
        result["observation_packet"] = self.observe()
        self.last_action_result = {k: v for k, v in result.items() if k != "observation_packet"}
        return result

    def close(self) -> None:
        return None

    def _explore(self, room: str, action: str) -> Dict[str, Any]:
        self.known_frontiers.update(TOPOLOGY.get(self.current_room, []))
        if room in TOPOLOGY:
            self.known_frontiers.update(TOPOLOGY[room])
        return self._success(action, f"Explored from {self.current_room}; known frontiers updated.")

    def _navigate_to(self, target: str, action: str) -> Dict[str, Any]:
        if target in self.objects:
            obj = self.objects[target]
            target_room = str(obj.get("room", self.current_room))
            self.current_room = target_room
        elif target in TOPOLOGY:
            if not self._path_available(self.current_room, target):
                door = self._blocking_door(self.current_room, target) or target
                return self._failure(action, "door_locked", door, f"Cannot navigate to {target}; {door} is locked.")
            self.current_room = target
        elif target in self.doors:
            door = self.doors[target]
            self.current_room = self._nearest_room_for_door(door)
        else:
            return self._failure(action, "unknown_target", target, f"Unknown navigation target {target}.")
        self.visited_rooms.add(self.current_room)
        self.known_frontiers.update(TOPOLOGY.get(self.current_room, []))
        return self._success(action, f"Navigated to {target}. Current room: {self.current_room}.")

    def _search(self, region: str, action: str) -> Dict[str, Any]:
        if region in TOPOLOGY:
            self.current_room = region
            self.visited_rooms.add(region)
        if self.episode_id == "local-door-locked-route" and region in {"key", "key_hook", "hallway", "visible_area"}:
            self.objects["key"]["visible"] = True
        if self.episode_id == "local-explore-book-relocated" and region in {"living_room", "side_table", "visible_area"}:
            self.objects["book"]["visible"] = self.objects["book"]["room"] == self.current_room
        return self._success(action, f"Searched {region}.")

    def _open(self, obj: str, action: str) -> Dict[str, Any]:
        door = self.doors.get(obj)
        if door is None:
            if obj in self.objects and self.objects[obj].get("openable"):
                self.objects[obj]["state"] = "open"
                return self._success(action, f"Opened {obj}.")
            return self._failure(action, "unknown_object", obj, f"Cannot open unknown or non-openable {obj}.")
        if door.get("locked"):
            return self._failure(action, "door_locked", obj, f"Attempted {action}, but {obj} is locked.")
        door["open"] = True
        return self._success(action, f"Opened {obj}.")

    def _unlock(self, obj: str, action: str) -> Dict[str, Any]:
        door = self.doors.get(obj)
        if door is None:
            return self._failure(action, "unknown_object", obj, f"Cannot unlock unknown {obj}.")
        if obj == "kitchen_door" and self.holding != "key":
            return self._failure(action, "missing_tool", obj, "The key is required to unlock kitchen_door.")
        door["locked"] = False
        return self._success(action, f"Unlocked {obj}.")

    def _pick_up(self, obj: str, action: str) -> Dict[str, Any]:
        item = self.objects.get(obj)
        if item is None:
            return self._failure(action, "unknown_object", obj, f"Unknown object {obj}.")
        if self._should_relocate_on_pickup(obj):
            self.book_relocated = True
            self.generated_relocation_done = True
            relocation = self._relocation_exception()
            item["room"] = relocation.get("to_room", "living_room")
            item["region"] = relocation.get("to_region", "table_area")
            item["support"] = relocation.get("to_support", "side_table")
            item["visible"] = False
            return self._failure(
                action,
                "object_relocated",
                obj,
                f"Attempted {action}, but {obj} moved from its previous support to an unknown nearby room.",
                extra={
                    "likely_locations": relocation.get("likely_locations", [item["room"]]),
                    "prior_support": relocation.get("prior_support", ""),
                    "prior_region": relocation.get("prior_region", ""),
                },
            )
        if not item.get("available", True):
            if obj == "screwdriver":
                return self._failure(
                    action,
                    "tool_substitution",
                    obj,
                    "The screwdriver is unavailable; the coin can substitute for the screw slot.",
                    extra={"substitute": "coin", "target": "loose_screw"},
                )
            return self._failure(action, "object_unavailable", obj, f"{obj} is unavailable.")
        if not item.get("pickupable", False):
            return self._failure(action, "not_pickupable", obj, f"{obj} is not pickupable.")
        if item.get("room") != self.current_room:
            return self._failure(action, "object_not_visible", obj, f"{obj} is not visible in {self.current_room}.")
        self.holding = obj
        item["support"] = "agent_hand"
        item["region"] = "agent"
        item["room"] = self.current_room
        item["visible"] = True
        item["state"] = "held"
        return self._success(action, f"Picked up {obj}.")

    def _place(self, obj: str, target: str, relation: str, action: str) -> Dict[str, Any]:
        if self.holding != obj:
            return self._failure(action, "not_holding", obj, f"Cannot place {obj}; agent is not holding it.")
        target_item = self.objects.get(target)
        if target_item is None:
            return self._failure(action, "unknown_object", target, f"Unknown placement target {target}.")
        if target == "drawer" and not target_item.get("available", True):
            return self._failure(
                action,
                "target_container_unavailable",
                target,
                "The drawer is unavailable, so the cup needs a safe fallback surface.",
                extra={"object_to_place": obj, "fallback_target": "counter"},
            )
        target_room = str(target_item.get("room", self.current_room))
        if target_room != self.current_room:
            return self._failure(
                action,
                "target_not_reachable",
                target,
                "Cannot place object on target because target is not in current room.",
                extra={"object_to_place": obj, "target_room": target_room},
            )
        item = self.objects[obj]
        item["room"] = target_room
        item["region"] = str(target_item.get("region", "visible_area"))
        item["support"] = target
        item["visible"] = True
        item["state"] = "placed"
        self.holding = None
        return self._success(action, f"Placed {obj} {relation} {target}.")

    def _substitute_tool(self, old_tool: str, new_tool: str, action: str) -> Dict[str, Any]:
        if old_tool == "screwdriver" and new_tool == "coin":
            self.objects["coin"]["visible"] = True
            return self._success(action, "Substituted screwdriver with coin.")
        return self._failure(action, "unsupported_substitution", old_tool, f"Cannot substitute {old_tool} with {new_tool}.")

    def _use_tool(self, tool: str, target: str, action: str) -> Dict[str, Any]:
        if self.holding != tool:
            return self._failure(action, "not_holding", tool, f"Cannot use {tool}; agent is not holding it.")
        if tool == "coin" and target == "loose_screw":
            self.objects["loose_screw"]["state"] = "tightened"
            return self._success(action, "Used coin to tighten loose_screw.")
        return self._failure(action, "tool_mismatch", target, f"{tool} is not suitable for {target}.")

    def _success(self, action: str, message: str) -> Dict[str, Any]:
        return {"success": True, "result": "success", "message": message, "action": action}

    def _failure(
        self,
        action: str,
        exception_type: str,
        obj: str,
        message: str,
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        exception = {"type": exception_type, "object": obj, "state": "blocked"}
        if extra:
            exception.update(extra)
        return {
            "success": False,
            "result": "failure",
            "message": message,
            "action": action,
            "exception": exception,
        }

    def _visible_object_names(self) -> List[str]:
        names = []
        for name, obj in self.objects.items():
            if obj.get("room") == self.current_room and obj.get("visible", True):
                names.append(name)
        for door_name, door in self.doors.items():
            if self.current_room in door["connects"]:
                names.append(door_name)
        return sorted(dict.fromkeys(names))

    def _visible_frontiers(self) -> List[Dict[str, Any]]:
        frontiers = []
        for room in TOPOLOGY.get(self.current_room, []):
            door_name = self._door_between(self.current_room, room)
            door = self.doors.get(door_name, {})
            frontiers.append(
                {
                    "target": room,
                    "via": door_name,
                    "status": "locked" if door.get("locked") else ("open" if door.get("open") else "closed"),
                    "confidence": 1.0,
                }
            )
        return frontiers

    def _topology_nodes(self) -> List[Dict[str, Any]]:
        nodes = []
        for room, neighbors in TOPOLOGY.items():
            nodes.append(
                {
                    "room": room,
                    "node_type": "room",
                    "visited": room in self.visited_rooms,
                    "frontiers": [
                        {
                            "target": neighbor,
                            "via": self._door_between(room, neighbor),
                            "status": "known",
                            "confidence": 1.0,
                        }
                        for neighbor in neighbors
                    ],
                }
            )
        return nodes

    def _partial_topology_nodes(self) -> List[Dict[str, Any]]:
        nodes = []
        discovered_rooms = set(self.visited_rooms)
        discovered_rooms.add(self.current_room)
        for room in sorted(discovered_rooms):
            if room not in TOPOLOGY:
                continue
            frontiers = []
            for neighbor in TOPOLOGY.get(room, []):
                door_name = self._door_between(room, neighbor)
                door = self.doors.get(door_name, {})
                frontiers.append(
                    {
                        "target": neighbor,
                        "via": door_name,
                        "status": "locked" if door.get("locked") else ("open" if door.get("open") else "closed"),
                        "confidence": 1.0,
                    }
                )
            nodes.append(
                {
                    "room": room,
                    "node_type": "room",
                    "visited": room in self.visited_rooms,
                    "frontiers": frontiers,
                }
            )
        return nodes

    def _object_hints(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        hints: Dict[str, Dict[str, Any]] = {}
        for name in names:
            if name in self.doors:
                door = self.doors[name]
                hints[name] = {
                    "category": "door",
                    "region": "doorway",
                    "support": "",
                    "confidence": 1.0,
                    "state": "locked" if door.get("locked") else ("open" if door.get("open") else "closed"),
                }
                continue
            obj = self.objects[name]
            status = "known" if obj.get("available", True) else "unknown"
            hints[name] = {
                "category": obj.get("category", "object"),
                "region": obj.get("region", "visible_area"),
                "support": obj.get("support", ""),
                "confidence": 0.95 if status == "known" else 0.3,
                "status": status,
                "state": obj.get("state", "observed"),
            }
        return hints

    def _render_text(self, visible_objects: List[str], visible_frontiers: List[Dict[str, Any]]) -> str:
        object_parts = []
        for name in visible_objects:
            if name in self.doors:
                door = self.doors[name]
                state = "locked" if door.get("locked") else ("open" if door.get("open") else "closed")
                object_parts.append(f"{name} is a {state} door")
                continue
            obj = self.objects[name]
            support = obj.get("support")
            if support and support != "agent_hand":
                object_parts.append(f"{name} is on {support}")
            else:
                object_parts.append(f"{name} is visible")
        frontiers = ", ".join(f"{item['target']} via {item['via']} ({item['status']})" for item in visible_frontiers)
        held = self.holding or "none"
        task_text = f" Task: {self.task}" if self.task_visible else ""
        return (
            f"Room: {self.current_room}. Visible objects: {', '.join(visible_objects)}. "
            f"Observed facts: {'; '.join(object_parts)}. "
            f"Visible frontiers: {frontiers or 'none'}. Agent holding: {held}. "
            f"Visited rooms: {', '.join(sorted(self.visited_rooms))}."
            f"{task_text}"
        )

    def _agent_state(self) -> Dict[str, Any]:
        return {
            "current_room": self.current_room,
            "holding": self.holding,
            "visited_rooms": sorted(self.visited_rooms),
            "known_frontiers": sorted(self.known_frontiers),
            "step": self.step_count,
        }

    def _path_available(self, start: str, target: str) -> bool:
        if start == target:
            return True
        if target in TOPOLOGY.get(start, []):
            door_name = self._door_between(start, target)
            door = self.doors.get(door_name, {})
            return not door.get("locked", False)
        return target in TOPOLOGY

    def _blocking_door(self, start: str, target: str) -> str:
        if target in TOPOLOGY.get(start, []):
            door_name = self._door_between(start, target)
            if self.doors.get(door_name, {}).get("locked"):
                return door_name
        if target == "kitchen" and self.doors["kitchen_door"].get("locked"):
            return "kitchen_door"
        return ""

    def _nearest_room_for_door(self, door: Dict[str, Any]) -> str:
        first, second = door["connects"]
        return first if self.current_room == first else second

    def _door_between(self, room_a: str, room_b: str) -> str:
        for door_name, door in self.doors.items():
            if {room_a, room_b} == set(door["connects"]):
                return door_name
        return DOOR_BY_ROOM.get(room_b, "door")

    def _episode_from_spec(self, episode_spec: Dict[str, Any] | None) -> Dict[str, Any]:
        if not episode_spec:
            return {}
        return {
            "task": episode_spec.get("task", ""),
            "start_room": episode_spec.get("start_room", "bedroom"),
            "expected_status": episode_spec.get("expected_task_status", "complete"),
        }

    def _relocation_exception(self) -> Dict[str, Any]:
        if self.episode_spec:
            exception = self.episode_spec.get("controlled_exception", {})
            if isinstance(exception, dict) and exception.get("type") == "object_relocated":
                return exception
        return {
            "type": "object_relocated",
            "object": "book",
            "to_room": "living_room",
            "to_region": "table_area",
            "to_support": "side_table",
            "likely_locations": ["living_room"],
            "prior_support": "bed",
            "prior_region": "bed_area",
        }

    def _should_relocate_on_pickup(self, obj: str) -> bool:
        if self.episode_spec:
            exception = self.episode_spec.get("controlled_exception", {})
            return (
                isinstance(exception, dict)
                and exception.get("type") == "object_relocated"
                and exception.get("object") == obj
                and not self.generated_relocation_done
            )
        return self.episode_id == "local-explore-book-relocated" and obj == "book" and not self.book_relocated
