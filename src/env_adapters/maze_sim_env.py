from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Set, Tuple

from env_adapters.base import BaseEnvAdapter, adapter_capabilities


Cell = Tuple[int, int]
Edge = Tuple[Cell, Cell]


EPISODES = {
    "simple_t_maze",
    "plus_maze",
    "radial_arm_maze",
    "generated_grid_maze",
    "loop_lure_maze",
    "dead_end_comb_maze",
    "blocked_shortcut_maze",
    "unreachable_goal_maze",
}
DIFFICULTIES = {"easy", "medium", "hard"}
DIRECTIONS: Dict[str, Cell] = {
    "north": (0, -1),
    "south": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}


@dataclass
class MazeSpec:
    episode_id: str
    start: Cell
    goal: Cell
    cells: Set[Cell]
    edges: Set[Edge]
    blocked_edges: Set[Edge]
    relocated_goal: Cell | None = None
    door_blocked_edge: Edge | None = None
    hidden_goal: bool = True


class MazeSimEnv(BaseEnvAdapter):
    """Lightweight synthetic topology stress environment.

    MazeSim is intentionally not an official EAGC runtime. It exists to stress
    unknown-topology exploration, map building, dead-end handling, and replanning
    without external simulator dependencies.
    """

    def __init__(
        self,
        episode: str = "simple_t_maze",
        seed: int = 42,
        difficulty: str = "easy",
    ) -> None:
        if episode not in EPISODES:
            raise ValueError(f"Unknown maze episode: {episode}")
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown maze difficulty: {difficulty}")
        self.episode = episode
        self.seed = seed
        self.difficulty = difficulty
        self.rng = random.Random(seed)
        self.spec = self._build_spec()
        self.current_cell = self.spec.start
        self.step_count = 0
        self.visited_cells: Set[Cell] = set()
        self.discovered_edges: Set[Edge] = set()
        self.discovered_blocked_edges: Set[Edge] = set()
        self.goal_found = False
        self.goal_relocated = False
        self.last_result: Dict[str, Any] = {}

    def reset(self) -> Dict[str, Any]:
        self.current_cell = self.spec.start
        self.step_count = 0
        self.visited_cells = {self.current_cell}
        self.discovered_edges = set()
        self.discovered_blocked_edges = set()
        self.goal_found = self.current_cell == self.spec.goal
        self.goal_relocated = False
        self.last_result = {"success": True, "message": "maze reset"}
        return self.observe()

    def observe(self) -> Dict[str, Any]:
        visible_edges = self._visible_edges(self.current_cell)
        self.discovered_edges.update(visible_edges)
        visible_neighbors = sorted({_cell_name(other) for edge in visible_edges for other in edge if other != self.current_cell})
        goal_visible = self.current_cell == self.spec.goal
        self.goal_found = self.goal_found or goal_visible
        return {
            "episode_id": f"maze-{self.episode}",
            "source": "maze_sim",
            "step": self.step_count,
            "task": "Explore the unknown maze topology and find the hidden goal.",
            "current_cell": _cell_name(self.current_cell),
            "visible_neighbors": visible_neighbors,
            "visible_edges": [_edge_name(edge) for edge in sorted(visible_edges)],
            "blocked_edges_observed": [_edge_name(edge) for edge in sorted(self.discovered_blocked_edges)],
            "goal_visible": goal_visible,
            "goal_cell": _cell_name(self.spec.goal) if goal_visible else "",
            "last_action_result": self.last_result,
            "text": (
                f"Agent is at maze cell {_cell_name(self.current_cell)}. "
                f"Visible neighboring cells: {', '.join(visible_neighbors) or 'none'}. "
                f"Goal visible: {goal_visible}."
            ),
        }

    def step(self, action: str) -> Dict[str, Any]:
        return self.execute_action(action)

    def execute_action(self, action: str) -> Dict[str, Any]:
        target = _parse_target_cell(action)
        self.step_count += 1
        if target is None:
            self.last_result = {
                "success": False,
                "result": "invalid_action",
                "reason": "invalid_maze_action",
                "message": f"Unsupported maze action: {action}",
            }
            return self.last_result

        edge = _edge(self.current_cell, target)
        if target not in self.spec.cells or edge not in self.spec.edges:
            self.last_result = {
                "success": False,
                "result": "failed",
                "reason": "not_adjacent",
                "message": f"Target cell {_cell_name(target)} is not reachable from {_cell_name(self.current_cell)}.",
                "current_cell": _cell_name(self.current_cell),
            }
            return self.last_result

        if edge in self.spec.blocked_edges:
            self.discovered_blocked_edges.add(edge)
            if self.spec.relocated_goal and not self.goal_relocated:
                self.spec.goal = self.spec.relocated_goal
                self.goal_relocated = True
            self.last_result = {
                "success": False,
                "result": "blocked",
                "reason": "blocked_corridor",
                "exception_type": "blocked_corridor",
                "message": f"Corridor {_edge_name(edge)} is blocked; replanning required.",
                "blocked_edge": _edge_name(edge),
                "current_cell": _cell_name(self.current_cell),
            }
            return self.last_result

        self.current_cell = target
        self.visited_cells.add(target)
        self.goal_found = self.goal_found or target == self.spec.goal
        self.last_result = {
            "success": True,
            "result": "success",
            "message": f"Moved to {_cell_name(target)}.",
            "current_cell": _cell_name(target),
            "goal_found": self.goal_found,
        }
        return self.last_result

    def get_scene_graph(self) -> Dict[str, Any]:
        return {
            "success": True,
            "source": "maze_sim",
            "cells": [_cell_name(cell) for cell in sorted(self.spec.cells)],
            "edges": [_edge_name(edge) for edge in sorted(self.spec.edges)],
            "blocked_edges": [_edge_name(edge) for edge in sorted(self.spec.blocked_edges)],
            "start": _cell_name(self.spec.start),
            "goal": _cell_name(self.spec.goal),
        }

    def capture_frame(self) -> Dict[str, Any]:
        return {
            "success": False,
            "reason": "maze_has_no_renderer",
            "message": "MazeSim is a symbolic topology stress test and does not export visual frames.",
        }

    def get_agent_state(self) -> Dict[str, Any]:
        return {
            "current_cell": _cell_name(self.current_cell),
            "step": self.step_count,
            "visited_cells": [_cell_name(cell) for cell in sorted(self.visited_cells)],
            "goal_found": self.goal_found,
        }

    def capabilities(self) -> Dict[str, Any]:
        return adapter_capabilities(
            adapter_name="maze_sim",
            validated=True,
            validation_status="validated_synthetic_topology_stress",
            requires_rendering=False,
            supports_scene_graph=True,
            supports_frame_export=False,
            supports_action_execution=True,
            supports_online_closed_loop=True,
            known_blockers=["synthetic stress test; not official EAGC runtime"],
        )

    def shortest_path_length(self) -> int:
        graph = self._open_graph(include_hidden=True)
        queue: deque[tuple[Cell, int]] = deque([(self.spec.start, 0)])
        seen = {self.spec.start}
        while queue:
            cell, distance = queue.popleft()
            if cell == self.spec.goal:
                return distance
            for neighbor in graph.get(cell, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        return 0

    def _build_spec(self) -> MazeSpec:
        if self.episode == "simple_t_maze":
            cells = {(0, 0), (1, 0), (2, 0), (1, -1), (1, 1)}
            edges = _edges_from_pairs([((0, 0), (1, 0)), ((1, 0), (2, 0)), ((1, 0), (1, -1)), ((1, 0), (1, 1))])
            blocked = {_edge((1, 0), (1, -1))} if self.difficulty in {"medium", "hard"} else set()
            return MazeSpec(self.episode, (0, 0), (1, 1), cells, edges, blocked)
        if self.episode == "plus_maze":
            cells = {(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (0, 2), (1, 1)}
            edges = _edges_from_pairs(
                [
                    ((0, 0), (1, 0)),
                    ((0, 0), (-1, 0)),
                    ((0, 0), (0, 1)),
                    ((0, 0), (0, -1)),
                    ((0, 1), (0, 2)),
                    ((0, 1), (1, 1)),
                ]
            )
            blocked = {_edge((0, 0), (-1, 0))} if self.difficulty == "hard" else set()
            return MazeSpec(self.episode, (0, -1), (0, 2), cells, edges, blocked)
        if self.episode == "radial_arm_maze":
            cells = {(0, 0)}
            pairs = []
            for arm in range(4):
                direction = [(1, 0), (-1, 0), (0, 1), (0, -1)][arm]
                prev = (0, 0)
                for index in range(1, 4):
                    cell = (direction[0] * index, direction[1] * index)
                    cells.add(cell)
                    pairs.append((prev, cell))
                    prev = cell
            blocked = {_edge((0, 0), (-1, 0))} if self.difficulty in {"medium", "hard"} else set()
            return MazeSpec(self.episode, (0, 0), (3, 0), cells, _edges_from_pairs(pairs), blocked)
        if self.episode == "loop_lure_maze":
            cells = {
                (0, 0),
                (1, 0),
                (2, 0),
                (0, 1),
                (1, 1),
                (2, 1),
                (3, 1),
                (4, 1),
                (4, 0),
            }
            edges = _edges_from_pairs(
                [
                    ((0, 0), (1, 0)),
                    ((1, 0), (2, 0)),
                    ((2, 0), (2, 1)),
                    ((2, 1), (1, 1)),
                    ((1, 1), (0, 1)),
                    ((0, 1), (0, 0)),
                    ((1, 0), (1, 1)),
                    ((2, 1), (3, 1)),
                    ((3, 1), (4, 1)),
                    ((4, 1), (4, 0)),
                ]
            )
            return MazeSpec(self.episode, (0, 0), (4, 0), cells, edges, set())
        if self.episode == "dead_end_comb_maze":
            cells = {(x, 0) for x in range(7)}
            pairs = [((x, 0), (x + 1, 0)) for x in range(6)]
            for x in range(1, 6):
                cells.add((x, 1))
                cells.add((x, 2))
                pairs.append(((x, 0), (x, 1)))
                pairs.append(((x, 1), (x, 2)))
            return MazeSpec(self.episode, (0, 0), (6, 0), cells, _edges_from_pairs(pairs), set())
        if self.episode == "blocked_shortcut_maze":
            cells = {(x, 0) for x in range(5)} | {(9, 0), (9, 1), (8, 1), (7, 1), (6, 1), (5, 1), (4, 1)}
            edges = _edges_from_pairs(
                [
                    ((0, 0), (1, 0)),
                    ((1, 0), (2, 0)),
                    ((2, 0), (3, 0)),
                    ((3, 0), (4, 0)),
                    ((0, 0), (9, 0)),
                    ((9, 0), (9, 1)),
                    ((9, 1), (8, 1)),
                    ((8, 1), (7, 1)),
                    ((7, 1), (6, 1)),
                    ((6, 1), (5, 1)),
                    ((5, 1), (4, 1)),
                    ((4, 1), (4, 0)),
                ]
            )
            blocked = {_edge((1, 0), (2, 0)), _edge((2, 0), (3, 0))}
            return MazeSpec(self.episode, (0, 0), (4, 0), cells, edges, blocked)
        if self.episode == "unreachable_goal_maze":
            cells = {(0, 0), (1, 0), (2, 0), (3, 0), (10, 10)}
            edges = _edges_from_pairs([((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))])
            return MazeSpec(self.episode, (0, 0), (10, 10), cells, edges, set())
        return self._generated_grid_spec()

    def _generated_grid_spec(self) -> MazeSpec:
        size = {"easy": 4, "medium": 5, "hard": 6}[self.difficulty]
        cells = {(x, y) for x in range(size) for y in range(size)}
        pairs = []
        visited = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            cell = stack[-1]
            neighbors = [n for n in _grid_neighbors(cell, size) if n not in visited]
            if not neighbors:
                stack.pop()
                continue
            neighbor = self.rng.choice(neighbors)
            visited.add(neighbor)
            pairs.append((cell, neighbor))
            stack.append(neighbor)
        extra_count = {"easy": 1, "medium": 3, "hard": 5}[self.difficulty]
        possible = [_edge(cell, n) for cell in cells for n in _grid_neighbors(cell, size)]
        existing = set(_edges_from_pairs(pairs))
        for edge in self.rng.sample(sorted(set(possible) - existing), min(extra_count, len(set(possible) - existing))):
            pairs.append(edge)
        edges = _edges_from_pairs(pairs)
        blocked_candidates = [edge for edge in sorted(edges) if (0, 0) not in edge and (size - 1, size - 1) not in edge]
        blocked_count = {"easy": 0, "medium": 2, "hard": 4}[self.difficulty]
        blocked: Set[Edge] = set()
        for candidate in self.rng.sample(blocked_candidates, len(blocked_candidates)):
            if len(blocked) >= blocked_count:
                break
            trial = set(blocked)
            trial.add(candidate)
            if _has_path(cells, edges, trial, (0, 0), (size - 1, size - 1)):
                blocked = trial
        return MazeSpec("generated_grid_maze", (0, 0), (size - 1, size - 1), cells, edges, blocked)

    def _visible_edges(self, cell: Cell) -> Set[Edge]:
        return {edge for edge in self.spec.edges if cell in edge}

    def _open_graph(self, include_hidden: bool = False) -> Dict[Cell, List[Cell]]:
        graph: Dict[Cell, List[Cell]] = {cell: [] for cell in self.spec.cells}
        for edge in self.spec.edges:
            if edge in self.spec.blocked_edges:
                continue
            a, b = edge
            graph[a].append(b)
            graph[b].append(a)
        return graph


def _grid_neighbors(cell: Cell, size: int) -> List[Cell]:
    x, y = cell
    result = []
    for dx, dy in DIRECTIONS.values():
        nxt = (x + dx, y + dy)
        if 0 <= nxt[0] < size and 0 <= nxt[1] < size:
            result.append(nxt)
    return result


def _parse_target_cell(action: str) -> Cell | None:
    text = action.strip()
    if text.startswith("move_to(") and text.endswith(")"):
        text = text[len("move_to(") : -1]
    elif text.startswith("navigate_to(") and text.endswith(")"):
        text = text[len("navigate_to(") : -1]
    else:
        return None
    return _parse_cell(text)


def _parse_cell(text: str) -> Cell | None:
    normalized = text.strip().replace("cell_", "")
    if "," not in normalized:
        return None
    left, right = normalized.split(",", 1)
    try:
        return int(left), int(right)
    except ValueError:
        return None


def _cell_name(cell: Cell) -> str:
    return f"cell_{cell[0]},{cell[1]}"


def _edge(a: Cell, b: Cell) -> Edge:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _edge_name(edge: Edge) -> str:
    a, b = edge
    return f"{_cell_name(a)}--{_cell_name(b)}"


def _edges_from_pairs(pairs: Iterable[tuple[Cell, Cell]]) -> Set[Edge]:
    return {_edge(a, b) for a, b in pairs}


def _has_path(cells: Set[Cell], edges: Set[Edge], blocked: Set[Edge], start: Cell, goal: Cell) -> bool:
    graph: Dict[Cell, List[Cell]] = {cell: [] for cell in cells}
    for edge in edges - blocked:
        a, b = edge
        graph[a].append(b)
        graph[b].append(a)
    queue: deque[Cell] = deque([start])
    seen = {start}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            return True
        for neighbor in graph.get(cell, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False
