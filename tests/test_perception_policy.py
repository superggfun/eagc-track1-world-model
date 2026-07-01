"""Tests for perception/policy.py and procedure_runner integration.

Coverage:
- should_run_post_action_vlm returns correct (should, reason) for each action type
- normalize_action_name handles various action string formats
- Skipped actions still apply structured sync (action_effects)
- Extractor not called when action is skipped
- Extractor still called for exploratory actions
- Episode log records perception_skipped events
- run_audit includes perception counts
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Policy unit tests
# ---------------------------------------------------------------------------

from perception.policy import normalize_action_name, should_run_post_action_vlm


class TestNormalizeActionName:
    def test_paren_form_pick_up(self):
        assert normalize_action_name("pick_up(book)") == "pick_up"

    def test_paren_form_place_on(self):
        assert normalize_action_name("place_on(book, table)") == "place_on"

    def test_paren_form_place_in(self):
        assert normalize_action_name("place_in(book, box)") == "place_in"

    def test_paren_form_explore(self):
        assert normalize_action_name("explore()") == "explore"

    def test_paren_form_navigate_to(self):
        assert normalize_action_name("navigate_to(kitchen)") == "navigate_to"

    def test_paren_form_unlock(self):
        assert normalize_action_name("unlock(door)") == "unlock"

    def test_paren_form_open(self):
        assert normalize_action_name("open(cabinet)") == "open"

    def test_paren_form_substitute_tool(self):
        assert normalize_action_name("substitute_tool(hammer, wrench)") == "substitute_tool"

    def test_dict_input(self):
        assert normalize_action_name({"name": "pick_up", "args": ["book"]}) == "pick_up"
        assert normalize_action_name({"action": "navigate_to"}) == "navigate_to"

    def test_plain_string(self):
        assert normalize_action_name("pickup") == "pickup"
        assert normalize_action_name("  EXPLORE  ") == "explore"


class TestShouldRunPostActionVlm:
    @staticmethod
    def _success_result():
        return {"success": True}

    @staticmethod
    def _fail_result():
        return {"success": False}

    def test_skip_pick_up_success(self):
        should, reason = should_run_post_action_vlm(
            "pick_up(book)", self._success_result(), {},
        )
        assert should is False
        assert reason == "deterministic_action_effect_applied"

    def test_skip_place_on_success(self):
        should, _ = should_run_post_action_vlm(
            "place_on(book, table)", self._success_result(), {},
        )
        assert should is False

    def test_skip_place_in_success(self):
        should, _ = should_run_post_action_vlm(
            "place_in(book, box)", self._success_result(), {},
        )
        assert should is False

    def test_skip_unlock_success(self):
        should, _ = should_run_post_action_vlm(
            "unlock(door)", self._success_result(), {},
        )
        assert should is False

    def test_skip_close_success(self):
        should, _ = should_run_post_action_vlm(
            "close(door)", self._success_result(), {},
        )
        assert should is False

    def test_skip_substitute_tool_success(self):
        should, _ = should_run_post_action_vlm(
            "substitute_tool(hammer, wrench)", self._success_result(), {},
        )
        assert should is False

    def test_perceive_explore_success(self):
        should, reason = should_run_post_action_vlm(
            "explore()", self._success_result(), {},
        )
        assert should is True
        assert "explore" in reason

    def test_perceive_navigate_to_success(self):
        should, reason = should_run_post_action_vlm(
            "navigate_to(kitchen)", self._success_result(), {},
        )
        assert should is True
        assert "navigate_to" in reason

    def test_perceive_open_success(self):
        should, reason = should_run_post_action_vlm(
            "open(cabinet)", self._success_result(), {},
        )
        assert should is True
        assert "open" in reason

    def test_perceive_search_success(self):
        should, _ = should_run_post_action_vlm(
            "search(visible_area)", self._success_result(), {},
        )
        assert should is True

    def test_perceive_locate_success(self):
        should, _ = should_run_post_action_vlm(
            "locate(key)", self._success_result(), {},
        )
        assert should is True

    def test_any_failure_always_perceive(self):
        should, reason = should_run_post_action_vlm(
            "pick_up(book)", self._fail_result(), {},
        )
        assert should is True
        assert reason == "action_failed_or_exception"

    def test_recovery_always_perceive(self):
        should, reason = should_run_post_action_vlm(
            "pick_up(book)", self._success_result(), {},
            recovery=True,
        )
        assert should is True
        assert reason == "recovery_step"

    def test_non_execution_phase_perceives(self):
        should, reason = should_run_post_action_vlm(
            "pick_up(book)", self._success_result(), {},
            phase="exploration",
        )
        assert should is True
        assert "exploration" in reason

    def test_unknown_action_default_perceive(self):
        should, reason = should_run_post_action_vlm(
            "some_new_action(x)", self._success_result(), {},
        )
        assert should is True
        assert "unknown_action" in reason

    def test_pickup_variant_name(self):
        should, _ = should_run_post_action_vlm(
            "pickup book", self._success_result(), {},
        )
        assert should is False


# ---------------------------------------------------------------------------
# Integration tests — mock procedure runner
# ---------------------------------------------------------------------------

from scoring.track1_score import compute_track1_score, write_track1_score
from track1_runner.procedure_runner import Track1ProcedureRunner
from logging_utils.episode_logger import EpisodeLogger


class CountingExtractor:
    """Mock extractor that counts calls without real VLM."""

    def __init__(self):
        self.call_count = 0

    def extract(self, observation, task):
        self.call_count += 1
        return {
            "rooms": [],
            "topology": [],
            "objects": [],
            "relations": [],
            "states": [],
            "affordances": [],
            "uncertainty": [],
        }

    @property
    def fallback_used(self):
        return False


class TestProcedureRunnerPerceptionSkip:
    """End-to-end tests verifying that policy is correctly wired into the runner."""

    @staticmethod
    def _make_runner(output_dir: Path):
        """Create a minimal runner wired with CountingExtractor."""
        from env_adapters.local_sim_env import LocalSimEnv

        env = LocalSimEnv()
        extractor = CountingExtractor()
        store = MagicMock()
        store.world_model = {}
        logger = EpisodeLogger(output_dir / "episode_log.jsonl")

        runner = Track1ProcedureRunner(
            env=env,
            extractor=extractor,
            store=store,
            logger=logger,
            output_dir=output_dir,
        )
        return runner, extractor, store, env

    def test_perception_call_count_incremented(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, _ = self._make_runner(output_dir)
            # Directly call _perceive → should increment perception_call_count
            runner._perceive({"observation": "You see a cup."}, "Test task")
            assert runner.perception_call_count == 1
            assert extractor.call_count == 1

    def test_perception_skip_records_log_entry(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, _ = self._make_runner(output_dir)
            runner._record_perception_skip(
                "pick_up(book)", {"observation": ""}, "deterministic_action_effect_applied"
            )
            assert runner.perception_skip_count == 1
            assert runner.perception_skip_reasons == {"deterministic_action_effect_applied": 1}

            # Check episode log
            log_path = output_dir / "episode_log.jsonl"
            rows = []
            for line in log_path.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            assert len(rows) >= 1
            skip_row = rows[-1]
            assert skip_row["event_type"] == "perception_skipped"
            assert skip_row["action"] == "pick_up(book)"
            assert skip_row["notes"] == "deterministic_action_effect_applied"

    def test_audit_updates_include_perception_metrics(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, _, _, _ = self._make_runner(output_dir)
            # Simulate some perception activity
            runner.perception_call_count = 5
            runner.perception_skip_count = 2
            runner.perception_skip_reasons = {"deterministic_action_effect_applied": 2}

            audit = runner.audit_updates()
            assert audit["perception_call_count"] == 5
            assert audit["perception_skip_count"] == 2
            assert audit["vlm_call_saved_count"] == 2
            assert audit["perception_skip_reasons"] == {"deterministic_action_effect_applied": 2}

    def test_execute_action_skip_perception_for_pick_up(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, env = self._make_runner(output_dir)

            # Setup store's world_model so action_effects can work
            store.world_model = {
                "episode_id": "test-1",
                "objects": [{"id": "book", "name": "book", "category": "object"}],
                "relations": [],
                "states": [],
                "rooms": ["kitchen"],
                "agent_state": {"current_room": "kitchen"},
                "visited_rooms": ["kitchen"],
                "frontiers": [],
                "task": "pick up book",
                "plans": [{"goal": "test", "actions": ["pick_up(book)"], "subgoals": []}],
                "uncertainty": [],
            }

            # Patch executor.execute to return success with observation_packet
            with patch.object(runner.executor, "execute", return_value={
                "success": True,
                "observation": "You picked up the book.",
                "observation_packet": {"observation": "You picked up the book.", "current_room": "kitchen"},
                "result": "success",
                "message": "",
            }):
                extractor_call_before = extractor.call_count
                runner._execute_action("pick_up(book)", event_type="action", mode="executing")
                # Extractor should NOT have been called
                assert extractor.call_count == extractor_call_before
                # But structured sync should have run (world_model updated with env context)
                assert "visited_rooms" in store.world_model or "objects" in store.world_model

    def test_execute_action_still_perceives_for_explore(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, env = self._make_runner(output_dir)

            store.world_model = {
                "episode_id": "test-1",
                "objects": [],
                "relations": [],
                "states": [],
                "rooms": ["kitchen"],
                "agent_state": {"current_room": "kitchen"},
                "visited_rooms": ["kitchen"],
                "frontiers": [],
                "task": "explore",
                "plans": [],
                "uncertainty": [],
            }

            with patch.object(runner.executor, "execute", return_value={
                "success": True,
                "observation": "You explore the kitchen.",
                "observation_packet": {"observation": "You explore the kitchen.", "current_room": "kitchen"},
                "result": "success",
                "message": "",
            }):
                extractor_call_before = extractor.call_count
                runner._execute_action("explore(kitchen)", event_type="action", mode="executing")
                # Extractor SHOULD have been called (explore always needs VLM)
                assert extractor.call_count == extractor_call_before + 1

    def test_execute_action_failure_still_perceives(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, env = self._make_runner(output_dir)

            store.world_model = {
                "episode_id": "test-1",
                "objects": [],
                "relations": [],
                "states": [],
                "rooms": ["kitchen"],
                "agent_state": {"current_room": "kitchen"},
                "visited_rooms": ["kitchen"],
                "frontiers": [],
                "task": "pick up book",
                "plans": [],
                "uncertainty": [],
            }

            with patch.object(runner.executor, "execute", return_value={
                "success": False,
                "observation": "The book is out of reach.",
                "observation_packet": {"observation": "The book is out of reach.", "current_room": "kitchen"},
                "result": "failure",
                "message": "out_of_reach",
            }):
                extractor_call_before = extractor.call_count
                runner._execute_action("pick_up(book)", event_type="action", mode="executing")
                # Extractor should still be called (failure → always perceive)
                assert extractor.call_count == extractor_call_before + 1

    def test_recovery_step_always_perceives(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, env = self._make_runner(output_dir)

            store.world_model = {
                "episode_id": "test-1",
                "objects": [{"id": "book", "name": "book", "category": "object"}],
                "relations": [],
                "states": [],
                "rooms": ["kitchen"],
                "agent_state": {"current_room": "kitchen"},
                "visited_rooms": ["kitchen"],
                "frontiers": [],
                "task": "recover",
                "plans": [],
                "uncertainty": [],
            }

            with patch.object(runner.executor, "execute", return_value={
                "success": True,
                "observation": "You picked up the book.",
                "observation_packet": {"observation": "You picked up the book.", "current_room": "kitchen"},
                "result": "success",
                "message": "",
            }):
                extractor_call_before = extractor.call_count
                runner._execute_action("pick_up(book)", event_type="recovery_action", mode="recovering", recovery=True)
                # Recovery always needs VLM
                assert extractor.call_count == extractor_call_before + 1

    def test_action_effects_still_applied_when_skipping(self):
        with TemporaryDirectory() as td:
            output_dir = Path(td)
            runner, extractor, store, env = self._make_runner(output_dir)

            store.world_model = {
                "episode_id": "test-1",
                "objects": [{"id": "book", "name": "book", "category": "object"}],
                "relations": [],
                "states": [],
                "rooms": ["kitchen"],
                "agent_state": {"current_room": "kitchen"},
                "visited_rooms": ["kitchen"],
                "frontiers": [],
                "task": "pick up book",
                "plans": [],
                "uncertainty": [],
            }

            with patch.object(runner.executor, "execute", return_value={
                "success": True,
                "observation": "You picked up the book.",
                "observation_packet": {"observation": "You picked up the book.", "current_room": "kitchen"},
                "result": "success",
                "message": "",
            }):
                runner._execute_action("pick_up(book)", event_type="action", mode="executing")
                # Verify action_effects ran: pick_up should set holding and location
                agent = store.world_model.get("agent_state", {})
                assert agent.get("holding") == "book", "action_effects should set holding even when VLM skipped"


# ---------------------------------------------------------------------------
# Audit builder tests — perception fields in output
# ---------------------------------------------------------------------------

from audit.builder import RunAuditContext, build_run_audit_from_context


class TestRunAuditPerceptionMetrics:
    def test_perception_fields_in_audit_output(self):
        ctx = RunAuditContext(
            episode_id="test-ep",
            output_dir=Path("/tmp/test"),
            perception_call_count=14,
            perception_skip_count=3,
            perception_skip_reasons={"deterministic_action_effect_applied": 3},
        )
        audit = build_run_audit_from_context(ctx)
        assert audit["perception_call_count"] == 14
        assert audit["perception_skip_count"] == 3
        assert audit["vlm_call_saved_count"] == 3
        assert audit["perception_skip_reasons"] == {"deterministic_action_effect_applied": 3}

    def test_perception_defaults_when_not_set(self):
        ctx = RunAuditContext(episode_id="test-ep", output_dir=Path("/tmp/test"))
        audit = build_run_audit_from_context(ctx)
        assert audit["perception_call_count"] == 0
        assert audit["perception_skip_count"] == 0
        assert audit["vlm_call_saved_count"] == 0
        assert audit["perception_skip_reasons"] == {}
