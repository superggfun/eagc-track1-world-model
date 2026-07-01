from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


LOCATION_RELATION = "connected_to"
REFERENCE_SOURCE = "maze_sim_reference_spec"
WORLD_MODEL_SOURCE = "agent_exploration"


def canonical_edge_pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((str(a), str(b))))  # type: ignore[return-value]


def canonical_edge_id(a: str, b: str) -> str:
    left, right = canonical_edge_pair(a, b)
    return f"{left}--{right}"


def edge_id_from_pair(pair: Iterable[str]) -> str:
    left, right = list(pair)[:2]
    return canonical_edge_id(left, right)


def split_edge_id(edge_id: str) -> tuple[str, str]:
    left, right = str(edge_id).split("--", 1)
    return canonical_edge_pair(left, right)


def record_topology_edge(
    world_model: dict[str, Any],
    from_cell: str,
    to_cell: str,
    *,
    relation: str = LOCATION_RELATION,
    status: str = "verified",
    evidence_source: str,
    step: int,
    action: str,
    confidence: float = 1.0,
) -> None:
    """Upsert an evidence-backed undirected MazeSim topology edge."""

    left, right = canonical_edge_pair(from_cell, to_cell)
    edge_id = canonical_edge_id(left, right)
    edges = world_model.setdefault("topology_edges", [])
    existing = next((edge for edge in edges if edge.get("id") == edge_id), None)
    evidence = {
        "step": step,
        "action": action,
        "evidence_source": evidence_source,
        "status": status,
    }
    if existing is None:
        edges.append(
            {
                "id": edge_id,
                "from": left,
                "to": right,
                "relation": relation,
                "status": status,
                "evidence_source": evidence_source,
                "step": step,
                "action": action,
                "confidence": confidence,
                "evidence": [evidence],
            }
        )
        return

    evidence_rows = existing.setdefault("evidence", [])
    if evidence not in evidence_rows:
        evidence_rows.append(evidence)
    existing["confidence"] = max(float(existing.get("confidence") or 0.0), confidence)
    if status == "blocked":
        existing.update(
            {
                "relation": "blocked",
                "status": "blocked",
                "evidence_source": evidence_source,
                "step": step,
                "action": action,
            }
        )
    elif existing.get("status") != "blocked" and evidence_source == "successful_move":
        existing.update(
            {
                "relation": relation,
                "status": status,
                "evidence_source": evidence_source,
                "step": step,
                "action": action,
            }
        )


def sync_legacy_edges(world_model: dict[str, Any]) -> None:
    legacy_edges = []
    blocked_edges = []
    for edge in sorted(world_model.get("topology_edges", []), key=lambda item: item.get("id", "")):
        item = dict(edge)
        item.setdefault("id", canonical_edge_id(item.get("from", ""), item.get("to", "")))
        legacy_edges.append(item)
        if item.get("status") == "blocked":
            blocked_edges.append(item["id"])
    world_model["edges"] = legacy_edges
    world_model["blocked_edges"] = sorted(set(blocked_edges))


def append_trace(world_model: dict[str, Any], event: dict[str, Any]) -> None:
    trace = world_model.setdefault("exploration_trace", [])
    trace.append(event)


def build_reference_maze(env: Any, scenario_id: str) -> dict[str, Any]:
    spec = env.spec
    nodes = [_cell_name(cell) for cell in sorted(spec.cells)]
    edges = [_edge_list(_cell_name(a), _cell_name(b)) for a, b in sorted(spec.edges)]
    blocked_edges = [_edge_list(_cell_name(a), _cell_name(b)) for a, b in sorted(spec.blocked_edges)]
    start = _cell_name(spec.start)
    goal = _cell_name(spec.goal)
    shortest_path = _shortest_path(nodes, edges, blocked_edges, start, goal)
    return {
        "source": REFERENCE_SOURCE,
        "used_for_generation": False,
        "used_for_validation": True,
        "official_score": False,
        "scenario_id": scenario_id,
        "nodes": nodes,
        "edges": edges,
        "blocked_edges": blocked_edges,
        "start": start,
        "goal": goal,
        "shortest_path": shortest_path,
        "shortest_path_length": len(shortest_path) - 1 if shortest_path else None,
        "recoverable_solution_exists": bool(shortest_path),
        "hidden_goal": bool(getattr(spec, "hidden_goal", True)),
        "relocated_goal": _cell_name(spec.relocated_goal) if getattr(spec, "relocated_goal", None) else None,
        "door_blocked_edge": _edge_list(*[_cell_name(cell) for cell in spec.door_blocked_edge])
        if getattr(spec, "door_blocked_edge", None)
        else None,
    }


