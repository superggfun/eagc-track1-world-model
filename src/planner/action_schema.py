import re
from typing import Iterable, List, Tuple


ACTION_PATTERNS = {
    "explore": re.compile(r"^explore\([a-zA-Z0-9_]+\)$"),
    "inspect": re.compile(r"^inspect\([a-zA-Z0-9_]+\)$"),
    "locate": re.compile(r"^locate\([a-zA-Z0-9_]+\)$"),
    "answer_location": re.compile(r"^answer_location\([a-zA-Z0-9_]+\)$"),
    "answer_relation": re.compile(r"^answer_relation\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "mark_task_complete": re.compile(r"^mark_task_complete\([a-zA-Z0-9_]+\)$"),
    "navigate_to": re.compile(r"^navigate_to\([a-zA-Z0-9_]+\)$"),
    "search": re.compile(r"^search\([a-zA-Z0-9_]+\)$"),
    "pick_up": re.compile(r"^pick_up\([a-zA-Z0-9_]+\)$"),
    "place_on": re.compile(r"^place_on\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "place_in": re.compile(r"^place_in\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "open": re.compile(r"^open\([a-zA-Z0-9_]+\)$"),
    "close": re.compile(r"^close\([a-zA-Z0-9_]+\)$"),
    "unlock": re.compile(r"^unlock\([a-zA-Z0-9_]+\)$"),
    "substitute_tool": re.compile(r"^substitute_tool\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "use_tool": re.compile(r"^use_tool\([a-zA-Z0-9_]+,\s*[a-zA-Z0-9_]+\)$"),
    "enter": re.compile(r"^enter\([a-zA-Z0-9_]+\)$"),
    "wait": re.compile(r"^wait\(\)$"),
}


ALLOWED_ACTIONS = tuple(ACTION_PATTERNS)


def is_valid_action(action: str) -> bool:
    return any(pattern.match(action) for pattern in ACTION_PATTERNS.values())


def invalid_actions(actions: Iterable[str]) -> List[str]:
    return [action for action in actions if not is_valid_action(action)]


def parse_action(action: str) -> Tuple[str, List[str]]:
    match = re.match(r"^([a-z_]+)\((.*)\)$", action.strip())
    if not match:
        return action, []
    name = match.group(1)
    args_text = match.group(2).strip()
    if not args_text:
        return name, []
    return name, [arg.strip() for arg in args_text.split(",")]
