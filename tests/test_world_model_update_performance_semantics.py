"""Performance-semantics tests for world_model/update.py upsert functions.

Verifies that the O(1)-indexed upsert implementations produce identical
output to the previous O(n²) linear-scan versions.

Covers:
- upsert_objects: same id/name updates without duplicate append
- upsert_states: same (entity, attribute) updates without duplicate append
- upsert_topology: same room update, frontier merge correctness
- _merge_frontiers: same (target, via) update without duplicate append
- upsert_relations: stale semantics, same-key non-stale, cross-subject non-stale
- _fingerprint: nested dict/list safety, no unhashable errors
- merge_unique: nested dedup, custom key parameter
- _ensure_support_object: index optimisation, no duplicate insert
- _reconcile_support_relation: index optimisation, stale semantics preserved
- Non-dict input filtering
- Order stability
- Large-input smoke test (1000 existing + 100 incoming)
"""

from pathlib import Path

import pytest
from sys import path as sys_path

sys_path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_model.update import (  # noqa: E402
    _ensure_support_object,
    _fingerprint,
    _freeze_for_fingerprint,
    _is_active_location_relation,
    _merge_frontiers,
    _reconcile_support_relation,
    apply_frame_visibility,
    merge_affordances,
    merge_unique,
    upsert_objects,
    upsert_relations,
    upsert_states,
    upsert_topology,
)


# ---------------------------------------------------------------------------
# upsert_objects
# ---------------------------------------------------------------------------

class TestUpsertObjects:
    def test_upsert_by_id_updates_in_place(self):
        existing = [
            {"id": "obj1", "name": "cup", "color": "red"},
            {"id": "obj2", "name": "plate", "color": "blue"},
        ]
        incoming = [{"id": "obj1", "name": "cup", "color": "green"}]
        result = upsert_objects(existing, incoming)
        assert len(result) == 2
        assert result[0]["color"] == "green"
        assert result[1]["color"] == "blue"

    def test_upsert_by_name_falls_back_when_no_id(self):
        existing = [{"name": "cup", "color": "red"}]
        incoming = [{"name": "cup", "color": "green"}]
        result = upsert_objects(existing, incoming)
        assert len(result) == 1
        assert result[0]["color"] == "green"

    def test_new_object_appended(self):
        existing = [{"id": "obj1", "name": "cup"}]
        incoming = [{"id": "obj2", "name": "plate"}]
        result = upsert_objects(existing, incoming)
        assert len(result) == 2
        assert result[1]["name"] == "plate"

    def test_non_dict_incoming_skipped(self):
        existing = [{"id": "obj1"}]
        incoming = ["not_a_dict", {"id": "obj2"}]
        result = upsert_objects(existing, incoming)
        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

    def test_non_dict_existing_filtered(self):
        existing = ["bad", {"id": "obj1"}]
        incoming = []
        result = upsert_objects(existing, incoming)
        assert len(result) == 1
        assert result[0]["id"] == "obj1"

    def test_merge_preserves_extra_fields(self):
        existing = [{"id": "obj1", "name": "cup", "extra_field": "keep_me"}]
        incoming = [{"id": "obj1", "color": "green"}]
        result = upsert_objects(existing, incoming)
        assert result[0]["extra_field"] == "keep_me"
        assert result[0]["color"] == "green"

    def test_many_existing_and_incoming(self):
        existing = [{"id": f"obj_{i}", "data": i} for i in range(1000)]
        incoming = [{"id": f"obj_{i}", "data": i * 10} for i in range(50)]
        incoming += [{"id": f"new_{i}", "data": i} for i in range(50)]
        result = upsert_objects(existing, incoming)
        assert len(result) == 1050
        assert result[0]["data"] == 0
        assert result[49]["data"] == 490
        assert result[999]["data"] == 999
        assert result[-1]["id"] == "new_49"


# ---------------------------------------------------------------------------
# upsert_states
# ---------------------------------------------------------------------------

