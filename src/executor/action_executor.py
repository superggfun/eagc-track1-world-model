from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter
from executor.action_translator import ActionTranslationError, ActionTranslator, invalid_action_result


class ActionExecutor:
    def __init__(self, env: BaseEnvAdapter) -> None:
        self.env = env
        self.translator = ActionTranslator()

    def execute(self, action: str) -> Dict[str, Any]:
        try:
            action_schema = self.env.action_schema()
            translated = self.translator.to_env_action(action, action_schema)
        except ActionTranslationError as exc:
            return invalid_action_result(action, exc)
        return self.env.step(translated)
