from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "world_model.json",
    "episode_log.jsonl",
    "run_audit.json",
    "maze_metrics.json",
    "status.json",
    "reference_maze.json",
    "comparison_report.json",
]
ALLOWED_VERIFIED_EVIDENCE = {"successful_move", "visible_neighbor_observation", "navigation_transition"}
ALLOWED_BLOCKED_EVIDENCE = {"failed_move", "blocked_observation"}
LOCAL_PATH_RE = re.compile(r"([A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp)/)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MazeSim predicted/reference evidence outputs.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args()

    summary = validate_detailed(Path(args.output_dir), recursive=bool(args.recursive))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def validate(output_dir: Path, recursive: bool = False) -> list[str]:
    return validate_detailed(output_dir, recursive=recursive)["errors"]


def validate_detailed(output_dir: Path, recursive: bool = False) -> dict[str, Any]:
    output_dir = Path(output_dir)
    dirs = _candidate_dirs(output_dir, recursive=recursive)
    summary: dict[str, Any] = {
        "passed": True,
        "output_dir": str(output_dir),
        "recursive": recursive,
        "validated_dirs": [],
        "errors": [],
        "warnings": [],
    }
    if not dirs:
        summary["errors"].append(f"No MazeSim status.json found under {output_dir}")
    for directory in dirs:
        result = _validate_one(directory)
        summary["validated_dirs"].append(result)
        summary["errors"].extend([f"{directory}: {error}" for error in result["errors"]])
        summary["warnings"].extend([f"{directory}: {warning}" for warning in result["warnings"]])
    summary["passed"] = not summary["errors"]
    return summary


def _candidate_dirs(output_dir: Path, *, recursive: bool) -> list[Path]:
    dirs: list[Path] = []
    if (output_dir / "status.json").exists():
        dirs.append(output_dir)
    if recursive and output_dir.exists():
        for status_path in sorted(output_dir.rglob("status.json")):
            directory = status_path.parent
            if directory not in dirs:
                dirs.append(directory)
    return dirs


def _validate_one(output_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    payloads: dict[str, Any] = {}
    for filename in REQUIRED_FILES:
        path = output_dir / filename
        if not path.exists():
            errors.append(f"Missing required artifact: {filename}")
            continue
        if filename.endswith(".json"):
            payloads[filename] = _read_json(path, errors, filename)
        elif filename.endswith(".jsonl"):
            _read_jsonl(path, errors, filename)
        _check_no_local_paths(path, errors)

    if errors:
        return {"output_dir": str(output_dir), "passed": False, "errors": errors, "warnings": warnings}

    world_model = payloads["world_model.json"]
    audit = payloads["run_audit.json"]
    metrics = payloads["maze_metrics.json"]
    status = payloads["status.json"]
    reference = payloads["reference_maze.json"]
    comparison = payloads["comparison_report.json"]

    _validate_reference_separation(world_model, audit, metrics, status, reference, comparison, errors=errors)
    _validate_world_model(world_model, reference, errors, warnings)
    _validate_reference(reference, errors)
    _validate_comparison(comparison, errors, warnings)
    _validate_metrics(metrics, reference, comparison, warnings)
    _validate_expected_outcome(status, audit, metrics, reference, comparison, errors, warnings)

    return {"output_dir": str(output_dir), "passed": not errors, "errors": errors, "warnings": warnings}


def _validate_reference_separation(*payloads: dict[str, Any], errors: list[str]) -> None:
    labels = ["world_model", "run_audit", "maze_metrics", "status", "reference_maze", "comparison_report"]
    for label, payload in zip(labels, payloads):
        if payload.get("reference_used_for_generation") is True or payload.get("used_for_generation") is True:
            errors.append(f"{label}.reference_used_for_generation/used_for_generation must be false.")
    world_model, audit, *_ = payloads
    if world_model.get("world_model_source") != "agent_exploration":
        errors.append("world_model.world_model_source must be agent_exploration.")
    if audit.get("world_model_source") != "agent_exploration":
        errors.append("run_audit.world_model_source must be agent_exploration.")
    if audit.get("reference_model_source") != "maze_sim_reference_spec":
        errors.append("run_audit.reference_model_source must be maze_sim_reference_spec.")
    if audit.get("reference_used_for_generation") is not False:
        errors.append("run_audit.reference_used_for_generation must be false.")
    if audit.get("reference_used_for_validation") is not True:
        errors.append("run_audit.reference_used_for_validation must be true.")
    if audit.get("official_score") is not False:
        errors.append("run_audit.official_score must be false.")


def _validate_world_model(world_model: dict[str, Any], reference: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if world_model.get("source") != "maze_sim":
        errors.append("world_model.source must be maze_sim.")
    if not world_model.get("cells") and not world_model.get("topology"):
        errors.append("world_model must include observed cells/topology.")
    topology_edges = _topology_edges(world_model)
    if not topology_edges:
        warnings.append("predicted topology has zero edges.")
    reference_edges = {_edge_id(edge) for edge in reference.get("edges", []) if _is_pair(edge)}
    predicted_edges = {_edge_id([edge.get("from"), edge.get("to")]) for edge in topology_edges if edge.get("from") and edge.get("to")}
    copied_reference_without_evidence = reference_edges and predicted_edges == reference_edges and any(
        not _has_step_evidence(edge) for edge in topology_edges
    )
    if copied_reference_without_evidence:
        errors.append("world_model topology matches reference edges but lacks per-edge step evidence.")
    for index, edge in enumerate(topology_edges):
        if not isinstance(edge, dict):
            errors.append(f"topology edge {index} must be an object.")
            continue
        evidence_source = str(edge.get("evidence_source") or "")
        status = str(edge.get("status") or "")
        if evidence_source == "reference_spec":
            errors.append(f"topology edge {index} uses forbidden evidence_source=reference_spec.")
        if status == "verified":
            if not _has_step_evidence(edge):
                errors.append(f"verified topology edge {index} requires step/action/evidence_source.")
            if evidence_source not in ALLOWED_VERIFIED_EVIDENCE:
                errors.append(f"verified topology edge {index} has unsupported evidence_source={evidence_source!r}.")
        if status == "blocked":
            sources = {evidence_source}
            sources.update(str(item.get("evidence_source") or "") for item in edge.get("evidence", []) if isinstance(item, dict))
            if not (sources & ALLOWED_BLOCKED_EVIDENCE):
                errors.append(f"blocked topology edge {index} requires failed_move or blocked_observation evidence.")


def _validate_reference(reference: dict[str, Any], errors: list[str]) -> None:
    if reference.get("source") != "maze_sim_reference_spec":
        errors.append("reference_maze.source must be maze_sim_reference_spec.")
    if reference.get("used_for_generation") is not False:
        errors.append("reference_maze.used_for_generation must be false.")
    if reference.get("used_for_validation") is not True:
        errors.append("reference_maze.used_for_validation must be true.")
    if reference.get("official_score") is not False:
        errors.append("reference_maze.official_score must be false.")
    for key in ["nodes", "edges", "blocked_edges"]:
        if not isinstance(reference.get(key), list):
            errors.append(f"reference_maze.{key} must be a list.")


def _validate_comparison(comparison: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if comparison.get("reference_used_for_generation") is not False:
        errors.append("comparison_report.reference_used_for_generation must be false.")
    if comparison.get("reference_used_for_validation") is not True:
        errors.append("comparison_report.reference_used_for_validation must be true.")
    topology = comparison.get("topology")
    if not isinstance(topology, dict):
        errors.append("comparison_report.topology must be an object.")
        return
    for key in ["node_precision", "node_recall", "edge_precision", "edge_recall"]:
        if key not in topology:
            errors.append(f"comparison_report.topology missing {key}.")
    edge_recall = _number(topology.get("edge_recall"))
    if edge_recall is not None and edge_recall < 0.5:
        warnings.append(f"edge recall is low: {edge_recall}")


def _validate_metrics(
    metrics: dict[str, Any],
    reference: dict[str, Any],
    comparison: dict[str, Any],
    warnings: list[str],
) -> None:
    goal = comparison.get("goal", {}) if isinstance(comparison.get("goal"), dict) else {}
    if reference.get("recoverable_solution_exists") and goal.get("goal_reached") is not True:
        warnings.append("goal was not reached in a recoverable scenario.")
    if metrics.get("terminated_by_budget"):
        warnings.append("terminated_by_budget=true.")
    if int(metrics.get("oscillation_count") or metrics.get("total_oscillation_count") or 0) > 10:
        warnings.append("oscillation_count is high.")
    frontiers_remaining = metrics.get("frontiers_remaining")
    reference_nodes = metrics.get("reference_nodes") or comparison.get("topology", {}).get("reference_nodes") or 0
    if isinstance(frontiers_remaining, int) and frontiers_remaining > max(3, int(reference_nodes) // 4):
        warnings.append(f"many frontiers remain: {frontiers_remaining}")


def _validate_expected_outcome(
    status: dict[str, Any],
    audit: dict[str, Any],
    metrics: dict[str, Any],
    reference: dict[str, Any],
    comparison: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    expected_goal_reachable = _first_present(
        audit.get("expected_goal_reachable"),
        status.get("expected_goal_reachable"),
        metrics.get("expected_goal_reachable"),
        reference.get("recoverable_solution_exists"),
    )
    goal = comparison.get("goal", {}) if isinstance(comparison.get("goal"), dict) else {}
    goal_reached = _first_present(audit.get("goal_reached"), status.get("goal_reached"), metrics.get("goal_reached"), goal.get("goal_reached"))
    expected_outcome_met = _first_present(audit.get("expected_outcome_met"), status.get("expected_outcome_met"), metrics.get("expected_outcome_met"))

    if expected_goal_reachable is False:
        if goal_reached is not False:
            errors.append("expected_goal_reachable=false requires goal_reached=false.")
        if expected_outcome_met is not True:
            errors.append("expected_goal_reachable=false requires expected_outcome_met=true for graceful unreachable termination.")
        return
    if expected_goal_reachable is True and goal_reached is False and expected_outcome_met is True:
        warnings.append("reachable scenario marked expected_outcome_met=true without reaching the goal.")


def _topology_edges(world_model: dict[str, Any]) -> list[dict[str, Any]]:
    edges = world_model.get("topology_edges")
    if isinstance(edges, list):
        return [edge for edge in edges if isinstance(edge, dict)]
    legacy = world_model.get("edges")
    if isinstance(legacy, list):
        return [edge for edge in legacy if isinstance(edge, dict)]
    return []


def _has_step_evidence(edge: dict[str, Any]) -> bool:
    return edge.get("step") is not None and bool(edge.get("action")) and bool(edge.get("evidence_source"))


def _read_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object.")
        return {}
    return payload


def _read_jsonl(path: Path, errors: list[str], label: str) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        errors.append(f"Invalid {label}: {exc}")
        return
    if not any(line.strip() for line in lines):
        errors.append(f"{label} must not be empty.")
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} line {line_number} invalid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{label} line {line_number} must be an object.")


def _check_no_local_paths(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if LOCAL_PATH_RE.search(text):
        errors.append(f"{path.name} contains local absolute path.")


def _edge_id(edge: Any) -> str:
    left, right = str(edge[0]), str(edge[1])
    return "--".join(sorted([left, right]))


def _is_pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) >= 2


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
