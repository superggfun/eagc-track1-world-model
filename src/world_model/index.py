from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldModelIndex:
    objects_by_name: dict[str, dict[str, Any]]
    objects_by_id: dict[str, dict[str, Any]]
    states_by_entity_attr: dict[tuple[str, str], dict[str, Any]]
    relations_by_key: dict[tuple[str, str, str], list[dict[str, Any]]]
    active_relations_by_subject: dict[str, list[dict[str, Any]]]
    states_by_entity_attr_all: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def from_world_model(cls, world_model: dict[str, Any]) -> "WorldModelIndex":
        objects_by_name: dict[str, dict[str, Any]] = {}
        objects_by_id: dict[str, dict[str, Any]] = {}
        states_by_entity_attr: dict[tuple[str, str], dict[str, Any]] = {}
        states_by_entity_attr_all: dict[tuple[str, str], list[dict[str, Any]]] = {}
        relations_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        active_relations_by_subject: dict[str, list[dict[str, Any]]] = {}

        for obj in _iter_dicts(world_model.get("objects", [])):
            if obj.get("name"):
                objects_by_name.setdefault(str(obj["name"]), obj)
            if obj.get("id"):
                objects_by_id.setdefault(str(obj["id"]), obj)

        for state in _iter_dicts(world_model.get("states", [])):
            entity = state.get("entity")
            attribute = state.get("attribute")
            if entity is None or attribute is None:
                continue
            key = (str(entity), str(attribute))
            states_by_entity_attr.setdefault(key, state)
            states_by_entity_attr_all.setdefault(key, []).append(state)

        for relation in _iter_dicts(world_model.get("relations", [])):
            subject = relation.get("subject")
            relation_name = relation.get("relation")
            object_ = relation.get("object")
            if subject is None or relation_name is None or object_ is None:
                continue
            key = (str(subject), str(relation_name), str(object_))
            relations_by_key.setdefault(key, []).append(relation)
            if relation.get("status") == "active":
                active_relations_by_subject.setdefault(str(subject), []).append(relation)

        return cls(
            objects_by_name=objects_by_name,
            objects_by_id=objects_by_id,
            states_by_entity_attr=states_by_entity_attr,
            relations_by_key=relations_by_key,
            active_relations_by_subject=active_relations_by_subject,
            states_by_entity_attr_all=states_by_entity_attr_all,
        )

    def find_object(self, name: str) -> dict[str, Any] | None:
        if name is None:
            return None
        key = str(name)
        return self.objects_by_name.get(key) or self.objects_by_id.get(key)

    def iter_objects(self) -> list[dict[str, Any]]:
        seen: set[int] = set()
        objects: list[dict[str, Any]] = []
        for obj in list(self.objects_by_name.values()) + list(self.objects_by_id.values()):
            marker = id(obj)
            if marker not in seen:
                seen.add(marker)
                objects.append(obj)
        return objects

    def has_state(self, entity: str, attribute: str, value: Any = None) -> bool:
        if entity is None or attribute is None:
            return False
        states = self.states_by_entity_attr_all.get((str(entity), str(attribute)), [])
        if value is None:
            return bool(states)
        return any(state.get("value") == value for state in states)

    def has_relation(self, subject: str, relation: str, object_: str | None = None) -> bool:
        if subject is None or relation is None:
            return False
        subject_key = str(subject)
        relation_key = str(relation)
        if object_ is not None:
            key = (subject_key, relation_key, str(object_))
            return any(item.get("status") == "active" for item in self.relations_by_key.get(key, []))
        return any(
            item.get("relation") == relation_key and item.get("status") == "active"
            for item in self.active_relations_by_subject.get(subject_key, [])
        )


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
