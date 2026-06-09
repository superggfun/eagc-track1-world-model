import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from planner.action_schema import is_valid_action


RELATION_STATUSES = {"active", "stale", "inferred", "uncertain"}
LOCATION_RELATIONS = {"on", "inside", "under", "near", "beside", "at"}


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
    object_names = _object_names(objects)
    errors.extend(_validate_agent_state(data.get("agent_state")))
    errors.extend(_validate_topology(data.get("topology")))
    errors.extend(_validate_locations(objects))
    errors.extend(_validate_relations(data.get("relations", []), object_names, objects))
    errors.extend(_validate_actions(data))
    errors.extend(_validate_recovery_links(data))
    errors.extend(_validate_object_relocated(data, objects))
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


def _validate_actions(data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for plan_index, plan in enumerate(data.get("plans", [])):
        if not isinstance(plan, dict):
            continue
        for action in plan.get("actions", []):
            if not is_valid_action(action):
                errors.append(f"plans[{plan_index}] contains invalid action: {action}")
    for affordance in data.get("affordances", []):
        if not isinstance(affordance, dict):
            continue
        for action in affordance.get("actions", []):
            if not is_valid_action(action):
                errors.append(f"affordance for {affordance.get('object')} has invalid action: {action}")
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


def _validate_object_relocated(data: Dict[str, Any], objects: Any) -> List[str]:
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
        obj = _find_object(objects, object_name)
        if not obj or not isinstance(obj.get("location"), dict) or obj["location"].get("status") != "unknown":
            errors.append(f"object_relocated for {object_name} must set object location.status to unknown.")
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


def _find_object(objects: Any, name: str) -> Dict[str, Any] | None:
    if not isinstance(objects, list):
        return None
    for obj in objects:
        if isinstance(obj, dict) and (obj.get("name") == name or obj.get("id") == name):
            return obj
    return None


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
