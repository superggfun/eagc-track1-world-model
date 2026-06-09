from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter


class ActionExecutor:
    def __init__(self, env: BaseEnvAdapter) -> None:
        self.env = env

    def execute(self, action: str) -> Dict[str, Any]:
        return self.env.step(action)
