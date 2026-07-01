import copy
import json
from pathlib import Path

from task_evaluator.task_evaluator import evaluate_task_status
from validators.validate_semantic_consistency import validate
from world_model.index import WorldModelIndex


def test_world_model_index_finds_objects_by_name_and_id() -> None:
    world_model = {
        "objects": [
            {"id": "obj-cup-1", "name": "cup"},
            {"id": "obj-table-1", "name": "table"},
        ],
    }

    index = WorldModelIndex.from_world_model(world_model)

    assert index.find_object("cup") == {"id": "obj-cup-1", "name": "cup"}
    assert index.find_object("obj-table-1") == {"id": "obj-table-1", "name": "table"}
    assert index.iter_objects() == [{"id": "obj-cup-1", "name": "cup"}, {"id": "obj-table-1", "name": "table"}]
    assert "index" not in world_model


def test_world_model_index_has_state_with_optional_value() -> None:
    index = WorldModelIndex.from_world_model(
        {
            "states": [
                {"entity": "drawer", "attribute": "availability", "value": "available"},
                {"entity": "drawer", "attribute": "availability", "value": "unavailable"},
            ]
        }
    )

    assert index.has_state("drawer", "availability")
    assert index.has_state("drawer", "availability", "unavailable")
    assert not index.has_state("drawer", "availability", "locked")


def test_world_model_index_has_active_relation() -> None:
    index = WorldModelIndex.from_world_model(
        {
            "relations": [
                {"subject": "cup", "relation": "inside", "object": "drawer", "status": "stale"},
                {"subject": "cup", "relation": "on", "object": "counter", "status": "active"},
            ]
        }
    )

    assert index.has_relation("cup", "on", "counter")
    assert index.has_relation("cup", "on")
    assert not index.has_relation("cup", "inside", "drawer")


def test_task_evaluator_behavior_is_unchanged_with_index() -> None:
    world_model = {
        "agent_state": {},
        "objects": [
            {"id": "cup", "name": "cup", "location": {"support": "counter"}},
            {"id": "counter", "name": "counter", "location": {}},
        ],
        "states": [{"entity": "drawer", "attribute": "availability", "value": "unavailable"}],
        "relations": [],
    }

    status = evaluate_task_status("", world_model, "mock-kitchen-container-unavailable")

    assert status == {
        "task_status": "blocked_recovered",
        "success": True,
        "reason": "Drawer is unavailable; cup was placed on the counter as a safe fallback.",
        "evidence": ["drawer availability unavailable", "cup support counter"],
    }


def test_semantic_validator_output_is_unchanged_with_index(tmp_path: Path) -> None:
    world_model = _valid_semantic_world_model()
    world_model["exceptions"] = [{"exception": {"type": "door_locked", "object": "kitchen_door"}}]
    path = tmp_path / "world_model.json"
    path.write_text(json.dumps(world_model), encoding="utf-8")

    assert validate(path) == ["door_locked exception must record a locked state."]

    fixed = copy.deepcopy(world_model)
    fixed["states"].append({"entity": "kitchen_door", "attribute": "status", "value": "locked"})
    path.write_text(json.dumps(fixed), encoding="utf-8")

    assert validate(path) == []


def _valid_semantic_world_model() -> dict:
    return {
        "agent_state": {
            "current_room": "kitchen",
            "holding": None,
            "step": 1,
            "last_action": "observe()",
            "mode": "mock",
        },
        "topology": [{"room": "kitchen", "visited": True, "frontiers": []}],
        "objects": [
            {
                "id": "cup",
                "name": "cup",
                "category": "portable",
                "location": {"status": "known", "confidence": 0.9, "room": "kitchen", "support": "table"},
            },
            {
                "id": "table",
                "name": "table",
                "category": "surface",
                "location": {"status": "known", "confidence": 0.9, "room": "kitchen"},
            },
            {
                "id": "kitchen_door",
                "name": "kitchen_door",
                "category": "door",
                "location": {"status": "known", "confidence": 0.9, "room": "kitchen"},
            },
        ],
        "relations": [
            {
                "subject": "cup",
                "relation": "on",
                "object": "table",
                "status": "active",
                "confidence": 0.9,
                "observed_at_step": 1,
            }
        ],
        "states": [],
        "plans": [],
        "affordances": [],
        "exceptions": [],
    }