class TestUpsertStates:
    def test_same_entity_attribute_updates(self):
        existing = [
            {"entity": "cup", "attribute": "visibility", "value": "visible"},
            {"entity": "cup", "attribute": "location", "value": "table"},
        ]
        incoming = [{"entity": "cup", "attribute": "visibility", "value": "hidden"}]
        result = upsert_states(existing, incoming)
        assert len(result) == 2
        vis = next(s for s in result if s["attribute"] == "visibility")
        assert vis["value"] == "hidden"

    def test_new_state_appended(self):
        existing = [{"entity": "cup", "attribute": "visibility", "value": "visible"}]
        incoming = [{"entity": "cup", "attribute": "location", "value": "table"}]
        result = upsert_states(existing, incoming)
        assert len(result) == 2
        assert any(s["attribute"] == "location" for s in result)

    def test_non_dict_skipped(self):
        existing = [{"entity": "cup", "attribute": "vis", "value": "v"}]
        incoming = ["bad", {"entity": "cup", "attribute": "loc", "value": "t"}]
        result = upsert_states(existing, incoming)
        assert len(result) == 2

    def test_many_states(self):
        existing = [
            {"entity": f"e{i}", "attribute": f"a{i}", "value": i} for i in range(1000)
        ]
        incoming = [
            {"entity": f"e{i}", "attribute": f"a{i}", "value": i * 2} for i in range(50)
        ]
        incoming += [
            {"entity": f"new_e{i}", "attribute": f"new_a{i}", "value": i}
            for i in range(50)
        ]
        result = upsert_states(existing, incoming)
        assert len(result) == 1050
        assert result[0]["value"] == 0
        assert result[49]["value"] == 98


# ---------------------------------------------------------------------------
# upsert_topology
# ---------------------------------------------------------------------------

class TestUpsertTopology:
    def test_same_room_updates(self):
        existing = [
            {"room": "kitchen", "visited": True, "frontiers": []},
            {"room": "living_room", "visited": False, "frontiers": []},
        ]
        incoming = [{"room": "kitchen", "visited": False, "frontiers": []}]
        result = upsert_topology(existing, incoming)
        assert len(result) == 2
        kitchen = next(n for n in result if n["room"] == "kitchen")
        assert kitchen["visited"] is True

    def test_new_room_appended(self):
        existing = [{"room": "kitchen", "visited": True, "frontiers": []}]
        incoming = [{"room": "bathroom", "visited": False, "frontiers": []}]
        result = upsert_topology(existing, incoming)
        assert len(result) == 2
        assert result[1]["room"] == "bathroom"

    def test_merges_frontiers(self):
        existing = [{
            "room": "kitchen", "visited": True,
            "frontiers": [{"target": "living_room", "via": "door"}],
        }]
        incoming = [{
            "room": "kitchen", "visited": True,
            "frontiers": [{"target": "hallway", "via": "doorway"}],
        }]
        result = upsert_topology(existing, incoming)
        assert len(result) == 1
        assert len(result[0]["frontiers"]) == 2

    def test_same_frontier_merged_not_duplicated(self):
        existing = [{
            "room": "kitchen", "visited": True,
            "frontiers": [{"target": "living_room", "via": "door", "extra": "old"}],
        }]
        incoming = [{
            "room": "kitchen", "visited": True,
            "frontiers": [{"target": "living_room", "via": "door", "extra": "new"}],
        }]
        result = upsert_topology(existing, incoming)
        assert len(result[0]["frontiers"]) == 1
        assert result[0]["frontiers"][0]["extra"] == "new"

    def test_non_dict_topology_skipped(self):
        existing = [{"room": "kitchen", "visited": True, "frontiers": []}]
        incoming = ["bad", {"room": "hallway", "visited": False, "frontiers": []}]
        result = upsert_topology(existing, incoming)
        assert len(result) == 2

    def test_missing_room_skipped(self):
        incoming = [{"visited": True, "frontiers": []}]
        result = upsert_topology([], incoming)
        assert len(result) == 0

    def test_non_list_frontiers_normalized(self):
        incoming = [{"room": "kitchen", "visited": True, "frontiers": "not_a_list"}]
        result = upsert_topology([], incoming)
        assert result[0]["frontiers"] == []


# ---------------------------------------------------------------------------
# _merge_frontiers
# ---------------------------------------------------------------------------

