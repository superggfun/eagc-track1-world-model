import json
from pathlib import Path
from typing import Any, Dict, List

from planner.action_schema import invalid_actions


def compute_track1_score(
    world_model: Dict[str, Any],
    episode_rows: List[Dict[str, Any]],
    audit: Dict[str, Any],
    validation_status: Dict[str, Any] | str | None = None,
) -> Dict[str, Any]:
    task_completion = _task_completion_score(world_model)
    world_model_quality = _world_model_quality_score(world_model)
    exception_recovery = _exception_recovery_score(world_model, episode_rows)
    execution_efficiency = _execution_efficiency_score(audit)
    robustness_safety = _robustness_safety_score(world_model, episode_rows, validation_status)
    total = round(
        task_completion
        + world_model_quality
        + exception_recovery
        + execution_efficiency
        + robustness_safety,
        2,
    )
    return {
        "total_score": total,
        "max_score": 100,
        "components": {
            "task_completion": task_completion,
            "world_model_quality": world_model_quality,
            "exception_recovery": exception_recovery,
            "execution_efficiency": execution_efficiency,
            "robustness_safety": robustness_safety,
        },
        "notes": {
            "task_status": world_model.get("task_status", {}).get("status", "unknown"),
            "phase_budget_exceeded": bool(audit.get("phase_budget_exceeded", False)),
        },
    }


def write_track1_score(path: Path, score: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(score, indent=2, ensure_ascii=False), encoding="utf-8")


def _task_completion_score(world_model: Dict[str, Any]) -> float:
    status = world_model.get("task_status", {}).get("status")
    if status == "complete":
        return 40.0
    if status == "blocked_recovered":
        return 25.0
    return 0.0


def _world_model_quality_score(world_model: Dict[str, Any]) -> float:
    score = 0.0
    if world_model.get("topology"):
        score += 4.0
    if world_model.get("visited_rooms"):
        score += 4.0
    if world_model.get("objects"):
        score += 4.0
    if _location_relations_are_consistent(world_model):
        score += 4.0
    if world_model.get("uncertainty") or not world_model.get("exceptions"):
        score += 4.0
    return score


def _exception_recovery_score(world_model: Dict[str, Any], rows: List[Dict[str, Any]]) -> float:
    exceptions = world_model.get("exceptions", [])
    event_types = {row.get("event_type") for row in rows}
    status = world_model.get("task_status", {}).get("status")
    if not exceptions:
        return 20.0 if status == "complete" else 8.0
    score = 0.0
    if exceptions:
        score += 5.0
    if "replanning" in event_types:
        score += 5.0
    if "recovery_action" in event_types:
        score += 5.0
    if status in {"complete", "blocked_recovered"}:
        score += 5.0
    return score


def _execution_efficiency_score(audit: Dict[str, Any]) -> float:
    total_used = float(audit.get("total_steps_used", 0) or 0)
    budgets = audit.get("track1_budgets", {})
    if not isinstance(budgets, dict):
        budgets = {}
    total_budget = float(
        (budgets.get("exploration_steps", 0) or 0)
        + (budgets.get("planning_steps", 0) or 0)
        + (budgets.get("execution_steps", 0) or 0)
        + (budgets.get("max_recovery_steps", 0) or 0)
    )
    if total_budget <= 0:
        return 0.0
    ratio = total_used / total_budget
    if ratio <= 0.5:
        return 10.0
    if ratio <= 1.0:
        return round(10.0 - ((ratio - 0.5) * 10.0), 2)
    return 0.0


def _robustness_safety_score(
    world_model: Dict[str, Any],
    rows: List[Dict[str, Any]],
    validation_status: Dict[str, Any] | str | None,
) -> float:
    score = 0.0
    if isinstance(validation_status, dict) and validation_status.get("passed") is True:
        score += 5.0
    elif validation_status is None or validation_status == "not_requested":
        score += 2.5

    actions = [row.get("action", "") for row in rows if row.get("action")]
    if not invalid_actions(actions):
        score += 3.0

    if not _has_holding_conflict(world_model):
        score += 2.0
    return score


def _location_relations_are_consistent(world_model: Dict[str, Any]) -> bool:
    active_by_subject: Dict[str, int] = {}
    for relation in world_model.get("relations", []):
        if (
            isinstance(relation, dict)
            and relation.get("status") == "active"
            and relation.get("relation") in {"on", "inside", "under", "near", "beside", "at"}
        ):
            subject = str(relation.get("subject"))
            active_by_subject[subject] = active_by_subject.get(subject, 0) + 1
    return all(count <= 1 for count in active_by_subject.values())


def _has_holding_conflict(world_model: Dict[str, Any]) -> bool:
    holding = world_model.get("agent_state", {}).get("holding")
    held_states = [
        state
        for state in world_model.get("states", [])
        if isinstance(state, dict)
        and state.get("attribute") == "held_by"
        and state.get("value") == "agent"
    ]
    if holding is None:
        return bool(held_states)
    return len(held_states) > 1
