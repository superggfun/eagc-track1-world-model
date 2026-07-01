from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from harness.virtualhome_exploration import _build_audit, _collect_continuous_episode, _visual_topology_edges, run_replay
from infra.paths import PROJECT_ROOT
from planner.virtualhome_policy import PolicyContext, VirtualHomeExplorationPolicy
from validators.validate_virtualhome_exploration import validate_detailed


ROOMS = ["bathroom", "bedroom", "kitchen", "livingroom"]


def test_validator_fails_if_reference_used_for_generation_is_true(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    audit_path = output_dir / "run_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["reference_used_for_generation"] = True
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("reference_used_for_generation must be false" in error for error in summary["errors"])


def test_validator_fails_if_frame_order_edge_is_in_topology(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    world_model_path = output_dir / "world_model.json"
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    world_model["topology"]["edges"][0]["evidence_source"] = "frame_manifest_order"
    world_model_path.write_text(json.dumps(world_model, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("frame order edge" in error for error in summary["errors"])


def test_validator_fails_if_verified_topology_is_not_navigation(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    world_model_path = output_dir / "world_model.json"
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    world_model["topology"]["edges"][0]["evidence_source"] = "vlm_frame_extraction"
    world_model_path.write_text(json.dumps(world_model, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("verified topology edge" in error for error in summary["errors"])


def test_validator_fails_if_frame_file_is_not_real_image(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    (output_dir / "frames" / "frame_000.jpg").write_bytes(b"not-a-real-jpeg")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("not a valid image" in error for error in summary["errors"])


def test_validator_fails_if_vlm_model_call_metadata_is_missing(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    manifest_path = output_dir / "frame_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frames"][0]["visual_extraction"].pop("model_call", None)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("model_call" in error for error in summary["errors"])


def test_final_validator_fails_if_evidence_level_is_not_closed_loop(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    for name in ["coverage_report.json", "run_audit.json"]:
        path = output_dir / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["evidence_level"] = "visual_replay_diagnostic"
        payload["capture_mode"] = "keyframe_capture"
        payload["continuous_closed_loop"] = False
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("evidence_level=closed_loop_final_evidence" in error for error in summary["errors"])
    assert any("capture_mode=continuous_episode" in error for error in summary["errors"])


def test_final_validator_fails_if_room_recall_is_low(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    coverage_path = output_dir / "coverage_report.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["room_coverage"] = 0.5
    coverage["room_coverage_against_reference"] = 0.5
    coverage["comparison_room_recall"] = 0.5
    coverage_path.write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    comparison_path = output_dir / "comparison_report.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["rooms"]["recall"] = 0.5
    comparison["rooms"]["matched"] = ["bathroom", "bedroom"]
    comparison["rooms"]["missed"] = ["kitchen", "livingroom"]
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("room_coverage_against_reference" in error for error in summary["errors"])
    assert any("comparison_report.rooms.recall" in error for error in summary["errors"])


def test_final_validator_fails_if_rooms_visited_are_unknown_only(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    coverage_path = output_dir / "coverage_report.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage["rooms_visited"] = ["unknown"]
    coverage_path.write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("rooms_visited must include at least one non-unknown room" in error for error in summary["errors"])


def test_final_validator_fails_if_too_few_reference_rooms_are_matched(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)
    comparison_path = output_dir / "comparison_report.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["rooms"]["matched"] = ["bathroom"]
    comparison["rooms"]["missed"] = ["bedroom", "kitchen", "livingroom"]
    comparison["rooms"]["recall"] = 0.9
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    summary = validate_detailed(output_dir, final_submission=True)

    assert any("matched must include at least" in error for error in summary["errors"])


def test_visual_topology_edges_supports_vlm_from_to_schema() -> None:
    edges = _visual_topology_edges(
        [
            {
                "frame": "frames/frame_000.jpg",
                "step": 0,
                "room": "bedroom",
                "action": "look_around",
                "visual_extraction": {
                    "source": "vlm_frame_extraction",
                    "topology": [
                        {
                            "from": "bedroom",
                            "to": "hallway",
                            "relation": "connected_to",
                            "evidence": "visible doorway",
                            "confidence": 0.62,
                        }
                    ],
                },
            }
        ]
    )

    assert edges == [
        {
            "from": "bedroom",
            "to": "hallway",
            "relation": "connected_to",
            "status": "inferred",
            "evidence_source": "vlm_frame_extraction",
            "evidence_frames": ["frames/frame_000.jpg"],
            "action": "look_around",
            "confidence": 0.62,
            "evidence": "visible doorway",
        }
    ]


def test_visual_topology_edges_supports_legacy_room_frontiers_schema() -> None:
    edges = _visual_topology_edges(
        [
            {
                "frame": "frames/frame_001.jpg",
                "step": 1,
                "room": "bedroom",
                "action": "look_around",
                "visual_extraction": {
                    "source": "vlm_frame_extraction",
                    "topology": [
                        {
                            "room": "bedroom",
                            "visited": True,
                            "frontiers": ["doorway"],
                            "status": "observed",
                            "confidence": 0.57,
                        }
                    ],
                },
            }
        ]
    )

    assert edges == [
        {
            "from": "bedroom",
            "to": "unknown_frontier_doorway",
            "relation": "connected_to",
            "status": "inferred",
            "evidence_source": "visual_doorway_or_passage_cue",
            "evidence_frames": ["frames/frame_001.jpg"],
            "action": "look_around",
            "confidence": 0.57,
            "evidence": "visible frontier: doorway",
            "frontier": "doorway",
        }
    ]


def test_validator_warns_for_mock_and_fails_in_final_mode(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path, mode="mock_visual_extraction")

    smoke_summary = validate_detailed(output_dir)
    final_summary = validate_detailed(output_dir, final_submission=True)

    assert smoke_summary["errors"] == []
    assert any("mock_visual_extraction" in warning for warning in smoke_summary["warnings"])
    assert any("final-submission VirtualHome evidence must use" in error for error in final_summary["errors"])


def test_replay_validate_final_submission_uses_strict_validator(tmp_path: Path) -> None:
    output_dir = tmp_path / "virtualhome_replay_final_check"

    exit_code = run_replay(
        frames=PROJECT_ROOT / "assets" / "test_sequences" / "virtualhome_exploration" / "frames",
        manifest=PROJECT_ROOT / "assets" / "test_sequences" / "virtualhome_exploration" / "frame_manifest.json",
        output_dir=output_dir,
        validate=True,
        prediction_input_mode="mock_visual_extraction",
        final_submission=True,
    )

    audit = json.loads((output_dir / "run_audit.json").read_text(encoding="utf-8"))
    errors = audit.get("validation_status", {}).get("errors", [])
    assert exit_code == 1
    assert any("final-submission VirtualHome evidence must use" in error for error in errors)


def test_partial_diagnostic_audit_separates_artifact_and_evidence_success() -> None:
    coverage = {
        "evidence_level": "visual_replay_diagnostic",
        "world_model_source": "visual_observation_pipeline",
        "prediction_input_mode": "vlm_frame_extraction",
        "visual_extractor_mode": "vlm_frame_extraction",
        "capture_mode": "continuous_episode",
        "continuous_closed_loop": True,
        "synthetic_capture": False,
        "mock_extraction": False,
        "reference_model_source": "virtualhome_scene_graph_answer_key",
        "action_policy_source": "agent_policy",
        "action_decision_count": 5,
        "policy_action_decision_count": 5,
        "harness_fallback_count": 0,
        "harness_fallback_used": False,
        "policy_failure_count": 0,
        "policy_failure_closed": False,
        "action_grounding_mode": "observation_side_only",
        "grounding_attempt_count": 11,
        "grounded_action_count": 5,
        "ungrounded_intent_count": 6,
        "ungrounded_attempt_count": 6,
        "grounding_target_sources": ["visual_extraction"],
        "fallback_reasons": {},
        "insufficient_grounding": True,
        "final_status": "partial",
        "termination_reason": "insufficient_executable_action_grounding",
        "not_final_evidence": True,
        "rooms_visited": ["bedroom", "livingroom"],
        "room_coverage": 0.5,
        "frames_used": 6,
        "exploration_trace_length": 6,
        "verified_topology_edges": 0,
        "inferred_visual_topology_edges": 1,
        "inferred_sequence_edges": 1,
        "exploration_order_edges": 1,
        "scene_graph_diagnostic_edges": 0,
        "topology_source": "visual_observation_pipeline",
        "notes": "diagnostic partial evidence",
    }

    audit = _build_audit(
        live_run=True,
        live_runtime_connected=True,
        attach_existing=False,
        launch_attempted=True,
        runtime_connection={"connected": True},
        start_time="2026-06-30T00:00:00Z",
        duration_seconds=1.0,
        coverage=coverage,
        validation_summary={"passed": True, "errors": [], "warnings": []},
    )

    assert audit["success"] is True
    assert audit["artifact_validation_success"] is True
    assert audit["task_or_evidence_success"] is False
    assert audit["final_status"] == "partial"
    assert audit["insufficient_grounding"] is True
    assert audit["not_final_evidence"] is True
    assert audit["policy_action_decision_count"] == 5
    assert audit["grounding_attempt_count"] == 11
    assert audit["grounded_action_count"] == 5
    assert audit["ungrounded_attempt_count"] == 6


def test_replay_accepts_manifest_relative_frame_paths_from_sequence_root(tmp_path: Path) -> None:
    output_dir = tmp_path / "virtualhome_replay_sequence_root"

    exit_code = run_replay(
        frames=PROJECT_ROOT / "assets" / "test_sequences" / "virtualhome_exploration",
        manifest=PROJECT_ROOT / "assets" / "test_sequences" / "virtualhome_exploration" / "frame_manifest.json",
        output_dir=output_dir,
        validate=True,
        prediction_input_mode="mock_visual_extraction",
    )

    assert exit_code == 0
    assert (output_dir / "frames" / "frame_000.jpg").exists()
    audit = json.loads((output_dir / "run_audit.json").read_text(encoding="utf-8"))
    coverage = json.loads((output_dir / "coverage_report.json").read_text(encoding="utf-8"))
    assert audit["evidence_level"] == "mock_ci_smoke"
    assert audit["not_final_evidence"] is True
    assert audit["artifact_validation_success"] is True
    assert audit["task_or_evidence_success"] is False
    assert coverage["not_final_evidence"] is True
    assert coverage["artifact_validation_success"] is True
    assert coverage["task_or_evidence_success"] is False


def test_virtualhome_policy_prefers_observation_derived_navigation() -> None:
    policy = VirtualHomeExplorationPolicy()
    context = PolicyContext(
        step=1,
        task="explore",
        observation_text=json.dumps({"topology_cues": ["door"], "visible_objects": ["sofa"]}),
        frame_path="frames/frame_000.png",
        world_model={"rooms": [{"name": "bedroom"}]},
        recent_events=[],
        available_actions=[
            "<char0> [TurnLeft]",
            "<char0> [Walk] <door> (1)",
            "<char0> [Walk] <sofa> (1)",
        ],
    )

    decision = policy.decide(context)

    assert decision.source == "agent_policy"
    assert decision.name == "inspect_frontier"
    assert decision.target_label == "door"


def test_continuous_episode_logs_policy_and_bounded_fallback(tmp_path: Path) -> None:
    comm = _FakeVirtualHomeComm(fail_first_action=True)

    rows = _collect_continuous_episode(
        comm,
        output_dir=tmp_path,
        mode="mock_visual_extraction",
        max_steps=1,
        target_room_coverage=1.0,
    )

    assert len(rows) == 2
    assert rows[1]["initial_policy_decision"]["source"] == "agent_policy"
    assert rows[1]["policy_decision"]["source"] == "harness_fallback"
    assert rows[1]["fallback_events"]
    assert rows[1]["harness_fallback_used"] is True


def test_virtualhome_report_and_audit_are_final_submission_clean(tmp_path: Path) -> None:
    output_dir = _write_virtualhome_artifacts(tmp_path)

    summary = validate_detailed(output_dir, final_submission=True)
    report = (output_dir / "virtualhome_exploration_report.md").read_text(encoding="utf-8")
    audit_text = (output_dir / "run_audit.json").read_text(encoding="utf-8")

    assert summary["errors"] == []
    assert "## Prediction Input Mode" in report
    assert "prediction_input_mode: `vlm_frame_extraction`" in report
    assert "C:\\Users" not in audit_text
    assert "/home/" not in audit_text


def test_source_package_excludes_python_caches() -> None:
    from tools import package_source

    assert "__pycache__" in package_source.EXCLUDED_DIR_PARTS
    assert ".pyc" in package_source.EXCLUDED_SUFFIXES
    assert ".pyo" in package_source.EXCLUDED_SUFFIXES


def _write_virtualhome_artifacts(root: Path, *, mode: str = "vlm_frame_extraction", case_name: str = "virtualhome_case") -> Path:
    output_dir = root / case_name
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True)
    world_model_source = "manifest_action_trace_baseline" if mode == "manifest_action_trace" else "visual_observation_pipeline"
    final_like = mode == "vlm_frame_extraction"
    evidence_level = "closed_loop_final_evidence" if final_like else "mock_ci_smoke"
    capture_mode = "continuous_episode" if final_like else "mock"
    continuous_closed_loop = final_like
    live_runtime_connected = final_like
    virtualhome_live_run = final_like
    final_status = "success" if final_like else "partial"
    insufficient_grounding = not final_like
    not_final_evidence = not final_like
    grounded_action_count = 11 if final_like else 0
    ungrounded_intent_count = 0 if final_like else 11
    grounding_target_sources = ["current_observation_runtime_metadata"] if final_like else []
    manifest_rows = []
    objects = []
    relations = []
    evidence_trace = []
    for step in range(12):
        room = ROOMS[step // 3]
        frame = f"frames/frame_{step:03d}.jpg"
        _write_test_frame(output_dir / frame, step)
        object_name = f"{room}_object_{step % 3}"
        model_call = {
            "provider": "qwen_vllm_openai_compatible",
            "real_model_call": mode == "vlm_frame_extraction",
            "success": True,
            "parse_success": mode == "vlm_frame_extraction",
            "fallback_used": False,
            "input_mode": "vision" if mode == "vlm_frame_extraction" else None,
            "model": "test-vlm",
            "base_url": "http://127.0.0.1:8000/v1" if mode == "vlm_frame_extraction" else "mock://local",
            "image_path": frame,
            "qwen_call_count": step + 1 if mode == "vlm_frame_extraction" else 0,
            "qwen_call_success_count": step + 1 if mode == "vlm_frame_extraction" else 0,
            "qwen_call_failure_count": 0,
        }
        extraction = {
            "source": mode,
            "extractor_mode": mode,
            "mock": mode == "mock_visual_extraction",
            "synthetic": mode != "vlm_frame_extraction",
            "model_call": model_call,
            "objects": [{"id": f"{room}_{step}", "name": object_name, "room": room, "confidence": 0.72}],
            "relations": [],
            "topology": [],
            "uncertainty": [],
        }
        action_text = "observe_initial_state" if step == 0 else f"<char0> [Walk] <{room}> (1)"
        grounded_action = (
            {
                "intent": {
                    "name": "approach_visible_anchor",
                    "action": "approach_visible_anchor",
                    "target_label": room,
                    "reason": "Selected current-observation runtime target.",
                    "confidence": 0.72,
                    "source": "agent_policy",
                    "metadata": {"rank": "fixture_policy"},
                },
                "executable": True,
                "vh_script": action_text,
                "target_id": f"{room}_runtime_anchor",
                "target_label": room,
                "target_source": "current_observation_runtime_metadata",
                "failure_reason": None,
                "confidence": 0.82,
            }
            if step > 0
            else {}
        )
        grounding_events = (
            [
                {
                    "event_type": "action_grounding",
                    "step": step,
                    "intent": grounded_action["intent"],
                    "executable": True,
                    "vh_script": action_text,
                    "target_label": room,
                    "target_source": "current_observation_runtime_metadata",
                    "failure_reason": None,
                    "confidence": 0.82,
                }
            ]
            if step > 0
            else []
        )
        manifest_rows.append(
            {
                "frame": frame,
                "step": step,
                "room": room,
                "action": action_text,
                "camera_movement": "pan",
                "prediction_input_mode": mode,
                "frame_validation": {"valid_image": True, "width": 64, "height": 48, "format": "JPEG"},
                "visual_extraction": extraction,
                "available_actions": [f"<char0> [Walk] <{room}> (1)", "<char0> [TurnLeft]", "<char0> [TurnRight]"]
                if step > 0
                else [],
                "policy_decision": {
                    "action": f"<char0> [Walk] <{room}> (1)",
                    "reason": "Selected visible room/object anchor from observation-derived context.",
                    "confidence": 0.72,
                    "source": "agent_policy",
                    "metadata": {"rank": "fixture_policy"},
                }
                if step > 0
                else {},
                "initial_policy_decision": {
                    "name": "approach_visible_anchor",
                    "action": "approach_visible_anchor",
                    "target_label": room,
                    "reason": "Selected visible room/object anchor from observation-derived context.",
                    "confidence": 0.72,
                    "source": "agent_policy",
                    "metadata": {"rank": "fixture_policy"},
                }
                if step > 0
                else {},
                "grounded_action": grounded_action,
                "grounding_events": grounding_events,
                "fallback_events": [],
                "harness_fallback_used": False,
                "action_policy_source": "agent_policy" if step > 0 else "none",
                "action_result": {"success": True, "action": f"<char0> [Walk] <{room}> (1)"} if step > 0 else {"success": True},
            }
        )
        evidence_trace.append(
            {
                "frame": frame,
                "step": step,
                "room": room,
                "prediction_input_mode": mode,
                "visual_extraction": extraction,
                "reference_used_for_generation": False,
            }
        )
        object_id = f"obj_{room}_{step}"
        objects.append(
            {
                "id": object_id,
                "name": object_name,
                "category": "visual_observation",
                "location": {"room": room, "region": "visible_area", "support": "", "status": "known", "confidence": 0.72},
                "state": "observed",
                "confidence": 0.72,
                "source": mode,
                "prediction_input_mode": mode,
                "evidence_frames": [frame],
                "raw_mentions": [
                    {
                        "frame": frame,
                        "step": step,
                        "room": room,
                        "label": object_name,
                        "source": mode,
                        "prediction_input_mode": mode,
                        "reference_used_for_generation": False,
                    }
                ],
            }
        )
        relations.append(
            {
                "subject": object_id,
                "subject_label": object_name,
                "relation": "inside",
                "object": room,
                "object_label": room,
                "status": "active",
                "confidence": 0.72,
                "source": mode,
                "prediction_input_mode": mode,
                "evidence_frames": [frame],
            }
        )
    topology_edge = {
        "from": "bathroom",
        "to": "bedroom",
        "relation": "connected_to",
        "status": "verified",
        "evidence_source": "navigation_transition",
        "evidence_frames": ["frames/frame_002.jpg", "frames/frame_003.jpg"],
        "action": "walk_to(bedroom_anchor)",
        "confidence": 0.8,
    }
    world_model = {
        "episode_id": "virtualhome-multi-room-exploration",
        "source": world_model_source,
        "world_model_source": world_model_source,
        "prediction_input_mode": mode,
        "visual_extractor_mode": mode,
        "reference_used_for_generation": False,
        "official_score": False,
        "rooms": [{"id": room, "name": room, "category": "room"} for room in ROOMS],
        "topology": {
            "nodes": [{"room": room, "node_type": "room", "visited": True} for room in ROOMS],
            "edges": [topology_edge],
            "topology_source": world_model_source,
        },
        "room_connectivity": [],
        "exploration_trace": evidence_trace,
        "exploration_order_edges": [
            {
                "from": "bathroom",
                "to": "bedroom",
                "relation": "visited_after",
                "status": "inferred_from_sequence",
                "evidence_source": "frame_manifest_order",
                "evidence_frames": ["frames/frame_002.jpg", "frames/frame_003.jpg"],
                "action": "manifest order only",
                "confidence": 0.35,
            }
        ],
        "visited_rooms": ROOMS,
        "objects": objects,
        "relations": relations,
        "states": [],
        "affordances": [],
        "uncertainty": [],
        "evidence_trace": evidence_trace,
    }
    coverage = {
        "source": "VirtualHome replay from exported keyframes and frame_manifest.json",
        "evidence_level": evidence_level,
        "official_score": False,
        "world_model_source": world_model_source,
        "prediction_input_mode": mode,
        "visual_extractor_mode": mode,
        "capture_mode": capture_mode,
        "continuous_closed_loop": continuous_closed_loop,
        "live_runtime_connected": live_runtime_connected,
        "synthetic_capture": False,
        "mock_extraction": mode == "mock_visual_extraction",
        "reference_model_source": "virtualhome_scene_graph_answer_key",
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "action_policy_source": "agent_policy" if final_like else "none",
        "action_decision_count": 11 if final_like else 0,
        "policy_action_decision_count": 11 if final_like else 0,
        "harness_fallback_count": 0,
        "harness_fallback_used": False,
        "policy_failure_count": 0,
        "policy_failure_closed": False,
        "action_grounding_mode": "observation_side_only",
        "grounding_attempt_count": 11,
        "grounded_action_count": grounded_action_count,
        "ungrounded_intent_count": ungrounded_intent_count,
        "ungrounded_attempt_count": ungrounded_intent_count,
        "grounding_target_sources": grounding_target_sources,
        "fallback_reasons": [],
        "insufficient_grounding": insufficient_grounding,
        "final_status": final_status,
        "not_final_evidence": not_final_evidence,
        "rooms_expected": ROOMS,
        "predicted_rooms": ROOMS,
        "rooms_visited": ROOMS,
        "reference_rooms": ROOMS,
        "room_coverage": 1.0,
        "room_coverage_against_reference": 1.0,
        "comparison_room_recall": 1.0,
        "exploration_trace_length": 12,
        "frames_used": 12,
        "objects_detected": len(objects),
        "relations_detected": len(relations),
        "topology_edges": 1,
        "predicted_topology_edges": 1,
        "reference_topology_edges": 1,
        "verified_topology_edges": 1,
        "inferred_visual_topology_edges": 0,
        "inferred_sequence_edges": 1,
        "exploration_order_edges": 1,
        "scene_graph_diagnostic_edges": 0,
        "topology_source": world_model_source,
        "topology_precision": 1.0,
        "topology_recall": 1.0,
        "validation_passed": True,
        "notes": "Local evidence only; official_score=false.",
    }
    audit = {
        "start_time": "2026-06-30T00:00:00Z",
        "end_time": "2026-06-30T00:00:01Z",
        "duration_seconds": 1.0,
        "episode_id": "virtualhome-multi-room-exploration",
        "env": "virtualhome_live" if final_like else "virtualhome_replay",
        "success": True,
        "artifact_validation_success": True,
        "task_or_evidence_success": final_like,
        "virtualhome_live_run": virtualhome_live_run,
        "live_runtime_connected": live_runtime_connected,
        "launch_attempted": False,
        "attach_existing": final_like,
        "runtime_connection": {"connected": True, "attach_existing": True, "port": 8080} if final_like else {},
        "evidence_level": evidence_level,
        "official_score": False,
        "world_model_source": world_model_source,
        "prediction_input_mode": mode,
        "visual_extractor_mode": mode,
        "capture_mode": capture_mode,
        "continuous_closed_loop": continuous_closed_loop,
        "synthetic_capture": False,
        "mock_extraction": mode == "mock_visual_extraction",
        "reference_model_source": "virtualhome_scene_graph_answer_key",
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "action_policy_source": "agent_policy" if final_like else "none",
        "action_decision_count": 11 if final_like else 0,
        "harness_fallback_count": 0,
        "harness_fallback_used": False,
        "policy_failure_count": 0,
        "policy_failure_closed": False,
        "action_grounding_mode": "observation_side_only",
        "policy_action_decision_count": 11 if final_like else 0,
        "grounding_attempt_count": 11,
        "grounded_action_count": grounded_action_count,
        "ungrounded_intent_count": ungrounded_intent_count,
        "ungrounded_attempt_count": ungrounded_intent_count,
        "grounding_target_sources": grounding_target_sources,
        "fallback_reasons": [],
        "insufficient_grounding": insufficient_grounding,
        "final_status": final_status,
        "not_final_evidence": not_final_evidence,
        "rooms_visited_count": len(ROOMS),
        "room_coverage": 1.0,
        "frames_used": 12,
        "exploration_trace_length": 12,
        "verified_topology_edges": 1,
        "inferred_visual_topology_edges": 0,
        "inferred_sequence_edges": 1,
        "exploration_order_edges": 1,
        "scene_graph_diagnostic_edges": 0,
        "topology_source": world_model_source,
        "topology_notes": "Local evidence only.",
        "world_model_path": "world_model.json",
        "reference_world_model_path": "reference_world_model.json",
        "comparison_report_path": "comparison_report.json",
        "episode_log_path": "episode_log.jsonl",
        "coverage_report_path": "coverage_report.json",
        "frame_manifest_path": "frame_manifest.json",
        "errors": [],
        "warnings": [],
    }
    reference = {
        "episode_id": "virtualhome-multi-room-exploration-reference",
        "source": "virtualhome_scene_graph_answer_key",
        "official_score": False,
        "reference_model": True,
        "used_for_generation": False,
        "used_for_validation": True,
        "used_for_prediction_generation": False,
        "rooms": ROOMS,
        "objects": [],
        "relations": [],
        "topology": {"nodes": [], "edges": [topology_edge], "topology_source": "scene_graph_diagnostic_answer_key"},
    }
    comparison = {
        "source": "prediction_vs_reference_comparison",
        "official_score": False,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "rooms": {"precision": 1.0, "recall": 1.0, "matched": ROOMS, "missed": [], "spurious": [], "reference": ROOMS},
        "objects": {"precision": 1.0, "recall": 1.0, "matched": [], "missed": [], "spurious": []},
        "relations": {"precision": 1.0, "recall": 1.0, "matched": [], "missed": [], "spurious": []},
        "topology": {"precision": 1.0, "recall": 1.0, "matched": ["bathroom|bedroom"], "missed": [], "spurious": []},
    }
    dedup = {
        "raw_object_mentions": len(objects),
        "unique_objects": len(objects),
        "raw_relation_mentions": len(relations),
        "unique_relations": len(relations),
        "merged_object_clusters": [],
        "alias_merges": [],
        "objects_by_room": {room: 3 for room in ROOMS},
        "active_relations": len(relations),
        "stale_relations": 0,
        "warnings": [],
    }
    _write_json(output_dir / "world_model.json", world_model)
    _write_json(output_dir / "frame_manifest.json", {"frames": manifest_rows})
    _write_json(output_dir / "coverage_report.json", coverage)
    _write_json(output_dir / "run_audit.json", audit)
    _write_json(output_dir / "reference_world_model.json", reference)
    _write_json(output_dir / "comparison_report.json", comparison)
    _write_json(output_dir / "dedup_report.json", dedup)
    _write_json(output_dir / "visual_task_result.json", {"status": "complete"})
    if mode == "vlm_frame_extraction":
        (output_dir / "qwen_calls.jsonl").write_text(
            "\n".join(
                json.dumps(
                    {
                        "timestamp": "2026-06-30T00:00:00Z",
                        "model": "test-vlm",
                        "base_url": "http://127.0.0.1:8000/v1",
                        "prompt_chars": 100,
                        "prompt_summary": "user:text:100;images:1",
                        "max_tokens": 1024,
                        "temperature": 0.1,
                        "latency_seconds": 0.01,
                        "success": True,
                        "error_message": "",
                    }
                )
                for _ in manifest_rows
            )
            + "\n",
            encoding="utf-8",
        )
    (output_dir / "episode_log.jsonl").write_text(json.dumps({"event_type": "frame_observation"}) + "\n", encoding="utf-8")
    (output_dir / "virtualhome_exploration_report.md").write_text(
        "## Prediction Input Mode\n\n- prediction_input_mode: `vlm_frame_extraction`\n",
        encoding="utf-8",
    )
    return output_dir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_test_frame(path: Path, step: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color = ((40 + step * 17) % 255, (90 + step * 11) % 255, (140 + step * 7) % 255)
    image = Image.new("RGB", (64, 48), color=color)
    image.save(path, format="JPEG", quality=80)


class _FakeVirtualHomeComm:
    def __init__(self, *, fail_first_action: bool = False) -> None:
        self.fail_first_action = fail_first_action
        self.action_calls = 0
        self.frame_count = 0

    def camera_count(self) -> tuple[bool, int]:
        return True, 1

    def camera_image(self, indexes: list[int], mode: str = "normal", image_width: int = 640, image_height: int = 480):
        self.frame_count += 1
        image = Image.new("RGB", (64, 48), color=(20 + self.frame_count, 80, 130))
        return True, [image]

    def render_script(self, script: list[str], **kwargs):
        self.action_calls += 1
        if self.fail_first_action and self.action_calls == 1:
            return False, {"message": "simulated action failure"}
        return True, {"script": script, "kwargs": kwargs}