class TestMergeFrontiers:
    def test_same_key_updates(self):
        existing = [{"target": "living_room", "via": "door", "extra": "old"}]
        incoming = [{"target": "living_room", "via": "door", "extra": "new"}]
        result = _merge_frontiers(existing, incoming)
        assert len(result) == 1
        assert result[0]["extra"] == "new"

    def test_new_key_appended(self):
        existing = [{"target": "living_room", "via": "door"}]
        incoming = [{"target": "hallway", "via": "doorway"}]
        result = _merge_frontiers(existing, incoming)
        assert len(result) == 2

    def test_non_dict_incoming_skipped(self):
        existing = [{"target": "a", "via": "b"}]
        incoming = ["bad", {"target": "c", "via": "d"}]
        result = _merge_frontiers(existing, incoming)
        assert len(result) == 2

    def test_non_dict_existing_filtered(self):
        existing = ["bad", {"target": "a", "via": "b"}]
        incoming = []
        result = _merge_frontiers(existing, incoming)
        assert len(result) == 1
        assert result[0]["target"] == "a"

    def test_many_frontiers(self):
        existing = [{"target": f"t{i}", "via": f"v{i}", "d": i} for i in range(500)]
        incoming = [{"target": f"t{i}", "via": f"v{i}", "d": i * 10} for i in range(100)]
        incoming += [{"target": f"new_t{i}", "via": f"new_v{i}", "d": i} for i in range(50)]
        result = _merge_frontiers(existing, incoming)
        assert len(result) == 550
        assert result[0]["d"] == 0
        assert result[99]["d"] == 990


# ---------------------------------------------------------------------------
# upsert_relations — stale semantics
# ---------------------------------------------------------------------------

