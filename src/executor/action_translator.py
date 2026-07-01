from __future__ import annotations

import re
from typing import Any


class ActionTranslationError(ValueError):
    """Raised when an internal action cannot be translated to runtime schema."""


class ActionTranslator:
    """Translate internal symbolic actions into the environment action format."""

    def to_env_action(
        self,
        action: dict[str, Any] | str,
        action_schema: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | str:
        schema = list(action_schema or [])
        if not schema:
            return action

        action_name = _action_name(action)
        exact = str(action).strip()
        allowed_names = _schema_action_names(schema)
        allowed_exact = _schema_exact_actions(schema)
        templates = _schema_templates(schema)

        if exact in allowed_exact or action_name in allowed_names:
            return action
        if _matches_template(exact, templates):
            return action

        raise ActionTranslationError(
            f"Unsupported action {exact!r}; not present in adapter action_schema."
        )


def invalid_action_result(action: dict[str, Any] | str, error: Exception | str) -> dict[str, Any]:
    return {
        "success": False,
        "action": action,
        "result": "invalid_action",
        "message": str(error),
        "error": "unsupported_action_schema",
        "observation": "",
        "observation_packet": {},
        "metadata": {
            "translation_failed": True,
            "reason": "unsupported_action_schema",
        },
    }


def _action_name(action: dict[str, Any] | str) -> str:
    if isinstance(action, dict):
        for key in ("name", "action", "type", "verb"):
            value = action.get(key)
            if value:
                return str(value).strip()
        return ""
    text = str(action).strip()
    match = re.match(r"^([A-Za-z0-9_]+)\s*(?:\(|$)", text)
    return match.group(1) if match else text


def _schema_action_names(schema: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in schema:
        for key in ("name", "action", "type", "verb"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip())
        aliases = item.get("aliases")
        if isinstance(aliases, list):
            names.update(str(alias).strip() for alias in aliases if str(alias).strip())
    return names


def _schema_exact_actions(schema: list[dict[str, Any]]) -> set[str]:
    exact: set[str] = set()
    for item in schema:
        for key in ("command", "example", "literal"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                exact.add(value.strip())
    return exact


def _schema_templates(schema: list[dict[str, Any]]) -> list[str]:
    templates: list[str] = []
    for item in schema:
        value = item.get("template")
        if isinstance(value, str) and value.strip():
            templates.append(value.strip())
    return templates


def _matches_template(action: str, templates: list[str]) -> bool:
    for template in templates:
        pattern = re.escape(template)
        pattern = re.sub(r"\\\{[A-Za-z0-9_]+\\\}", r"[^,()]+", pattern)
        if re.fullmatch(pattern, action):
            return True
    return False
