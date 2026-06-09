from typing import Any, Dict

from env_adapters.base import BaseEnvAdapter


class OfficialAdapter(BaseEnvAdapter):
    """Placeholder for a future official EAGC runtime/API adapter."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError(
            "Official EAGC runtime/API is not available yet. Use MockEnv for the MVP."
        )

    def reset(self) -> Dict[str, Any]:
        raise NotImplementedError

    def step(self, action: str) -> Dict[str, Any]:
        raise NotImplementedError
