from __future__ import annotations

import json
import importlib
import os
import shutil
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from clients.qwen_client import QwenClient, QwenClientError
from executor.virtualhome_grounder import GroundingContext, VirtualHomeActionGrounder, grounded_action_to_dict
from harness._common import elapsed, resolve_project_path, write_harness_result
from infra.paths import PROJECT_ROOT
from logging_utils.episode_logger import EpisodeLogger
from perception.vlm_extractor import VLMExtractor
from planner.virtualhome_policy import (
    ActionIntent,
    PolicyContext,
    VirtualHomeExplorationPolicy,
    action_intent_to_dict,
)
from world_model.canonicalize import canonicalize_world_model


DEFAULT_PORT = 8080
DEFAULT_PREDICTION_INPUT_MODE = "vlm_frame_extraction"
PREDICTION_INPUT_MODES = {"vlm_frame_extraction", "mock_visual_extraction", "manifest_action_trace"}
EVIDENCE_CLOSED_LOOP = "closed_loop_final_evidence"
EVIDENCE_VISUAL_REPLAY = "visual_replay_diagnostic"
EVIDENCE_MOCK_CI = "mock_ci_smoke"
EVIDENCE_SCENE_GRAPH_REFERENCE = "scene_graph_reference_only"
DEFAULT_REPLAY_ASSETS_DIR = PROJECT_ROOT / "assets" / "test_sequences" / "virtualhome_exploration"
ROOMS = ["bathroom", "bedroom", "kitchen", "livingroom"]
OBJECTS_BY_ROOM = {
    "bathroom": ["sink", "toilet", "mirror"],
    "bedroom": ["bed", "table", "book"],
    "kitchen": ["fridge", "counter", "cabinet"],
    "livingroom": ["sofa", "television", "coffee_table"],
}
OFFICIAL_SCORE_NOTE = "Local VirtualHome evidence only; official_score=false."
MIN_REPLAY_FRAMES = 12
DEFAULT_CONTINUOUS_MAX_STEPS = 30
DEFAULT_TARGET_ROOM_COVERAGE = 0.8
VIRTUALHOME_CONTINUOUS_TASK = "Explore reachable VirtualHome rooms and build an observation-derived world model."
MAX_CONTINUOUS_ACTION_FAILURES = 5
DEFAULT_MAX_FALLBACKS = 5
MAX_FALLBACKS_PER_STEP = 2


class VirtualHomeEvidenceError(RuntimeError):
    """Raised when VirtualHome evidence would otherwise become synthetic or mislabeled."""


def run_live(
    *,
    virtualhome_exe: str | None = None,
    attach_existing: bool = False,
    output_dir: str | Path = "outputs/virtualhome_exploration",
    max_rooms: str = "all",
    frames_per_room: int = 3,
    scene: int = 0,
    port: int = DEFAULT_PORT,
    validate: bool = False,
    replay_assets_dir: str | Path = DEFAULT_REPLAY_ASSETS_DIR,
    canonicalize: bool = True,
    prediction_input_mode: str = DEFAULT_PREDICTION_INPUT_MODE,
    continuous_run: bool = False,
    continuous_episode: bool | None = None,
    max_steps: int = DEFAULT_CONTINUOUS_MAX_STEPS,
    target_room_coverage: float = DEFAULT_TARGET_ROOM_COVERAGE,
    max_fallbacks: int = DEFAULT_MAX_FALLBACKS,
    final_submission: bool = False,
) -> int:
    started = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()
    out = resolve_project_path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _clear_virtualhome_artifacts(out)
    mode = _normalize_prediction_input_mode(prediction_input_mode)
    is_continuous_episode = bool(continuous_run if continuous_episode is None else continuous_episode)
    launch_attempted = bool(virtualhome_exe and not attach_existing)
    if not attach_existing and not virtualhome_exe:
        return _fail_live(
            out,
            start_time=start_time,
            started=started,
            mode=mode,
            reason=(
                "run_virtualhome_live requires either --attach-existing or --virtualhome-exe. "
                "Use run_virtualhome_replay for exported keyframes, or explicit mock mode for CI smoke tests."
            ),
            attach_existing=attach_existing,
            launch_attempted=launch_attempted,
            capture_mode="continuous_episode" if is_continuous_episode else "keyframe_capture",
            continuous_closed_loop=is_continuous_episode,
        )
    try:
        comm, connection = _connect_virtualhome_runtime(
            virtualhome_exe=virtualhome_exe,
            attach_existing=attach_existing,
            port=port,
            output_dir=out,
        )
        _call_if_exists(comm, "reset", scene)
        _call_if_exists(comm, "add_character")
        if is_continuous_episode:
            rows = _collect_continuous_episode(
                comm,
                output_dir=out,
                mode=mode,
                max_steps=max(1, int(max_steps)),
                target_room_coverage=float(target_room_coverage),
                max_fallbacks=max(0, int(max_fallbacks)),
            )
        else:
            rows = _collect_live_keyframes(
                comm,
                output_dir=out,
                frames_per_room=max(3, int(frames_per_room)),
                max_rooms=str(max_rooms),
            )
        # Build the reference answer key only after the observation/action episode.
        # It is validation-only data and must not influence predicted world-model generation.
        scene_graph = _get_scene_graph(comm)
        reference_world_model = _build_reference_world_model_from_scene_graph(scene_graph)
        partial_or_failed_grounding = any(row.get("terminal_status") in {"partial", "failed"} for row in rows)
        if len(rows) < MIN_REPLAY_FRAMES and not partial_or_failed_grounding:
            raise VirtualHomeEvidenceError(
                f"VirtualHome live capture produced {len(rows)} validated frames; at least {MIN_REPLAY_FRAMES} are required."
            )
        result = _write_artifacts(
            output_dir=out,
            frame_manifest=_prepare_prediction_rows(rows, mode, output_dir=out),
            source="VirtualHome live run on local Unity runtime",
            live_run=True,
            live_runtime_connected=True,
            attach_existing=attach_existing,
            launch_attempted=launch_attempted,
            runtime_connection=connection,
            synthetic_capture=False,
            start_time=start_time,
            duration_seconds=elapsed(started),
            prediction_input_mode=mode,
            capture_mode="continuous_episode" if is_continuous_episode else "keyframe_capture",
            continuous_closed_loop=bool(is_continuous_episode),
            reference_world_model=reference_world_model,
            canonicalize=canonicalize,
            validate=validate,
            final_submission=final_submission,
        )
        if not partial_or_failed_grounding:
            _export_replay_assets(out, resolve_project_path(replay_assets_dir))
        return 0 if result.get("success") else 1
    except (VirtualHomeEvidenceError, QwenClientError, ImportError, OSError, RuntimeError, TimeoutError) as exc:
        return _fail_live(
            out,
            start_time=start_time,
            started=started,
            mode=mode,
            reason=str(exc),
            attach_existing=attach_existing,
            launch_attempted=launch_attempted,
            capture_mode="continuous_episode" if is_continuous_episode else "keyframe_capture",
            continuous_closed_loop=is_continuous_episode,
        )


