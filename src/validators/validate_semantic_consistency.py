import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from planner.action_schema import is_valid_action, parse_action
from world_model.index import WorldModelIndex


RELATION_STATUSES = {"active", "stale", "inferred", "uncertain"}
LOCATION_RELATIONS = {"on", "inside", "under", "near", "beside", "at"}
PLACEHOLDER_ARGS = {"object", "target", "thing", "item", "entity"}
ALLOWED_SYMBOLIC_REGIONS = {
    "visible_area",
    "under_mat",
    "agent_hand",
    "next_room",
    "on",
    "inside",
    "under",
    "near",
    "beside",
    "at",
}
PICKUP_BLOCKED_CATEGORIES = {"furniture", "room", "door", "container", "surface", "inferred_support"}
INTERACTIVE_NAMES = {"door", "drawer", "cabinet", "container", "box"}
INTERACTIVE_CATEGORIES = {"door", "drawer", "container", "furniture", "inferred_support"}
SUPPORT_CATEGORIES = {"furniture", "container", "surface", "inferred_support"}


def validate(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.exists():
        return [f"Missing world model file: {path}"]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return ["World model must be a JSON object."]

    objects = data.get("objects", [])
    index = WorldModelIndex.from_world_model(data)
    object_names = _object_names(objects)
    errors.extend(_validate_agent_state(data.get("agent_state")))
    errors.extend(_validate_topology(data.get("topology")))
    errors.extend(_validate_locations(objects))
    errors.extend(_validate_relations(data.get("relations", []), object_names, objects))
    errors.extend(_validate_location_relation_consistency(data, index))
    errors.extend(_validate_holding_consistency(data, index))
    errors.extend(_validate_actions(data, objects))
    errors.extend(_validate_recovery_links(data))
    errors.extend(_validate_object_relocated(data, index))
    errors.extend(_validate_exception_state_effects(data, index))
    return errors


def _validate_agent_state(agent_state: Any) -> List[str]:
    required = ["current_room", "holding", "step", "last_action", "mode"]
    if not isinstance(agent_state, dict) or not agent_state:
        return ["agent_state must be a non-empty object."]
    return [f"agent_state missing field: {field}" for field in required if field not in agent_state]


def _validate_topology(topology: Any) -> List[str]:
    if not isinstance(topology, list) or not topology:
        return ["topology must be a non-empty list."]
    errors: List[str] = []
    if not any(isinstance(node, dict) and node.get("visited") is True for node in topology):
        errors.append("topology must include at least one visited room node.")
    if not any(isinstance(node, dict) and isinstance(node.get("frontiers"), list) for node in topology):
        errors.append("topology must include frontiers.")
    return errors


def _validate_locations(objects: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(objects, list):
        return ["objects must be a list."]
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        location = obj.get("location")
        if not isinstance(location, dict):
            errors.append(f"{obj.get('name', '<unknown>')} location must be structured.")
            continue
        if location.get("status") not in {"known", "unknown", "inferred"}:
            errors.append(f"{obj.get('name')} has invalid location.status: {location.get('status')}")
        confidence = location.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            errors.append(f"{obj.get('name')} location.confidence must be between 0.0 and 1.0.")
    return errors


def _validate_relations(relations: Any, object_names: Set[str], objects: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(relations, list):
        return ["relations must be a list."]
    unknown_location_objects = {
        obj.get("name")
        for obj in objects
        if isinstance(obj, dict)
        and isinstance(obj.get("location"), dict)
        and obj["location"].get("status") == "unknown"
    }

    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(f"relations[{index}] must be an object.")
            continue
        for field in ["subject", "relation", "object", "status", "confidence", "observed_at_step"]:
            if field not in relation:
                errors.append(f"relations[{index}] missing field: {field}")
        if relation.get("status") not in RELATION_STATUSES:
            errors.append(f"relations[{index}] invalid status: {relation.get('status')}")
        for endpoint in ["subject", "object"]:
            value = relation.get(endpoint)
            if value and value not in object_names:
                errors.append(
                    f"relations[{index}].{endpoint}={value!r} is not present in objects; "
                    "create an inferred object if it is an inferred support."
                )
        if (
            relation.get("subject") in unknown_location_objects
            and relation.get("relation") in LOCATION_RELATIONS
            and relation.get("status") == "active"
        ):
            errors.append(
                f"{relation.get('subject')} has unknown location but active location relation remains: "
                f"{relation.get('relation')} {relation.get('object')}"
            )
    return errors


def _validate_actions(data: Dict[str, Any], objects: Any) -> List[str]:
    errors: List[str] = []
    context = _action_context(data, objects)
    for plan_index, plan in enumerate(data.get("plans", [])):
        if not isinstance(plan, dict):
            continue
        for action in plan.get("actions", []):
            errors.extend(_validate_action(action, context, f"plans[{plan_index}]"))
    for affordance in data.get("affordances", []):
        if not isinstance(affordance, dict):
            continue
        for action in affordance.get("actions", []):
            errors.extend(_validate_action(action, context, f"affordance for {affordance.get('object')}"))
    return errors


def _validate_recovery_links(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    plan_signatures = {
        _plan_signature(plan) for plan in data.get("plans", []) if isinstance(plan, dict)
    }
    for index, exception in enumerate(data.get("exceptions", [])):
        if not isinstance(exception, dict) or "recovery_plan" not in exception:
            continue
        recovery_plan = exception.get("recovery_plan")
        if _plan_signature(recovery_plan) not in plan_signatures:
            errors.append(f"exceptions[{index}].recovery_plan does not match any plan entry.")
    return errors


def _validate_object_relocated(data: Dict[str, Any], index: WorldModelIndex) -> List[str]:
    errors: List[str] = []
    relocated = [
        item
        for item in data.get("exceptions", [])
        if isinstance(item, dict)
        and isinstance(item.get("exception"), dict)
        and item["exception"].get("type") == "object_relocated"
    ]
    for item in relocated:
        object_name = item["exception"].get("object")
        obj = index.find_object(object_name)
        if not obj or not isinstance(obj.get("location"), dict):
            errors.append(f"object_relocated for {object_name} must keep a structured object location.")
        stale_found = any(
            isinstance(relation, dict)
            and relation.get("subject") == object_name
            and relation.get("relation") in LOCATION_RELATIONS
            and relation.get("status") == "stale"
            for relation in data.get("relations", [])
        )
        if not stale_found:
            errors.append(f"object_relocated for {object_name} must leave a stale previous relation.")
        recovery_actions = item.get("recovery_plan", {}).get("actions", [])
        if not any(isinstance(action, str) and action.startswith("search(") for action in recovery_actions):
            errors.append(f"object_relocated for {object_name} must include recovery search actions.")
    return errors


def _validate_location_relation_consistency(data: Dict[str, Any], index: WorldModelIndex) -> List[str]:
    errors: List[str] = []
    objects = data.get("objects", [])
    relations = data.get("relations", [])
    if not isinstance(objects, list) or not isinstance(relations, list):
        return errors

    active_by_subject: Dict[str, List[Dict[str, Any]]] = {
        subject: [relation for relation in active_relations if relation.get("relation") in LOCATION_RELATIONS]
        for subject, active_relations in index.active_relations_by_subject.items()
    }

    for subject, active_relations in active_by_subject.items():
        if len(active_relations) > 1:
            rendered = [f"{rel.get('relation')} {rel.get('object')}" for rel in active_relations]
            errors.append(f"{subject} has multiple active location relations: {rendered}")

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name") or obj.get("id"))
        location = obj.get("location")
        if not isinstance(location, dict):
            continue
        support = location.get("support")
        if location.get("status") == "known" and support and support != "agent_hand":
            if not any(rel.get("object") == support for rel in active_by_subject.get(name, [])):
                errors.append(f"{name} location.support={support!r} lacks matching active relation.")
        if location.get("status") == "known" and support == "agent_hand":
            holding = data.get("agent_state", {}).get("holding")
            if holding != name:
                errors.append(f"{name} is supported by agent_hand but agent_state.holding is {holding!r}.")
    return errors


def _validate_holding_consistency(data: Dict[str, Any], index: WorldModelIndex) -> List[str]:
    errors: List[str] = []
    agent_state = data.get("agent_state", {})
    holding = agent_state.get("holding") if isinstance(agent_state, dict) else None
    states = data.get("states", [])

    held_by_agent = [
        state
        for state in states
        if isinstance(state, dict)
        and state.get("attribute") == "held_by"
        and state.get("value") == "agent"
    ]
    if holding is None and held_by_agent:
        errors.append("agent_state.holding is null but states still contain held_by=agent.")
    if holding is not None:
        obj = index.find_object(str(holding))
        if not obj or not isinstance(obj.get("location"), dict):
            errors.append(f"held object {holding} is missing structured location.")
        elif obj["location"].get("support") != "agent_hand":
            errors.append(f"held object {holding} must have location.support=agent_hand.")
    return errors


def _validate_exception_state_effects(data: Dict[str, Any], index: WorldModelIndex) -> List[str]:
    errors: List[str] = []
    for item in data.get("exceptions", []):
        if not isinstance(item, dict) or not isinstance(item.get("exception"), dict):
            continue
        exception = item["exception"]
        exception_type = exception.get("type")
        obj = exception.get("object")
        if exception_type == "door_locked":
            if (
                not index.has_state(obj, "lock_state", "locked")
                and not index.has_state(obj, "status", "locked")
                and not index.has_state(obj, "observed_lock_state", "locked")
            ):
                errors.append("door_locked exception must record a locked state.")
        elif exception_type == "target_container_unavailable":
            if not index.has_state(obj, "availability", "unavailable"):
                errors.append("target_container_unavailable exception must record unavailable state.")
        elif exception_type == "tool_substitution":
            substitute = exception.get("substitute")
            if not substitute:
                errors.append("tool_substitution exception must include substitute.")
            if not index.has_state("task", "substitute_tool", substitute):
                errors.append("tool_substitution must record substitute_tool state.")
    return errors


def _validate_action(action: str, context: Dict[str, Any], source: str) -> List[str]:
    errors: List[str] = []
    if not is_valid_action(action):
        return [f"{source} contains invalid action: {action}"]

    action_name, args = parse_action(action)
    for arg in args:
        if arg in PLACEHOLDER_ARGS:
            errors.append(f"{source} action {action} uses generic placeholder argument: {arg}")
        if arg not in context["known_args"]:
            errors.append(f"{source} action {action} references unknown argument: {arg}")

    objects_by_name = context["objects_by_name"]
    if action_name == "pick_up" and args:
        obj = objects_by_name.get(args[0])
        category = str(obj.get("category", "")) if obj else ""
        if category in PICKUP_BLOCKED_CATEGORIES or args[0] in {"door", "drawer"}:
            errors.append(f"{source} action {action} tries to pick up non-portable object.")
    elif action_name in {"open", "unlock", "close"} and args:
        obj = objects_by_name.get(args[0])
        category = str(obj.get("category", "")) if obj else ""
        if args[0] not in INTERACTIVE_NAMES and category not in INTERACTIVE_CATEGORIES:
            errors.append(f"{source} action {action} targets an object without interactive affordance.")
    elif action_name == "place_on" and len(args) == 2:
        target = objects_by_name.get(args[1])
        if target is None:
            errors.append(f"{source} action {action} target does not exist.")
        else:
            category = str(target.get("category", ""))
            support_actions = context["affordance_actions"].get(args[1], set())
            if category not in SUPPORT_CATEGORIES and not any(a.startswith("place_on(") for a in support_actions):
                errors.append(f"{source} action {action} target is not a known support surface.")
    return errors


def _action_context(data: Dict[str, Any], objects: Any) -> Dict[str, Any]:
    objects_by_name: Dict[str, Dict[str, Any]] = {}
    known_args = set(ALLOWED_SYMBOLIC_REGIONS)
    regions = set()
    if isinstance(objects, list):
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            for key in ["id", "name"]:
                if obj.get(key):
                    known_args.add(str(obj[key]))
                    objects_by_name[str(obj[key])] = obj
            location = obj.get("location")
            if isinstance(location, dict):
                for key in ["room", "region", "support"]:
                    value = location.get(key)
                    if value:
                        known_args.add(str(value))
                        regions.add(str(value))

    for node in data.get("topology", []):
        if not isinstance(node, dict):
            continue
        if node.get("room"):
            known_args.add(str(node["room"]))
        for frontier in node.get("frontiers", []):
            if isinstance(frontier, dict) and frontier.get("target"):
                known_args.add(str(frontier["target"]))

    affordance_actions: Dict[str, set[str]] = {}
    for affordance in data.get("affordances", []):
        if isinstance(affordance, dict) and affordance.get("object"):
            affordance_actions[str(affordance["object"])] = set(affordance.get("actions", []))

    return {
        "known_args": known_args | regions,
        "objects_by_name": objects_by_name,
        "affordance_actions": affordance_actions,
    }


def _object_names(objects: Any) -> Set[str]:
    names: Set[str] = set()
    if not isinstance(objects, list):
        return names
    for obj in objects:
        if isinstance(obj, dict):
            if obj.get("id"):
                names.add(str(obj["id"]))
            if obj.get("name"):
                names.add(str(obj["name"]))
    return names


def _plan_signature(plan: Any) -> tuple:
    if not isinstance(plan, dict):
        return ()
    return (
        plan.get("planner"),
        plan.get("trigger"),
        tuple(plan.get("subgoals", [])),
        tuple(plan.get("actions", [])),
    )


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs/world_model.json")
    errors = validate(path)
    if errors:
        print("Semantic consistency validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Semantic consistency validation passed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
