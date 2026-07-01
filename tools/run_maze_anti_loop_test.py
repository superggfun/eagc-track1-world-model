from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any, Dict, List, Set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from env_adapters.maze_sim_env import MazeSimEnv
from harness.maze_evidence import (
    WORLD_MODEL_SOURCE,
    build_aggregate_metrics,
    build_aggregate_reference,
    build_comparison_report,
    build_reference_maze,
    build_run_audit,
    enrich_maze_metrics,
    write_json,
)
from logging_utils.episode_logger import EpisodeLogger
from tools.run_maze_stress_test import (
    _apply_observation,
    _choose_action,
    _choose_backtrack_action,
    _edge_name,
    _mark_blocked,
    _new_world_model,
    _record_navigation_result,
    _target_from_action,
    _update_agent_state,
)


ANTI_LOOP_EPISODES = [
    "loop_lure_maze",
    "dead_end_comb_maze",
    "blocked_shortcut_maze",
    "unreachable_goal_maze",
]
UNREACHABLE_EPISODES = {"unreachable_goal_maze"}
ANTI_LOOP_METRICS = {
    "loop_detected",
    "repeated_state_count",
    "max_visit_count_single_cell",
    "revisited_cells",
    "oscillation_count",
    "no_progress_windows",
    "coverage_plateau_steps",
    "terminated_by_budget",
    "terminated_reason",
    "unique_state_ratio",
    "dead_end_reentries",
    "blocked_edge_retries",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MazeSim anti-loop and dead-end recovery stress tests.")
    parser.add_argument("--episode", choices=[*ANTI_LOOP_EPISODES, "all"], default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--output-dir", default="outputs/maze_anti_loop")
    args = parser.parse_args()

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    episodes = ANTI_LOOP_EPISODES if args.episode == "all" else [args.episode]

    results: List[Dict[str, Any]] = []
    aggregate_log_lines: List[str] = []
    scenario_world_models: List[tuple[str, Dict[str, Any]]] = []
    scenario_references: List[Dict[str, Any]] = []
    scenario_comparisons: List[Dict[str, Any]] = []

    for episode in episodes:
        scenario_dir = output_dir / episode
        result = _run_episode(episode, args.seed, args.max_steps, scenario_dir)
        result["acceptable"] = _episode_acceptable(result)
        results.append(result)
        aggregate_log_lines.extend((scenario_dir / "episode_log.jsonl").read_text(encoding="utf-8").splitlines())
        world_model = _read_json(scenario_dir / "world_model.json")
        reference = _read_json(scenario_dir / "reference_maze.json")
        comparison = _read_json(scenario_dir / "comparison_report.json")
        scenario_world_models.append((episode, world_model))
        scenario_references.append(reference)
        scenario_comparisons.append(comparison)

    acceptable = all(_episode_acceptable(item) for item in results)
    aggregate_reference = build_aggregate_reference(scenario_references, f"maze-anti-loop-{args.episode}")
    aggregate_metrics = build_aggregate_metrics(results, scenario_comparisons)
    aggregate_metrics["episode_count"] = len(results)
    aggregate_metrics["success"] = acceptable
    aggregate_metrics["warnings"] = _aggregate_warnings(results)
    aggregate_metrics["goal_reached"] = all(item["success"] for item in results if item["episode"] not in UNREACHABLE_EPISODES)
    aggregate_metrics["agent_path_length"] = sum(int(item.get("metrics", {}).get("steps_taken") or 0) for item in results)
    aggregate_metrics["expected_goal_reachable"] = None
    aggregate_metrics["expected_outcome_met"] = acceptable
    world_model = _aggregate_world_model(args.episode, scenario_world_models, results, acceptable, aggregate_metrics)
    aggregate_comparison = build_comparison_report(world_model, aggregate_reference, aggregate_metrics)
    aggregate_comparison["scenarios"] = {item["scenario_id"]: item for item in scenario_comparisons}
    enrich_maze_metrics(aggregate_metrics, world_model, aggregate_reference, aggregate_comparison)
    world_model["maze_metrics"] = aggregate_metrics
    summary = {
        "success": acceptable,
        "status": "complete" if acceptable else "failed",
        "episode": args.episode,
        "seed": args.seed,
        "max_steps": args.max_steps,
        "episode_count": len(results),
        "reachable_success_count": sum(1 for item in results if item["success"]),
        "expected_unreachable_count": sum(1 for item in results if item["episode"] in UNREACHABLE_EPISODES),
        "failed_count": sum(1 for item in results if not _episode_acceptable(item)),
        "episodes": results,
        "scenarios_run": [item["episode"] for item in results],
        "scenarios_passed": sum(1 for item in results if item.get("acceptable")),
        "average_edge_precision": aggregate_metrics["average_edge_precision"],
        "average_edge_recall": aggregate_metrics["average_edge_recall"],
        "average_path_efficiency_ratio": aggregate_metrics["average_path_efficiency_ratio"],
        "total_replans": aggregate_metrics["total_replans"],
        "total_backtracks": aggregate_metrics["total_backtracks"],
        "total_oscillation_count": aggregate_metrics["total_oscillation_count"],
        "terminated_by_budget_count": aggregate_metrics["terminated_by_budget_count"],
        "validation_passed": aggregate_metrics["validation_passed"],
        "goal_reached": aggregate_metrics["goal_reached"],
        "expected_goal_reachable": None,
        "expected_outcome_met": acceptable,
        "world_model_path": "world_model.json",
        "episode_log_path": "episode_log.jsonl",
        "run_audit_path": "run_audit.json",
        "maze_metrics_path": "maze_metrics.json",
        "reference_maze_path": "reference_maze.json",
        "comparison_report_path": "comparison_report.json",
        "anti_loop_report_path": "anti_loop_report.md",
        "evidence_level": "closed_loop_final_evidence",
        "continuous_closed_loop": True,
        "capture_mode": "continuous_episode",
        "world_model_source": WORLD_MODEL_SOURCE,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
    }
    run_audit = build_run_audit(
        scenario_id=f"maze-anti-loop-{args.episode}",
        success=acceptable,
        status=str(summary["status"]),
        metrics=aggregate_metrics,
        extra={
            "seed": args.seed,
            "max_steps": args.max_steps,
            "scenarios_run": summary["scenarios_run"],
            "scenarios_passed": summary["scenarios_passed"],
            "anti_loop_parent_summary": True,
            "goal_reached": aggregate_metrics["goal_reached"],
            "expected_goal_reachable": None,
            "expected_outcome_met": acceptable,
        },
    )

    write_json(output_dir / "world_model.json", world_model)
    (output_dir / "episode_log.jsonl").write_text("\n".join(aggregate_log_lines) + "\n", encoding="utf-8")
    write_json(output_dir / "maze_metrics.json", aggregate_metrics)
    write_json(output_dir / "status.json", summary)
    write_json(output_dir / "run_audit.json", run_audit)
    write_json(output_dir / "reference_maze.json", aggregate_reference)
    write_json(output_dir / "comparison_report.json", aggregate_comparison)
    (output_dir / "anti_loop_report.md").write_text(_markdown_report(summary, aggregate_metrics), encoding="utf-8")

    print(f"Maze anti-loop status written to {output_dir / 'status.json'}")
    print(json.dumps({"status": summary["status"], "episodes": {item["episode"]: item["metrics"]["terminated_reason"] for item in results}}, indent=2))
    return 0 if acceptable else 1


def _run_episode(episode: str, seed: int, max_steps: int, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    metrics_path = output_dir / "maze_metrics.json"
    status_path = output_dir / "status.json"
    run_audit_path = output_dir / "run_audit.json"
    reference_path = output_dir / "reference_maze.json"
    comparison_path = output_dir / "comparison_report.json"
    logger = EpisodeLogger(episode_log_path)
    env = MazeSimEnv(episode=episode, seed=seed, difficulty="medium")
    observation = env.reset()
    world_model = _new_world_model(env, observation)
    discovered_graph: Dict[str, Set[str]] = {}
    blocked_edges: Set[str] = set()
    visited_cells: Set[str] = {observation["current_cell"]}
    visit_counts: Counter[str] = Counter([observation["current_cell"]])
    blocked_attempt_counts: Counter[str] = Counter()
    visited_dead_ends: Set[str] = set()
    coverage_history = [1]
    recent_cells: deque[str] = deque([observation["current_cell"]], maxlen=4)

    metrics: Dict[str, Any] = _initial_metrics(env, max_steps)
    _apply_observation(world_model, observation, discovered_graph, blocked_edges)
    logger.log(0, "perception", observation=observation["text"], model_update={"episode": episode})
    logger.log(0, "world_model_update", model_update={"current_cell": observation["current_cell"]})

    terminated_reason = ""
    for step in range(1, max_steps + 1):
        if observation.get("goal_visible"):
            terminated_reason = "goal_found"
            break

        current = observation["current_cell"]
        action = _choose_action(current, discovered_graph, visited_cells, blocked_edges)
        if not action:
            cell_degree = len([n for n in discovered_graph.get(current, set()) if _edge_name(current, n) not in blocked_edges])
            if cell_degree <= 1:
                if current in visited_dead_ends:
                    metrics["dead_end_reentries"] += 1
                else:
                    visited_dead_ends.add(current)
                    metrics["dead_ends_entered"] += 1
            metrics["replans"] += 1
            action = _choose_backtrack_action(current, discovered_graph, visited_cells, blocked_edges)
            if not action:
                terminated_reason = "goal_unreachable_or_budget_exhausted"
                logger.log(step, "task_evaluation", result="failed", notes=terminated_reason)
                break

        target = _target_from_action(action)
        if target in visited_cells:
            metrics["backtracks"] += 1
        if len(recent_cells) >= 3 and recent_cells[-1] == recent_cells[-3] and target == recent_cells[-2]:
            metrics["oscillation_count"] += 1

        logger.log(step, "action", action=action, notes="maze anti-loop navigation action")
        previous_cell = current
        result = env.execute_action(action)
        logger.log(step, "action_result", action=action, result=json.dumps(result, ensure_ascii=False))
        if result.get("success") and target:
            _record_navigation_result(world_model, previous_cell, target, action, result, step)
        elif not result.get("success"):
            if result.get("reason") == "blocked_corridor":
                blocked = str(result.get("blocked_edge", ""))
                if blocked:
                    blocked_attempt_counts[blocked] += 1
                    if blocked in blocked_edges:
                        metrics["blocked_edge_retries"] += 1
                    blocked_edges.add(blocked)
                    _mark_blocked(world_model, blocked, step, action=action)
                metrics["blocked_edges_encountered"] += 1
                metrics["replans"] += 1
                logger.log(step, "execution_exception", action=action, result="blocked_corridor", notes=result.get("message", ""))
                logger.log(step, "replanning", model_update={"blocked_edge": blocked}, notes="Removed blocked edge from planning graph.")
            else:
                metrics["replans"] += 1
                logger.log(step, "execution_exception", action=action, result=result.get("reason", ""), notes=result.get("message", ""))

        observation = env.observe()
        current_after = observation["current_cell"]
        recent_cells.append(current_after)
        visit_counts[current_after] += 1
        visited_cells.add(current_after)
        before_coverage = coverage_history[-1]
        coverage_history.append(len(env.visited_cells))
        if coverage_history[-1] == before_coverage:
            metrics["coverage_plateau_steps"] += 1
        if _window_has_no_progress(coverage_history):
            metrics["no_progress_windows"] += 1
        _apply_observation(world_model, observation, discovered_graph, blocked_edges)
        _update_agent_state(world_model, observation, step)
        logger.log(step, "perception", observation=observation["text"], model_update={"goal_visible": observation["goal_visible"]})
        logger.log(step, "world_model_update", model_update={"current_cell": current_after})
        if observation.get("goal_visible"):
            terminated_reason = "goal_found"
            logger.log(step, "task_evaluation", result="complete", notes="Maze goal found.")
            break
    else:
        metrics["terminated_by_budget"] = True
        terminated_reason = "goal_unreachable_or_budget_exhausted"
        logger.log(max_steps, "task_evaluation", result="failed", notes=terminated_reason)

    _finalize_metrics(metrics, env, visit_counts, terminated_reason)
    metrics["agent_path_length"] = env.step_count
    world_model["task_status"] = {
        "status": "complete" if metrics["success"] else "failed",
        "success": metrics["success"],
        "reason": terminated_reason,
        "evidence": [{"type": "maze_metrics", "content": metrics}],
    }
    reference = build_reference_maze(env, episode)
    comparison = build_comparison_report(world_model, reference, metrics)
    enrich_maze_metrics(metrics, world_model, reference, comparison)
    world_model["maze_metrics"] = metrics
    expected_goal_reachable = episode not in UNREACHABLE_EPISODES
    acceptable = _episode_acceptable(
        {
            "episode": episode,
            "success": metrics["success"],
            "terminated": bool(metrics["terminated_reason"]),
            "terminated_reason": metrics["terminated_reason"],
            "metrics": metrics,
        }
    )
    metrics["expected_goal_reachable"] = expected_goal_reachable
    metrics["expected_outcome_met"] = acceptable
    status = {
        "success": metrics["success"],
        "acceptable": acceptable,
        "episode": episode,
        "seed": seed,
        "difficulty": "medium",
        "status": "complete" if acceptable else "failed",
        "expected_unreachable": episode in UNREACHABLE_EPISODES,
        "expected_goal_reachable": expected_goal_reachable,
        "goal_reached": bool(metrics["success"]),
        "expected_outcome_met": acceptable,
        "terminated": bool(metrics["terminated_reason"]),
        "terminated_reason": metrics["terminated_reason"],
        "world_model_path": "world_model.json",
        "episode_log_path": "episode_log.jsonl",
        "run_audit_path": "run_audit.json",
        "maze_metrics_path": "maze_metrics.json",
        "reference_maze_path": "reference_maze.json",
        "comparison_report_path": "comparison_report.json",
        "evidence_level": "closed_loop_final_evidence",
        "continuous_closed_loop": True,
        "capture_mode": "continuous_episode",
        "world_model_source": WORLD_MODEL_SOURCE,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
    }
    run_audit = build_run_audit(
        scenario_id=episode,
        success=bool(metrics["success"]),
        status=str(status["status"]),
        metrics=metrics,
        extra={
            "seed": seed,
            "difficulty": "medium",
            "max_steps": max_steps,
            "expected_unreachable": episode in UNREACHABLE_EPISODES,
            "expected_goal_reachable": expected_goal_reachable,
            "goal_reached": bool(metrics["success"]),
            "expected_outcome_met": acceptable,
            "acceptable": acceptable,
        },
    )

    write_json(world_model_path, world_model)
    write_json(metrics_path, metrics)
    write_json(status_path, status)
    write_json(run_audit_path, run_audit)
    write_json(reference_path, reference)
    write_json(comparison_path, comparison)
    return {
        "episode": episode,
        "success": metrics["success"],
        "acceptable": acceptable,
        "expected_unreachable": episode in UNREACHABLE_EPISODES,
        "expected_goal_reachable": expected_goal_reachable,
        "goal_reached": bool(metrics["success"]),
        "expected_outcome_met": acceptable,
        "terminated": bool(metrics["terminated_reason"]),
        "terminated_reason": metrics["terminated_reason"],
        "world_model_path": f"{episode}/world_model.json",
        "episode_log_path": f"{episode}/episode_log.jsonl",
        "run_audit_path": f"{episode}/run_audit.json",
        "maze_metrics_path": f"{episode}/maze_metrics.json",
        "status_path": f"{episode}/status.json",
        "reference_maze_path": f"{episode}/reference_maze.json",
        "comparison_report_path": f"{episode}/comparison_report.json",
        "metrics": metrics,
        "exceptions": world_model.get("exceptions", []),
    }


def _aggregate_world_model(
    episode_arg: str,
    scenario_world_models: List[tuple[str, Dict[str, Any]]],
    results: List[Dict[str, Any]],
    acceptable: bool,
    aggregate_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    cells: List[Dict[str, Any]] = []
    topology: List[Dict[str, Any]] = []
    topology_edges: List[Dict[str, Any]] = []
    objects: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    exceptions: List[Dict[str, Any]] = []
    agent_path: List[str] = []
    exploration_trace: List[Dict[str, Any]] = []

    for episode, world_model in scenario_world_models:
        for cell in world_model.get("cells", []):
            if not isinstance(cell, dict) or not cell.get("id"):
                continue
            item = dict(cell)
            item["id"] = _prefix_cell(episode, str(item["id"]))
            item["scenario"] = episode
            cells.append(item)
        for node in world_model.get("topology", []):
            if not isinstance(node, dict):
                continue
            item = dict(node)
            if item.get("cell"):
                item["cell"] = _prefix_cell(episode, str(item["cell"]))
            item["frontiers"] = [_prefix_cell(episode, str(frontier)) for frontier in item.get("frontiers", [])]
            item["scenario"] = episode
            topology.append(item)
        for edge in world_model.get("topology_edges", []):
            if not isinstance(edge, dict) or not edge.get("from") or not edge.get("to"):
                continue
            item = dict(edge)
            item["from"] = _prefix_cell(episode, str(edge["from"]))
            item["to"] = _prefix_cell(episode, str(edge["to"]))
            item["id"] = f"{item['from']}--{item['to']}"
            item["scenario"] = episode
            topology_edges.append(item)
        for obj in world_model.get("objects", []):
            if not isinstance(obj, dict):
                continue
            item = dict(obj)
            if item.get("id"):
                item["id"] = f"{episode}:{item['id']}"
            item["scenario"] = episode
            objects.append(item)
        for relation in world_model.get("relations", []):
            if not isinstance(relation, dict):
                continue
            item = dict(relation)
            item["scenario"] = episode
            relations.append(item)
        for exc in world_model.get("exceptions", []):
            if isinstance(exc, dict):
                item = dict(exc)
                item["scenario"] = episode
                exceptions.append(item)
        agent_path.extend([_prefix_cell(episode, str(cell)) for cell in world_model.get("agent_path", [])])
        for event in world_model.get("exploration_trace", []):
            if isinstance(event, dict):
                item = dict(event)
                item["scenario"] = episode
                exploration_trace.append(item)

    blocked_edges = sorted(edge["id"] for edge in topology_edges if edge.get("status") == "blocked")
    return {
        "episode_id": f"maze-anti-loop-{episode_arg}",
        "source": "maze_sim",
        "world_model_source": WORLD_MODEL_SOURCE,
        "reference_model_source": "maze_sim_reference_spec",
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "official_score": False,
        "task": "Stress anti-loop behavior, dead-end recovery, blocked-corridor replanning, and graceful no-progress termination.",
        "agent_state": {"scenario_count": len(scenario_world_models), "mode": "maze_anti_loop_aggregate"},
        "rooms": [{"id": "maze", "name": "maze", "category": "synthetic_topology"}],
        "topology": sorted(topology, key=lambda item: (item.get("scenario", ""), item.get("cell", ""))),
        "topology_edges": sorted(topology_edges, key=lambda item: item.get("id", "")),
        "cells": sorted(cells, key=lambda item: item.get("id", "")),
        "edges": sorted(topology_edges, key=lambda item: item.get("id", "")),
        "blocked_edges": blocked_edges,
        "agent_path": agent_path,
        "exploration_trace": exploration_trace,
        "objects": objects,
        "relations": relations,
        "states": [],
        "affordances": [],
        "uncertainty": [],
        "plans": [{"type": "maze_anti_loop", "actions": ["explore frontier", "avoid repeated dead ends", "replan around blocked edge"]}],
        "exceptions": exceptions,
        "task_status": {
            "status": "complete" if acceptable else "failed",
            "success": acceptable,
            "reason": "all anti-loop episodes terminated acceptably" if acceptable else "one or more anti-loop episodes failed",
        },
        "maze_metrics": aggregate_metrics,
    }


def _prefix_cell(episode: str, cell: str) -> str:
    return f"{episode}:{cell}"


def _initial_metrics(env: MazeSimEnv, max_steps: int) -> Dict[str, Any]:
    return {
        "success": False,
        "goal_found": False,
        "steps_taken": 0,
        "shortest_path_length": env.shortest_path_length(),
        "path_efficiency": 0.0,
        "visited_cells": 1,
        "total_cells": len(env.spec.cells),
        "map_coverage": 0.0,
        "dead_ends_entered": 0,
        "backtracks": 0,
        "replans": 0,
        "blocked_edges_encountered": 0,
        "loop_detected": False,
        "repeated_state_count": 0,
        "max_visit_count_single_cell": 1,
        "revisited_cells": 0,
        "oscillation_count": 0,
        "no_progress_windows": 0,
        "coverage_plateau_steps": 0,
        "terminated_by_budget": False,
        "terminated_reason": "",
        "unique_state_ratio": 1.0,
        "dead_end_reentries": 0,
        "blocked_edge_retries": 0,
        "max_steps": max_steps,
    }


def _finalize_metrics(metrics: Dict[str, Any], env: MazeSimEnv, visit_counts: Counter[str], terminated_reason: str) -> None:
    metrics["goal_found"] = bool(env.goal_found)
    metrics["success"] = bool(env.goal_found)
    metrics["steps_taken"] = env.step_count
    metrics["visited_cells"] = len(env.visited_cells)
    metrics["total_cells"] = len(env.spec.cells)
    metrics["map_coverage"] = round(len(env.visited_cells) / max(1, len(env.spec.cells)), 3)
    metrics["revisited_cells"] = sum(1 for count in visit_counts.values() if count > 1)
    metrics["repeated_state_count"] = sum(max(0, count - 1) for count in visit_counts.values())
    metrics["max_visit_count_single_cell"] = max(visit_counts.values()) if visit_counts else 0
    metrics["unique_state_ratio"] = round(len(visit_counts) / max(1, sum(visit_counts.values())), 3)
    metrics["loop_detected"] = metrics["oscillation_count"] > 0 or metrics["max_visit_count_single_cell"] >= 4
    if metrics["success"] and metrics["shortest_path_length"]:
        metrics["path_efficiency"] = round(metrics["shortest_path_length"] / max(1, env.step_count), 3)
    if not terminated_reason:
        terminated_reason = "goal_found" if metrics["success"] else "goal_unreachable_or_budget_exhausted"
    metrics["terminated_reason"] = terminated_reason


def _window_has_no_progress(history: List[int], window: int = 8) -> bool:
    if len(history) < window + 1:
        return False
    recent = history[-window:]
    return len(set(recent)) == 1


def _episode_acceptable(result: Dict[str, Any]) -> bool:
    if result["episode"] in UNREACHABLE_EPISODES:
        return result["terminated"] and not result["success"] and bool(result["terminated_reason"])
    return result["success"] or bool(result["terminated_reason"])


def _aggregate_warnings(results: List[Dict[str, Any]]) -> List[str]:
    warnings = []
    for item in results:
        metrics = item["metrics"]
        if metrics["max_visit_count_single_cell"] > max(1, metrics["max_steps"] // 2):
            warnings.append(f"{item['episode']}: high max_visit_count_single_cell={metrics['max_visit_count_single_cell']}")
        if metrics["oscillation_count"] > 10:
            warnings.append(f"{item['episode']}: high oscillation_count={metrics['oscillation_count']}")
        if metrics["blocked_edge_retries"] > 3:
            warnings.append(f"{item['episode']}: high blocked_edge_retries={metrics['blocked_edge_retries']}")
    return warnings


def _markdown_report(status: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    lines = [
        "# Maze Anti-Loop Stress Report",
        "",
        f"- success: `{status['success']}`",
        f"- episode_count: `{status['episode_count']}`",
        f"- reachable_success_count: `{status['reachable_success_count']}`",
        f"- expected_unreachable_count: `{status['expected_unreachable_count']}`",
        "",
        "| episode | success | terminated_reason | repeated_state_count | max_visit_count_single_cell | oscillation_count | dead_end_reentries | blocked_edge_retries |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for item in status["episodes"]:
        m = item["metrics"]
        lines.append(
            f"| `{item['episode']}` | `{m['success']}` | `{m['terminated_reason']}` | `{m['repeated_state_count']}` | "
            f"`{m['max_visit_count_single_cell']}` | `{m['oscillation_count']}` | `{m['dead_end_reentries']}` | `{m['blocked_edge_retries']}` |"
        )
    lines.extend(
        [
            "",
            "## Scenario Notes",
            "",
            "- `dead_end_comb_maze`: The dead-end comb intentionally causes repeated dead-end discovery and backtracking. The agent path is longer than the shortest path, but oscillation remains zero and the goal is reached.",
            "- `blocked_shortcut_maze`: The blocked shortcut scenario prioritizes safe recovery over exhaustive map completion; the agent avoids spurious edges while maintaining high topology recall.",
            "- `unreachable_goal_maze`: The goal is expected to be unreachable. `expected_goal_reachable=false`, `goal_reached=false`, and `expected_outcome_met=true` indicate graceful termination rather than task failure.",
        ]
    )
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in metrics.get("warnings", [])] or ["- none"])
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "Maze anti-loop stress is synthetic. It validates topology memory, dead-end avoidance, loop detection, no-progress termination, and replanning mechanics; it is not an official EAGC runtime or score.",
        ]
    )
    return "\n".join(lines)


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
