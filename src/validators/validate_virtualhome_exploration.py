from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from infra.paths import PROJECT_ROOT


LOCAL_ABSOLUTE_PATTERNS = [
    re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|Windows|ProgramData|Temp|tmp)[\\/]", re.IGNORECASE),
    re.compile(r"/(?:Users|home|mnt/data|tmp)/"),
]
VISUAL_MODES = {"vlm_frame_extraction", "mock_visual_extraction"}
ALL_MODES = {"vlm_frame_extraction", "mock_visual_extraction", "manifest_action_trace"}
EVIDENCE_LEVELS = {
    "closed_loop_final_evidence",
    "visual_replay_diagnostic",
    "mock_ci_smoke",
    "scene_graph_reference_only",
}
FINAL_ROOM_RECALL_THRESHOLD = 0.8
MIN_FINAL_REFERENCE_ROOM_MATCHES = 2
ALLOWED_FINAL_TARGET_SOURCES = {
    "current_observation_runtime_metadata",
    "previously_verified_executable_target",
    "safe_scan_action",
}
DISALLOWED_FINAL_TARGET_SOURCES = {
    "environment_graph",
    "reference_world_model",
    "scene_graph_answer_key",
    "hardcoded_room_object_table",
    "mock_alias_map",
}


def validate(output_dir: str | Path, *, final_submission: bool = False) -> list[str]:
    return validate_detailed(output_dir, final_submission=final_submission)["errors"]


def validate_detailed(output_dir: str | Path, *, final_submission: bool = False) -> dict[str, list[str]]:
    root = _resolve_output_dir(output_dir)
    errors: list[str] = []
    warnings: list[str] = []
    world_model = _read_json(root / "world_model.json", "world_model.json", errors)
    rows = _read_jsonl(root / "episode_log.jsonl", errors)
    audit = _read_json(root / "run_audit.json", "run_audit.json", errors)
    manifest_payload = _read_json(root / "frame_manifest.json", "frame_manifest.json", errors)
    coverage = _read_json(root / "coverage_report.json", "coverage_report.json", errors)
    dedup_report = _read_json(root / "dedup_report.json", "dedup_report.json", errors)
    reference_model = _read_json(root / "reference_world_model.json", "reference_world_model.json", errors)
    comparison_report = _read_json(root / "comparison_report.json", "comparison_report.json", errors)
    _read_json(root / "visual_task_result.json", "visual_task_result.json", errors)

    mode = _prediction_input_mode(world_model, audit, coverage)
    if mode not in ALL_MODES:
        errors.append(f"prediction_input_mode must be one of {sorted(ALL_MODES)}, got {mode!r}.")
    if final_submission and mode != "vlm_frame_extraction":
        errors.append(f"final-submission VirtualHome evidence must use prediction_input_mode=vlm_frame_extraction; got {mode}.")
    if mode == "mock_visual_extraction":
        warnings.append("prediction_input_mode=mock_visual_extraction uses deterministic mock frame extraction, not real VLM scoring.")
    if mode == "manifest_action_trace":
        warnings.append("prediction_input_mode=manifest_action_trace is a baseline and must not be described as visual-only evidence.")

    frames = _manifest_rows(manifest_payload, errors)
    strict_visual_mode = mode in VISUAL_MODES
    for index, row in enumerate(frames):
        frame = str(row.get("frame") or "")
        if not frame:
            errors.append(f"frame_manifest frame {index} missing frame field.")
        elif Path(frame).is_absolute() or _contains_local_absolute_path(frame):
            errors.append(f"frame_manifest frame {index} uses absolute/local path: {frame}")
        elif not (root / frame).exists():
            errors.append(f"frame_manifest references missing frame: {frame}")
        elif final_submission or strict_visual_mode:
            image_error = _validate_image_file(root / frame)
            if image_error:
                errors.append(f"frame_manifest frame {index} is not a valid image: {image_error}")
        if not str(row.get("room") or "").strip():
            errors.append(f"frame_manifest frame {index} missing room.")
        if strict_visual_mode:
            if "expected_visible_objects" in row:
                errors.append(f"frame_manifest frame {index} must not carry expected_visible_objects in strict visual mode.")
            extraction = row.get("visual_extraction")
            if not isinstance(extraction, dict):
                errors.append(f"frame_manifest frame {index} missing visual_extraction for strict visual mode.")
                continue
            if extraction.get("source") != mode:
                errors.append(f"frame_manifest frame {index} visual_extraction.source must be {mode}.")
            objects = extraction.get("objects")
            if not isinstance(objects, list):
                errors.append(f"frame_manifest frame {index} visual_extraction.objects must be a list.")
            if mode == "vlm_frame_extraction" and isinstance(objects, list) and not objects and not extraction.get("uncertainty"):
                errors.append(f"frame_manifest frame {index} has no VLM objects and no uncertainty entry explaining the empty extraction.")
            if mode == "vlm_frame_extraction" and extraction.get("mock") is True:
                errors.append(f"frame_manifest frame {index} uses mock extraction while prediction_input_mode=vlm_frame_extraction.")
            if mode == "vlm_frame_extraction" and extraction.get("synthetic") is True:
                errors.append(f"frame_manifest frame {index} uses synthetic extraction while prediction_input_mode=vlm_frame_extraction.")
            if mode == "vlm_frame_extraction":
                _validate_vlm_model_call(extraction.get("model_call"), frame, index, errors, final_submission=final_submission)

    rooms_from_manifest = {str(row.get("room")) for row in frames if str(row.get("room") or "").strip()}
    _validate_world_model(world_model, mode, rooms_from_manifest, errors, warnings)
    _validate_coverage(coverage, mode, rooms_from_manifest, errors, warnings, final_submission=final_submission)
    _validate_audit(audit, mode, errors, warnings, final_submission=final_submission)
    _validate_dedup_report(dedup_report, errors, warnings)
    _validate_reference_model(reference_model, errors)
    _validate_comparison_report(comparison_report, errors, warnings, final_submission=final_submission)
    if final_submission and mode == "vlm_frame_extraction":
        _validate_qwen_call_log(root / "qwen_calls.jsonl", len(frames), errors)
    _validate_action_grounding(frames, rows, coverage, audit, errors, warnings, final_submission=final_submission)
    if not rows:
        errors.append("episode_log.jsonl must contain at least one JSON record.")

    for label, value in [
        ("world_model", world_model),
        ("episode_log", rows),
        ("run_audit", audit),
        ("frame_manifest", manifest_payload),
        ("coverage_report", coverage),
        ("dedup_report", dedup_report),
        ("reference_world_model", reference_model),
        ("comparison_report", comparison_report),
    ]:
        for key_path, offender in _absolute_path_values(value):
            errors.append(f"{label} contains local absolute path at {key_path}: {offender}")
    return {"errors": errors, "warnings": warnings}


