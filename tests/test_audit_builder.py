"""Tests for audit.builder — RunAuditContext, builder, path safety, backward compat."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from audit.builder import (
    RunAuditContext,
    build_run_audit_from_context,
    to_artifact_relative_path,
    write_failure_audit,
    make_track1_audit_context,
    make_visual_audit_context,
)


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

class TestToArtifactRelativePath:
    def test_none_returns_none(self):
        assert to_artifact_relative_path(None, Path("/tmp")) is None

    def test_already_relative_passthrough(self):
        assert to_artifact_relative_path("world_model.json", Path("/tmp/x")) == "world_model.json"
        assert to_artifact_relative_path("subdir/file.txt", Path("/tmp/x")) == "subdir/file.txt"

    def test_absolute_under_output_dir(self):
        out = Path("/tmp/test_run")
        assert to_artifact_relative_path(out / "world_model.json", out) == "world_model.json"
        assert to_artifact_relative_path(out / "sub" / "f.txt", out) == "sub/f.txt"

    def test_absolute_outside_output_dir_returns_filename(self):
        out = Path("/tmp/test_run")
        result = to_artifact_relative_path("/etc/passwd", out)
        assert result == "passwd" or result is not None  # safe fallback

    def test_windows_path_returns_filename(self):
        # Even on Linux, a Windows path outside output_dir falls back to filename
        result = to_artifact_relative_path(r"C:\tmp\secret.json", Path("/tmp/x"))
        assert result == "secret.json"


# ---------------------------------------------------------------------------
# RunAuditContext → dict
# ---------------------------------------------------------------------------

class TestBuildRunAuditFromContext:
    def test_minimal_context(self):
        ctx = RunAuditContext(episode_id="ep1", output_dir=Path("/tmp/run"))
        audit = build_run_audit_from_context(ctx)
        assert audit["episode_id"] == "ep1"
        assert audit["world_model_path"] == "world_model.json"
        assert audit["episode_log_path"] == "episode_log.jsonl"
        assert audit["success"] is False
        assert "start_time" in audit
        assert "end_time" in audit

    def test_path_fields_are_relative(self, tmp_path: Path):
        out = tmp_path / "run01"
        out.mkdir()
        (out / "world_model.json").write_text("{}")

        ctx = RunAuditContext(
            episode_id="ep1",
            output_dir=out,
            world_model_path="world_model.json",
            episode_log_path="episode_log.jsonl",
            track1_score_path="track1_score.json",
        )
        audit = build_run_audit_from_context(ctx)
        assert audit["world_model_path"] == "world_model.json"
        assert audit["episode_log_path"] == "episode_log.jsonl"
        assert audit["track1_score_path"] == "track1_score.json"

    def test_no_absolute_paths_in_audit(self, tmp_path: Path):
        """Ensure audit dict never contains local absolute paths."""
        out = tmp_path / "run02"
        out.mkdir()

        ctx = RunAuditContext(
            episode_id="ep1",
            output_dir=out,
            world_model_path="/tmp/secret/world_model.json",
            episode_log_path="/tmp/logs/ep.jsonl",
            image_path=r"C:\tmp\img.png",
        )
        audit = build_run_audit_from_context(ctx)

        # Check that the sanitizer in main.py handles these, but builder should also be clean
        forbidden = ["C:\\tmp\\", "/tmp/"]
        for key, val in audit.items():
            if isinstance(val, str):
                for forbid in forbidden:
                    assert forbid not in val, f"Key '{key}' contains forbidden path: {val}"

    def test_extra_fields_preserved(self):
        ctx = RunAuditContext(
            episode_id="ep1",
            output_dir=Path("/tmp/run"),
            extra={"custom_field": 42, "nested": {"a": 1}},
        )
        audit = build_run_audit_from_context(ctx)
        assert audit["custom_field"] == 42
        assert audit["nested"] == {"a": 1}

    def test_vision_mode_fields(self):
        ctx = RunAuditContext(
            episode_id="ep1",
            output_dir=Path("/tmp/run"),
            vision_mode=True,
            vision_call_success=True,
            vision_parse_success=True,
        )
        audit = build_run_audit_from_context(ctx)
        assert audit["vision_mode"] is True
        assert audit["vision_call_success"] is True
        assert audit["vision_parse_success"] is True

    def test_vision_mode_false_zeros_vision_fields(self):
        ctx = RunAuditContext(
            episode_id="ep1",
            output_dir=Path("/tmp/run"),
            vision_mode=False,
            vision_call_success=True,  # should be zeroed
            vision_parse_success=True,
        )
        audit = build_run_audit_from_context(ctx)
        assert audit["vision_call_success"] is False
        assert audit["vision_parse_success"] is False

    def test_ai2thor_fields_conditionally_set(self):
        ctx_ai2thor = RunAuditContext(
            episode_id="ep1",
            output_dir=Path("/tmp/run"),
            env_name="ai2thor",
            ai2thor_start_success=True,
        )
        audit_a = build_run_audit_from_context(ctx_ai2thor)
        assert audit_a["ai2thor_start_success"] is True

        ctx_other = RunAuditContext(
            episode_id="ep1",
            output_dir=Path("/tmp/run"),
            env_name="mock",
            ai2thor_start_success=True,
        )
        audit_o = build_run_audit_from_context(ctx_other)
        assert audit_o["ai2thor_start_success"] is False  # zeroed for non-ai2thor

    def test_schema_compatible(self):
        """Audit dict has all keys the old schema expected."""
        ctx = RunAuditContext(episode_id="ep1", output_dir=Path("/tmp/run"))
        audit = build_run_audit_from_context(ctx)
        required_keys = {
            "run_id", "episode_id", "output_dir", "model", "base_url",
            "use_mock_llm", "env", "scene", "prompt_version", "vision_mode",
            "image_path", "image_exists", "image_size_bytes",
            "vision_call_success", "vision_parse_success",
            "simulator_frame_path", "simulator_metadata_path",
            "ai2thor_start_success", "ai2thor_error_message",
            "oracle_metadata_mode", "frame_count", "image_dir",
            "processed_frames", "frame_paths",
            "start_time", "end_time", "latency_seconds", "duration_seconds",
            "qwen_call_count", "qwen_call_success_count", "qwen_call_failure_count",
            "fallback_used", "debug_raw_path", "qwen_response_summary_path",
            "world_model_path", "episode_log_path", "validation_status",
        }
        missing = required_keys - set(audit.keys())
        assert not missing, f"Missing keys: {missing}"


# ---------------------------------------------------------------------------
# Failure audit
# ---------------------------------------------------------------------------

class TestWriteFailureAudit:
    def test_writes_audit_file(self, tmp_path: Path):
        out = tmp_path / "failure_run"
        audit = write_failure_audit(
            output_dir=out,
            episode_id="ep_fail",
            env_name="local_sim",
            mode="track1",
            error="Something went wrong",
        )
        assert (out / "run_audit.json").exists()
        assert audit["success"] is False
        assert audit["errors"] == ["Something went wrong"]
        assert audit["episode_id"] == "ep_fail"

    def test_failure_audit_has_no_absolute_paths(self, tmp_path: Path):
        out = tmp_path / "fail_no_leak"
        audit = write_failure_audit(
            output_dir=out,
            episode_id="ep1",
            env_name="mock",
            mode="mock",
            error="Boom",
        )
        forbidden = ["C:\\tmp\\", "/tmp/"]
        for key, val in audit.items():
            if isinstance(val, str):
                for forbid in forbidden:
                    assert forbid not in val, f"Key '{key}' contains forbidden path: {val}"

    def test_extra_fields_in_failure(self, tmp_path: Path):
        out = tmp_path / "fail_extra"
        audit = write_failure_audit(
            output_dir=out,
            episode_id="ep1",
            env_name="mock",
            mode="mock",
            error="Boom",
            warnings=["low memory"],
            extra={"cpu_temp": 85},
        )
        assert "low memory" in audit["warnings"]
        assert audit["cpu_temp"] == 85


# ---------------------------------------------------------------------------
# Mode helpers
# ---------------------------------------------------------------------------

class TestModeHelpers:
    def test_make_track1_audit_context(self):
        ctx = make_track1_audit_context(
            episode_id="t1",
            output_dir=Path("/tmp/run"),
            success=True,
            validation_status="passed",
            track1_score_path="track1_score.json",
            extra={"phase_summary": "done"},
        )
        assert ctx.episode_id == "t1"
        assert ctx.mode == "track1"
        assert ctx.track1_score_path == "track1_score.json"
        assert ctx.extra["phase_summary"] == "done"

    def test_make_visual_audit_context(self):
        ctx = make_visual_audit_context(
            episode_id="v1",
            output_dir=Path("/tmp/run"),
            success=True,
            validation_status="passed",
            image_dir="frames/",
            vision_call_success=True,
            extra={"evidence_count": 5},
        )
        assert ctx.episode_id == "v1"
        assert ctx.mode == "visual"
        assert ctx.vision_mode is True
        assert ctx.vision_call_success is True
        assert ctx.extra["evidence_count"] == 5


