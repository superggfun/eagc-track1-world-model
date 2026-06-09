import re
from typing import Iterable, List


ACTION_PATTERNS = {
    "locate": re.compile(r"^locate\([a-zA-Z0-9_]+\)$"),
    "navigate_to": re.compile(r"^navigate_to\([a-zA-Z0-9_]+\)$"),
    "search": re.compile(r"^search\([a-zA-Z0-9_]+\)$"),
    "pick_up": re.compile(r"^pick_up\([a-zA-Z0-9_]+\)$"),
    "place_on": re.compile(r"^place_on\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "open": re.compile(r"^open\([a-zA-Z0-9_]+\)$"),
    "close": re.compile(r"^close\([a-zA-Z0-9_]+\)$"),
    "unlock": re.compile(r"^unlock\([a-zA-Z0-9_]+\)$"),
    "substitute_tool": re.compile(r"^substitute_tool\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "wait": re.compile(r"^wait\(\)$"),
}


ALLOWED_ACTIONS = tuple(ACTION_PATTERNS)


def is_valid_action(action: str) -> bool:
    return any(pattern.match(action) for pattern in ACTION_PATTERNS.values())


def invalid_actions(actions: Iterable[str]) -> List[str]:
    return [action for action in actions if not is_valid_action(action)]