def run_replay(
    *,
    frames: str | Path,
    manifest: str | Path,
    output_dir: str | Path = "outputs/virtualhome_exploration_replay",
    validate: bool = False,
    canonicalize: bool = True,
    prediction_input_mode: str = DEFAULT_PREDICTION_INPUT_MODE,
    final_submission: bool = False,
) -> int:
    started = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()
    out = resolve_project_path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _clear_virtualhome_artifacts(out)
    source_frames = resolve_project_path(frames)
    manifest_path = resolve_project_path(manifest)
    rows = _read_manifest(manifest_path)
    copied_rows: list[dict[str, Any]] = []
    target_frames = out / "frames"
    target_frames.mkdir(parents=True, exist_ok=True)
    for index, row in enumerate(rows):
        rel_frame = str(row.get("frame") or f"frames/frame_{index:03d}.jpg")
        source = source_frames / rel_frame
        if not source.exists() and rel_frame.startswith("frames/"):
            source = source_frames / Path(rel_frame).name
        if not source.exists():
            print(f"VirtualHome replay frame missing: {source}", file=sys.stderr)
            return 1
        target = target_frames / f"frame_{index:03d}{source.suffix.lower() or '.jpg'}"
        shutil.copy2(source, target)
        try:
            image_info = _verify_image_file(target)
        except VirtualHomeEvidenceError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        clean = dict(row)
        clean["frame"] = f"frames/{target.name}"
        clean["frame_validation"] = image_info
        copied_rows.append(clean)
    mode = _normalize_prediction_input_mode(prediction_input_mode)
    try:
        reference_world_model = _load_reference_world_model(manifest_path.parent, copied_rows)
        result = _write_artifacts(
            output_dir=out,
            frame_manifest=_prepare_prediction_rows(copied_rows, mode, output_dir=out),
            source="VirtualHome replay from exported keyframes and frame_manifest.json",
            live_run=False,
            live_runtime_connected=False,
            attach_existing=False,
            launch_attempted=False,
            runtime_connection={},
            synthetic_capture=any(bool(row.get("synthetic_capture")) for row in copied_rows),
            start_time=start_time,
            duration_seconds=elapsed(started),
            prediction_input_mode=mode,
            capture_mode="replay",
            continuous_closed_loop=False,
            reference_world_model=reference_world_model,
            canonicalize=canonicalize,
            validate=validate,
            final_submission=final_submission,
        )
        return 0 if result.get("success") else 1
    except (VirtualHomeEvidenceError, QwenClientError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _prepare_prediction_rows(rows: list[dict[str, Any]], mode: str, *, output_dir: Path) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    vlm: tuple[VLMExtractor, QwenClient] | None = None
    needs_vlm = mode == "vlm_frame_extraction" and any(
        not _has_prepared_visual_extraction(row, mode) for row in rows
    )
    if needs_vlm:
        vlm = _make_vlm_extractor(output_dir)
    for row in rows:
        clean = dict(row)
        for key in ["expected_visible_objects", "reference_visible_objects", "visual_observation_objects", "observed_visible_objects"]:
            clean.pop(key, None)
        clean["prediction_input_mode"] = mode
        if not _has_prepared_visual_extraction(clean, mode):
            clean["visual_extraction"] = _extract_from_row(clean, mode, output_dir=output_dir, vlm=vlm)
        clean = _apply_extracted_room(clean)
        prepared.append(clean)
    return prepared


def _has_prepared_visual_extraction(row: dict[str, Any], mode: str) -> bool:
    extraction = row.get("visual_extraction")
    if not isinstance(extraction, dict) or extraction.get("source") != mode:
        return False
    if mode != "vlm_frame_extraction":
        return True
    model_call = extraction.get("model_call")
    return isinstance(model_call, dict) and model_call.get("real_model_call") is True


def _extract_from_row(
    row: dict[str, Any],
    mode: str,
    *,
    output_dir: Path,
    vlm: tuple[VLMExtractor, QwenClient] | None,
) -> dict[str, Any]:
    if mode == "vlm_frame_extraction":
        if vlm is None:
            raise VirtualHomeEvidenceError("prediction_input_mode=vlm_frame_extraction requires a real VLMExtractor.")
        return _extract_with_vlm(row, output_dir=output_dir, extractor=vlm[0], client=vlm[1])
    return _mock_or_manifest_extraction(row, mode)


def _mock_or_manifest_extraction(row: dict[str, Any], mode: str) -> dict[str, Any]:
    room = _norm(str(row.get("room") or "unknown"))
    step = int(row.get("step", 0))
    labels = OBJECTS_BY_ROOM.get(room, ["object"])
    visible = [labels[step % len(labels)], labels[(step + 1) % len(labels)]]
    if mode == "manifest_action_trace":
        visible = [str(row.get("anchor_object") or "action_target")]
    objects = [
        {
            "id": f"{mode}_{step:03d}_{_slug(label)}",
            "name": label,
            "category": "visual_observation" if mode != "manifest_action_trace" else "action_trace_target",
            "room": room,
            "confidence": 0.74 if mode == "vlm_frame_extraction" else 0.52,
        }
        for label in visible
    ]
    topology = []
    if mode in {"vlm_frame_extraction", "mock_visual_extraction"} and step % 3 == 1:
        topology.append(
            {
                "from": room,
                "to": "hallway" if room != "livingroom" else "unknown_frontier_doorway",
                "relation": "connected_to",
                "cue": "visible doorway or passage",
                "confidence": 0.56,
            }
        )
    return {
        "source": mode,
        "extractor_mode": mode,
        "mock": mode == "mock_visual_extraction",
        "synthetic": True,
        "objects": objects,
        "relations": [],
        "states": [{"entity": obj["name"], "attribute": "visibility", "value": "observed"} for obj in objects],
        "affordances": [],
        "topology": topology,
        "model_call": {
            "provider": "deterministic_mock" if mode == "mock_visual_extraction" else "manifest_action_trace",
            "real_model_call": False,
            "success": True,
            "image_path": str(row.get("frame") or ""),
        },
        "uncertainty": []
        if objects
        else [{"item": "visual_extraction", "level": "high", "reason": "No visible objects extracted."}],
    }


def _extract_with_vlm(
    row: dict[str, Any],
    *,
    output_dir: Path,
    extractor: VLMExtractor,
    client: QwenClient,
) -> dict[str, Any]:
    frame_rel = str(row.get("frame") or "")
    frame_path = output_dir / frame_rel
    _verify_image_file(frame_path)
    observation_text = (
        f"Frame: {frame_rel}\n"
        f"Step: {row.get('step', '')}\n"
        f"Action/camera movement: {row.get('action', '')} / {row.get('camera_movement', '')}\n"
        "Use only visible evidence from the image and this action/camera context. "
        "Do not use frame manifest expected objects or scene graph reference data."
    )
    try:
        extracted = extractor.extract(
            {"image_path": frame_path, "text": observation_text},
            "VirtualHome multi-room exploration: extract visible rooms, objects, relations, states, and doorway/passage topology cues.",
        )
    except QwenClientError as exc:
        raise VirtualHomeEvidenceError(
            "prediction_input_mode=vlm_frame_extraction requires a local vision-capable Qwen/vLLM endpoint. "
            "No synthetic extraction was generated. Use --prediction-input-mode mock_visual_extraction only for CI/docker smoke. "
            f"Underlying error: {exc}"
        ) from exc
    model_call = {
        "provider": "qwen_vllm_openai_compatible",
        "real_model_call": True,
        "success": bool(extractor.last_call_success),
        "parse_success": bool(extractor.last_parse_success),
        "fallback_used": bool(extractor.fallback_used),
        "input_mode": extractor.last_input_mode,
        "model": client.model,
        "base_url": client.base_url,
        "image_path": frame_rel,
        "qwen_call_count": client.call_count,
        "qwen_call_success_count": client.success_count,
        "qwen_call_failure_count": client.failure_count,
    }
    extracted.update(
        {
            "source": "vlm_frame_extraction",
            "extractor_mode": "vlm_frame_extraction",
            "mock": False,
            "synthetic": False,
            "model_call": model_call,
        }
    )
    if not extracted.get("objects") and not extracted.get("uncertainty"):
        extracted["uncertainty"] = [
            {
                "item": "visual_extraction",
                "level": "high",
                "reason": "Real VLM call returned no visible objects for this frame.",
            }
        ]
    return extracted


def _apply_extracted_room(row: dict[str, Any]) -> dict[str, Any]:
    extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
    rooms = extraction.get("rooms")
    detected_room = ""
    if isinstance(rooms, list):
        for item in rooms:
            if isinstance(item, dict):
                detected_room = str(item.get("name") or item.get("id") or item.get("room") or "")
            else:
                detected_room = str(item or "")
            if detected_room.strip():
                break
    detected_room = _norm(detected_room)
    current_room = _norm(str(row.get("room") or ""))
    if detected_room and current_room in {"", "unknown"}:
        row["room"] = detected_room
        for obj in extraction.get("objects", []) if isinstance(extraction.get("objects"), list) else []:
            if isinstance(obj, dict) and _norm(str(obj.get("room") or "")) in {"", "unknown"}:
                obj["room"] = detected_room
    return row


def _make_vlm_extractor(output_dir: Path, *, reset_audit: bool = True) -> tuple[VLMExtractor, QwenClient]:
    qwen_calls_path = output_dir / "qwen_calls.jsonl"
    if reset_audit and qwen_calls_path.exists():
        qwen_calls_path.unlink()
    config = _load_qwen_config()
    client = QwenClient(
        base_url=str(config.get("base_url", "http://127.0.0.1:8000/v1")),
        model=str(config.get("model", "qwen3.6-35b-nvfp4")),
        temperature=float(config.get("temperature", 0.2)),
        max_tokens=int(config.get("max_tokens", 2048)),
        timeout_seconds=int(config.get("timeout_seconds", 120)),
        audit_path=qwen_calls_path,
    )
    extractor = VLMExtractor(
        client,
        debug_output_path=output_dir / "debug_virtualhome_qwen_raw.txt",
        response_summary_path=output_dir / "qwen_response_summary.json",
    )
    return extractor, client


def _load_qwen_config() -> dict[str, Any]:
    config: dict[str, Any] = {}
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        current_section: str | None = None
        for line in config_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
                continue
            if line.startswith((" ", "\t")) and current_section:
                key, value = line.strip().split(":", 1)
                section = config.setdefault(current_section, {})
                if isinstance(section, dict):
                    section[key.strip()] = _parse_scalar(value.strip())
                continue
            key, value = line.strip().split(":", 1)
            key = key.strip()
            if value.strip():
                config[key] = _parse_scalar(value.strip())
                current_section = None
            else:
                config[key] = {}
                current_section = key
    for env_name, key, caster in [
        ("QWEN_BASE_URL", "base_url", str),
        ("QWEN_MODEL", "model", str),
        ("QWEN_TEMPERATURE", "temperature", float),
        ("QWEN_MAX_TOKENS", "max_tokens", int),
    ]:
        raw = os.environ.get(env_name)
        if raw:
            config[key] = caster(raw)
    return config


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value.strip('"').strip("'")


def _connect_virtualhome_runtime(
    *,
    virtualhome_exe: str | None,
    attach_existing: bool,
    port: int,
    output_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    comm_module = _import_virtualhome_comm_module()
    UnityCommunication = getattr(comm_module, "UnityCommunication")
    port_text = str(port)
    if attach_existing:
        if not _is_port_open("127.0.0.1", port):
            raise VirtualHomeEvidenceError(
                f"--attach-existing was set, but no VirtualHome/Unity runtime is listening on 127.0.0.1:{port}."
            )
        comm = UnityCommunication(port=port_text, logging=False)
    else:
        exe = Path(str(virtualhome_exe or ""))
        if not exe.exists():
            raise VirtualHomeEvidenceError("--virtualhome-exe must point to an existing VirtualHome/Unity executable.")
        comm = UnityCommunication(file_name=str(exe), port=port_text, logging=False)
    connection = {
        "connected": True,
        "port": port,
        "attach_existing": bool(attach_existing),
        "launch_attempted": bool(virtualhome_exe and not attach_existing),
        "comm_module": comm_module.__name__,
        "virtualhome_exe_provided": bool(virtualhome_exe),
    }
    _write_json(output_dir / "virtualhome_runtime_connection.json", connection)
    return comm, connection


def _import_virtualhome_comm_module() -> Any:
    _ensure_virtualhome_api_on_path()
    for module_name in [
        "simulation.unity_simulator.comm_unity",
        "virtualhome.simulation.unity_simulator.comm_unity",
    ]:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    raise ImportError(
        "Could not import VirtualHome UnityCommunication. Install the VirtualHome Python API or use replay mode."
    )


def _ensure_virtualhome_api_on_path() -> None:
    for candidate in _candidate_virtualhome_repo_paths():
        if _repo_has_virtualhome_api(candidate):
            for path in [candidate, candidate / "virtualhome"]:
                if path.exists():
                    text = str(path)
                    if text not in sys.path:
                        sys.path.insert(0, text)
            return


def _candidate_virtualhome_repo_paths() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.environ.get("VIRTUALHOME_REPO_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path.home() / "Documents" / "VirtualHome",
            Path.home() / "Documents" / "virtualhome",
            Path.home() / "Downloads" / "virtualhome",
            Path.home() / "Documents" / "ExternalTools" / "virtualhome",
            PROJECT_ROOT.parent / "virtualhome",
            PROJECT_ROOT.parent / "VirtualHome",
        ]
    )
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _repo_has_virtualhome_api(path: Path) -> bool:
    return any(
        (path / relative).exists()
        for relative in [
            Path("simulation/unity_simulator/comm_unity.py"),
            Path("virtualhome/simulation/unity_simulator/comm_unity.py"),
        ]
    )


def _collect_live_keyframes(
    comm: Any,
    *,
    output_dir: Path,
    frames_per_room: int,
    max_rooms: str,
) -> list[dict[str, Any]]:
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    camera_count, camera_indexes = _candidate_camera_indexes(comm)
    if not camera_indexes:
        raise VirtualHomeEvidenceError("VirtualHome runtime did not expose camera indexes for real frame capture.")
    requested_rooms = len(camera_indexes)
    if max_rooms != "all":
        try:
            requested_rooms = max(1, min(requested_rooms, int(max_rooms)))
        except ValueError:
            requested_rooms = len(camera_indexes)
    frame_count = max(MIN_REPLAY_FRAMES, requested_rooms * max(1, frames_per_room))
    rows: list[dict[str, Any]] = []
    for step in range(frame_count):
        camera_index = camera_indexes[step % len(camera_indexes)]
        frame_path = frames_dir / f"frame_{step:03d}.png"
        capture_status = _capture_frame_from_virtualhome(comm, frame_path, camera_index)
        image_info = _verify_image_file(frame_path)
        rows.append(
            {
                "frame": f"frames/{frame_path.name}",
                "step": step,
                "room": "unknown",
                "action": "capture_frame_after_live_runtime_reset" if step == 0 else "capture_live_keyframe",
                "camera_movement": f"camera_index={camera_index}",
                "capture_mode": "keyframe_capture",
                "continuous_closed_loop": False,
                "frame_validation": image_info,
                "capture_metadata": {
                    "source": "virtualhome_camera_image",
                    "camera_index": camera_index,
                    "camera_count": camera_count,
                    "real_image": True,
                    "reason": capture_status.get("reason", ""),
                },
                "notes": "Captured from VirtualHome camera_image API; room label must come from VLM/action evidence.",
            }
        )
    return rows


def _collect_continuous_episode(
    comm: Any,
    *,
    output_dir: Path,
    mode: str,
    max_steps: int,
    target_room_coverage: float,
    max_fallbacks: int = DEFAULT_MAX_FALLBACKS,
) -> list[dict[str, Any]]:
    # Kept for CLI compatibility. Final room coverage is checked after the run
    # against the reference comparison report, not used as a scripted stop rule.
    _ = target_room_coverage
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    camera_count, camera_indexes = _candidate_camera_indexes(comm)
    if not camera_indexes:
        raise VirtualHomeEvidenceError("VirtualHome runtime did not expose camera indexes for continuous observation capture.")
    camera_index = camera_indexes[0]
    vlm: tuple[VLMExtractor, QwenClient] | None = None
    if mode == "vlm_frame_extraction":
        vlm = _make_vlm_extractor(output_dir)

    rows: list[dict[str, Any]] = []
    policy = VirtualHomeExplorationPolicy()
    grounder = VirtualHomeActionGrounder()
    recent_events: list[dict[str, Any]] = []
    total_action_failures = 0
    total_fallbacks = 0
    ungrounded_intents = 0
    frontier_exhaustion_count = 0
    initial = _capture_continuous_observation(
        comm,
        output_dir=output_dir,
        frames_dir=frames_dir,
        step=0,
        camera_index=camera_index,
        camera_count=camera_count,
        action="observe_initial_state",
        action_result={"success": True, "reason": "initial_observation"},
        mode=mode,
        vlm=vlm,
    )
    rows.append(initial)
    recent_events.append(
        {
            "step": 0,
            "event_type": "observation",
            "action": initial.get("action"),
            "result": initial.get("action_result", {}),
            "room": initial.get("room"),
        }
    )

    observed_rooms = {_norm(str(initial.get("room") or ""))} - {"", "unknown"}
    for step in range(1, max_steps + 1):
        policy_world_model = _build_world_model(rows, source="VirtualHome continuous policy memory", mode=mode)
        available_actions = ["scan_left", "scan_right", "observe", "stop"]
        grounding_context = _build_grounding_context(
            step=step,
            row=rows[-1],
            world_model=policy_world_model,
            recent_events=recent_events,
            final_evidence=mode == "vlm_frame_extraction",
        )
        if _frontiers_exhausted(rows[-1], policy_world_model, available_actions):
            frontier_exhaustion_count += 1
            recent_events.append(
                {
                    "step": step,
                    "event_type": "frontier_exhaustion_check",
                    "action": "",
                    "result": {"success": True, "reason": "no observation-derived frontier actions available"},
                    "room": rows[-1].get("room"),
                }
            )
            if frontier_exhaustion_count >= 2:
                rows[-1]["terminal_status"] = "partial"
                rows[-1]["terminal_reason"] = "insufficient_executable_action_grounding"
                rows[-1]["insufficient_grounding"] = True
                rows[-1]["frontier_exhausted"] = True
                rows[-1]["policy_failure_count"] = total_action_failures
                break
        else:
            frontier_exhaustion_count = 0
        context = PolicyContext(
            step=step,
            task=VIRTUALHOME_CONTINUOUS_TASK,
            observation_text=_policy_observation_text(rows[-1]),
            frame_path=str(rows[-1].get("frame") or ""),
            world_model=policy_world_model,
            recent_events=list(recent_events[-12:]),
            available_actions=available_actions,
            last_action=str(rows[-1].get("action") or "") or None,
            last_result=rows[-1].get("action_result") if isinstance(rows[-1].get("action_result"), dict) else None,
        )
        intent = policy.decide(context)
        execution = _execute_policy_intent(
            comm,
            context=context,
            intent=intent,
            policy=policy,
            grounder=grounder,
            grounding_context=grounding_context,
            total_action_failures=total_action_failures,
            max_fallbacks_remaining=max(0, int(max_fallbacks) - total_fallbacks),
        )
        action = execution["action"]
        action_result = execution["result"]
        step_fallback_events = execution["fallback_events"]
        step_grounding_events = execution["grounding_events"]
        total_action_failures += int(execution["failure_count"])
        total_fallbacks += sum(1 for event in step_fallback_events if isinstance(event, dict) and event.get("fallback_action"))
        ungrounded_intents += sum(1 for event in step_grounding_events if isinstance(event, dict) and event.get("executable") is False)
        if action_result.get("success") is not True:
            rows[-1]["terminal_status"] = "partial" if action_result.get("reason") == "insufficient_executable_action_grounding" else "failed"
            rows[-1]["terminal_reason"] = _sanitize_text(str(action_result.get("reason") or action))
            rows[-1]["insufficient_grounding"] = action_result.get("reason") == "insufficient_executable_action_grounding"
            rows[-1]["grounding_events"] = list(rows[-1].get("grounding_events") or []) + step_grounding_events
            rows[-1]["fallback_events"] = list(rows[-1].get("fallback_events") or []) + step_fallback_events
            rows[-1]["policy_failure_count"] = total_action_failures
            break
        row = _capture_continuous_observation(
            comm,
            output_dir=output_dir,
            frames_dir=frames_dir,
            step=step,
            camera_index=camera_index,
            camera_count=camera_count,
            action=action,
            action_result=action_result,
            mode=mode,
            vlm=vlm,
        )
        row["available_actions"] = available_actions
        row["policy_intent"] = action_intent_to_dict(execution["intent"])
        row["policy_decision"] = dict(row["policy_intent"])
        row["initial_policy_intent"] = action_intent_to_dict(intent)
        row["initial_policy_decision"] = dict(row["initial_policy_intent"])
        row["grounded_action"] = grounded_action_to_dict(execution["grounded_action"])
        row["grounding_events"] = step_grounding_events
        row["fallback_events"] = step_fallback_events
        row["harness_fallback_used"] = bool(step_fallback_events)
        row["policy_failure_count"] = total_action_failures
        row["action_policy_source"] = "agent_policy"
        row["action_grounding_mode"] = "observation_side_only"
        row["ungrounded_intent_count"] = ungrounded_intents
        previous = rows[-1]
        previous_room = _norm(str(previous.get("room") or "unknown"))
        current_room = _norm(str(row.get("room") or "unknown"))
        if (
            action_result.get("success") is True
            and previous_room not in {"", "unknown"}
            and current_room not in {"", "unknown"}
            and current_room != previous_room
        ):
            row.update(
                {
                    "navigation_success": True,
                    "navigation_evidence_source": "navigation_transition",
                    "navigation_from_room": previous_room,
                    "navigation_to_room": current_room,
                    "navigation_action": action,
                    "navigation_evidence_frames": [str(previous.get("frame") or ""), str(row.get("frame") or "")],
                }
            )
        rows.append(row)
        recent_events.append(
            {
                "step": step,
                "event_type": "action_decision",
                "action": action,
                "intent": row["policy_intent"],
                "grounded_action": row["grounded_action"],
                "fallback_events": step_fallback_events,
                "result": action_result,
                "room": current_room,
            }
        )
        if current_room not in {"", "unknown"}:
            observed_rooms.add(current_room)
        if total_action_failures >= MAX_CONTINUOUS_ACTION_FAILURES:
            raise VirtualHomeEvidenceError(
                f"Continuous VirtualHome action policy failed closed after {total_action_failures} failed action attempts."
            )
    return rows


def _capture_continuous_observation(
    comm: Any,
    *,
    output_dir: Path,
    frames_dir: Path,
    step: int,
    camera_index: int,
    camera_count: int | None,
    action: str,
    action_result: dict[str, Any],
    mode: str,
    vlm: tuple[VLMExtractor, QwenClient] | None,
) -> dict[str, Any]:
    frame_path = frames_dir / f"frame_{step:03d}.png"
    capture_status = _capture_frame_from_virtualhome(comm, frame_path, camera_index)
    image_info = _verify_image_file(frame_path)
    row = {
        "frame": f"frames/{frame_path.name}",
        "step": step,
        "room": "unknown",
        "action": action,
        "camera_movement": f"camera_index={camera_index}",
        "capture_mode": "continuous_episode",
        "continuous_closed_loop": True,
        "frame_validation": image_info,
        "action_result": _sanitize_action_result(action_result),
        "capture_metadata": {
            "source": "virtualhome_camera_image",
            "camera_index": camera_index,
            "camera_count": camera_count,
            "real_image": True,
            "reason": capture_status.get("reason", ""),
        },
        "notes": "Continuous episode observation captured after reset/add_character and sequential action execution.",
    }
    row["prediction_input_mode"] = mode
    row["visual_extraction"] = _extract_from_row(row, mode, output_dir=output_dir, vlm=vlm)
    return _apply_extracted_room(row)


def _frontiers_exhausted(current_row: dict[str, Any], world_model: dict[str, Any], available_actions: list[str]) -> bool:
    navigation_actions = [action for action in available_actions if "[Walk]" in action]
    if navigation_actions:
        return False
    extraction = current_row.get("visual_extraction") if isinstance(current_row.get("visual_extraction"), dict) else {}
    topology_cues = extraction.get("topology") if isinstance(extraction.get("topology"), list) else []
    frontiers = world_model.get("frontiers") if isinstance(world_model.get("frontiers"), list) else []
    return not topology_cues and not frontiers


def _build_grounding_context(
    *,
    step: int,
    row: dict[str, Any],
    world_model: dict[str, Any],
    recent_events: list[dict[str, Any]],
    final_evidence: bool,
) -> GroundingContext:
    extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
    frontiers: list[str] = []
    for cue in extraction.get("topology", []) if isinstance(extraction.get("topology"), list) else []:
        if not isinstance(cue, dict):
            continue
        if cue.get("frontier"):
            frontiers.append(str(cue.get("frontier")))
        for item in cue.get("frontiers", []) if isinstance(cue.get("frontiers"), list) else []:
            if isinstance(item, dict):
                frontiers.append(str(item.get("name") or item.get("frontier") or item.get("exit") or ""))
            else:
                frontiers.append(str(item))
    return GroundingContext(
        step=step,
        observation_text=_policy_observation_text(row),
        frame_path=str(row.get("frame") or ""),
        world_model=world_model,
        observed_objects=[dict(obj) for obj in extraction.get("objects", []) if isinstance(obj, dict)],
        recent_events=list(recent_events[-16:]),
        known_executable_targets=_known_executable_targets(world_model, recent_events),
        allowed_safe_scan_actions={
            "scan_left": "<char0> [TurnLeft]",
            "scan_right": "<char0> [TurnRight]",
        },
        current_room=str(row.get("room") or "unknown"),
        frontiers=frontiers,
        final_evidence=final_evidence,
    )


def _known_executable_targets(world_model: dict[str, Any], recent_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for event in recent_events:
        if not isinstance(event, dict):
            continue
        grounded = event.get("grounded_action") if isinstance(event.get("grounded_action"), dict) else {}
        if event.get("result", {}).get("success") is not True:
            continue
        if grounded.get("target_source") not in {"current_observation_runtime_metadata", "previously_verified_executable_target"}:
            continue
        label = _norm(str(grounded.get("target_label") or ""))
        if not label:
            continue
        targets[label] = {
            "target_label": label,
            "target_id": grounded.get("target_id"),
            "vh_script": grounded.get("vh_script"),
            "target_source": "previously_verified_executable_target",
            "confidence": grounded.get("confidence", 0.7),
        }
    return targets


def _execute_policy_intent(
    comm: Any,
    *,
    context: PolicyContext,
    intent: ActionIntent,
    policy: VirtualHomeExplorationPolicy,
    grounder: VirtualHomeActionGrounder,
    grounding_context: GroundingContext,
    total_action_failures: int,
    max_fallbacks_remaining: int = DEFAULT_MAX_FALLBACKS,
) -> dict[str, Any]:
    attempted: list[ActionIntent] = []
    fallback_events: list[dict[str, Any]] = []
    grounding_events: list[dict[str, Any]] = []
    candidates = [intent]
    grounded = grounder.ground(intent, grounding_context)
    grounding_events.append(_grounding_event(context.step, grounded))
    if not grounded.executable:
        fallback_events.append(
            {
                "event_type": "harness_fallback",
                "step": context.step,
                "reason": grounded.failure_reason or "intent_not_executable",
                "intent": intent.name,
                "target_label": intent.target_label,
                "fallback_action": "",
            }
        )
        candidates = []
    fallback_limit = min(MAX_FALLBACKS_PER_STEP, max(0, int(max_fallbacks_remaining)))
    candidates.extend(policy.fallback_intents(context, [intent])[:fallback_limit])

    failure_count = 0
    last_result: dict[str, Any] = {"success": False, "reason": "insufficient_executable_action_grounding"}
    last_intent = intent
    last_grounded = grounded
    for index, candidate in enumerate(candidates):
        if candidate not in attempted:
            attempted.append(candidate)
        candidate_grounded = grounded if candidate is intent else grounder.ground(candidate, grounding_context)
        if candidate is not intent:
            grounding_events.append(_grounding_event(context.step, candidate_grounded))
        last_intent = candidate
        last_grounded = candidate_grounded
        if not candidate_grounded.executable:
            if candidate.source == "harness_fallback":
                fallback_events.append(
                    {
                        "event_type": "harness_fallback",
                        "step": context.step,
                        "reason": candidate_grounded.failure_reason or "fallback_intent_not_executable",
                        "intent": candidate.name,
                        "target_label": candidate.target_label,
                        "fallback_action": "",
                    }
                )
            continue
        result = _execute_grounded_virtualhome_action(comm, candidate_grounded)
        last_result = result
        if candidate.source == "harness_fallback":
            fallback_events.append(
                {
                    "event_type": "harness_fallback",
                    "step": context.step,
                    "reason": candidate.reason,
                    "intent": candidate.name,
                    "target_label": candidate.target_label,
                    "fallback_action": candidate_grounded.vh_script or candidate.name,
                    "attempt_index": index,
                    "result": _sanitize_action_result(result),
                }
            )
        if result.get("success") is True:
            return {
                "action": candidate_grounded.vh_script or candidate.name,
                "intent": candidate,
                "grounded_action": candidate_grounded,
                "result": result,
                "fallback_events": fallback_events,
                "grounding_events": grounding_events,
                "failure_count": failure_count,
            }
        failure_count += 1
        if total_action_failures + failure_count >= MAX_CONTINUOUS_ACTION_FAILURES:
            break

    return {
        "action": last_grounded.vh_script or last_intent.name if last_intent else "",
        "intent": last_intent,
        "grounded_action": last_grounded,
        "result": last_result,
        "fallback_events": fallback_events,
        "grounding_events": grounding_events,
        "failure_count": failure_count,
    }


def _grounding_event(step: int, grounded: Any) -> dict[str, Any]:
    payload = grounded_action_to_dict(grounded)
    return {
        "event_type": "action_grounding",
        "step": step,
        "intent": payload["intent"].get("name"),
        "target_label": payload["intent"].get("target_label"),
        "executable": payload.get("executable"),
        "vh_script": payload.get("vh_script"),
        "target_source": payload.get("target_source"),
        "failure_reason": payload.get("failure_reason"),
        "confidence": payload.get("confidence"),
    }


def _execute_grounded_virtualhome_action(comm: Any, grounded: Any) -> dict[str, Any]:
    if not grounded.executable:
        return {"success": False, "reason": grounded.failure_reason or "not_executable"}
    if not grounded.vh_script:
        return {"success": True, "action": grounded.intent.name, "method": "observe_noop", "reason": "observe_without_runtime_action"}
    if not _is_safe_virtualhome_action(grounded.vh_script):
        return {"success": False, "action": grounded.vh_script, "reason": "unsafe_or_unsupported_grounded_action"}
    return _execute_virtualhome_action(comm, grounded.vh_script)


def _is_safe_virtualhome_action(action: str) -> bool:
    text = str(action or "").strip()
    if not text.startswith("<char0> [") or "\n" in text or "\r" in text:
        return False
    if any(token in text.lower() for token in ["environment_graph", "scene_graph", "..", ":", "\\", "/"]):
        return False
    allowed_verbs = {"walk", "turnleft", "turnright", "lookaround"}
    verb = text.split("[", 1)[1].split("]", 1)[0].strip().lower() if "[" in text and "]" in text else ""
    return verb in allowed_verbs


def _policy_observation_text(row: dict[str, Any]) -> str:
    extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
    objects = [
        str(obj.get("name") or obj.get("id") or "")
        for obj in extraction.get("objects", [])
        if isinstance(obj, dict)
    ]
    topology = [
        str(cue.get("to") or cue.get("frontier") or cue.get("room") or "")
        for cue in extraction.get("topology", [])
        if isinstance(cue, dict)
    ]
    return json.dumps(
        {
            "room": row.get("room", "unknown"),
            "frame": row.get("frame", ""),
            "visible_objects": [item for item in objects if item],
            "topology_cues": [item for item in topology if item],
            "uncertainty": extraction.get("uncertainty", []),
        },
        ensure_ascii=False,
    )


def _execute_virtualhome_action(comm: Any, action: str) -> dict[str, Any]:
    render_script = getattr(comm, "render_script", None)
    if callable(render_script):
        attempts = [
            lambda: render_script([action], recording=False, skip_animation=True),
            lambda: render_script([action], skip_animation=True),
            lambda: render_script([action]),
        ]
        for attempt in attempts:
            try:
                result = attempt()
            except TypeError:
                continue
            except Exception as exc:
                return {"success": False, "action": action, "reason": f"{type(exc).__name__}: {exc}"}
            success = _virtualhome_success(result)
            return {"success": success, "action": action, "method": "render_script", "raw_result": _summarize_virtualhome_result(result)}

    for method_name in ["execute_action", "step", "action"]:
        method = getattr(comm, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(action)
        except Exception as exc:
            return {"success": False, "action": action, "method": method_name, "reason": f"{type(exc).__name__}: {exc}"}
        success = _virtualhome_success(result)
        return {"success": success, "action": action, "method": method_name, "raw_result": _summarize_virtualhome_result(result)}

    return {
        "success": False,
        "action": action,
        "reason": "VirtualHome communication object exposes no supported action execution method.",
    }


def _virtualhome_success(result: Any) -> bool:
    if isinstance(result, tuple) and result:
        return bool(result[0])
    if isinstance(result, dict):
        for key in ["success", "ok", "status"]:
            if key in result:
                value = result[key]
                if isinstance(value, str):
                    return value.lower() in {"success", "ok", "true", "completed"}
                return bool(value)
    return bool(result)


def _summarize_virtualhome_result(result: Any) -> Any:
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    if isinstance(result, tuple):
        return [_summarize_virtualhome_result(item) for item in result[:3]]
    if isinstance(result, list):
        return [_summarize_virtualhome_result(item) for item in result[:3]]
    if isinstance(result, dict):
        return {str(key): _summarize_virtualhome_result(value) for key, value in list(result.items())[:8]}
    return type(result).__name__


def _sanitize_action_result(result: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _sanitize_text(str(value)) if isinstance(value, str) else value for key, value in result.items()}


def _capture_frame_from_virtualhome(comm: Any, frame_output: Path, camera_index: int) -> dict[str, Any]:
    method = getattr(comm, "camera_image", None)
    if not callable(method):
        raise VirtualHomeEvidenceError("VirtualHome communication object does not expose camera_image().")
    ok, images = method([camera_index], mode="normal", image_width=640, image_height=480)
    if not ok or not images:
        raise VirtualHomeEvidenceError(f"VirtualHome camera_image failed for camera_index={camera_index}.")
    _save_frame_payload(images[0], frame_output)
    return {"success": True, "reason": "virtualhome_camera_image", "camera_index": camera_index}


def _candidate_camera_indexes(comm: Any) -> tuple[int | None, list[int]]:
    method = getattr(comm, "camera_count", None)
    if not callable(method):
        return None, []
    ok, camera_count = method()
    if not ok or not isinstance(camera_count, int) or camera_count <= 0:
        return None, []
    candidates: list[int] = []
    for index in [camera_count - 1, 0, max(0, camera_count - 8)]:
        if index not in candidates and 0 <= index < camera_count:
            candidates.append(index)
    return camera_count, candidates


def _save_frame_payload(payload: Any, frame_output: Path) -> None:
    frame_output.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, Image.Image):
        payload.save(frame_output)
        return
    if isinstance(payload, bytes):
        frame_output.write_bytes(payload)
        return
    shape = getattr(payload, "shape", None)
    if shape is not None:
        array = payload
        if len(shape) == 3 and shape[2] >= 3:
            array = payload[:, :, :3][:, :, ::-1]
        Image.fromarray(array).save(frame_output)
        return
    extracted = _extract_frame_payload(payload)
    if extracted:
        frame_output.write_bytes(extracted)
        return
    raise VirtualHomeEvidenceError(f"Unsupported VirtualHome frame payload type: {type(payload).__name__}")


def _extract_frame_payload(result: Any) -> bytes | None:
    if isinstance(result, bytes):
        return result
    if isinstance(result, tuple):
        for item in result:
            payload = _extract_frame_payload(item)
            if payload:
                return payload
    if isinstance(result, dict):
        for key in ["image", "frame", "png", "jpg", "bytes"]:
            payload = _extract_frame_payload(result.get(key))
            if payload:
                return payload
    return None


def _verify_image_file(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or ""
            image.verify()
    except Exception as exc:
        raise VirtualHomeEvidenceError(f"Frame is not a valid image file: {path.name} ({type(exc).__name__}: {exc})") from exc
    if width <= 0 or height <= 0:
        raise VirtualHomeEvidenceError(f"Frame has invalid dimensions: {path.name}")
    return {"valid_image": True, "width": width, "height": height, "format": image_format}


def _write_artifacts(
    *,
    output_dir: Path,
    frame_manifest: list[dict[str, Any]],
    source: str,
    live_run: bool,
    live_runtime_connected: bool,
    attach_existing: bool,
    launch_attempted: bool,
    runtime_connection: dict[str, Any],
    synthetic_capture: bool,
    start_time: str,
    duration_seconds: float,
    prediction_input_mode: str,
    capture_mode: str,
    continuous_closed_loop: bool,
    reference_world_model: dict[str, Any],
    canonicalize: bool,
    validate: bool,
    final_submission: bool,
) -> dict[str, Any]:
    world_model = _build_world_model(frame_manifest, source=source, mode=prediction_input_mode)
    if canonicalize:
        world_model, dedup_report = canonicalize_world_model(world_model, {"frames": frame_manifest})
    else:
        dedup_report = _identity_dedup_report(world_model)
    comparison_report = _compare(world_model, reference_world_model)
    topology_summary = _topology_summary(world_model)
    policy_summary = _policy_summary(frame_manifest)
    grounding_summary = _grounding_summary(frame_manifest)
    rooms = _ordered_unique([str(row.get("room") or "unknown") for row in frame_manifest])
    predicted_rooms = [
        str(room.get("name") or room.get("id") or "")
        for room in world_model.get("rooms", [])
        if isinstance(room, dict) and str(room.get("name") or room.get("id") or "").strip()
    ]
    reference_rooms = _reference_rooms(reference_world_model)
    mock_extraction = prediction_input_mode == "mock_visual_extraction" or any(
        bool(row.get("visual_extraction", {}).get("mock"))
        for row in frame_manifest
        if isinstance(row.get("visual_extraction"), dict)
    )
    evidence_level = _classify_evidence_level(
        prediction_input_mode=prediction_input_mode,
        capture_mode=capture_mode,
        continuous_closed_loop=continuous_closed_loop,
        live_run=live_run,
        live_runtime_connected=live_runtime_connected,
        synthetic_capture=synthetic_capture,
        mock_extraction=mock_extraction,
    )
    if grounding_summary["final_status"] != "success" and evidence_level != EVIDENCE_MOCK_CI:
        evidence_level = EVIDENCE_VISUAL_REPLAY
    reference_source = str(reference_world_model.get("source") or "virtualhome_manifest_reference_fallback")
    reference_note = (
        "VirtualHome scene graph data is reference-only."
        if reference_source == "virtualhome_scene_graph_answer_key"
        else "Reference data is loaded from explicit replay annotations/reference files only."
    )
    coverage = {
        "source": source,
        "evidence_level": evidence_level,
        "official_score": False,
        "world_model_source": _world_model_source(prediction_input_mode),
        "prediction_input_mode": prediction_input_mode,
        "visual_extractor_mode": prediction_input_mode,
        "capture_mode": capture_mode,
        "continuous_closed_loop": bool(continuous_closed_loop),
        "live_runtime_connected": bool(live_runtime_connected),
        "synthetic_capture": bool(synthetic_capture),
        "mock_extraction": bool(mock_extraction),
        "reference_model_source": reference_source,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "action_policy_source": policy_summary["action_policy_source"],
        "action_decision_count": policy_summary["action_decision_count"],
        "harness_fallback_count": policy_summary["harness_fallback_count"],
        "harness_fallback_used": policy_summary["harness_fallback_used"],
        "policy_failure_count": policy_summary["policy_failure_count"],
        "policy_failure_closed": False,
        "action_grounding_mode": "observation_side_only",
        "grounded_action_count": grounding_summary["grounded_action_count"],
        "ungrounded_intent_count": grounding_summary["ungrounded_intent_count"],
        "grounding_target_sources": grounding_summary["target_sources"],
        "fallback_reasons": grounding_summary["fallback_reasons"],
        "insufficient_grounding": grounding_summary["insufficient_grounding"],
        "final_status": grounding_summary["final_status"],
        "termination_reason": grounding_summary["termination_reason"],
        "not_final_evidence": grounding_summary["final_status"] != "success",
        "rooms_expected": reference_rooms,
        "predicted_rooms": predicted_rooms,
        "rooms_visited": rooms,
        "reference_rooms": reference_rooms,
        "room_coverage": comparison_report["rooms"]["recall"],
        "room_coverage_against_reference": comparison_report["rooms"]["recall"],
        "comparison_room_recall": comparison_report["rooms"]["recall"],
        "exploration_trace_length": len(world_model.get("exploration_trace", [])),
        "frames_used": len(frame_manifest),
        "objects_detected": len(world_model.get("objects", [])),
        "relations_detected": len(world_model.get("relations", [])),
        "topology_edges": topology_summary["topology_edges"],
        "predicted_topology_edges": topology_summary["topology_edges"],
        "reference_topology_edges": len(reference_world_model["topology"]["edges"]),
        "verified_topology_edges": topology_summary["verified_topology_edges"],
        "inferred_visual_topology_edges": topology_summary["inferred_visual_topology_edges"],
        "inferred_sequence_edges": len(world_model.get("exploration_order_edges", [])),
        "exploration_order_edges": len(world_model.get("exploration_order_edges", [])),
        "scene_graph_diagnostic_edges": 0,
        "topology_source": world_model["topology"]["topology_source"],
        "topology_precision": comparison_report["topology"]["precision"],
        "topology_recall": comparison_report["topology"]["recall"],
        "validation_passed": True,
        "notes": (
            f"{OFFICIAL_SCORE_NOTE} Predicted world_model.json is generated from visual_extraction and action traces. "
            f"{reference_note}"
        ),
    }
    visual_task_result = {
        "status": "complete" if grounding_summary["final_status"] == "success" else grounding_summary["final_status"],
        "evidence_level": evidence_level,
        "answer": "multi-room exploration evidence generated",
        "confidence": 0.8,
        "supporting_evidence": ["world_model.json", "coverage_report.json", "comparison_report.json"],
        "contradicting_evidence": [],
        "missing_evidence": [],
        "insufficient_grounding": grounding_summary["insufficient_grounding"],
        "not_final_evidence": grounding_summary["final_status"] != "success",
    }
    _write_json(output_dir / "world_model.json", world_model)
    _write_json(output_dir / "reference_world_model.json", reference_world_model)
    _write_json(output_dir / "comparison_report.json", comparison_report)
    _write_json(output_dir / "dedup_report.json", dedup_report)
    _write_json(output_dir / "frame_manifest.json", {"frames": frame_manifest})
    _write_json(output_dir / "coverage_report.json", coverage)
    _write_json(output_dir / "visual_task_result.json", visual_task_result)
    validation_summary = {"passed": True, "errors": [], "warnings": []}
    _write_episode_log(output_dir / "episode_log.jsonl", frame_manifest, world_model, validation_summary)
    audit = _build_audit(
        live_run=live_run,
        live_runtime_connected=live_runtime_connected,
        attach_existing=attach_existing,
        launch_attempted=launch_attempted,
        runtime_connection=runtime_connection,
        start_time=start_time,
        duration_seconds=duration_seconds,
        coverage=coverage,
        validation_summary=validation_summary,
    )
    _write_json(output_dir / "run_audit.json", audit)
    if validate:
        from validators.validate_virtualhome_exploration import validate_detailed

        validation_summary = {
            **validate_detailed(output_dir, final_submission=final_submission),
        }
        validation_summary["passed"] = not validation_summary["errors"]
        coverage["validation_passed"] = bool(validation_summary["passed"])
        _write_json(output_dir / "coverage_report.json", coverage)
    _write_episode_log(output_dir / "episode_log.jsonl", frame_manifest, world_model, validation_summary)
    audit = _build_audit(
        live_run=live_run,
        live_runtime_connected=live_runtime_connected,
        attach_existing=attach_existing,
        launch_attempted=launch_attempted,
        runtime_connection=runtime_connection,
        start_time=start_time,
        duration_seconds=duration_seconds,
        coverage=coverage,
        validation_summary=validation_summary,
    )
    _write_json(output_dir / "run_audit.json", audit)
    write_harness_result(
        output_dir,
        mode="virtualhome_exploration",
        success=bool(validation_summary.get("passed", True)),
        validation_status=validation_summary,
        errors=list(validation_summary.get("errors", [])),
        extra={
            "coverage_report_path": "coverage_report.json",
            "frame_manifest_path": "frame_manifest.json",
            "visual_task_result_path": "visual_task_result.json",
            "reference_world_model_path": "reference_world_model.json",
            "comparison_report_path": "comparison_report.json",
            "dedup_report_path": "dedup_report.json",
        },
    )
    _write_report(output_dir / "virtualhome_exploration_report.md", coverage, world_model, reference_world_model, comparison_report, dedup_report)
    return {"success": bool(validation_summary.get("passed", True)), "coverage_report": coverage}


def _build_world_model(frame_manifest: list[dict[str, Any]], *, source: str, mode: str) -> dict[str, Any]:
    rooms = _rooms_from_manifest_and_extraction(frame_manifest)
    frame_by_room = {room: [row["frame"] for row in frame_manifest if row.get("room") == room] for room in rooms}
    objects: list[dict[str, Any]] = []
    object_index: dict[tuple[str, str], dict[str, Any]] = {}
    states: list[dict[str, Any]] = []
    uncertainty: list[dict[str, Any]] = []
    for row in frame_manifest:
        room = _norm(str(row.get("room") or "unknown"))
        frame = str(row.get("frame") or "")
        extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
        for item in extraction.get("objects", []) if isinstance(extraction.get("objects"), list) else []:
            name = _norm(str(item.get("name") or item.get("id") or "object"))
            item_location = item.get("location") if isinstance(item.get("location"), dict) else {}
            item_room = _norm(str(item.get("room") or item_location.get("room") or room or "unknown"))
            room = item_room or room
            key = (room, name)
            obj = object_index.get(key)
            if obj is None:
                obj = {
                    "id": f"pred_{_slug(room)}_{_slug(name)}",
                    "name": name,
                    "category": str(item.get("category") or "visual_observation"),
                    "location": {"room": room, "region": "observed_view", "support": "", "status": "known", "confidence": _safe_float(item.get("confidence"), 0.65)},
                    "state": "observed",
                    "confidence": _safe_float(item.get("confidence"), 0.65),
                    "source": extraction.get("source", mode),
                    "prediction_input_mode": mode,
                    "evidence_frames": [],
                    "raw_mentions": [],
                    "original_ids": [str(item.get("id") or "")],
                }
                object_index[key] = obj
                objects.append(obj)
            obj["evidence_frames"] = _ordered_unique([*obj.get("evidence_frames", []), frame])
            obj["raw_mentions"].append(
                {
                    "frame": frame,
                    "step": int(row.get("step", 0)),
                    "room": room,
                    "label": name,
                    "source": extraction.get("source", mode),
                    "prediction_input_mode": mode,
                    "reference_used_for_generation": False,
                }
            )
        states.extend(extraction.get("states", []) if isinstance(extraction.get("states"), list) else [])
        uncertainty.extend(extraction.get("uncertainty", []) if isinstance(extraction.get("uncertainty"), list) else [])
    relations = [
        {
            "subject": obj["id"],
            "subject_label": obj["name"],
            "relation": "inside",
            "object": obj["location"]["room"],
            "object_label": obj["location"]["room"],
            "status": "active",
            "confidence": obj.get("confidence", 0.65),
            "observed_at_step": 0,
            "source": obj.get("source", mode),
            "prediction_input_mode": mode,
            "evidence_frames": obj.get("evidence_frames", []),
        }
        for obj in objects
    ]
    topology_edges = _visual_topology_edges(frame_manifest) + _navigation_topology_edges(frame_manifest)
    exploration_order_edges = _exploration_order_edges(frame_manifest)
    grounding_summary = _grounding_summary(frame_manifest)
    topology_nodes = _ordered_unique(
        [*rooms, *[str(edge.get("from")) for edge in topology_edges], *[str(edge.get("to")) for edge in topology_edges]]
    )
    return {
        "episode_id": "virtualhome-multi-room-exploration",
        "source": _world_model_source(mode),
        "input_source": source,
        "world_model_source": _world_model_source(mode),
        "prediction_input_mode": mode,
        "visual_extractor_mode": mode,
        "reference_used_for_generation": False,
        "official_score": False,
        "rooms": [{"id": room, "name": room, "category": "room", "evidence_frames": frame_by_room.get(room, [])} for room in rooms],
        "topology": {
            "nodes": [{"room": room, "node_type": "room", "visited": room in rooms, "evidence_frames": frame_by_room.get(room, [])} for room in topology_nodes],
            "edges": topology_edges,
            "topology_source": _world_model_source(mode),
            "notes": "Chronological room visits are stored separately in exploration_trace and exploration_order_edges.",
        },
        "room_connectivity": [],
        "exploration_trace": _exploration_trace(frame_manifest),
        "exploration_order_edges": exploration_order_edges,
        "visited_rooms": rooms,
        "frontiers": [],
        "objects": objects,
        "relations": relations,
        "states": states,
        "affordances": [],
        "uncertainty": [{"entity": "reference_model", "attribute": "generation", "level": "low", "reason": "Scene graph is reference-only."}] + uncertainty,
        "evidence_trace": _prediction_rows(frame_manifest),
        "policy_trace": _policy_trace(frame_manifest),
        "action_grounding_mode": "observation_side_only",
        "action_grounding_trace": _action_grounding_trace(frame_manifest),
        "plans": [
            {
                "planner": "VirtualHomeExplorationPolicy",
                "type": "closed_loop_exploration",
                "source": "agent_policy",
                "task": VIRTUALHOME_CONTINUOUS_TASK,
                "actions": [
                    row.get("policy_decision", {}).get("action")
                    for row in frame_manifest
                    if isinstance(row.get("policy_decision"), dict) and row.get("policy_decision", {}).get("action")
                ],
                "subgoals": [
                    "Use current visual observations to select exploration intents.",
                    "Ground intents only through observation-side executable targets or safe scan actions.",
                    "Execute bounded safe VirtualHome actions when grounding succeeds.",
                    "Update the predicted world model from post-action observations.",
                ],
            }
        ],
        "task_status": {
            "status": "complete" if grounding_summary["final_status"] == "success" else grounding_summary["final_status"],
            "success": grounding_summary["final_status"] == "success",
            "reason": grounding_summary["termination_reason"] or f"Generated with prediction_input_mode={mode}.",
            "insufficient_grounding": grounding_summary["insufficient_grounding"],
        },
    }


def _visual_topology_edges(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in frame_manifest:
        extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
        for cue in extraction.get("topology", []) if isinstance(extraction.get("topology"), list) else []:
            if not isinstance(cue, dict):
                continue
            for edge_spec in _frame_extraction_topology_edges(cue, row, extraction):
                source_room = edge_spec["from"]
                target_room = edge_spec["to"]
                relation = edge_spec["relation"]
                key = (source_room, target_room, relation)
                edges.setdefault(
                    key,
                    {
                        "from": source_room,
                        "to": target_room,
                        "relation": relation,
                        "status": "inferred",
                        "evidence_source": edge_spec["evidence_source"],
                        "evidence_frames": [],
                        "action": str(row.get("action") or ""),
                        "confidence": edge_spec["confidence"],
                    },
                )
                if edge_spec.get("evidence"):
                    edges[key]["evidence"] = edge_spec["evidence"]
                if edge_spec.get("frontier"):
                    edges[key]["frontier"] = edge_spec["frontier"]
                edges[key]["confidence"] = max(_safe_float(edges[key].get("confidence"), 0.0), edge_spec["confidence"])
                edges[key]["evidence_frames"] = _ordered_unique([*edges[key]["evidence_frames"], str(row.get("frame") or "")])
    return list(edges.values())


def _frame_extraction_topology_edges(
    cue: dict[str, Any],
    row: dict[str, Any],
    extraction: dict[str, Any],
) -> list[dict[str, Any]]:
    if cue.get("from") or cue.get("to"):
        source_room = _norm(str(cue.get("from") or row.get("room") or "unknown"))
        target_room = _norm(str(cue.get("to") or "unknown_frontier_doorway"))
        relation = _norm(str(cue.get("relation") or "connected_to"))
        if not source_room or not target_room:
            return []
        return [
            {
                "from": source_room,
                "to": target_room,
                "relation": relation,
                "evidence_source": "vlm_frame_extraction"
                if extraction.get("source") == "vlm_frame_extraction"
                else "visual_doorway_or_passage_cue",
                "confidence": _safe_float(cue.get("confidence"), 0.55),
                "evidence": str(cue.get("evidence") or cue.get("cue") or "visible doorway or passage cue"),
            }
        ]

    source_room = _norm(str(cue.get("room") or row.get("room") or "unknown"))
    frontiers = cue.get("frontiers")
    if not isinstance(frontiers, list):
        frontiers = []
    edges = []
    for frontier in frontiers:
        target_room, frontier_label = _legacy_frontier_target(frontier)
        if not source_room or not target_room:
            continue
        edges.append(
            {
                "from": source_room,
                "to": target_room,
                "relation": "connected_to",
                "evidence_source": "visual_doorway_or_passage_cue",
                "confidence": _safe_float(_frontier_value(frontier, "confidence", cue.get("confidence")), 0.55),
                "evidence": str(cue.get("evidence") or cue.get("cue") or f"visible frontier: {frontier_label}"),
                "frontier": frontier_label,
            }
        )
    return edges


def _legacy_frontier_target(frontier: Any) -> tuple[str, str]:
    if isinstance(frontier, dict):
        label = str(
            frontier.get("name")
            or frontier.get("frontier")
            or frontier.get("via")
            or frontier.get("exit")
            or frontier.get("target")
            or frontier.get("to")
            or "unknown_frontier"
        )
        target = str(frontier.get("target") or frontier.get("to") or "")
        return _norm(target) if target else "unknown_frontier_doorway", _norm(label)
    label = _norm(str(frontier or "unknown_frontier"))
    return "unknown_frontier_doorway", label


def _frontier_value(frontier: Any, key: str, default: Any = None) -> Any:
    if isinstance(frontier, dict):
        return frontier.get(key, default)
    return default


def _navigation_topology_edges(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in frame_manifest:
        if row.get("navigation_success") is not True:
            continue
        if row.get("navigation_evidence_source") != "navigation_transition":
            continue
        source = _norm(str(row.get("navigation_from_room") or ""))
        target = _norm(str(row.get("navigation_to_room") or row.get("room") or ""))
        if not source or not target or source == target or (source, target) in seen:
            continue
        seen.add((source, target))
        frames = row.get("navigation_evidence_frames")
        if not isinstance(frames, list):
            frames = [str(row.get("frame") or "")]
        edges.append(
            {
                "from": source,
                "to": target,
                "relation": "connected_to",
                "status": "verified",
                "evidence_source": "navigation_transition",
                "evidence_frames": [str(frame) for frame in frames],
                "action": str(row.get("navigation_action") or row.get("action") or ""),
                "confidence": 0.8,
            }
        )
    return edges


def _exploration_order_edges(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    previous_room = ""
    previous_frame = ""
    seen: set[tuple[str, str]] = set()
    for row in frame_manifest:
        room = _norm(str(row.get("room") or "unknown"))
        frame = str(row.get("frame") or "")
        if previous_room and room != previous_room and (previous_room, room) not in seen:
            seen.add((previous_room, room))
            edges.append(
                {
                    "from": previous_room,
                    "to": room,
                    "relation": "visited_after",
                    "status": "inferred_from_sequence",
                    "evidence_source": "frame_manifest_order",
                    "evidence_frames": [previous_frame, frame],
                    "action": "chronological order only",
                    "confidence": 0.35,
                }
            )
        previous_room = room
        previous_frame = frame
    return edges


def _exploration_trace(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": int(row.get("step", index)),
            "frame": str(row.get("frame") or ""),
            "room": str(row.get("room") or "unknown"),
            "action": str(row.get("action") or ""),
            "camera_movement": str(row.get("camera_movement") or ""),
            "evidence_source": "frame_manifest",
        }
        for index, row in enumerate(frame_manifest)
    ]


def _prediction_rows(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in frame_manifest:
        extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
        rows.append(
            {
                "frame": str(row.get("frame") or ""),
                "step": int(row.get("step", len(rows))),
                "room": str(row.get("room") or "unknown"),
                "action": str(row.get("action") or ""),
                "prediction_input_mode": str(row.get("prediction_input_mode") or extraction.get("source") or ""),
                "visual_extraction": {
                    "source": str(extraction.get("source") or ""),
                    "mock": bool(extraction.get("mock", False)),
                    "synthetic": bool(extraction.get("synthetic", False)),
                    "objects": list(extraction.get("objects") or []),
                    "relations": list(extraction.get("relations") or []),
                    "uncertainty": list(extraction.get("uncertainty") or []),
                    "model_call": dict(extraction.get("model_call") or {}),
                },
                "reference_used_for_generation": False,
                "evidence_source": "visual_observation_pipeline",
            }
        )
    return rows


def _policy_trace(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace = []
    for row in frame_manifest:
        decision = row.get("policy_decision") if isinstance(row.get("policy_decision"), dict) else {}
        if not decision:
            continue
        trace.append(
            {
                "step": int(row.get("step", len(trace))),
                "frame": str(row.get("frame") or ""),
                "action": str(row.get("action") or decision.get("action") or ""),
                "decision": dict(decision),
                "available_actions": [str(action) for action in row.get("available_actions", []) if str(action)],
                "fallback_events": list(row.get("fallback_events") or []),
                "action_result": dict(row.get("action_result") or {}),
                "reference_used_for_generation": False,
            }
        )
    return trace


def _action_grounding_trace(frame_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for row in frame_manifest:
        for event in row.get("grounding_events", []) if isinstance(row.get("grounding_events"), list) else []:
            if not isinstance(event, dict):
                continue
            trace.append(
                {
                    "step": int(row.get("step", len(trace))),
                    "frame": str(row.get("frame") or ""),
                    "event_type": "action_grounding",
                    "intent": str(event.get("intent") or ""),
                    "target_label": str(event.get("target_label") or ""),
                    "executable": bool(event.get("executable", False)),
                    "vh_script": str(event.get("vh_script") or ""),
                    "target_source": str(event.get("target_source") or ""),
                    "failure_reason": str(event.get("failure_reason") or ""),
                    "reference_used_for_generation": False,
                }
            )
    return trace


def _rooms_from_manifest_and_extraction(frame_manifest: list[dict[str, Any]]) -> list[str]:
    rooms: list[str] = []
    for row in frame_manifest:
        row_room = _norm(str(row.get("room") or "unknown"))
        if row_room:
            rooms.append(row_room)
        extraction = row.get("visual_extraction") if isinstance(row.get("visual_extraction"), dict) else {}
        extracted_rooms = extraction.get("rooms")
        if isinstance(extracted_rooms, list):
            for item in extracted_rooms:
                if isinstance(item, dict):
                    rooms.append(_norm(str(item.get("name") or item.get("id") or item.get("room") or "")))
                else:
                    rooms.append(_norm(str(item or "")))
        for obj in extraction.get("objects", []) if isinstance(extraction.get("objects"), list) else []:
            if not isinstance(obj, dict):
                continue
            location = obj.get("location") if isinstance(obj.get("location"), dict) else {}
            rooms.append(_norm(str(obj.get("room") or location.get("room") or "")))
    cleaned = [room for room in rooms if room]
    return _ordered_unique(cleaned or ["unknown"])


def _load_reference_world_model(manifest_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference_path = manifest_dir / "reference_world_model.json"
    if reference_path.exists():
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise VirtualHomeEvidenceError("reference_world_model.json must be a JSON object.")
        payload.setdefault("source", "virtualhome_manifest_reference_fallback")
        payload.setdefault("official_score", False)
        payload.setdefault("reference_model", True)
        payload.setdefault("used_for_generation", False)
        payload.setdefault("used_for_validation", True)
        payload.setdefault("used_for_prediction_generation", False)
        return payload
    return _build_reference_world_model_from_manifest(rows)


def _build_reference_world_model_from_manifest(frame_manifest: list[dict[str, Any]]) -> dict[str, Any]:
    rooms = _ordered_unique([_norm(str(row.get("room") or "unknown")) for row in frame_manifest])
    objects: list[dict[str, Any]] = []
    seen_objects: set[tuple[str, str]] = set()
    for row in frame_manifest:
        room = _norm(str(row.get("room") or "unknown"))
        for name in _reference_object_names(row):
            key = (room, _norm(name))
            if key in seen_objects:
                continue
            seen_objects.add(key)
            objects.append(
                {
                    "id": f"ref_{_slug(room)}_{_slug(name)}",
                    "name": _norm(name),
                    "room": room,
                    "source": "virtualhome_manifest_reference_fallback",
                }
            )
    return {
        "episode_id": "virtualhome-multi-room-exploration-reference",
        "source": "virtualhome_manifest_reference_fallback",
        "official_score": False,
        "reference_model": True,
        "used_for_generation": False,
        "used_for_validation": True,
        "used_for_prediction_generation": False,
        "rooms": rooms,
        "objects": objects,
        "relations": [],
        "topology": {"nodes": [{"room": room} for room in rooms], "edges": [], "topology_source": "manifest_reference_fallback"},
    }


def _reference_object_names(row: dict[str, Any]) -> list[str]:
    for key in ["reference_visible_objects", "expected_visible_objects"]:
        values = row.get(key)
        if isinstance(values, list):
            return [str(value) for value in values if str(value).strip()]
    return []


def _build_reference_world_model_from_scene_graph(scene_graph: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in scene_graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in scene_graph.get("edges", []) if isinstance(edge, dict)]
    room_ids: set[str] = set()
    room_names: dict[str, str] = {}
    for node in nodes:
        node_id = str(node.get("id") or "")
        category = str(node.get("category") or "").lower()
        class_name = _norm(str(node.get("class_name") or node.get("name") or "unknown"))
        if category in {"rooms", "room"} or class_name in {"bathroom", "bedroom", "kitchen", "livingroom", "living_room", "hallway"}:
            room_ids.add(node_id)
            room_names[node_id] = class_name
    object_room: dict[str, str] = {}
    relations: list[dict[str, Any]] = []
    topology_edges: list[dict[str, Any]] = []
    for edge in edges:
        source_id = str(edge.get("from_id") or edge.get("from") or "")
        target_id = str(edge.get("to_id") or edge.get("to") or "")
        relation = _norm(str(edge.get("relation_type") or edge.get("relation") or ""))
        if source_id in room_ids and target_id in room_ids:
            topology_edges.append(
                {
                    "from": room_names.get(source_id, source_id),
                    "to": room_names.get(target_id, target_id),
                    "relation": relation or "connected_to",
                    "status": "diagnostic",
                    "evidence_source": "scene_graph_diagnostic_answer_key",
                    "evidence_frames": [],
                    "action": "reference scene graph only",
                    "confidence": 0.9,
                }
            )
        if target_id in room_ids:
            object_room[source_id] = room_names[target_id]
        relations.append(
            {
                "subject": source_id,
                "relation": relation or "related_to",
                "object": target_id,
                "status": "active",
                "confidence": 1.0,
                "source": "virtualhome_scene_graph_answer_key",
            }
        )
    objects = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id in room_ids:
            continue
        name = _norm(str(node.get("class_name") or node.get("name") or node_id or "object"))
        objects.append(
            {
                "id": f"ref_{node_id}" if node_id else f"ref_{_slug(name)}",
                "name": name,
                "room": object_room.get(node_id, "unknown"),
                "source": "virtualhome_scene_graph_answer_key",
            }
        )
    rooms = _ordered_unique(list(room_names.values()))
    return {
        "episode_id": "virtualhome-multi-room-exploration-reference",
        "source": "virtualhome_scene_graph_answer_key",
        "official_score": False,
        "reference_model": True,
        "used_for_generation": False,
        "used_for_validation": True,
        "used_for_prediction_generation": False,
        "rooms": rooms,
        "objects": objects,
        "relations": relations,
        "topology": {
            "nodes": [{"room": room} for room in rooms],
            "edges": topology_edges,
            "topology_source": "scene_graph_diagnostic_answer_key",
        },
    }


def _compare(predicted: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    predicted_rooms = {str(room.get("name") or room.get("id")) for room in predicted.get("rooms", []) if isinstance(room, dict)}
    reference_rooms = {
        str(room.get("name") or room.get("id")) if isinstance(room, dict) else str(room)
        for room in reference.get("rooms", [])
    }
    predicted_objects = {_norm(str(obj.get("name") or "")) for obj in predicted.get("objects", []) if isinstance(obj, dict)}
    reference_objects = {_norm(str(obj.get("name") or "")) for obj in reference.get("objects", []) if isinstance(obj, dict)}
    predicted_topology = {_edge_key(edge) for edge in predicted.get("topology", {}).get("edges", []) if isinstance(edge, dict)}
    reference_topology = {_edge_key(edge) for edge in reference.get("topology", {}).get("edges", []) if isinstance(edge, dict)}
    return {
        "source": "prediction_vs_reference_comparison",
        "official_score": False,
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "rooms": _metric(predicted_rooms, reference_rooms, include_reference=True),
        "objects": _metric(predicted_objects, reference_objects),
        "relations": _metric(set(), set()),
        "topology": _metric(predicted_topology, reference_topology),
    }


def _metric(predicted: set[str], reference: set[str], *, include_reference: bool = False) -> dict[str, Any]:
    matched = sorted(predicted & reference)
    missed = sorted(reference - predicted)
    spurious = sorted(predicted - reference)
    block = {
        "precision": round(len(matched) / max(1, len(predicted)), 3),
        "recall": round(len(matched) / max(1, len(reference)), 3),
        "matched": matched,
        "missed": missed,
        "spurious": spurious,
    }
    if include_reference:
        block["reference"] = sorted(reference)
    return block


def _edge_key(edge: dict[str, Any]) -> str:
    endpoints = sorted([_norm(str(edge.get("from") or "")), _norm(str(edge.get("to") or ""))])
    return f"{endpoints[0]}|{_norm(str(edge.get('relation') or 'connected_to'))}|{endpoints[1]}"


def _topology_summary(world_model: dict[str, Any]) -> dict[str, int | str]:
    edges = world_model.get("topology", {}).get("edges", [])
    if not isinstance(edges, list):
        edges = []
    return {
        "topology_edges": len(edges),
        "verified_topology_edges": sum(1 for edge in edges if isinstance(edge, dict) and edge.get("status") == "verified"),
        "inferred_visual_topology_edges": sum(
            1
            for edge in edges
            if isinstance(edge, dict)
            and edge.get("status") == "inferred"
            and edge.get("evidence_source") in {"visual_doorway_or_passage_cue", "vlm_frame_extraction"}
        ),
    }


def _policy_summary(frame_manifest: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = [
        row.get("policy_decision")
        for row in frame_manifest
        if isinstance(row.get("policy_decision"), dict) and row.get("policy_decision", {}).get("action")
    ]
    fallback_events = [
        event
        for row in frame_manifest
        for event in row.get("fallback_events", [])
        if isinstance(event, dict)
    ]
    return {
        "action_policy_source": "agent_policy" if decisions else "none",
        "action_decision_count": len(decisions),
        "harness_fallback_count": len(fallback_events),
        "harness_fallback_used": bool(fallback_events),
        "policy_failure_count": max(
            [int(row.get("policy_failure_count") or 0) for row in frame_manifest if isinstance(row, dict)] or [0]
        ),
    }


def _grounding_summary(frame_manifest: list[dict[str, Any]]) -> dict[str, Any]:
    grounding_events = [
        event
        for row in frame_manifest
        for event in row.get("grounding_events", [])
        if isinstance(event, dict)
    ]
    fallback_events = [
        event
        for row in frame_manifest
        for event in row.get("fallback_events", [])
        if isinstance(event, dict)
    ]
    target_sources = sorted(
        {
            str(event.get("target_source"))
            for event in grounding_events
            if event.get("executable") is True and str(event.get("target_source") or "")
        }
    )
    fallback_reasons: dict[str, int] = {}
    for event in fallback_events:
        reason = str(event.get("reason") or "unknown")
        fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
    terminal_rows = [row for row in frame_manifest if row.get("terminal_status")]
    final_status = str(terminal_rows[-1].get("terminal_status")) if terminal_rows else "success"
    termination_reason = str(terminal_rows[-1].get("terminal_reason")) if terminal_rows else "completed"
    insufficient_grounding = any(bool(row.get("insufficient_grounding")) for row in frame_manifest)
    return {
        "grounded_action_count": sum(1 for event in grounding_events if event.get("executable") is True),
        "ungrounded_intent_count": sum(1 for event in grounding_events if event.get("executable") is False),
        "target_sources": target_sources,
        "harness_fallback_count": len(fallback_events),
        "fallback_reasons": fallback_reasons,
        "insufficient_grounding": insufficient_grounding,
        "final_status": final_status,
        "termination_reason": termination_reason,
    }


def _classify_evidence_level(
    *,
    prediction_input_mode: str,
    capture_mode: str,
    continuous_closed_loop: bool,
    live_run: bool,
    live_runtime_connected: bool,
    synthetic_capture: bool,
    mock_extraction: bool,
) -> str:
    if mock_extraction or prediction_input_mode == "mock_visual_extraction":
        return EVIDENCE_MOCK_CI
    if (
        prediction_input_mode == "vlm_frame_extraction"
        and capture_mode == "continuous_episode"
        and continuous_closed_loop
        and live_run
        and live_runtime_connected
        and not synthetic_capture
    ):
        return EVIDENCE_CLOSED_LOOP
    if capture_mode in {"replay", "keyframe_capture"}:
        return EVIDENCE_VISUAL_REPLAY
    return EVIDENCE_VISUAL_REPLAY


def _reference_rooms(reference_world_model: dict[str, Any]) -> list[str]:
    rooms: list[str] = []
    for room in reference_world_model.get("rooms", []):
        if isinstance(room, dict):
            value = room.get("name") or room.get("id") or room.get("room")
        else:
            value = room
        normalized = _norm(str(value or ""))
        if normalized:
            rooms.append(normalized)
    return _ordered_unique(rooms)


def _identity_dedup_report(world_model: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_object_mentions": len(world_model.get("objects", [])),
        "unique_objects": len(world_model.get("objects", [])),
        "raw_relation_mentions": len(world_model.get("relations", [])),
        "unique_relations": len(world_model.get("relations", [])),
        "merged_object_clusters": [],
        "alias_merges": [],
        "objects_by_room": {},
        "active_relations": len(world_model.get("relations", [])),
        "stale_relations": 0,
        "warnings": [],
    }


def _build_audit(
    *,
    live_run: bool,
    live_runtime_connected: bool,
    attach_existing: bool,
    launch_attempted: bool,
    runtime_connection: dict[str, Any],
    start_time: str,
    duration_seconds: float,
    coverage: dict[str, Any],
    validation_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "start_time": start_time,
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_seconds,
        "episode_id": "virtualhome-multi-room-exploration",
        "env": "virtualhome_live" if live_run else "virtualhome_replay",
        "success": bool(validation_summary.get("passed", True)),
        "virtualhome_live_run": bool(live_run),
        "live_runtime_connected": bool(live_runtime_connected),
        "launch_attempted": bool(launch_attempted),
        "attach_existing": bool(attach_existing),
        "runtime_connection": _sanitize_runtime_connection(runtime_connection),
        "evidence_level": coverage["evidence_level"],
        "official_score": False,
        "world_model_source": coverage["world_model_source"],
        "prediction_input_mode": coverage["prediction_input_mode"],
        "visual_extractor_mode": coverage["visual_extractor_mode"],
        "capture_mode": coverage["capture_mode"],
        "continuous_closed_loop": bool(coverage["continuous_closed_loop"]),
        "synthetic_capture": bool(coverage.get("synthetic_capture", False)),
        "mock_extraction": bool(coverage.get("mock_extraction", False)),
        "reference_model_source": coverage["reference_model_source"],
        "reference_used_for_generation": False,
        "reference_used_for_validation": True,
        "action_policy_source": coverage.get("action_policy_source", "none"),
        "action_decision_count": coverage.get("action_decision_count", 0),
        "harness_fallback_count": coverage.get("harness_fallback_count", 0),
        "harness_fallback_used": coverage.get("harness_fallback_used", False),
        "policy_failure_count": coverage.get("policy_failure_count", 0),
        "policy_failure_closed": coverage.get("policy_failure_closed", False),
        "action_grounding_mode": coverage.get("action_grounding_mode", "observation_side_only"),
        "grounded_action_count": coverage.get("grounded_action_count", 0),
        "ungrounded_intent_count": coverage.get("ungrounded_intent_count", 0),
        "grounding_target_sources": coverage.get("grounding_target_sources", []),
        "fallback_reasons": coverage.get("fallback_reasons", {}),
        "insufficient_grounding": coverage.get("insufficient_grounding", False),
        "final_status": coverage.get("final_status", "success"),
        "termination_reason": coverage.get("termination_reason", ""),
        "not_final_evidence": coverage.get("not_final_evidence", False),
        "rooms_visited_count": len(coverage["rooms_visited"]),
        "room_coverage": coverage["room_coverage"],
        "frames_used": coverage["frames_used"],
        "exploration_trace_length": coverage["exploration_trace_length"],
        "verified_topology_edges": coverage["verified_topology_edges"],
        "inferred_visual_topology_edges": coverage["inferred_visual_topology_edges"],
        "inferred_sequence_edges": coverage["inferred_sequence_edges"],
        "exploration_order_edges": coverage["exploration_order_edges"],
        "scene_graph_diagnostic_edges": coverage["scene_graph_diagnostic_edges"],
        "topology_source": coverage["topology_source"],
        "topology_notes": coverage["notes"],
        "world_model_path": "world_model.json",
        "reference_world_model_path": "reference_world_model.json",
        "comparison_report_path": "comparison_report.json",
        "episode_log_path": "episode_log.jsonl",
        "coverage_report_path": "coverage_report.json",
        "frame_manifest_path": "frame_manifest.json",
        "visual_task_result_path": "visual_task_result.json",
        "dedup_report_path": "dedup_report.json",
        "validation_status": validation_summary,
        "warnings": list(validation_summary.get("warnings", [])),
        "errors": list(validation_summary.get("errors", [])),
        "output_dir": ".",
    }


def _write_episode_log(path: Path, rows: list[dict[str, Any]], world_model: dict[str, Any], validation: dict[str, Any]) -> None:
    logger = EpisodeLogger(path)
    for row in rows:
        extraction = row.get("visual_extraction", {}) if isinstance(row.get("visual_extraction"), dict) else {}
        logger.log(
            step=int(row.get("step", 0)),
            event_type="frame_observation",
            observation=json.dumps({"frame": row.get("frame"), "room": row.get("room"), "prediction_input_mode": row.get("prediction_input_mode")}),
            model_update={
                "perceived_room": row.get("room"),
                "extracted_objects": extraction.get("objects", []),
                "visual_extraction_metadata": {
                    "source": extraction.get("source", ""),
                    "mock": bool(extraction.get("mock", False)),
                    "synthetic": bool(extraction.get("synthetic", False)),
                    "model_call": extraction.get("model_call", {}),
                },
                "world_model_update": {"object_count": len(world_model.get("objects", [])), "relation_count": len(world_model.get("relations", []))},
                "action_policy": {
                    "available_actions": row.get("available_actions", []),
                    "policy_intent": row.get("policy_intent", {}),
                    "policy_decision": row.get("policy_decision", {}),
                    "grounded_action": row.get("grounded_action", {}),
                    "grounding_events": row.get("grounding_events", []),
                    "initial_policy_decision": row.get("initial_policy_decision", {}),
                    "fallback_events": row.get("fallback_events", []),
                    "harness_fallback_used": bool(row.get("harness_fallback_used", False)),
                },
                "uncertainty": extraction.get("uncertainty", []),
            },
            action=str(row.get("action") or ""),
            result="observed",
            notes=str(row.get("notes") or ""),
        )
        policy_intent = row.get("policy_intent") if isinstance(row.get("policy_intent"), dict) else {}
        if policy_intent:
            logger.log(
                step=int(row.get("step", 0)),
                event_type="policy_decision",
                model_update={
                    "event_type": "policy_decision",
                    "step": int(row.get("step", 0)),
                    "intent": policy_intent.get("name") or policy_intent.get("action"),
                    "target_label": policy_intent.get("target_label"),
                    "reason": policy_intent.get("reason"),
                    "confidence": policy_intent.get("confidence"),
                },
                action=str(policy_intent.get("name") or policy_intent.get("action") or ""),
                result="selected",
            )
        for event in row.get("grounding_events", []) if isinstance(row.get("grounding_events"), list) else []:
            if not isinstance(event, dict):
                continue
            logger.log(
                step=int(row.get("step", 0)),
                event_type="action_grounding",
                model_update=dict(event),
                action=str(event.get("vh_script") or event.get("intent") or ""),
                result="grounded" if event.get("executable") is True else "ungrounded",
                notes=str(event.get("failure_reason") or ""),
            )
        for event in row.get("fallback_events", []) if isinstance(row.get("fallback_events"), list) else []:
            if not isinstance(event, dict):
                continue
            logger.log(
                step=int(row.get("step", 0)),
                event_type="harness_fallback",
                model_update=dict(event),
                action=str(event.get("fallback_action") or ""),
                result="fallback",
                notes=str(event.get("reason") or ""),
            )
    logger.log(step=len(rows), event_type="validation", model_update=validation, result="passed" if validation.get("passed") else "pending")


def _write_report(path: Path, coverage: dict[str, Any], world_model: dict[str, Any], reference: dict[str, Any], comparison: dict[str, Any], dedup: dict[str, Any]) -> None:
    mode = coverage.get("prediction_input_mode", "unknown")
    reference_source = str(coverage.get("reference_model_source") or "")
    if mode == "vlm_frame_extraction":
        reference_phrase = (
            "The VirtualHome scene graph was used only to build `reference_world_model.json` for local validation."
            if reference_source == "virtualhome_scene_graph_answer_key"
            else "`reference_world_model.json` was loaded from explicit replay reference annotations for local validation."
        )
        mode_note = (
            "The predicted world model was generated from exported frame observations through the visual/VLM extraction "
            f"pipeline and action/navigation traces. {reference_phrase}"
        )
    else:
        mode_note = (
            "WARNING: This VirtualHome evidence was generated with mock or manifest-based extraction. It is suitable for "
            "smoke/reproducibility testing but should not be described as real VLM visual evidence."
        )
    text = f"""# VirtualHome Multi-Room Exploration Evidence

- evidence_level: `{coverage.get('evidence_level')}`
- capture_mode: `{coverage.get('capture_mode')}`
- continuous_closed_loop: `{coverage.get('continuous_closed_loop')}`
- official_score: `{coverage.get('official_score')}`
- rooms_visited: `{', '.join(coverage.get('rooms_visited', []))}`
- frames_used: `{coverage.get('frames_used')}`
- objects_detected: `{coverage.get('objects_detected')}`
- relations_detected: `{coverage.get('relations_detected')}`
- predicted_topology_edges: `{coverage.get('predicted_topology_edges')}`
- verified_topology_edges: `{coverage.get('verified_topology_edges')}`
- inferred_visual_topology_edges: `{coverage.get('inferred_visual_topology_edges')}`
- exploration_order_edges: `{coverage.get('exploration_order_edges')}`
- live_runtime_connected: `{coverage.get('live_runtime_connected')}`
- synthetic_capture: `{coverage.get('synthetic_capture')}`
- mock_extraction: `{coverage.get('mock_extraction')}`
- final_status: `{coverage.get('final_status')}`
- action_grounding_mode: `{coverage.get('action_grounding_mode')}`
- grounded_action_count: `{coverage.get('grounded_action_count')}`
- ungrounded_intent_count: `{coverage.get('ungrounded_intent_count')}`
- grounding_target_sources: `{', '.join(coverage.get('grounding_target_sources', []))}`
- insufficient_grounding: `{coverage.get('insufficient_grounding')}`
- action_policy_source: `{coverage.get('action_policy_source')}`
- action_decision_count: `{coverage.get('action_decision_count')}`
- harness_fallback_count: `{coverage.get('harness_fallback_count')}`

## Prediction Input Mode

- prediction_input_mode: `{mode}`
- world_model_source: `{coverage.get('world_model_source')}`
- reference_model_source: `{coverage.get('reference_model_source')}`
- reference_used_for_generation: `{coverage.get('reference_used_for_generation')}`
- reference_used_for_validation: `{coverage.get('reference_used_for_validation')}`
- official_score: `{coverage.get('official_score')}`

{mode_note}

Final bundle note: VirtualHome is optional and is copied into final `sample_outputs` only when this report is backed by
`evidence_level=closed_loop_final_evidence`, `capture_mode=continuous_episode`, real Unity frames, and real VLM calls.
Mock, synthetic, replay, or keyframe-only outputs are diagnostics, not final Track 1 evidence.

## Prediction vs Reference

- room precision/recall: `{comparison.get('rooms', {}).get('precision')}` / `{comparison.get('rooms', {}).get('recall')}`
- object precision/recall: `{comparison.get('objects', {}).get('precision')}` / `{comparison.get('objects', {}).get('recall')}`
- topology precision/recall: `{comparison.get('topology', {}).get('precision')}` / `{comparison.get('topology', {}).get('recall')}`

## Topology Semantics

- chronological visits are stored in `exploration_trace`.
- frame-order transitions are stored in `exploration_order_edges` with `status=inferred_from_sequence`.
- `topology.edges` contains visual inferred edges and verified navigation transitions only.
- scene graph data is reference-only in `reference_world_model.json`.

## Action Policy

- The VirtualHome continuous mode uses an observation-driven agent policy.
- The policy selects bounded VirtualHome actions from the current visual extraction, predicted world model, recent events, and available action schema.
- The harness validates action syntax, executes actions, and may use bounded fallback only when the selected action is invalid or fails.
- Fallback events are logged in `frame_manifest.json`, `episode_log.jsonl`, `coverage_report.json`, and `run_audit.json`.

## World Model Summary

- rooms: `{len(world_model.get('rooms', []))}`
- objects: `{len(world_model.get('objects', []))}`
- relations: `{len(world_model.get('relations', []))}`
- topology_edges: `{len(world_model.get('topology', {}).get('edges', []))}`
- raw_object_mentions: `{dedup.get('raw_object_mentions')}`
- unique_objects: `{dedup.get('unique_objects')}`

## Reference Summary

- reference rooms: `{len(reference.get('rooms', []))}`
- reference objects: `{len(reference.get('objects', []))}`
- reference topology_edges: `{len(reference.get('topology', {}).get('edges', []))}`
"""
    path.write_text(text, encoding="utf-8")


def _export_replay_assets(output_dir: Path, replay_assets_dir: Path) -> None:
    frames_source = output_dir / "frames"
    replay_frames = replay_assets_dir / "frames"
    if replay_assets_dir.exists():
        shutil.rmtree(replay_assets_dir)
    replay_frames.mkdir(parents=True, exist_ok=True)
    for frame in sorted(frames_source.glob("*")):
        if frame.is_file():
            shutil.copy2(frame, replay_frames / frame.name)
    for name in ["frame_manifest.json", "reference_world_model.json"]:
        if (output_dir / name).exists():
            shutil.copy2(output_dir / name, replay_assets_dir / name)
    (replay_assets_dir / "README.md").write_text(
        "Compact VirtualHome replay keyframes for local validation; full Unity runtime is not redistributed.\n",
        encoding="utf-8",
    )


def _call_if_exists(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if callable(method):
        return method(*args)
    return None


def _get_scene_graph(comm: Any) -> dict[str, Any]:
    for method_name in ["environment_graph", "get_scene_graph"]:
        method = getattr(comm, method_name, None)
        if not callable(method):
            continue
        result = method()
        if isinstance(result, tuple) and len(result) >= 2:
            if result[0] is False:
                raise VirtualHomeEvidenceError(f"{method_name} returned success=false.")
            if isinstance(result[1], dict):
                return result[1]
        if isinstance(result, dict):
            return result
    raise VirtualHomeEvidenceError("VirtualHome runtime does not expose environment_graph()/get_scene_graph().")


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _clear_virtualhome_artifacts(output_dir: Path) -> None:
    known_files = [
        "world_model.json",
        "reference_world_model.json",
        "comparison_report.json",
        "episode_log.jsonl",
        "run_audit.json",
        "visual_task_result.json",
        "frame_manifest.json",
        "coverage_report.json",
        "dedup_report.json",
        "virtualhome_exploration_report.md",
        "harness_result.json",
        "qwen_calls.jsonl",
        "qwen_response_summary.json",
        "debug_virtualhome_qwen_raw.txt",
        "virtualhome_runtime_connection.json",
        "live_connection_error.json",
    ]
    for name in known_files:
        path = output_dir / name
        if path.exists() and path.is_file():
            path.unlink()
    frames_dir = output_dir / "frames"
    if frames_dir.exists():
        resolved = frames_dir.resolve()
        if resolved.parent != output_dir.resolve():
            raise VirtualHomeEvidenceError(f"Refusing to clear unexpected frames directory: {resolved}")
        shutil.rmtree(frames_dir)


def _fail_live(
    output_dir: Path,
    *,
    start_time: str,
    started: float,
    mode: str,
    reason: str,
    attach_existing: bool,
    launch_attempted: bool,
    capture_mode: str,
    continuous_closed_loop: bool,
) -> int:
    error = {
        "success": False,
        "start_time": start_time,
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": elapsed(started),
        "evidence_level": EVIDENCE_MOCK_CI if mode == "mock_visual_extraction" else EVIDENCE_VISUAL_REPLAY,
        "capture_mode": capture_mode,
        "continuous_closed_loop": bool(continuous_closed_loop),
        "prediction_input_mode": mode,
        "world_model_source": _world_model_source(mode),
        "reference_model_source": "",
        "virtualhome_live_run": True,
        "live_runtime_connected": False,
        "synthetic_capture": False,
        "mock_extraction": mode == "mock_visual_extraction",
        "attach_existing": bool(attach_existing),
        "launch_attempted": bool(launch_attempted),
        "reference_used_for_generation": False,
        "reason": _sanitize_text(reason),
    }
    _write_json(output_dir / "live_connection_error.json", error)
    write_harness_result(
        output_dir,
        mode="virtualhome_exploration",
        success=False,
        validation_status={"passed": False, "errors": [error["reason"]], "warnings": []},
        errors=[error["reason"]],
        extra={"live_connection_error_path": "live_connection_error.json"},
    )
    print(error["reason"], file=sys.stderr)
    return 1


def _sanitize_runtime_connection(value: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, child in value.items():
        if isinstance(child, (str, int, float, bool)) or child is None:
            sanitized[key] = _sanitize_text(str(child)) if isinstance(child, str) else child
    return sanitized


def _sanitize_text(value: str) -> str:
    text = str(value)
    text = text.replace(str(PROJECT_ROOT), "<PROJECT_ROOT>")
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    if home:
        text = text.replace(home, "<HOME>")
    return text


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("frames", payload if isinstance(payload, list) else [])
    return [row for row in rows if isinstance(row, dict)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _world_model_source(mode: str) -> str:
    return "manifest_action_trace_baseline" if mode == "manifest_action_trace" else "visual_observation_pipeline"


def _normalize_prediction_input_mode(value: str) -> str:
    mode = str(value or DEFAULT_PREDICTION_INPUT_MODE).strip().lower()
    if mode not in PREDICTION_INPUT_MODES:
        raise ValueError(f"Unknown prediction_input_mode={value!r}. Expected one of {sorted(PREDICTION_INPUT_MODES)}.")
    return mode


def _ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_") or "unknown"


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
