from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env_adapters.maze_sim_env import DIFFICULTIES, EPISODES, MazeSimEnv
from logging_utils.episode_logger import EpisodeLogger


LOCATION_RELATION = "connected_to"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a synthetic maze topology stress test.")
    parser.add_argument("--episode", choices=sorted(EPISODES), default="simple_t_maze")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="easy")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--output-dir", default="outputs/maze_stress")
    args = parser.parse_args()

    output_dir = _resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    metrics_path = output_dir / "maze_metrics.json"
    status_path = output_dir / "status.json"

    env = MazeSimEnv(episode=args.episode, seed=args.seed, difficulty=args.difficulty)
    logger = EpisodeLogger(episode_log_path)
    observation = env.reset()
    world_model = _new_world_model(env, observation)
    metrics: Dict[str, Any] = {
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
    }
    visited_dead_ends: Set[str] = set()
    discovered_graph: Dict[str, Set[str]] = {}
    blocked_edges: Set[str] = set()
    visited_cells: Set[str] = {observation["current_cell"]}

    _apply_observation(world_model, observation, discovered_graph, blocked_edges)
    logger.log(0, "perception", observation=observation["text"], model_update={"source": "maze_sim"})
    logger.log(0, "world_model_update", model_update={"current_cell": observation["current_cell"]})

    status = {
        "success": False,
        "episode": args.episode,
        "seed": args.seed,
        "difficulty": args.difficulty,
        "status": "running",
        "world_model_path": str(world_model_path),
        "episode_log_path": str(episode_log_path),
        "maze_metrics_path": str(metrics_path),
        "error_message": "",
    }

    for step in range(1, args.max_steps + 1):
        if observation.get("goal_visible"):
            status["status"] = "complete"
            status["success"] = True
            break

        current = observation["current_cell"]
        action = _choose_action(current, discovered_graph, visited_cells, blocked_edges)
        if not action:
            cell_degree = len([n for n in discovered_graph.get(current, set()) if _edge_name(current, n) not in blocked_edges])
            if cell_degree <= 1 and current not in visited_dead_ends:
                visited_dead_ends.add(current)
                metrics["dead_ends_entered"] += 1
            metrics["replans"] += 1
            action = _choose_backtrack_action(current, discovered_graph, visited_cells, blocked_edges)
            if not action:
                status["status"] = "failed"
                status["error_message"] = "No reachable unexplored frontier remains."
                break

        target = _target_from_action(action)
        if target in visited_cells:
            metrics["backtracks"] += 1
        logger.log(step, "action", action=action, notes="maze navigation action")
        result = env.execute_action(action)
        logger.log(step, "action_result", action=action, result=json.dumps(result, ensure_ascii=False))

        if not result.get("success"):
            if result.get("reason") == "blocked_corridor":
                blocked = str(result.get("blocked_edge", ""))
                if blocked:
                    blocked_edges.add(blocked)
                    _mark_blocked(world_model, blocked, step)
                metrics["blocked_edges_encountered"] += 1
                metrics["replans"] += 1
                logger.log(step, "execution_exception", action=action, result=result.get("reason", ""), notes=result.get("message", ""))
                logger.log(step, "replanning", model_update={"blocked_edge": blocked}, notes="Removed blocked edge from planning graph.")
            else:
                logger.log(step, "execution_exception", action=action, result=result.get("reason", ""), notes=result.get("message", ""))
                metrics["replans"] += 1

        observation = env.observe()
        visited_cells.add(observation["current_cell"])
        _apply_observation(world_model, observation, discovered_graph, blocked_edges)
        _update_agent_state(world_model, observation, step)
        logger.log(step, "perception", observation=observation["text"], model_update={"goal_visible": observation["goal_visible"]})
        logger.log(step, "world_model_update", model_update={"current_cell": observation["current_cell"]})
        if observation.get("goal_visible"):
            status["status"] = "complete"
            status["success"] = True
            logger.log(step, "task_evaluation", result="complete", notes="Maze goal found.")
            break
    else:
        status["status"] = "failed"
        status["error_message"] = "Max steps exhausted before finding goal."

    metrics["goal_found"] = bool(env.goal_found)
    metrics["success"] = bool(env.goal_found)
    metrics["steps_taken"] = env.step_count
    metrics["visited_cells"] = len(env.visited_cells)
    metrics["total_cells"] = len(env.spec.cells)
    metrics["map_coverage"] = round(len(env.visited_cells) / max(1, len(env.spec.cells)), 3)
    if metrics["success"] and metrics["shortest_path_length"]:
        metrics["path_efficiency"] = round(metrics["shortest_path_length"] / max(1, env.step_count), 3)
    world_model["task_status"] = {
        "status": "complete" if metrics["success"] else "failed",
        "success": metrics["success"],
        "reason": "maze goal found" if metrics["success"] else status["error_message"],
        "evidence": [{"type": "cell", "content": env.get_agent_state()}],
    }
    world_model["maze_metrics"] = metrics
    status["success"] = bool(metrics["success"])
    if status["success"]:
        status["status"] = "complete"

    world_model_path.write_text(json.dumps(world_model, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Maze stress status written to {status_path}")
    print(json.dumps({"status": status["status"], **metrics}, indent=2))
    return 0 if status["success"] else 1


def _new_world_model(env: MazeSimEnv, observation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "episode_id": observation["episode_id"],
        "source": "maze_sim",
        "agent_state": {
            "current_room": "maze",
            "current_cell": observation["current_cell"],
            "holding": None,
            "step": 0,
            "last_action": "",
            "mode": "maze_exploration",
        },
        "rooms": [{"id": "maze", "name": "maze", "category": "synthetic_topology"}],
        "topology": [],
        "cells": [],
        "edges": [],
        "blocked_edges": [],
        "visited_rooms": ["maze"],
        "frontiers": [],
        "objects": [
            {
                "id": "hidden_goal",
                "name": "hidden_goal",
                "category": "goal",
                "location": {"room": "maze", "region": "", "support": "", "status": "unknown", "confidence": 0.0},
                "state": "hidden",
            }
        ],
        "relations": [],
        "states": [],
        "affordances": [],
        "uncertainty": [
            {
                "entity": "hidden_goal",
                "attribute": "location",
                "level": "high",
                "reason": "Goal is hidden until observed in the maze.",
            }
        ],
        "plans": [{"type": "maze_exploration", "actions": ["explore frontiers", "backtrack from dead ends", "replan around blocked corridors"]}],
        "exceptions": [],
        "task_status": {"status": "in_progress", "success": False, "reason": "", "evidence": []},
    }


def _apply_observation(world_model: Dict[str, Any], observation: Dict[str, Any], graph: Dict[str, Set[str]], blocked_edges: Set[str]) -> None:
    current = observation["current_cell"]
    cells = {item["id"]: item for item in world_model["cells"]}
    cells.setdefault(current, {"id": current, "visited": True, "frontier": False})
    cells[current]["visited"] = True
    cells[current]["frontier"] = False
    for neighbor in observation.get("visible_neighbors", []):
        cells.setdefault(neighbor, {"id": neighbor, "visited": False, "frontier": True})
        if not cells[neighbor].get("visited"):
            cells[neighbor]["frontier"] = True
        graph.setdefault(current, set()).add(neighbor)
        graph.setdefault(neighbor, set()).add(current)
    world_model["cells"] = sorted(cells.values(), key=lambda item: item["id"])
    world_model["frontiers"] = sorted([cell for cell, item in cells.items() if item.get("frontier") and not item.get("visited")])
    world_model["topology"] = [
        {
            "cell": cell,
            "node_type": "maze_cell",
            "visited": item.get("visited", False),
            "frontiers": sorted(graph.get(cell, set())),
        }
        for cell, item in sorted(cells.items())
    ]
    edge_map = {item["id"]: item for item in world_model["edges"]}
    for edge in observation.get("visible_edges", []):
        edge_map.setdefault(edge, {"id": edge, "status": "blocked" if edge in blocked_edges else "open"})
    for edge in blocked_edges:
        edge_map[edge] = {"id": edge, "status": "blocked"}
    world_model["edges"] = sorted(edge_map.values(), key=lambda item: item["id"])
    world_model["blocked_edges"] = sorted(blocked_edges)
    relation_ids = {(item["subject"], item["object"]) for item in world_model["relations"]}
    for edge in world_model["edges"]:
        a, b = edge["id"].split("--", 1)
        status = "blocked" if edge["status"] == "blocked" else "active"
        for subject, obj in [(a, b), (b, a)]:
            if (subject, obj) not in relation_ids:
                world_model["relations"].append(
                    {
                        "subject": subject,
                        "relation": LOCATION_RELATION,
                        "object": obj,
                        "status": status,
                        "confidence": 1.0,
                        "observed_at_step": observation.get("step", 0),
                    }
                )
                relation_ids.add((subject, obj))
    if observation.get("goal_visible"):
        goal = next(item for item in world_model["objects"] if item["id"] == "hidden_goal")
        goal["location"] = {
            "room": "maze",
            "region": observation["current_cell"],
            "support": observation["current_cell"],
            "status": "known",
            "confidence": 1.0,
        }
        goal["state"] = "found"


def _update_agent_state(world_model: Dict[str, Any], observation: Dict[str, Any], step: int) -> None:
    world_model["agent_state"]["current_cell"] = observation["current_cell"]
    world_model["agent_state"]["step"] = step
    world_model["agent_state"]["last_action"] = ""


def _mark_blocked(world_model: Dict[str, Any], blocked_edge: str, step: int) -> None:
    world_model["exceptions"].append(
        {
            "type": "blocked_corridor",
            "blocked_edge": blocked_edge,
            "step": step,
            "recovery_plan": {"actions": ["remove blocked edge from graph", "search alternate frontier"]},
        }
    )
    for relation in world_model.get("relations", []):
        if {relation.get("subject"), relation.get("object")} == set(blocked_edge.split("--")):
            relation["status"] = "blocked"


def _choose_action(current: str, graph: Dict[str, Set[str]], visited: Set[str], blocked_edges: Set[str]) -> str:
    for neighbor in sorted(graph.get(current, set())):
        if neighbor not in visited and _edge_name(current, neighbor) not in blocked_edges:
            return f"move_to({neighbor})"
    return ""


def _choose_backtrack_action(current: str, graph: Dict[str, Set[str]], visited: Set[str], blocked_edges: Set[str]) -> str:
    targets = [cell for cell in visited if any(n not in visited for n in graph.get(cell, set()))]
    path = _shortest_path(current, targets, graph, blocked_edges)
    if len(path) >= 2:
        return f"move_to({path[1]})"
    return ""


def _shortest_path(start: str, targets: List[str], graph: Dict[str, Set[str]], blocked_edges: Set[str]) -> List[str]:
    target_set = set(targets)
    queue: deque[List[str]] = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        cell = path[-1]
        if cell in target_set and cell != start:
            return path
        for neighbor in sorted(graph.get(cell, set())):
            if neighbor in seen or _edge_name(cell, neighbor) in blocked_edges:
                continue
            seen.add(neighbor)
            queue.append(path + [neighbor])
    return []


def _target_from_action(action: str) -> str:
    if action.startswith("move_to(") and action.endswith(")"):
        return action[len("move_to(") : -1]
    return ""


def _edge_name(a: str, b: str) -> str:
    return "--".join(sorted([a, b]))


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