class TestUpsertRelationsStale:
    def test_new_active_location_relation_stales_same_subject_active(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9, "observed_at_step": 1},
            {"subject": "plate", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.8, "observed_at_step": 1},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "active", "confidence": 0.95, "observed_at_step": 2},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 3
        old_cup = next(r for r in result if r["subject"] == "cup" and r["object"] == "table")
        assert old_cup["status"] == "stale"
        assert old_cup["confidence"] <= 0.2
        new_cup = next(r for r in result if r["subject"] == "cup" and r["object"] == "shelf")
        assert new_cup["status"] == "active"
        assert new_cup["confidence"] == 0.95
        plate_rel = next(r for r in result if r["subject"] == "plate")
        assert plate_rel["status"] == "active"
        assert plate_rel["confidence"] == 0.8

    def test_same_key_relation_is_not_staled(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9, "observed_at_step": 1},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.99, "observed_at_step": 2},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 1
        assert result[0]["status"] == "active"
        assert result[0]["confidence"] == 0.99

    def test_different_subject_not_staled(self):
        existing = [
            {"subject": "plate", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.8},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "active", "confidence": 0.95},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 2
        plate = next(r for r in result if r["subject"] == "plate")
        assert plate["status"] == "active"

    def test_non_location_relation_does_not_trigger_stale(self):
        existing = [
            {"subject": "cup", "relation": "inside", "object": "cabinet",
             "status": "active", "confidence": 0.9},
        ]
        incoming = [
            {"subject": "cup", "relation": "has_color", "object": "red",
             "status": "active", "confidence": 0.9},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 2
        old = next(r for r in result if r["relation"] == "inside")
        assert old["status"] == "active"

    def test_non_active_location_relation_is_ignored_for_stale(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "stale", "confidence": 0.1},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "inferred", "confidence": 0.5},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 2
        old = next(r for r in result if r["object"] == "table")
        assert old["status"] == "stale"

    def test_active_to_inactive_removed_from_active_index(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "stale", "confidence": 0.1},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 1
        assert result[0]["status"] == "stale"

        incoming2 = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "active", "confidence": 0.95},
        ]
        result2 = upsert_relations(result, incoming2)
        assert len(result2) == 2
        old_stale = next(r for r in result2 if r["object"] == "table")
        assert old_stale["status"] == "stale"

    def test_multiple_incoming_stale_cascade(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9, "observed_at_step": 1},
            {"subject": "cup", "relation": "inside", "object": "cabinet",
             "status": "active", "confidence": 0.8, "observed_at_step": 1},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "active", "confidence": 0.95, "observed_at_step": 2},
            {"subject": "cup", "relation": "inside", "object": "drawer",
             "status": "active", "confidence": 0.85, "observed_at_step": 2},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 4
        table_rel = next(r for r in result if r["object"] == "table")
        cabinet_rel = next(r for r in result if r["object"] == "cabinet")
        shelf = next(r for r in result if r["object"] == "shelf")
        drawer = next(r for r in result if r["object"] == "drawer")
        assert table_rel["status"] == "stale"
        assert cabinet_rel["status"] == "stale"
        assert shelf["status"] == "stale"
        assert drawer["status"] == "active"

    def test_non_dict_incoming_skipped(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9},
        ]
        incoming = [
            "not_a_relation",
            {"subject": "plate", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.8},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 2

    def test_same_subject_same_key_not_staled_other_same_subject_diff_key_staled(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.9},
            {"subject": "cup", "relation": "inside", "object": "cabinet",
             "status": "active", "confidence": 0.8},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.99},
        ]
        result = upsert_relations(existing, incoming)
        assert len(result) == 2
        on_table = next(r for r in result if r["object"] == "table")
        assert on_table["status"] == "active"
        assert on_table["confidence"] == 0.99
        inside = next(r for r in result if r["object"] == "cabinet")
        assert inside["status"] == "stale"
        assert inside["confidence"] <= 0.2

    def test_already_stale_confidence_preserved_at_ceiling(self):
        existing = [
            {"subject": "cup", "relation": "on", "object": "table",
             "status": "active", "confidence": 0.05},
        ]
        incoming = [
            {"subject": "cup", "relation": "on", "object": "shelf",
             "status": "active", "confidence": 0.95},
        ]
        result = upsert_relations(existing, incoming)
        old = next(r for r in result if r["object"] == "table")
        assert old["status"] == "stale"
        assert old["confidence"] <= 0.2

    def test_large_scale_relations(self):
        existing = []
        for i in range(500):
            existing.append({
                "subject": f"obj_{i}", "relation": "on", "object": f"support_{i}",
                "status": "active", "confidence": 0.9,
            })
            existing.append({
                "subject": f"obj_{i}", "relation": "has_color", "object": f"color_{i}",
                "status": "active", "confidence": 0.95,
            })
        incoming = []
        for i in range(50):
            incoming.append({
                "subject": f"obj_{i}", "relation": "on", "object": f"new_support_{i}",
                "status": "active", "confidence": 0.99,
            })
        for i in range(50):
            incoming.append({
                "subject": f"new_obj_{i}", "relation": "on", "object": f"support_{i}",
                "status": "active", "confidence": 0.9,
            })
        result = upsert_relations(existing, incoming)
        assert len(result) == 1100
        for i in range(50):
            obj_name = f"obj_{i}"
            active_rels = [
                r for r in result
                if r["subject"] == obj_name and r["relation"] == "on"
                and r["object"] == f"new_support_{i}" and r["status"] == "active"
            ]
            assert len(active_rels) == 1
        for i in range(50, 500):
            color_rels = [
                r for r in result
                if r["subject"] == f"obj_{i}" and r["relation"] == "has_color"
            ]
            assert len(color_rels) == 1
            assert color_rels[0]["status"] == "active"


# ---------------------------------------------------------------------------
# merge_affordances
# ---------------------------------------------------------------------------

class TestMergeAffordances:
    def test_same_object_merges_actions(self):
        existing = [{"object": "cup", "actions": ["pick_up"]}]
        incoming = [{"object": "cup", "actions": ["put_down"]}]
        result = merge_affordances(existing, incoming)
        assert len(result) == 1
        assert set(result[0]["actions"]) == {"pick_up", "put_down"}

    def test_new_object_appended(self):
        existing = [{"object": "cup", "actions": ["pick_up"]}]
        incoming = [{"object": "plate", "actions": ["pick_up"]}]
        result = merge_affordances(existing, incoming)
        assert len(result) == 2

    def test_duplicate_actions_not_duplicated(self):
        existing = [{"object": "cup", "actions": ["pick_up"]}]
        incoming = [{"object": "cup", "actions": ["pick_up", "put_down"]}]
        result = merge_affordances(existing, incoming)
        assert result[0]["actions"] == ["pick_up", "put_down"]

    def test_non_dict_skipped(self):
        incoming = ["bad", {"object": "cup", "actions": ["pick_up"]}]
        result = merge_affordances([], incoming)
        assert len(result) == 1

    def test_many_affordances(self):
        existing = [{"object": f"obj_{i}", "actions": [f"a_{i}"]} for i in range(500)]
        incoming = [{"object": f"obj_{i}", "actions": [f"a_{i}", f"b_{i}"]} for i in range(100)]
        incoming += [{"object": f"new_{i}", "actions": ["pick_up"]} for i in range(50)]
        result = merge_affordances(existing, incoming)
        assert len(result) == 550


