from pathlib import Path

import requests

from clients.qwen_client import _response_preview
from env_adapters.ai2thor_adapter import AI2ThorAdapter


class _StopFailsController:
    def stop(self) -> None:
        raise RuntimeError("stop exploded")


class _TextFailsResponse:
    @property
    def text(self) -> str:
        raise RuntimeError("preview exploded")


def test_ai2thor_close_records_stop_failure_without_raising(tmp_path: Path) -> None:
    adapter = AI2ThorAdapter(output_dir=tmp_path)
    adapter.controller = _StopFailsController()

    adapter.close()

    assert adapter.controller is None
    assert adapter.error_message == "AI2-THOR controller.stop() failed during close(): RuntimeError: stop exploded"


def test_response_preview_returns_tagged_message_when_text_fails() -> None:
    exc = requests.exceptions.RequestException("request failed")
    exc.response = _TextFailsResponse()

    preview = _response_preview(exc)

    assert preview == "<response preview unavailable: RuntimeError: preview exploded>"
