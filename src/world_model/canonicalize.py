from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


ALIASES = {
    "tv": "television",
    "couch": "sofa",
    "bookshelf": "bookcase",
    "nightstand": "table",
}


def canonicalize_world_model(
    world_model: dict[str, Any],
    frame_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    objects = [obj for obj in world_model.get("objects", []) if isinstance(obj, dict)]
    relations = [rel for rel in world_model.get("relations", []) if isinstance(rel, dict)]
    raw_object_mentions = _count_raw_object_mentions(objects, frame_manifest)
    raw_relation_mentions = len(relations)

    clusters: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for obj in objects:
        room = _object_room(obj)
        label = _normalize_label(str(obj.get("name") or obj.get("id") or "object"))
        support = _object_support(obj)
        stable_id = str(obj.get("id") or "")
        key = (room, label, stable_id if _stable_id(stable_id) else support)
        clusters[key].append(obj)

    canonical_objects: list[dict[str, Any]] = []
    id_map: dict[str, str] = {}
    merged_clusters: list[dict[str, Any]] = []
    alias_merges: list[dict[str, Any]] = []
    room_counts: dict[str, int] = defaultdict(int)
    base_counts: Counter[str] = Counter()
    for (room, label, _context), members in clusters.items():
        base = f"obj_{_slug(room)}_{_slug(label)}"
        base_counts[base] += 1
        canonical_id = base if base_counts[base] == 1 else f"{base}_{base_counts[base]}"
        evidence_frames = _ordered_unique(
            frame
            for obj in members
            for frame in _string_list(obj.get("evidence_frames"))
        )
        raw_mentions = [
            mention
            for obj in members
            for mention in obj.get("raw_mentions", [])
            if isinstance(mention, dict)
        ]
        original_ids = _ordered_unique(str(obj.get("id") or "") for obj in members if obj.get("id"))
        for original_id in original_ids:
            id_map[original_id] = canonical_id
        aliases = sorted(
            {
                str(obj.get("name") or "")
                for obj in members
                if str(obj.get("name") or "") and _normalize_label(str(obj.get("name") or "")) != label
            }
        )
        if aliases:
            alias_merges.append({"canonical": label, "aliases": aliases})
        confidence_values = [_safe_float(obj.get("confidence"), 0.65) for obj in members]
        canonical = {
            "id": canonical_id,
            "name": label,
            "category": _most_common(str(obj.get("category") or "object") for obj in members),
            "location": {
                "room": room,
                "region": "observed_view",
                "support": _most_common(_object_support(obj) for obj in members),
                "status": "known",
                "confidence": round(sum(confidence_values) / max(1, len(confidence_values)), 4),
            },
            "state": _most_common(str(obj.get("state") or "observed") for obj in members),
            "confidence": round(sum(confidence_values) / max(1, len(confidence_values)), 4),
            "aliases": aliases,
            "evidence_frames": evidence_frames,
            "raw_mentions": raw_mentions,
            "original_ids": original_ids,
        }
        if len(members) > 1:
            merged_clusters.append({"canonical_id": canonical_id, "original_ids": original_ids, "label": label, "room": room})
        room_counts[room] += 1
        canonical_objects.append(canonical)

    canonical_relations = _canonicalize_relations(relations, id_map)
    canonical = dict(world_model)
    canonical["objects"] = canonical_objects
    canonical["relations"] = canonical_relations
    report = {
        "raw_object_mentions": raw_object_mentions,
        "unique_objects": len(canonical_objects),
        "raw_relation_mentions": raw_relation_mentions,
        "unique_relations": len(canonical_relations),
        "merged_object_clusters": merged_clusters,
        "alias_merges": alias_merges,
        "objects_by_room": dict(sorted(room_counts.items())),
        "active_relations": sum(1 for rel in canonical_relations if rel.get("status") == "active"),
        "stale_relations": sum(1 for rel in canonical_relations if rel.get("status") == "stale"),
        "warnings": [],
    }
    return canonical, report


def _canonicalize_relations(relations: list[dict[str, Any]], id_map: dict[str, str]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for relation in relations:
        subject = id_map.get(str(relation.get("subject") or ""), str(relation.get("subject") or ""))
        obj = id_map.get(str(relation.get("object") or ""), str(relation.get("object") or ""))
        rel_name = _normalize_relation(str(relation.get("relation") or "related_to"))
        status = str(relation.get("status") or "active")
        key = (subject, rel_name, obj, status)
        evidence_frames = _string_list(relation.get("evidence_frames"))
        confidence = _safe_float(relation.get("confidence"), 0.65)
        if key not in merged:
            item = dict(relation)
            item.update(
                {
                    "subject": subject,
                    "relation": rel_name,
                    "object": obj,
                    "status": status,
                    "confidence": confidence,
                    "evidence_frames": evidence_frames,
                    "raw_mentions": [
                        {
                            "subject": relation.get("subject"),
                            "subject_label": relation.get("subject_label", ""),
                            "relation": relation.get("relation"),
                            "object": relation.get("object"),
                            "object_label": relation.get("object_label", ""),
                            "source": relation.get("source", ""),
                            "evidence_frames": evidence_frames,
                        }
                    ],
                }
            )
            merged[key] = item
        else:
            item = merged[key]
            item["evidence_frames"] = _ordered_unique([*item.get("evidence_frames", []), *evidence_frames])
            item["confidence"] = round(max(_safe_float(item.get("confidence"), confidence), confidence), 4)
            item.setdefault("raw_mentions", []).append(
                {
                    "subject": relation.get("subject"),
                    "subject_label": relation.get("subject_label", ""),
                    "relation": relation.get("relation"),
                    "object": relation.get("object"),
                    "object_label": relation.get("object_label", ""),
                    "source": relation.get("source", ""),
                    "evidence_frames": evidence_frames,
                }
            )
    return list(merged.values())


def _count_raw_object_mentions(objects: list[dict[str, Any]], frame_manifest: dict[str, Any] | None) -> int:
    count = sum(len(obj.get("raw_mentions", [])) for obj in objects if isinstance(obj.get("raw_mentions"), list))
    if count:
        return count
    frames = frame_manifest.get("frames", []) if isinstance(frame_manifest, dict) else []
    if isinstance(frames, list):
        return sum(
            len(row.get("visual_extraction", {}).get("objects", []))
            for row in frames
            if isinstance(row, dict) and isinstance(row.get("visual_extraction"), dict)
        )
    return len(objects)


def _normalize_label(value: str) -> str:
    text = value.strip().lower().replace("_", " ").replace("-", " ")
    for article in ("a ", "an ", "the "):
        if text.startswith(article):
            text = text[len(article) :]
    text = " ".join(text.split())
    text = ALIASES.get(text, text)
    if text.endswith("ies") and len(text) > 4:
        text = text[:-3] + "y"
    elif text.endswith("s") and not text.endswith("ss") and len(text) > 3:
        text = text[:-1]
    return text or "object"


def _normalize_relation(value: str) -> str:
    return value.strip().lower().replace(" ", "_") or "related_to"


def _object_room(obj: dict[str, Any]) -> str:
    location = obj.get("location")
    if isinstance(location, dict):
        room = str(location.get("room") or "").strip().lower()
        if room:
            return room
    return str(obj.get("room") or "unknown").strip().lower() or "unknown"


def _object_support(obj: dict[str, Any]) -> str:
    location = obj.get("location")
    if isinstance(location, dict):
        return str(location.get("support") or "")
    return str(obj.get("support") or "")


def _stable_id(value: str) -> bool:
    return value.isdigit() or value.startswith(("vh_", "virtualhome_", "scene_"))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _most_common(values: Any) -> str:
    cleaned = [str(value) for value in values if str(value)]
    if not cleaned:
        return ""
    return Counter(cleaned).most_common(1)[0][0]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _slug(value: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    return "_".join(part for part in slug.split("_") if part) or "unknown"