# ---------------------------------------------------------------------------
# _is_active_location_relation
# ---------------------------------------------------------------------------

class TestIsActiveLocationRelation:
    def test_active_on_is_true(self):
        assert _is_active_location_relation(
            {"status": "active", "relation": "on"}) is True

    def test_stale_on_is_false(self):
        assert _is_active_location_relation(
            {"status": "stale", "relation": "on"}) is False

    def test_active_has_color_is_false(self):
        assert _is_active_location_relation(
            {"status": "active", "relation": "has_color"}) is False

    def test_active_location_relations_are_true(self):
        for rel in ["on", "inside", "under", "near", "beside", "at"]:
            assert _is_active_location_relation(
                {"status": "active", "relation": rel}) is True


# ---------------------------------------------------------------------------
# _fingerprint — nested dict/list safety
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_flat_dict(self):
        result = _fingerprint({"a": 1, "b": 2})
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_nested_dict(self):
        result = _fingerprint({"a": {"b": 1}, "c": [2, 3]})
        assert isinstance(result, tuple)

    def test_list_with_dicts(self):
        result = _fingerprint([{"a": 1}, {"b": 2}])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_nested_lists(self):
        result = _fingerprint({"data": [1, [2, 3], {"x": "y"}]})
        assert isinstance(result, tuple)

    def test_unhashable_dict_value(self):
        result = _fingerprint({"items": [{"name": "cup"}, {"name": "plate"}]})
        assert isinstance(result, tuple)

    def test_empty_structures(self):
        assert _fingerprint({}) == ()
        assert _fingerprint([]) == ()
        assert _fingerprint(set()) == ()

    def test_scalar_values(self):
        assert _fingerprint(42) == 42
        assert _fingerprint("hello") == "hello"
        assert _fingerprint(None) is None
        assert _fingerprint(True) is True

    def test_deterministic_ordering(self):
        a = {"b": 1, "a": 2}
        b = {"a": 2, "b": 1}
        assert _fingerprint(a) == _fingerprint(b)

    def test_freezes_sets(self):
        result = _fingerprint({3, 1, 2})
        assert isinstance(result, tuple)
        assert result == (1, 2, 3)


# ---------------------------------------------------------------------------
# merge_unique — nested dedup + key parameter
# ---------------------------------------------------------------------------

class TestMergeUnique:
    def test_nested_dict_dedup(self):
        existing = [{"a": {"nested": True}}]
        incoming = [{"a": {"nested": True}}]
        result = merge_unique(existing, incoming)
        assert len(result) == 1

    def test_nested_list_dedup(self):
        existing = [{"items": [1, 2, 3]}]
        incoming = [{"items": [1, 2, 3]}]
        result = merge_unique(existing, incoming)
        assert len(result) == 1

    def test_different_nested_not_deduped(self):
        existing = [{"a": {"b": 1}}]
        incoming = [{"a": {"b": 2}}]
        result = merge_unique(existing, incoming)
        assert len(result) == 2

    def test_with_custom_key(self):
        existing = [1, 2, 3]
        incoming = [2, 4]
        result = merge_unique(existing, incoming, key=lambda x: x)
        assert result == [1, 2, 3, 4]

    def test_with_custom_key_tuples(self):
        existing = [(1, "a"), (2, "b")]
        incoming = [(1, "a"), (3, "c")]
        result = merge_unique(existing, incoming, key=lambda x: x)
        assert result == [(1, "a"), (2, "b"), (3, "c")]

    def test_scalar_dedup(self):
        existing = ["a", "b"]
        incoming = ["b", "c"]
        result = merge_unique(existing, incoming)
        assert result == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _ensure_support_object — index optimisation
# ---------------------------------------------------------------------------

