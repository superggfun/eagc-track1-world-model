import json
from pathlib import Path
from typing import Any

import pytest

from env_adapters.official_env import OfficialEnvAdapter, OfficialRuntimeUnavailable
from env_adapters.registry import capabilities_for, get_adapter, list_adapters
from executor.action_translator import ActionTranslationError, ActionTranslator
from harness.run_official import run_official, run_official_with_adapter


class FakeOfficialAdapter:
    def __init__(self, episode_id: str = "local-explore-book-relocated") -> None:
        self.episode_id = episode_id
        self.step_count = 0
        self.holding = ""
        self.book_support = "bed"

    def reset(self, episode_config: dict[str, Any] | None = None) -> dict[str, Any]:
        if episode_config and episode_config.get("episode_id"):
            self.episode_id = str(episode_config["episode_id"])
        self.step_count = 0
        self.holding = ""
        self.book_support = "bed"
        return self._packet(task="")

    def observe(self) -> dict[str, Any]:
        return self._packet(task="Find the book and place it on the chair.")

    def step(self, action: dict[str, Any] | str) -> dict[str, Any]:
        self.step_count += 1
        text = str(action)
        if text == "pick_up(book)":
            self.holding = "book"
            self.book_support = "agent_hand"
        elif text == "place_on(book, chair)":
            self.holding = ""
            self.book_support = "chair"
        return {
            "success": True,
            "action": text,
            "result": "success",
            "message": f"Executed {text}",
            "observation": self._packet(task="").get("observation", ""),
            "observation_packet": self._packet(task=""),
        }

    def action_schema(self) -> list[dict[str, Any]]:
        return []

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": "official",
            "status": "fake_test_adapter",
            "supports_hidden_runtime": True,
            "supports_observe_step_loop": True,
            "uses_hidden_ground_truth": False,
            "requires_internet": False,
        }

    def close(self) -> None:
        return None

    def _packet(self, *, task: str) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task": task,
            "source": "fake_official_adapter_test",
            "observation": "Room: bedroom. Visible objects: book, chair, bed. The room has a visible reading area.",
            "current_room": "bedroom",
            "room": "bedroom",
            "visible_objects": ["book", "chair", "bed"],
            "available_actions": ["explore", "search", "navigate_to", "locate", "pick_up", "place_on"],
            "agent_state": {
                "current_room": "bedroom",
                "holding": self.holding or None,
                "step": self.step_count,
                "visited_rooms": ["bedroom"],
            },
            "topology": [
                {"room": "bedroom", "node_type": "room", "visited": True, "frontiers": ["hallway via doorway"]},
                {"room": "hallway", "node_type": "room", "visited": False, "frontiers": []},
            ],
            "visible_frontiers": [{"target": "hallway", "via": "doorway"}],
            "object_hints": {
                "book": {
                    "category": "book",
                    "region": "bed_area",
                    "support": self.book_support,
                    "confidence": 0.95,
                },
                "chair": {
                    "category": "furniture",
                    "region": "bed_area",
                    "support": "floor",
                    "confidence": 0.9,
                },
                "bed": {
                    "category": "furniture",
                    "region": "bed_area",
                    "support": "floor",
                    "confidence": 0.9,
                },
            },
        }


def test_official_adapter_imports_without_sdk() -> None:
    assert OfficialEnvAdapter.__name__ == "OfficialEnvAdapter"
    assert get_adapter("official") is OfficialEnvAdapter


def test_registry_lists_official_capabilities() -> None:
    names = {item.get("adapter_name") for item in list_adapters()}
    assert "official" in names
    caps = capabilities_for("official")
    assert caps["status"] == "stub_until_official_runtime_release"
    assert caps["supports_hidden_runtime"] is True
    assert caps["uses_hidden_ground_truth"] is False
    assert caps["requires_internet"] is False


def test_official_adapter_fails_closed_without_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "EAGC_OFFICIAL_MODE",
        "EAGC_ENV_HOST",
        "EAGC_ENV_PORT",
        "EAGC_EPISODE_ID",
        "EAGC_CONFIG_PATH",
        "EAGC_OUTPUT_DIR",
        "EAGC_ACTION_SCHEMA_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(OfficialRuntimeUnavailable, match="never falls back to LocalSim"):
        OfficialEnvAdapter()


def test_run_official_fails_closed_and_writes_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EAGC_OFFICIAL_MODE", raising=False)
    code = run_official(output_dir=tmp_path, episode_id="hidden_episode", validate=False)
    assert code == 1
    audit = _read_json(tmp_path / "run_audit.json")
    result = _read_json(tmp_path / "harness_result.json")
    assert audit["env"] == "official"
    assert audit["success"] is False
    assert audit["fallback_to_local_sim"] is False
    assert result["success"] is False
    assert not (tmp_path / "world_model.json").exists()


def test_track1_runner_accepts_fake_official_adapter(tmp_path: Path) -> None:
    code = run_official_with_adapter(
        adapter=FakeOfficialAdapter(),
        episode_id="local-explore-book-relocated",
        output_dir=tmp_path,
        validate=True,
        use_mock_llm=True,
    )
    assert code == 0
    world_model = _read_json(tmp_path / "world_model.json")
    audit = _read_json(tmp_path / "run_audit.json")
    assert world_model["episode_id"] == "local-explore-book-relocated"
    assert world_model["task_status"]["success"] is True
    assert audit["env"] == "official"
    assert audit["official_runtime_adapter"] is True
    assert audit["reference_used_for_generation"] is False
    assert (tmp_path / "episode_log.jsonl").exists()


def test_action_translator_rejects_unsupported_schema_action() -> None:
    translator = ActionTranslator()
    with pytest.raises(ActionTranslationError):
        translator.to_env_action("pick_up(book)", [{"name": "move"}])


def test_fake_official_artifacts_do_not_leak_local_absolute_paths(tmp_path: Path) -> None:
    code = run_official_with_adapter(
        adapter=FakeOfficialAdapter(),
        episode_id="local-explore-book-relocated",
        output_dir=tmp_path,
        validate=False,
        use_mock_llm=True,
    )
    assert code == 0
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [tmp_path / "world_model.json", tmp_path / "episode_log.jsonl", tmp_path / "run_audit.json"]
    )
    assert "C:\\Users" not in combined
    assert "/home/" not in combined


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