def _validate_world_model(
    world_model: dict[str, Any],
    mode: str,
    rooms_from_manifest: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(world_model, dict):
        return
    if world_model.get("source") == "virtualhome_scene_graph_answer_key" or world_model.get("world_model_source") == "virtualhome_scene_graph_answer_key":
        errors.append("predicted world_model.json must not be generated from environment_graph/scene graph answer key.")
    if world_model.get("reference_used_for_generation") is not False:
        errors.append("predicted world_model.json must set reference_used_for_generation=false.")
    expected_source = "manifest_action_trace_baseline" if mode == "manifest_action_trace" else "visual_observation_pipeline"
    if world_model.get("world_model_source") != expected_source:
        errors.append(f"world_model.world_model_source must be {expected_source} for prediction_input_mode={mode}.")
    if world_model.get("prediction_input_mode") not in {mode, None}:
        errors.append("world_model.prediction_input_mode disagrees with selected mode.")
    topology = world_model.get("topology")
    topology_edges = _topology_edges(topology, errors)
    if not world_model.get("rooms") and not (isinstance(topology, dict) and topology.get("nodes")):
        errors.append("world_model must contain rooms/topology.")
    _validate_topology_edges(topology_edges, errors, warnings)
    if not topology_edges:
        warnings.append("Predicted topology has zero topology.edges; only room coverage/exploration trace is available.")
    if not isinstance(world_model.get("objects"), list) or not world_model.get("objects"):
        errors.append("canonical world_model must contain a non-empty objects list.")
    if not isinstance(world_model.get("relations"), list) or not world_model.get("relations"):
        errors.append("canonical world_model must contain a non-empty relations list.")
    _validate_exploration_order_edges(world_model.get("exploration_order_edges", []), errors)
    _validate_room_connectivity(world_model.get("room_connectivity", []), errors)
    evidence_trace = world_model.get("evidence_trace", [])
    if not isinstance(evidence_trace, list):
        errors.append("world_model.evidence_trace must be a list.")
        evidence_trace = []
    evidence_rooms = {str(row.get("room")) for row in evidence_trace if isinstance(row, dict)}
    for room in rooms_from_manifest:
        if room not in evidence_rooms:
            errors.append(f"visited room lacks observation evidence in world_model.evidence_trace: {room}")
    if mode == "vlm_frame_extraction":
        for object_index, obj in enumerate(world_model.get("objects", [])):
            if not isinstance(obj, dict):
                continue
            for mention in obj.get("raw_mentions", []) if isinstance(obj.get("raw_mentions"), list) else []:
                source = mention.get("source") if isinstance(mention, dict) else ""
                if source in {"manifest_action_trace", "virtualhome_scene_graph_answer_key", "frame_manifest", "expected_visible_objects"}:
                    errors.append(f"world_model.objects[{object_index}] raw mention uses forbidden source in VLM mode: {source}")


def _validate_coverage(
    coverage: dict[str, Any],
    mode: str,
    rooms_from_manifest: set[str],
    errors: list[str],
    warnings: list[str],
    *,
    final_submission: bool,
) -> None:
    required = [
        "evidence_level",
        "world_model_source",
        "prediction_input_mode",
        "visual_extractor_mode",
        "capture_mode",
        "continuous_closed_loop",
        "live_runtime_connected",
        "synthetic_capture",
        "mock_extraction",
        "reference_model_source",
        "reference_used_for_generation",
        "reference_used_for_validation",
        "action_policy_source",
        "action_decision_count",
        "harness_fallback_count",
        "harness_fallback_used",
        "policy_failure_count",
        "policy_failure_closed",
        "action_grounding_mode",
        "grounded_action_count",
        "ungrounded_intent_count",
        "grounding_target_sources",
        "fallback_reasons",
        "insufficient_grounding",
        "final_status",
        "not_final_evidence",
        "rooms_visited",
        "reference_rooms",
        "predicted_rooms",
        "room_coverage",
        "room_coverage_against_reference",
        "comparison_room_recall",
        "frames_used",
        "exploration_trace_length",
        "predicted_topology_edges",
        "reference_topology_edges",
        "verified_topology_edges",
        "inferred_visual_topology_edges",
        "inferred_sequence_edges",
        "exploration_order_edges",
        "scene_graph_diagnostic_edges",
        "topology_source",
        "topology_precision",
        "topology_recall",
        "official_score",
    ]
    for key in required:
        if key not in coverage:
            errors.append(f"coverage_report.json missing required field: {key}")
    evidence_level = str(coverage.get("evidence_level") or "")
    if evidence_level not in EVIDENCE_LEVELS:
        errors.append(f"coverage_report.evidence_level must be one of {sorted(EVIDENCE_LEVELS)}, got {evidence_level!r}.")
    if mode == "mock_visual_extraction" and evidence_level != "mock_ci_smoke":
        errors.append("mock_visual_extraction coverage must use evidence_level=mock_ci_smoke.")
    if coverage.get("capture_mode") in {"replay", "keyframe_capture", "mock"} and evidence_level == "closed_loop_final_evidence":
        errors.append("replay/keyframe/mock coverage must not use evidence_level=closed_loop_final_evidence.")
    if coverage.get("reference_used_for_generation") is not False:
        errors.append("coverage_report.reference_used_for_generation must be false.")
    if coverage.get("reference_used_for_validation") is not True:
        errors.append("coverage_report.reference_used_for_validation must be true.")
    if coverage.get("official_score") is not False:
        errors.append("coverage_report.official_score must be false.")
    if final_submission and coverage.get("synthetic_capture") is True:
        errors.append("final-submission VirtualHome evidence must not use synthetic_capture=true.")
    if final_submission and coverage.get("mock_extraction") is True:
        errors.append("final-submission VirtualHome evidence must not use mock_extraction=true.")
    if final_submission:
        if coverage.get("action_grounding_mode") != "observation_side_only":
            errors.append("final-submission coverage_report.action_grounding_mode must be observation_side_only.")
        if coverage.get("final_status") != "success":
            errors.append("final-submission VirtualHome evidence must have final_status=success.")
        if coverage.get("insufficient_grounding") is True:
            errors.append("final-submission VirtualHome evidence must not have insufficient_grounding=true.")
        if coverage.get("not_final_evidence") is True:
            errors.append("final-submission VirtualHome evidence must not set not_final_evidence=true.")
        if evidence_level != "closed_loop_final_evidence":
            errors.append("final-submission VirtualHome evidence must use evidence_level=closed_loop_final_evidence.")
        if coverage.get("continuous_closed_loop") is not True:
            errors.append("final-submission VirtualHome evidence must set continuous_closed_loop=true.")
        if coverage.get("capture_mode") != "continuous_episode":
            errors.append("final-submission VirtualHome evidence must use capture_mode=continuous_episode.")
        if coverage.get("live_runtime_connected") is not True:
            errors.append("final-submission VirtualHome evidence must have live_runtime_connected=true.")
        if coverage.get("action_policy_source") != "agent_policy":
            errors.append("final-submission VirtualHome evidence must use action_policy_source=agent_policy.")
        if _safe_int(coverage.get("action_decision_count"), 0) < max(1, _safe_int(coverage.get("frames_used"), 0) - 1):
            errors.append("final-submission VirtualHome evidence must record one agent policy decision per post-initial frame.")
        if coverage.get("policy_failure_closed") is True:
            errors.append("final-submission VirtualHome evidence must not mark policy_failure_closed=true in successful artifacts.")
        if _safe_int(coverage.get("harness_fallback_count"), 0) > 0:
            warnings.append("VirtualHome final evidence used bounded harness fallback; inspect fallback_events for details.")
    expected_source = "manifest_action_trace_baseline" if mode == "manifest_action_trace" else "visual_observation_pipeline"
    if coverage.get("world_model_source") != expected_source:
        errors.append(f"coverage_report.world_model_source must be {expected_source}.")
    rooms_visited = coverage.get("rooms_visited")
    if not isinstance(rooms_visited, list) or not rooms_visited:
        errors.append("coverage_report.rooms_visited must be a non-empty list.")
    elif rooms_from_manifest - {str(room) for room in rooms_visited}:
        errors.append(f"coverage_report.rooms_visited missing manifest rooms: {sorted(rooms_from_manifest - {str(room) for room in rooms_visited})}")
    if final_submission and isinstance(rooms_visited, list) and not _has_known_room(rooms_visited):
        errors.append("final-submission coverage_report.rooms_visited must include at least one non-unknown room.")
    partial_diagnostic = (
        not final_submission
        and coverage.get("final_status") == "partial"
        and coverage.get("insufficient_grounding") is True
        and coverage.get("not_final_evidence") is True
    )
    room_coverage = _safe_float(coverage.get("room_coverage"), 0.0)
    if room_coverage < 0.8 and not partial_diagnostic:
        errors.append(f"coverage_report.room_coverage must be >= 0.8, got {coverage.get('room_coverage')}.")
    room_coverage_against_reference = coverage.get("room_coverage_against_reference")
    if final_submission and room_coverage_against_reference is None:
        errors.append("final-submission coverage_report.room_coverage_against_reference is required.")
    if final_submission and _safe_float(room_coverage_against_reference, 0.0) < FINAL_ROOM_RECALL_THRESHOLD:
        errors.append(
            "final-submission coverage_report.room_coverage_against_reference must be "
            f">= {FINAL_ROOM_RECALL_THRESHOLD}, got {room_coverage_against_reference}."
        )
    comparison_room_recall = coverage.get("comparison_room_recall")
    if final_submission and comparison_room_recall is None:
        errors.append("final-submission coverage_report.comparison_room_recall is required.")
    if _safe_float(coverage.get("predicted_topology_edges"), 0) == 0:
        warnings.append("Predicted topology has zero edges.")
    elif _safe_int(coverage.get("verified_topology_edges"), 0) == 0:
        warnings.append("Predicted topology has inferred edges but no verified navigation transition.")
    if final_submission and str(coverage.get("termination_reason") or "").lower() in {"max_steps", "step_budget", "budget"}:
        warnings.append("Continuous VirtualHome episode ended by budget.")
    if coverage.get("final_status") == "partial":
        warnings.append("VirtualHome evidence ended partial due to insufficient executable action grounding.")
    if _safe_int(coverage.get("frames_used"), 0) < 12 and not partial_diagnostic:
        errors.append("coverage_report.frames_used must be at least 12 for multi-room evidence.")


def _validate_audit(
    audit: dict[str, Any],
    mode: str,
    errors: list[str],
    warnings: list[str],
    *,
    final_submission: bool,
) -> None:
    required = [
        "success",
        "start_time",
        "end_time",
        "duration_seconds",
        "virtualhome_live_run",
        "live_runtime_connected",
        "launch_attempted",
        "attach_existing",
        "runtime_connection",
        "evidence_level",
        "official_score",
        "world_model_source",
        "prediction_input_mode",
        "visual_extractor_mode",
        "capture_mode",
        "continuous_closed_loop",
        "synthetic_capture",
        "mock_extraction",
        "reference_model_source",
        "reference_used_for_generation",
        "reference_used_for_validation",
        "action_policy_source",
        "action_decision_count",
        "harness_fallback_count",
        "harness_fallback_used",
        "policy_failure_count",
        "policy_failure_closed",
        "action_grounding_mode",
        "grounded_action_count",
        "ungrounded_intent_count",
        "grounding_target_sources",
        "fallback_reasons",
        "insufficient_grounding",
        "final_status",
        "not_final_evidence",
        "rooms_visited_count",
        "room_coverage",
        "frames_used",
        "exploration_trace_length",
        "verified_topology_edges",
        "inferred_visual_topology_edges",
        "inferred_sequence_edges",
        "exploration_order_edges",
        "scene_graph_diagnostic_edges",
        "topology_source",
        "topology_notes",
        "world_model_path",
        "reference_world_model_path",
        "comparison_report_path",
        "episode_log_path",
        "coverage_report_path",
        "frame_manifest_path",
        "errors",
        "warnings",
    ]
    for key in required:
        if key not in audit:
            errors.append(f"run_audit.json missing required field: {key}")
    evidence_level = str(audit.get("evidence_level") or "")
    if evidence_level not in EVIDENCE_LEVELS:
        errors.append(f"run_audit.evidence_level must be one of {sorted(EVIDENCE_LEVELS)}, got {evidence_level!r}.")
    if audit.get("prediction_input_mode") != mode:
        errors.append("run_audit.prediction_input_mode disagrees with selected mode.")
    if audit.get("world_model_source") != ("manifest_action_trace_baseline" if mode == "manifest_action_trace" else "visual_observation_pipeline"):
        errors.append("run_audit.world_model_source is inconsistent with prediction_input_mode.")
    if audit.get("reference_used_for_generation") is not False:
        errors.append("run_audit.reference_used_for_generation must be false.")
    if audit.get("reference_used_for_validation") is not True:
        errors.append("run_audit.reference_used_for_validation must be true.")
    if audit.get("official_score") is not False:
        errors.append("run_audit.official_score must be false.")
    if audit.get("virtualhome_live_run") is True and audit.get("live_runtime_connected") is not True:
        errors.append("live VirtualHome evidence must not claim success without live_runtime_connected=true.")
    if audit.get("live_runtime_connected") is True:
        runtime_connection = audit.get("runtime_connection")
        if not isinstance(runtime_connection, dict) or runtime_connection.get("connected") is not True:
            errors.append("run_audit.live_runtime_connected=true requires runtime_connection.connected=true.")
    if final_submission and audit.get("synthetic_capture") is True:
        errors.append("final-submission VirtualHome evidence must not use synthetic_capture=true.")
    if final_submission and audit.get("mock_extraction") is True:
        errors.append("final-submission VirtualHome evidence must not use mock_extraction=true.")
    if mode == "mock_visual_extraction" and evidence_level != "mock_ci_smoke":
        errors.append("mock_visual_extraction audit must use evidence_level=mock_ci_smoke.")
    if audit.get("capture_mode") in {"replay", "keyframe_capture", "mock"} and evidence_level == "closed_loop_final_evidence":
        errors.append("replay/keyframe/mock audit must not use evidence_level=closed_loop_final_evidence.")
    if final_submission:
        if audit.get("action_grounding_mode") != "observation_side_only":
            errors.append("final-submission run_audit.action_grounding_mode must be observation_side_only.")
        if audit.get("final_status") != "success":
            errors.append("final-submission VirtualHome run_audit must have final_status=success.")
        if audit.get("insufficient_grounding") is True:
            errors.append("final-submission VirtualHome run_audit must not have insufficient_grounding=true.")
        if audit.get("not_final_evidence") is True:
            errors.append("final-submission VirtualHome run_audit must not set not_final_evidence=true.")
        if evidence_level != "closed_loop_final_evidence":
            errors.append("final-submission VirtualHome evidence must use run_audit.evidence_level=closed_loop_final_evidence.")
        if audit.get("virtualhome_live_run") is not True:
            errors.append("final-submission VirtualHome evidence must come from a live continuous VirtualHome run.")
        if audit.get("continuous_closed_loop") is not True:
            errors.append("final-submission VirtualHome evidence must set run_audit.continuous_closed_loop=true.")
        if audit.get("capture_mode") != "continuous_episode":
            errors.append("final-submission VirtualHome evidence must set run_audit.capture_mode=continuous_episode.")
        if audit.get("live_runtime_connected") is not True:
            errors.append("final-submission VirtualHome evidence must set live_runtime_connected=true.")
        if audit.get("action_policy_source") != "agent_policy":
            errors.append("final-submission VirtualHome run_audit must use action_policy_source=agent_policy.")
        if _safe_int(audit.get("action_decision_count"), 0) < max(1, _safe_int(audit.get("frames_used"), 0) - 1):
            errors.append("final-submission VirtualHome run_audit must record one agent policy decision per post-initial frame.")
        if audit.get("policy_failure_closed") is True:
            errors.append("final-submission VirtualHome run_audit must not mark policy_failure_closed=true in successful artifacts.")
    for key, expected in [
        ("world_model_path", "world_model.json"),
        ("reference_world_model_path", "reference_world_model.json"),
        ("comparison_report_path", "comparison_report.json"),
        ("episode_log_path", "episode_log.jsonl"),
        ("coverage_report_path", "coverage_report.json"),
        ("frame_manifest_path", "frame_manifest.json"),
    ]:
        if audit.get(key) != expected:
            errors.append(f"run_audit.{key} must be {expected}")
    if audit.get("virtualhome_live_run") is True and audit.get("continuous_closed_loop") is not True:
        warnings.append("continuous_closed_loop is false for live evidence; final live evidence should use --continuous-run.")


def _validate_topology_edges(edges: list[dict[str, Any]], errors: list[str], warnings: list[str]) -> None:
    allowed_status = {"verified", "inferred", "diagnostic", "blocked", "unknown"}
    for index, edge in enumerate(edges):
        for key in ["from", "to", "relation", "status", "evidence_source", "evidence_frames", "action", "confidence"]:
            if key not in edge:
                errors.append(f"world_model.topology.edges[{index}] missing required field: {key}")
        status = str(edge.get("status") or "")
        evidence_source = str(edge.get("evidence_source") or "")
        if status not in allowed_status:
            errors.append(f"world_model.topology.edges[{index}] has invalid status: {status}")
        if status == "verified" and evidence_source != "navigation_transition":
            errors.append(f"verified topology edge {index} must use evidence_source=navigation_transition.")
        if status == "verified" and str(edge.get("action") or "").lower() in {"chronological order only", "manifest order only"}:
            errors.append(f"verified topology edge {index} appears to come from frame order instead of navigation.")
        if status == "verified" and str(edge.get("navigation_evidence_source") or "").lower() in {"render_script_walk_action", "hardcoded_room_order"}:
            errors.append(f"verified topology edge {index} uses hardcoded navigation evidence.")
        if evidence_source in {"visual_doorway_or_passage_cue", "vlm_frame_extraction"} and status != "inferred":
            errors.append(f"visual topology edge {index} must use status=inferred.")
        if evidence_source == "frame_manifest_order":
            errors.append(f"frame order edge {index} must be stored in exploration_order_edges, not world_model.topology.edges.")
        if status == "diagnostic":
            warnings.append(f"topology edge {index} is diagnostic reference evidence, not official hidden-evaluation observation.")


def _validate_exploration_order_edges(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("world_model.exploration_order_edges must be a list.")
        return
    for index, edge in enumerate(value):
        if not isinstance(edge, dict):
            errors.append(f"world_model.exploration_order_edges[{index}] must be an object.")
            continue
        if edge.get("status") != "inferred_from_sequence":
            errors.append(f"world_model.exploration_order_edges[{index}] must use status=inferred_from_sequence.")
        if edge.get("evidence_source") != "frame_manifest_order":
            errors.append(f"world_model.exploration_order_edges[{index}] must use evidence_source=frame_manifest_order.")


def _validate_room_connectivity(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("world_model.room_connectivity must be a list.")
        return
    for index, edge in enumerate(value):
        if isinstance(edge, dict) and (edge.get("evidence_source") == "frame_manifest_order" or edge.get("status") == "inferred_from_sequence"):
            errors.append(f"world_model.room_connectivity[{index}] must not contain frame-order inferred edges.")


def _validate_vlm_model_call(
    value: Any,
    frame: str,
    index: int,
    errors: list[str],
    *,
    final_submission: bool,
) -> None:
    if not isinstance(value, dict):
        errors.append(f"frame_manifest frame {index} missing real VLM model_call metadata.")
        return
    if value.get("real_model_call") is not True:
        errors.append(f"frame_manifest frame {index} model_call.real_model_call must be true for VLM mode.")
    if value.get("success") is not True:
        errors.append(f"frame_manifest frame {index} model_call.success must be true for VLM mode.")
    if value.get("input_mode") not in {"vision", None}:
        errors.append(f"frame_manifest frame {index} model_call.input_mode must be vision.")
    provider = str(value.get("provider") or "").lower()
    base_url = str(value.get("base_url") or "").lower()
    if "mock" in provider or base_url.startswith("mock://"):
        errors.append(f"frame_manifest frame {index} model_call must not use a mock provider/base_url in VLM mode.")
    image_path = str(value.get("image_path") or "")
    if image_path and image_path != frame:
        errors.append(f"frame_manifest frame {index} model_call.image_path must match frame_manifest frame.")
    if final_submission and value.get("fallback_used") is True:
        errors.append(f"frame_manifest frame {index} final VLM extraction must not rely on parser fallback.")
    if final_submission and value.get("parse_success") is not True:
        errors.append(f"frame_manifest frame {index} final VLM extraction must record parse_success=true.")


def _validate_dedup_report(dedup_report: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    required = [
        "raw_object_mentions",
        "unique_objects",
        "raw_relation_mentions",
        "unique_relations",
        "merged_object_clusters",
        "alias_merges",
        "objects_by_room",
        "active_relations",
        "stale_relations",
        "warnings",
    ]
    for key in required:
        if key not in dedup_report:
            errors.append(f"dedup_report.json missing required field: {key}")
    raw_objects = _safe_int(dedup_report.get("raw_object_mentions"), -1)
    unique_objects = _safe_int(dedup_report.get("unique_objects"), -1)
    if raw_objects > 20 and unique_objects < 0:
        errors.append("dedup_report must include unique_objects when raw_object_mentions is high.")
    if raw_objects > 20 and unique_objects > 0 and unique_objects / raw_objects > 0.8:
        warnings.append(f"unique_objects/raw_object_mentions ratio is {unique_objects / raw_objects:.3f}; deduplication may be conservative.")


def _validate_reference_model(reference_model: dict[str, Any], errors: list[str]) -> None:
    if reference_model.get("source") not in {"virtualhome_scene_graph_answer_key", "virtualhome_manifest_reference_fallback"}:
        errors.append("reference_world_model.source must identify an answer key/reference source.")
    if reference_model.get("used_for_generation") is not False:
        errors.append("reference_world_model.used_for_generation must be false.")
    if reference_model.get("used_for_validation") is not True:
        errors.append("reference_world_model.used_for_validation must be true.")
    if reference_model.get("used_for_prediction_generation") is not False:
        errors.append("reference_world_model.used_for_prediction_generation must be false.")
    for key in ["rooms", "objects", "relations"]:
        if not isinstance(reference_model.get(key), list):
            errors.append(f"reference_world_model.{key} must be a list.")


def _validate_comparison_report(
    comparison_report: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    final_submission: bool,
) -> None:
    if comparison_report.get("reference_used_for_generation") is not False:
        errors.append("comparison_report.reference_used_for_generation must be false.")
    if comparison_report.get("reference_used_for_validation") is not True:
        errors.append("comparison_report.reference_used_for_validation must be true.")
    for key in ["rooms", "objects", "relations", "topology"]:
        block = comparison_report.get(key)
        if not isinstance(block, dict):
            errors.append(f"comparison_report.{key} must be an object.")
            continue
        for metric in ["precision", "recall", "matched", "missed", "spurious"]:
            if metric not in block:
                errors.append(f"comparison_report.{key} missing metric: {metric}")
    rooms = comparison_report.get("rooms")
    if not isinstance(rooms, dict):
        return
    room_recall = rooms.get("recall")
    if final_submission and room_recall is None:
        errors.append("final-submission comparison_report.rooms.recall is required.")
    recall_value = _safe_float(room_recall, 0.0)
    if recall_value < FINAL_ROOM_RECALL_THRESHOLD:
        message = f"comparison_report.rooms.recall is below {FINAL_ROOM_RECALL_THRESHOLD}: {room_recall}."
        if final_submission:
            errors.append("final-submission " + message)
        else:
            warnings.append(message)
    if final_submission:
        matched = rooms.get("matched")
        reference = rooms.get("reference")
        matched_known = [room for room in matched if _is_known_room(room)] if isinstance(matched, list) else []
        reference_count = len(reference) if isinstance(reference, list) else MIN_FINAL_REFERENCE_ROOM_MATCHES
        required_matches = min(MIN_FINAL_REFERENCE_ROOM_MATCHES, max(1, reference_count))
        if len(matched_known) < required_matches:
            errors.append(
                "final-submission comparison_report.rooms.matched must include at least "
                f"{required_matches} non-unknown reference rooms; got {len(matched_known)}."
            )


def _topology_edges(topology: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(topology, dict):
        errors.append("world_model.topology must be an object with nodes and edges.")
        return []
    edges = topology.get("edges")
    if not isinstance(edges, list):
        errors.append("world_model.topology.edges must be a list.")
        return []
    return [edge for edge in edges if isinstance(edge, dict)]


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _read_json(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        errors.append(f"Missing required artifact: {label}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object.")
        return {}
    return payload


def _read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        errors.append("Missing required artifact: episode_log.jsonl")
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"episode_log.jsonl line {line_number} is invalid JSON: {exc}")
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            errors.append(f"episode_log.jsonl line {line_number} must be an object.")
    return rows


def _validate_qwen_call_log(path: Path, expected_frames: int, errors: list[str]) -> None:
    if not path.exists():
        errors.append("final VLM VirtualHome evidence must include qwen_calls.jsonl real model call audit.")
        return
    rows = _read_jsonl(path, errors)
    successful_vision_calls = 0
    for index, row in enumerate(rows):
        if row.get("success") is not True:
            continue
        prompt_summary = str(row.get("prompt_summary") or "")
        if "images:1" not in prompt_summary:
            errors.append(f"qwen_calls.jsonl line {index + 1} does not record a vision/image prompt.")
            continue
        successful_vision_calls += 1
    if successful_vision_calls < expected_frames:
        errors.append(
            f"qwen_calls.jsonl must contain at least one successful vision call per frame; "
            f"got {successful_vision_calls}/{expected_frames}."
        )


def _validate_action_grounding(
    frames: list[dict[str, Any]],
    episode_rows: list[dict[str, Any]],
    coverage: dict[str, Any],
    audit: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    final_submission: bool,
) -> None:
    executed_sources: list[str] = []
    executed_actions: list[str] = []
    ungrounded_executed = False
    for index, row in enumerate(frames):
        action = str(row.get("action") or "")
        if action:
            executed_actions.append(action)
        grounded = row.get("grounded_action") if isinstance(row.get("grounded_action"), dict) else {}
        target_source = str(grounded.get("target_source") or "")
        if target_source:
            executed_sources.append(target_source)
        if target_source in DISALLOWED_FINAL_TARGET_SOURCES:
            message = f"frame_manifest frame {index} uses disallowed action grounding target_source={target_source}."
            if final_submission:
                errors.append(message)
            else:
                warnings.append(message)
        if final_submission and target_source and target_source not in ALLOWED_FINAL_TARGET_SOURCES:
            errors.append(f"frame_manifest frame {index} target_source is not allowed for final evidence: {target_source}")
        if final_submission and "[Walk]" in action and target_source not in ALLOWED_FINAL_TARGET_SOURCES:
            errors.append(f"frame_manifest frame {index} executed walk action without approved grounding target_source.")
        if grounded.get("executable") is False and row.get("action_result", {}).get("success") is True:
            ungrounded_executed = True
            errors.append(f"frame_manifest frame {index} executed an ungrounded intent.")
        for event in row.get("grounding_events", []) if isinstance(row.get("grounding_events"), list) else []:
            if not isinstance(event, dict):
                continue
            source = str(event.get("target_source") or "")
            if source in DISALLOWED_FINAL_TARGET_SOURCES:
                message = f"grounding event at frame {index} uses disallowed target_source={source}."
                if final_submission:
                    errors.append(message)
                else:
                    warnings.append(message)
            if final_submission and event.get("executable") is True and source and source not in ALLOWED_FINAL_TARGET_SOURCES:
                errors.append(f"grounding event at frame {index} has final-disallowed target_source={source}.")
        for event in row.get("fallback_events", []) if isinstance(row.get("fallback_events"), list) else []:
            if not isinstance(event, dict):
                continue
            fallback_action = str(event.get("fallback_action") or "")
            if final_submission and "[Walk]" in fallback_action:
                errors.append(f"harness fallback at frame {index} attempted non-scan action: {fallback_action}")

    final_status = str(coverage.get("final_status") or audit.get("final_status") or "")
    insufficient = coverage.get("insufficient_grounding") is True or audit.get("insufficient_grounding") is True
    if final_status == "success" and insufficient:
        errors.append("final_status cannot be success while insufficient_grounding=true.")
    if final_status == "partial":
        warnings.append("VirtualHome grounding ended with final_status=partial.")
    if final_submission and final_status == "partial":
        errors.append("final-submission VirtualHome evidence cannot have final_status=partial.")
    if final_submission and ungrounded_executed:
        errors.append("final-submission VirtualHome evidence executed an ungrounded intent.")
    if final_submission and any(source in DISALLOWED_FINAL_TARGET_SOURCES for source in executed_sources):
        errors.append("final-submission VirtualHome evidence used hidden/reference target source for grounding.")
    scan_actions = [action for action in executed_actions if "[TurnLeft]" in action or "[TurnRight]" in action or action == "observe"]
    if executed_actions and len(scan_actions) == len(executed_actions):
        warnings.append("VirtualHome action grounding executed only scan/observe actions; no grounded navigation target was available.")

    for row in episode_rows:
        if row.get("event_type") != "harness_fallback":
            continue
        update = row.get("model_update") if isinstance(row.get("model_update"), dict) else {}
        fallback_action = str(update.get("fallback_action") or row.get("action") or "")
        if final_submission and "[Walk]" in fallback_action:
            errors.append(f"episode_log harness fallback used non-scan action: {fallback_action}")


def _manifest_rows(payload: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    rows = payload.get("frames")
    if not isinstance(rows, list):
        errors.append("frame_manifest.json must contain a frames list.")
        return []
    return [row for row in rows if isinstance(row, dict)]


def _prediction_input_mode(world_model: dict[str, Any], audit: dict[str, Any], coverage: dict[str, Any]) -> str:
    for value in [world_model.get("prediction_input_mode"), audit.get("prediction_input_mode"), coverage.get("prediction_input_mode")]:
        if str(value or "").strip():
            return str(value).strip()
    return "unknown"


def _absolute_path_values(value: Any, key_path: str = "$") -> list[tuple[str, str]]:
    offenders: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            offenders.extend(_absolute_path_values(child, f"{key_path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            offenders.extend(_absolute_path_values(child, f"{key_path}[{index}]"))
    elif isinstance(value, str) and _contains_local_absolute_path(value):
        offenders.append((key_path, value))
    return offenders


def _contains_local_absolute_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return any(pattern.search(normalized) for pattern in LOCAL_ABSOLUTE_PATTERNS)


def _has_known_room(values: list[Any]) -> bool:
    return any(_is_known_room(value) for value in values)


def _is_known_room(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return bool(normalized) and normalized not in {"unknown", "unknown_room", "none", "null"}


def _validate_image_file(path: Path) -> str:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
        if width <= 0 or height <= 0:
            return "image dimensions must be positive"
        return ""
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate VirtualHome multi-room exploration evidence.")
    parser.add_argument("path", nargs="?", help="Output directory to validate.")
    parser.add_argument("--output-dir", dest="output_dir", help="Output directory to validate.")
    parser.add_argument("--final-submission", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir or args.path or "outputs/virtualhome_exploration")
    summary = validate_detailed(output_dir, final_submission=bool(args.final_submission))
    if summary["errors"]:
        print("VirtualHome exploration validation failed:")
        for error in summary["errors"]:
            print(f"- {error}")
        return 1
    if summary["warnings"]:
        print("VirtualHome exploration validation warnings:")
        for warning in summary["warnings"]:
            print(f"- {warning}")
    print(f"VirtualHome exploration validation passed: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
