import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from perception.json_utils import extract_json_from_text


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
        audit_path: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.audit_path = audit_path
        self.call_count = 0
        self.success_count = 0
        self.failure_count = 0

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
        prompt_chars = sum(len(message.get("content", "")) for message in messages)
        started = time.perf_counter()
        effective_temperature = self.temperature if temperature is None else temperature
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            latency = time.perf_counter() - started
            self._record_call(
                prompt_chars=prompt_chars,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                latency_seconds=latency,
                success=False,
                error_message=str(exc),
                messages=messages,
            )
            raise QwenClientError(
                "Failed to call local vLLM chat completion endpoint. "
                f"URL={url}, model={self.model}, error={exc}"
            ) from exc

        try:
            data: Dict[str, Any] = response.json()
            content = data["choices"][0]["message"]["content"]
            self._record_call(
                prompt_chars=prompt_chars,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                latency_seconds=time.perf_counter() - started,
                success=True,
                error_message="",
                messages=messages,
            )
            return content
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            preview = response.text[:500]
            self._record_call(
                prompt_chars=prompt_chars,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                latency_seconds=time.perf_counter() - started,
                success=False,
                error_message=f"Unexpected response schema: {preview}",
                messages=messages,
            )
            raise QwenClientError(
                "vLLM response did not match the expected OpenAI-compatible schema. "
                f"Response preview: {preview}"
            ) from exc

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        content = self.chat(messages)
        try:
            return json.loads(extract_json_from_text(content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise QwenClientError(
                "Model returned non-JSON content where JSON was required. "
                f"Raw content preview: {content[:500]}"
            ) from exc

    def _record_call(
        self,
        prompt_chars: int,
        temperature: float,
        max_tokens: int,
        latency_seconds: float,
        success: bool,
        error_message: str,
        messages: List[Dict[str, str]],
    ) -> None:
        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self.model,
            "base_url": self.base_url,
            "prompt_chars": prompt_chars,
            "prompt_summary": _prompt_summary(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "latency_seconds": round(latency_seconds, 6),
            "success": success,
            "error_message": error_message,
        }
        with self.audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _prompt_summary(messages: List[Dict[str, str]]) -> str:
    parts = []
    for message in messages:
        content = " ".join(message.get("content", "").split())
        parts.append(f"{message.get('role', 'unknown')}:{len(content)}")
    return "; ".join(parts)