class TestEnsureSupportObject:
    @staticmethod
    def _empty_wm():
        return {"objects": [], "relations": [], "states": []}

    def test_no_index_uses_linear_scan(self):
        wm = self._empty_wm()
        wm["objects"] = upsert_objects(wm["objects"], [{"id": "table", "name": "table"}])
        _ensure_support_object(wm, "table", "kitchen")
        assert len(wm["objects"]) == 1

    def test_with_index_avoids_duplicate(self):
        wm = self._empty_wm()
        wm["objects"] = upsert_objects(wm["objects"], [{"id": "sofa", "name": "sofa"}])
        idx: set[str] = {"sofa"}
        _ensure_support_object(wm, "sofa", "living_room", object_identity_index=idx)
        assert len(wm["objects"]) == 1

    def test_index_updated_after_insert(self):
        wm = self._empty_wm()
        idx: set[str] = set()
        _ensure_support_object(wm, "chair", "kitchen", object_identity_index=idx)
        assert "chair" in idx
        assert len(wm["objects"]) == 1

    def test_index_prevents_double_insert(self):
        wm = self._empty_wm()
        idx: set[str] = set()
        _ensure_support_object(wm, "table", "kitchen", object_identity_index=idx)
        _ensure_support_object(wm, "table", "kitchen", object_identity_index=idx)
        assert len(wm["objects"]) == 1

    def test_without_index_falls_back_to_scan(self):
        wm = self._empty_wm()
        wm["objects"] = upsert_objects(wm["objects"], [{"id": "lamp", "name": "lamp"}])
        _ensure_support_object(wm, "lamp", "bedroom")
        assert len(wm["objects"]) == 1


# ---------------------------------------------------------------------------
# _reconcile_support_relation — index optimisation
# ---------------------------------------------------------------------------

class TestReconcileSupportRelation:
    @staticmethod
    def _empty_wm():
        return {"objects": [], "relations": [], "states": []}

    def test_no_index_uses_linear_scan(self):
        wm = self._empty_wm()
        upsert_objects(wm["objects"], [{"id": "cup", "name": "cup"}])
        _ensure_support_object(wm, "table", "kitchen")
        _reconcile_support_relation(wm, "cup", "table")
        active = [r for r in wm["relations"] if r["status"] == "active"]
        assert len(active) == 1
        assert active[0]["subject"] == "cup"
        assert active[0]["relation"] == "on"
        assert active[0]["object"] == "table"

    def test_with_index_skips_when_already_active(self):
        wm = self._empty_wm()
        upsert_objects(wm["objects"], [
            {"id": "cup", "name": "cup"}, {"id": "table", "name": "table"},
        ])
        wm["relations"] = [{
            "subject": "cup", "relation": "on", "object": "table",
            "status": "active", "confidence": 0.85, "observed_at_step": 1,
        }]
        idx: set[tuple] = {("cup", "on", "table")}
        _reconcile_support_relation(wm, "cup", "table", active_relation_index=idx)
        assert len(wm["relations"]) == 1

    def test_index_updated_after_new_relation(self):
        wm = self._empty_wm()
        upsert_objects(wm["objects"], [
            {"id": "cup", "name": "cup"}, {"id": "table", "name": "table"},
        ])
        idx: set[tuple] = set()
        _reconcile_support_relation(wm, "cup", "table", active_relation_index=idx)
        assert ("cup", "on", "table") in idx

    def test_stales_old_location_relations(self):
        wm = self._empty_wm()
        upsert_objects(wm["objects"], [
            {"id": "cup", "name": "cup"},
            {"id": "table", "name": "table"},
            {"id": "shelf", "name": "shelf"},
        ])
        wm["relations"] = [{
            "subject": "cup", "relation": "on", "object": "shelf",
            "status": "active", "confidence": 0.9, "observed_at_step": 1,
        }]
        _reconcile_support_relation(wm, "cup", "table")
        old = next(r for r in wm["relations"] if r["object"] == "shelf")
        assert old["status"] == "stale"
        new_rel = next(r for r in wm["relations"] if r["object"] == "table")
        assert new_rel["status"] == "active"

    def test_without_index_falls_back_to_scan(self):
        wm = self._empty_wm()
        upsert_objects(wm["objects"], [{"id": "cup", "name": "cup"}])
        _ensure_support_object(wm, "table", "kitchen")
        _reconcile_support_relation(wm, "cup", "table")
        active = [r for r in wm["relations"] if r["status"] == "active"]
        assert len(active) == 1


