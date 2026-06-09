import json
from typing import Any, Dict, List, Optional

import requests


class QwenClientError(RuntimeError):
    pass


class QwenClient:
    """Small OpenAI-compatible text chat client for local vLLM."""

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout_seconds: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise QwenClientError(
                "Failed to call local vLLM chat completion endpoint. "
                f"URL={url}, model={self.model}, error={exc}"
            ) from exc

        try:
            data: Dict[str, Any] = response.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            preview = response.text[:500]
            raise QwenClientError(
                "vLLM response did not match the expected OpenAI-compatible schema. "
                f"Response preview: {preview}"
            ) from exc

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        content = self.chat(messages)
        try:
            return json.loads(_extract_json_object(content))
        except json.JSONDecodeError as exc:
            raise QwenClientError(
                "Model returned non-JSON content where JSON was required. "
                f"Raw content preview: {content[:500]}"
            ) from exc


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]
