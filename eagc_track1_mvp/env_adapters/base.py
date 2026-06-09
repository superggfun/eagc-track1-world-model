from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseEnvAdapter(ABC):
    """Minimal environment adapter contract for future official runtime swaps."""

    @abstractmethod
    def reset(self) -> Dict[str, Any]:
        """Start an episode and return the first observation packet."""

    @abstractmethod
    def step(self, action: str) -> Dict[str, Any]:
        """Execute one action and return an environment result packet."""