# ---------------------------------------------------------------------------
# apply_frame_visibility — batch states + uncertainty
# ---------------------------------------------------------------------------


class TestApplyFrameVisibility:
    @staticmethod
    def _wm_with_objects(*names: str) -> dict:
        objects = [{"id": n, "name": n, "visibility": "unknown"} for n in names]
        return {"objects": objects, "states": [], "uncertainty": []}

    def test_observed_marked_as_observed_current_frame(self):
        wm = self._wm_with_objects("cup", "plate")
        apply_frame_visibility(wm, ["cup"], frame_step=1)
        cup = next(o for o in wm["objects"] if o["name"] == "cup")
        assert cup["visibility"] == "observed_current_frame"
        assert cup["last_observed_step"] == 1

    def test_unobserved_marked_as_not_observed_current_frame(self):
        wm = self._wm_with_objects("cup", "plate")
        apply_frame_visibility(wm, ["cup"], frame_step=1)
        plate = next(o for o in wm["objects"] if o["name"] == "plate")
        assert plate["visibility"] == "not_observed_current_frame"

    def test_visibility_states_no_duplicate_per_entity(self):
        wm = self._wm_with_objects("cup", "plate", "spoon")
        # call twice — same entity visibility should be upserted, not duplicated
        apply_frame_visibility(wm, ["cup"], frame_step=1)
        apply_frame_visibility(wm, ["cup", "plate"], frame_step=2)
        vis_states = [
            s for s in wm["states"]
            if s.get("attribute") == "visibility"
        ]
        # 3 distinct entities → at most 3 visibility states
        entities = {s["entity"] for s in vis_states}
        assert len(entities) == len(vis_states), (
            f"Expected one visibility state per entity, got {len(vis_states)} states for {len(entities)} entities"
        )

    def test_uncertainty_behavior_preserved(self):
        wm = self._wm_with_objects("cup", "plate", "spoon")
        apply_frame_visibility(wm, ["cup"], frame_step=3)
        # plate and spoon not observed → 2 uncertainty items
        unobserved = {u["item"] for u in wm["uncertainty"]}
        assert "plate" in unobserved
        assert "spoon" in unobserved
        assert "cup" not in unobserved
        for item in wm["uncertainty"]:
            assert item["level"] == "medium"
            assert "3" in item["reason"]  # frame_step in reason

    def test_uncertainty_appends_not_overwrites(self):
        wm = self._wm_with_objects("cup", "plate")
        apply_frame_visibility(wm, ["cup"], frame_step=1)
        apply_frame_visibility(wm, ["cup"], frame_step=2)
        # plate unseen in both frames → 2 uncertainty entries for plate
        plate_uncertainty = [u for u in wm["uncertainty"] if u["item"] == "plate"]
        assert len(plate_uncertainty) == 2

    def test_no_objects_no_error(self):
        wm = {"objects": [], "states": [], "uncertainty": []}
        result = apply_frame_visibility(wm, [], frame_step=0)
        assert result["states"] == []
        assert result["uncertainty"] == []

    def test_confidence_boost_for_observed(self):
        wm = {
            "objects": [
                {"id": "cup", "name": "cup", "location": {"confidence": 0.7}},
            ],
            "states": [],
            "uncertainty": [],
        }
        apply_frame_visibility(wm, ["cup"], frame_step=1)
        cup = wm["objects"][0]
        assert cup["location"]["confidence"] == round(min(1.0, 0.7 + 0.05), 4)

    def test_confidence_decay_for_unobserved(self):
        wm = {
            "objects": [
                {"id": "cup", "name": "cup", "location": {"confidence": 0.7}},
            ],
            "states": [],
            "uncertainty": [],
        }
        apply_frame_visibility(wm, [], frame_step=1)
        cup = wm["objects"][0]
        assert cup["location"]["confidence"] == round(max(0.1, 0.7 * 0.85), 4)

    def test_match_by_id(self):
        wm = {
            "objects": [
                {"id": "obj-42", "name": "mug"},
            ],
            "states": [],
            "uncertainty": [],
        }
        apply_frame_visibility(wm, ["obj-42"], frame_step=1)
        mug = wm["objects"][0]
        assert mug["visibility"] == "observed_current_frame"
