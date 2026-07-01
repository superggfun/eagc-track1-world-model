"""Perception policy — decides whether a post-action VLM call is warranted.

Conservative first edition:
- Skip VLM for successful deterministic actions whose effects are
  already fully captured by `action_effects.py`.
- Keep VLM for exploratory, information‑gathering, and recovery actions.
- Never skip on failure or exception.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

# ---------------------------------------------------------------------------
# Action‑name normalisation
# ---------------------------------------------------------------------------
# Handles ``pick_up(book)``, ``place_on(book, table)``, ``pickup book``, etc.

_ACTION_PAREN_RE = re.compile(r"^([a-z_]+)\(.*\)$")


def normalize_action_name(action: Any) -> str:
    """Return a canonicalised action name string.

    Examples:
        ``"pick_up(book)"`` → ``"pick_up"``
        ``"place_on(book, table)"`` → ``"place_on"``
        ``"explore()"`` → ``"explore"``
        ``{"name": "pick_up", "args": ["book"]}`` → ``"pick_up"``
    """
    if isinstance(action, dict):
        return str(action.get("name") or action.get("action") or "").lower()
    raw = str(action).strip()
    m = _ACTION_PAREN_RE.match(raw)
    if m:
        return m.group(1).lower()
    # Fallback: take first word-ish token
    return raw.split()[0].lower() if raw.split() else raw.lower()


# ---------------------------------------------------------------------------
# Action sets
# ---------------------------------------------------------------------------

# Successful actions where action_effects.py already captures all state
# changes deterministically — no VLM needed.
_SKIPPABLE_ACTIONS: frozenset[str] = frozenset({
    "pick_up",
    "pickup",
    "place_on",
    "placeon",
    "place_in",
    "placein",
    "unlock",
    "close",
    "substitute_tool",
})

# Actions that inherently gather new information and MUST use VLM.
_ALWAYS_PERCEIVE_ACTIONS: frozenset[str] = frozenset({
    "explore",
    "search",
    "locate",
    "scan",
    "look",
    "observe",
    "navigate_to",
    "navigate",
    "move_to",
    "open",
})


# ---------------------------------------------------------------------------
# Core policy function
# ---------------------------------------------------------------------------


def should_run_post_action_vlm(
    action: str,
    result: Dict[str, Any],
    world_model: Dict[str, Any],  # noqa: ARG001 reserved for future use
    *,
    phase: str = "execution",
    recovery: bool = False,
) -> Tuple[bool, str]:
    """Return ``(should_perceive, reason)`` for a post-action VLM call.

    Rules (first match wins):
      1. Failure / exception → always perceive.
      2. Recovery step → always perceive (conservative).
      3. Non‑execution phase → perceive (exploration, planning).
      4. Deterministic skippable action → skip.
      5. Information‑gathering action → perceive.
      6. Unknown action → perceive (conservative).
    """
    name = normalize_action_name(action)
    success = result.get("success", False) is True

    if not success:
        return True, "action_failed_or_exception"
    if recovery:
        return True, "recovery_step"
    if phase != "execution":
        return True, f"non_execution_phase_{phase}"
    if name in _SKIPPABLE_ACTIONS:
        return False, "deterministic_action_effect_applied"
    if name in _ALWAYS_PERCEIVE_ACTIONS:
        return True, f"info_gathering_action_{name}"
    return True, f"unknown_action_{name}"