def build_run_audit(
    *,
    scenario_id: str,
    success: bool,
    status: str,
    metrics: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal_reached = bool(metrics.get("goal_reached", metrics.get("goal_found", False)))
    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "env": "maze_sim",
        "scenario_id": scenario_id,
        "success": bool(success),
        "status": status,
        "evidence_level": "closed_loop_final_evidence",
        "continuous_closed_loop": True,
        "capture_mode": "continuous_episode",
        "world_model_source": WORLD_MODEL_SOURCE,
        "reference_model_source": REFERENCE_SOURCE,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
        "world_model_path": "world_model.json",
        "episode_log_path": "episode_log.jsonl",
        "run_audit_path": "run_audit.json",
        "maze_metrics_path": "maze_metrics.json",
        "status_path": "status.json",
        "reference_maze_path": "reference_maze.json",
        "comparison_report_path": "comparison_report.json",
        "steps_taken": metrics.get("steps_taken"),
        "goal_reached": goal_reached,
        "expected_goal_reachable": metrics.get("expected_goal_reachable", True),
        "expected_outcome_met": metrics.get("expected_outcome_met", bool(success)),
        "replans": metrics.get("replans"),
        "backtracks": metrics.get("backtracks"),
        "oscillation_count": metrics.get("oscillation_count", 0),
    }
    if extra:
        audit.update(extra)
    return audit


