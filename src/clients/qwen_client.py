import base64
import io
import json
import mimetypes
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

    def chat_text(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        return self._chat_completion(messages, temperature=temperature, max_tokens=max_tokens)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        return self.chat_text(messages, temperature=temperature, max_tokens=max_tokens)

    def chat_vision(
        self,
        image_path: str | Path,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        path = Path(image_path)
        if not path.exists():
            raise QwenClientError(f"Vision image does not exist: {path}")
        data_url = _image_to_data_url(path)
        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        return self._chat_completion(messages, temperature=temperature, max_tokens=max_tokens)

    def _chat_completion(
        self,
        messages: List[Dict[str, Any]],
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
        prompt_chars = _prompt_chars(messages)
        started = time.perf_counter()
        effective_temperature = self.temperature if temperature is None else temperature
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            latency = time.perf_counter() - started
            response_preview = _response_preview(exc)
            error_message = str(exc)
            if response_preview:
                error_message = f"{error_message}; response_preview={response_preview}"
            self._record_call(
                prompt_chars=prompt_chars,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                latency_seconds=latency,
                success=False,
                error_message=error_message,
                messages=messages,
            )
            raise QwenClientError(
                "Failed to call local vLLM chat completion endpoint. "
                f"URL={url}, model={self.model}, error={error_message}"
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

    def chat_json(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        messages: List[Dict[str, Any]],
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


def _prompt_chars(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    total += len(str(item.get("text", "")))
    return total


def _prompt_summary(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            compact = " ".join(content.split())
            parts.append(f"{message.get('role', 'unknown')}:text:{len(compact)}")
        elif isinstance(content, list):
            text_chars = 0
            image_count = 0
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text_chars += len(" ".join(str(item.get("text", "")).split()))
                elif item.get("type") == "image_url":
                    image_count += 1
            parts.append(f"{message.get('role', 'unknown')}:text:{text_chars};images:{image_count}")
        else:
            parts.append(f"{message.get('role', 'unknown')}:unknown:0")
    return "; ".join(parts)


def _image_to_data_url(path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png"
    image_bytes, mime_type = _image_bytes_for_vllm(path, mime_type)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _image_bytes_for_vllm(path: Path, mime_type: str) -> tuple[bytes, str]:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return path.read_bytes(), mime_type

    max_edge = 1280
    max_pixels = 1_200_000
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        if max(width, height) <= max_edge and width * height <= max_pixels:
            return path.read_bytes(), mime_type

        scale = min(max_edge / max(width, height), (max_pixels / (width * height)) ** 0.5)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        if mime_type == "image/png" and image.mode in {"RGBA", "LA"}:
            image.save(output, format="PNG", optimize=True)
            return output.getvalue(), "image/png"
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(output, format="JPEG", quality=90, optimize=True)
        return output.getvalue(), "image/jpeg"


def _response_preview(exc: requests.exceptions.RequestException) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        return response.text[:800]
    except Exception as preview_exc:
        return f"<response preview unavailable: {type(preview_exc).__name__}: {preview_exc}>"