def build_comparison_report(
    world_model: dict[str, Any],
    reference: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    reference_nodes = set(str(node) for node in reference.get("nodes", []))
    predicted_nodes = _predicted_nodes(world_model)
    matched_nodes = predicted_nodes & reference_nodes

    reference_edges = {edge_id_from_pair(edge) for edge in reference.get("edges", []) if _is_pair(edge)}
    predicted_edges = _predicted_edges(world_model)
    matched_edges = predicted_edges & reference_edges

    reference_blocked = {edge_id_from_pair(edge) for edge in reference.get("blocked_edges", []) if _is_pair(edge)}
    predicted_blocked = _predicted_blocked_edges(world_model)
    matched_blocked = predicted_blocked & reference_blocked

    final_position = str(world_model.get("agent_state", {}).get("current_cell") or "")
    shortest_path_length = reference.get("shortest_path_length")
    agent_path_length = metrics.get("agent_path_length", metrics.get("steps_taken"))
    path_efficiency_ratio = _path_efficiency(shortest_path_length, agent_path_length, bool(metrics.get("goal_reached", metrics.get("goal_found"))))

    return {
        "source": "maze_prediction_vs_reference_comparison",
        "official_score": False,
        "world_model_source": WORLD_MODEL_SOURCE,
        "reference_model_source": REFERENCE_SOURCE,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "scenario_id": reference.get("scenario_id", world_model.get("episode_id", "")),
        "topology": {
            "reference_nodes": len(reference_nodes),
            "predicted_nodes": len(predicted_nodes),
            "matched_nodes": len(matched_nodes),
            "missed_nodes": sorted(reference_nodes - predicted_nodes),
            "spurious_nodes": sorted(predicted_nodes - reference_nodes),
            "node_precision": _ratio(len(matched_nodes), len(predicted_nodes)),
            "node_recall": _ratio(len(matched_nodes), len(reference_nodes)),
            "reference_edges": len(reference_edges),
            "predicted_edges": len(predicted_edges),
            "matched_edges": len(matched_edges),
            "missed_edges": sorted(reference_edges - predicted_edges),
            "spurious_edges": sorted(predicted_edges - reference_edges),
            "edge_precision": _ratio(len(matched_edges), len(predicted_edges)),
            "edge_recall": _ratio(len(matched_edges), len(reference_edges)),
        },
        "blocked_edges": {
            "reference_blocked_edges": len(reference_blocked),
            "predicted_blocked_edges": len(predicted_blocked),
            "matched_blocked_edges": len(matched_blocked),
            "missed_blocked_edges": sorted(reference_blocked - predicted_blocked),
            "spurious_blocked_edges": sorted(predicted_blocked - reference_blocked),
        },
        "goal": {
            "goal_reached": bool(metrics.get("goal_reached", metrics.get("goal_found", False))),
            "reference_goal": reference.get("goal", ""),
            "final_position": final_position,
            "shortest_path_length": shortest_path_length,
            "agent_path_length": agent_path_length,
            "path_efficiency_ratio": path_efficiency_ratio,
        },
        "replanning": {
            "replans": int(metrics.get("replans") or 0),
            "backtracks": int(metrics.get("backtracks") or 0),
            "oscillation_count": int(metrics.get("oscillation_count") or 0),
            "terminated_by_budget": bool(metrics.get("terminated_by_budget", False)),
        },
    }


def enrich_maze_metrics(
    metrics: dict[str, Any],
    world_model: dict[str, Any],
    reference: dict[str, Any],
    comparison: dict[str, Any],
) -> None:
    topology = comparison.get("topology", {})
    blocked = comparison.get("blocked_edges", {})
    goal = comparison.get("goal", {})
    metrics.update(
        {
            "visited_nodes": len([cell for cell in world_model.get("cells", []) if cell.get("visited")]),
            "reference_nodes": topology.get("reference_nodes"),
            "visited_edge_count": topology.get("predicted_edges"),
            "reference_edge_count": topology.get("reference_edges"),
            "frontiers_remaining": len(world_model.get("frontiers", [])),
            "blocked_edges_detected": blocked.get("predicted_blocked_edges"),
            "reference_blocked_edges": blocked.get("reference_blocked_edges"),
            "goal_reached": goal.get("goal_reached"),
            "agent_path_length": goal.get("agent_path_length"),
            "path_efficiency_ratio": goal.get("path_efficiency_ratio"),
            "topology_node_precision": topology.get("node_precision"),
            "topology_node_recall": topology.get("node_recall"),
            "topology_edge_precision": topology.get("edge_precision"),
            "topology_edge_recall": topology.get("edge_recall"),
            "reference_used_for_generation": False,
            "reference_used_for_validation": True,
            "official_score": False,
        }
    )
    if "shortest_path_length" not in metrics or metrics.get("shortest_path_length") in {0, None}:
        metrics["shortest_path_length"] = reference.get("shortest_path_length")


def prefix_reference(reference: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    def prefixed(value: str) -> str:
        return f"{scenario_id}:{value}"

    return {
        **reference,
        "scenario_id": scenario_id,
        "nodes": [prefixed(node) for node in reference.get("nodes", [])],
        "edges": [[prefixed(edge[0]), prefixed(edge[1])] for edge in reference.get("edges", []) if _is_pair(edge)],
        "blocked_edges": [[prefixed(edge[0]), prefixed(edge[1])] for edge in reference.get("blocked_edges", []) if _is_pair(edge)],
        "start": prefixed(str(reference.get("start", ""))),
        "goal": prefixed(str(reference.get("goal", ""))),
        "shortest_path": [prefixed(node) for node in reference.get("shortest_path", [])],
    }


def build_aggregate_reference(references: list[dict[str, Any]], scenario_id: str) -> dict[str, Any]:
    nodes: list[str] = []
    edges: list[list[str]] = []
    blocked_edges: list[list[str]] = []
    scenarios: list[dict[str, Any]] = []
    for reference in references:
        scenario = str(reference.get("scenario_id") or "")
        prefixed = prefix_reference(reference, scenario)
        nodes.extend(prefixed.get("nodes", []))
        edges.extend(prefixed.get("edges", []))
        blocked_edges.extend(prefixed.get("blocked_edges", []))
        scenarios.append(prefixed)
    return {
        "source": REFERENCE_SOURCE,
        "used_for_generation": False,
        "used_for_validation": True,
        "official_score": False,
        "scenario_id": scenario_id,
        "aggregate": True,
        "scenarios": scenarios,
        "nodes": sorted(nodes),
        "edges": sorted(edges),
        "blocked_edges": sorted(blocked_edges),
        "start": "",
        "goal": "",
        "shortest_path": [],
        "shortest_path_length": None,
        "recoverable_solution_exists": any(bool(item.get("recoverable_solution_exists")) for item in references),
    }


def build_aggregate_metrics(results: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    edge_precisions = [float(item.get("topology", {}).get("edge_precision") or 0.0) for item in comparisons]
    edge_recalls = [float(item.get("topology", {}).get("edge_recall") or 0.0) for item in comparisons]
    path_efficiencies = [
        float(item.get("goal", {}).get("path_efficiency_ratio") or 0.0)
        for item in comparisons
        if item.get("goal", {}).get("path_efficiency_ratio") is not None
    ]
    scenarios_passed = sum(1 for item in results if bool(item.get("acceptable", item.get("success"))))
    return {
        "success": scenarios_passed == len(results),
        "scenarios_run": [str(item.get("episode")) for item in results],
        "scenarios_passed": scenarios_passed,
        "scenario_count": len(results),
        "average_edge_precision": _mean(edge_precisions),
        "average_edge_recall": _mean(edge_recalls),
        "average_path_efficiency_ratio": _mean(path_efficiencies),
        "total_replans": sum(int(item.get("metrics", {}).get("replans") or 0) for item in results),
        "total_backtracks": sum(int(item.get("metrics", {}).get("backtracks") or 0) for item in results),
        "total_oscillation_count": sum(int(item.get("metrics", {}).get("oscillation_count") or 0) for item in results),
        "terminated_by_budget_count": sum(1 for item in results if item.get("metrics", {}).get("terminated_by_budget")),
        "validation_passed": scenarios_passed == len(results),
        "episodes": {item["episode"]: item["metrics"] for item in results},
        "warnings": [],
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(payload), encoding="utf-8")


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _predicted_nodes(world_model: dict[str, Any]) -> set[str]:
    nodes = {str(item.get("id")) for item in world_model.get("cells", []) if isinstance(item, dict) and item.get("id")}
    if nodes:
        return nodes
    topology = world_model.get("topology", [])
    if isinstance(topology, list):
        for item in topology:
            if isinstance(item, dict):
                node = item.get("cell") or item.get("id")
                if node:
                    nodes.add(str(node))
    return nodes


def _predicted_edges(world_model: dict[str, Any]) -> set[str]:
    edges = set()
    for edge in world_model.get("topology_edges", []):
        if not isinstance(edge, dict) or edge.get("status") not in {"verified", "blocked"}:
            continue
        if edge.get("from") and edge.get("to"):
            edges.add(canonical_edge_id(str(edge["from"]), str(edge["to"])))
    if edges:
        return edges
    for edge in world_model.get("edges", []):
        if isinstance(edge, dict) and edge.get("id"):
            edges.add(str(edge["id"]))
    return edges


def _predicted_blocked_edges(world_model: dict[str, Any]) -> set[str]:
    blocked = set()
    for edge in world_model.get("topology_edges", []):
        if isinstance(edge, dict) and edge.get("status") == "blocked" and edge.get("from") and edge.get("to"):
            blocked.add(canonical_edge_id(str(edge["from"]), str(edge["to"])))
    for edge in world_model.get("blocked_edges", []):
        if isinstance(edge, str):
            blocked.add(edge)
        elif _is_pair(edge):
            blocked.add(edge_id_from_pair(edge))
    return blocked


def _shortest_path(nodes: list[str], edges: list[list[str]], blocked_edges: list[list[str]], start: str, goal: str) -> list[str]:
    blocked = {edge_id_from_pair(edge) for edge in blocked_edges}
    graph = {node: [] for node in nodes}
    for edge in edges:
        if not _is_pair(edge) or edge_id_from_pair(edge) in blocked:
            continue
        left, right = edge
        graph.setdefault(left, []).append(right)
        graph.setdefault(right, []).append(left)
    queue: deque[str] = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = []
            current: str | None = cell
            while current is not None:
                path.append(current)
                current = parent[current]
            return list(reversed(path))
        for neighbor in sorted(graph.get(cell, [])):
            if neighbor in parent:
                continue
            parent[neighbor] = cell
            queue.append(neighbor)
    return []


def _cell_name(cell: Any) -> str:
    if isinstance(cell, str):
        return cell
    return f"cell_{cell[0]},{cell[1]}"


def _edge_list(left: str, right: str) -> list[str]:
    return list(canonical_edge_pair(left, right))


def _is_pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0 if numerator == 0 else 0.0
    return round(numerator / denominator, 3)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _path_efficiency(shortest_path_length: Any, agent_path_length: Any, goal_reached: bool) -> float | None:
    if not goal_reached or shortest_path_length in {None, 0} or agent_path_length in {None, 0}:
        return None
    return round(float(shortest_path_length) / max(1.0, float(agent_path_length)), 3)
