from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from infra.paths import PROJECT_ROOT


# ---------------------------------------------------------------------------
# Dataclass — single source of truth for audit parameters
# ---------------------------------------------------------------------------


@dataclass
class RunAuditContext:
    """All parameters needed to build a run_audit.json.

    Common fields get explicit slots.  Mode‑specific fields go into ``extra``.
    """

    # --- required identifiers ---
    episode_id: str
    output_dir: Path
    env_name: str = "mock"
    scene: str = ""
    run_id: str = ""
    mode: str = ""  # "mock" | "local_sim" | "track1" | "visual_sequence" | ...

    # --- timing (filled automatically by builder if None) ---
    start_time: Optional[str] = None  # ISO-8601
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None

    # --- status ---
    success: bool = False
    validation_status: Any = "not_run"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # --- artifact paths (relative to output_dir) ---
    world_model_path: str = "world_model.json"
    episode_log_path: str = "episode_log.jsonl"
    track1_score_path: Optional[str] = None
    visual_task_result_path: Optional[str] = None
    qwen_response_summary_path: Optional[str] = None
    debug_raw_path: Optional[str] = None

    # --- LLM stats ---
    qwen_call_count: int = 0
    qwen_call_success_count: int = 0
    qwen_call_failure_count: int = 0
    fallback_used: bool = False

    # --- perception policy stats ---
    perception_call_count: int = 0
    perception_skip_count: int = 0
    perception_skip_reasons: Dict[str, int] = field(default_factory=dict)

    # --- config info ---
    model: Optional[str] = None
    base_url: Optional[str] = None
    use_mock_llm: bool = False
    prompt_version: str = ""

    # --- vision mode ---
    vision_mode: bool = False
    image_path: Optional[str] = None
    image_exists: bool = False
    image_size_bytes: int = 0
    vision_call_success: bool = False
    vision_parse_success: bool = False
    frame_count: int = 0
    image_dir: Optional[str] = None
    processed_frames: List[str] = field(default_factory=list)

    # --- AI2Thor ---
    ai2thor_start_success: bool = False
    ai2thor_error_message: str = ""
    simulator_frame_path: Optional[str] = None
    simulator_metadata_path: Optional[str] = None

    # --- episode generation ---
    oracle_metadata_mode: bool = False

    # --- mode‑specific bag ---
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


_RE_WINDOWS_DRIVE = __import__("re").compile(r"^[A-Za-z]:[\\/]")


def to_artifact_relative_path(path: str | Path | None, output_dir: Path) -> str | None:
    """Convert *path* to a string relative to *output_dir*.

    * ``None`` → ``None``.
    * Already‑relative → passed through with forward‑slash separators.
    * Absolute under *output_dir* → relative path.
    * Absolute outside *output_dir* → filename only (safe fallback).

    Handles Windows‑style paths (``C:\\...``) even on non‑Windows hosts.
    """
    if path is None:
        return None
    raw = str(path).replace("\\", "/")
    # Detect Windows‑style absolute paths on any OS
    if _RE_WINDOWS_DRIVE.match(raw):
        candidate = Path(raw)
        if candidate.is_absolute():
            for base in [output_dir, PROJECT_ROOT]:
                try:
                    return candidate.resolve().relative_to(base.resolve()).as_posix() or "."
                except ValueError:
                    pass
        return raw.rsplit("/", 1)[-1]
    if raw.startswith("/"):
        raw_posix = PurePosixPath(raw)
        output_raw = str(output_dir).replace("\\", "/")
        if output_raw.startswith("/"):
            try:
                return raw_posix.relative_to(PurePosixPath(output_raw)).as_posix() or "."
            except ValueError:
                pass
        return raw_posix.name
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    resolved = p.resolve()
    resolved_dir = output_dir.resolve()
    try:
        return resolved.relative_to(resolved_dir).as_posix() or "."
    except ValueError:
        return resolved.name


# ---------------------------------------------------------------------------
# New builder — preferred API
# ---------------------------------------------------------------------------


def build_run_audit_from_context(ctx: RunAuditContext) -> Dict[str, Any]:
    """Build a ``run_audit.json``‑ready dict from a :class:`RunAuditContext`.

    Paths are written relative to *ctx.output_dir*.  The output dict matches
    the existing schema so existing validators / tests / submission bundles
    are not broken.
    """
    out_dir = ctx.output_dir

    # Normalise image‑related fields
    image_path_str = ""
    image_exists = ctx.image_exists
    image_size_bytes = ctx.image_size_bytes
    if ctx.image_path:
        p = Path(ctx.image_path)
        # Try to resolve against output_dir or project root to check existence
        resolved = p
        if not p.is_absolute():
            # try relative to output_dir first, then project root
            candidate = out_dir / p
            if candidate.exists():
                resolved = candidate
        if not resolved.is_absolute() or not resolved.exists():
            # try output_dir
            candidate = out_dir / p.name
            if candidate.exists():
                resolved = candidate
        image_path_str = to_artifact_relative_path(p, out_dir) or ""
        if resolved.exists():
            image_exists = True
            try:
                image_size_bytes = resolved.stat().st_size
            except OSError:
                pass

    # Normalise other path fields
    def _rel(value: str | None, default: str = "") -> str:
        if value is None:
            return default
        return to_artifact_relative_path(value, out_dir) or default

    debug_raw_rel = _rel(ctx.debug_raw_path)
    qwen_summary_rel = _rel(ctx.qwen_response_summary_path)
    wm_rel = _rel(ctx.world_model_path, "world_model.json")
    ep_log_rel = _rel(ctx.episode_log_path, "episode_log.jsonl")
    track1_rel = _rel(ctx.track1_score_path)
    vt_rel = _rel(ctx.visual_task_result_path)
    sim_frame_rel = _rel(ctx.simulator_frame_path)
    sim_meta_rel = _rel(ctx.simulator_metadata_path)
    image_dir_rel = _rel(ctx.image_dir)

    # Timing
    now = ctx.end_time or datetime.now(timezone.utc).isoformat()
    start = ctx.start_time or now
    duration = ctx.duration_seconds or 0.0

    audit: Dict[str, Any] = {
        "success": ctx.success,
        "errors": list(ctx.errors),
        "warnings": list(ctx.warnings),
        "run_id": ctx.run_id,
        "episode_id": ctx.episode_id,
        "output_dir": ".",
        "model": ctx.model or "",
        "base_url": ctx.base_url or "",
        "use_mock_llm": ctx.use_mock_llm,
        "env": ctx.env_name,
        "scene": ctx.scene,
        "prompt_version": ctx.prompt_version,
        "vision_mode": ctx.vision_mode,
        "image_path": image_path_str,
        "image_exists": image_exists,
        "image_size_bytes": image_size_bytes,
        "vision_call_success": ctx.vision_call_success if ctx.vision_mode else False,
        "vision_parse_success": ctx.vision_parse_success if ctx.vision_mode else False,
        "simulator_frame_path": sim_frame_rel,
        "simulator_metadata_path": sim_meta_rel,
        "ai2thor_start_success": ctx.ai2thor_start_success if ctx.env_name == "ai2thor" else False,
        "ai2thor_error_message": ctx.ai2thor_error_message,
        "oracle_metadata_mode": ctx.oracle_metadata_mode,
        "frame_count": ctx.frame_count,
        "image_dir": image_dir_rel,
        "processed_frames": [_rel(str(frame)) for frame in ctx.processed_frames],
        "frame_paths": [_rel(str(frame)) for frame in ctx.processed_frames],
        "start_time": start,
        "end_time": now,
        "latency_seconds": round(duration, 6),
        "duration_seconds": round(duration, 6),
        "qwen_call_count": ctx.qwen_call_count,
        "qwen_call_success_count": ctx.qwen_call_success_count,
        "qwen_call_failure_count": ctx.qwen_call_failure_count,
        "fallback_used": ctx.fallback_used,
        "perception_call_count": ctx.perception_call_count,
        "perception_skip_count": ctx.perception_skip_count,
        "vlm_call_saved_count": ctx.perception_skip_count,
        "perception_skip_reasons": dict(ctx.perception_skip_reasons),
        "debug_raw_path": debug_raw_rel,
        "qwen_response_summary_path": qwen_summary_rel,
        "world_model_path": wm_rel,
        "episode_log_path": ep_log_rel,
        "validation_status": ctx.validation_status,
    }

    # Inject track1 / visual paths when set
    if track1_rel:
        audit["track1_score_path"] = track1_rel
    if vt_rel:
        audit["visual_task_result_path"] = vt_rel

    # Merge extra fields (mode‑specific, post‑hoc additions)
    if ctx.extra:
        audit.update(ctx.extra)

    return audit
# ---------------------------------------------------------------------------
# Mode‑specific context helpers
# ---------------------------------------------------------------------------


def make_track1_audit_context(
    episode_id: str,
    output_dir: Path,
    success: bool,
    validation_status: Any,
    client: Any | None = None,
    fallback_used: bool = False,
    start_time: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    track1_score_path: str = "track1_score.json",
    extra: Optional[Dict[str, Any]] = None,
) -> RunAuditContext:
    """Quick constructor for Track‑1 runs (mock, local_sim)."""
    qwen_call_count = 0
    qwen_success_count = 0
    qwen_failure_count = 0
    if client is not None and hasattr(client, "call_count"):
        qwen_call_count = client.call_count
        qwen_success_count = getattr(client, "success_count", 0)
        qwen_failure_count = getattr(client, "failure_count", 0)

    return RunAuditContext(
        episode_id=episode_id,
        output_dir=output_dir,
        env_name="local_sim",
        mode="track1",
        success=success,
        validation_status=validation_status,
        start_time=start_time,
        duration_seconds=duration_seconds,
        track1_score_path=track1_score_path,
        qwen_call_count=qwen_call_count,
        qwen_call_success_count=qwen_success_count,
        qwen_call_failure_count=qwen_failure_count,
        fallback_used=fallback_used,
        extra=extra or {},
    )


def make_visual_audit_context(
    episode_id: str,
    output_dir: Path,
    success: bool,
    validation_status: Any,
    image_dir: Optional[str] = None,
    image_path: Optional[str] = None,
    vision_call_success: bool = False,
    vision_parse_success: bool = False,
    fallback_used: bool = False,
    client: Any | None = None,
    start_time: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> RunAuditContext:
    """Quick constructor for visual‑mode runs (visual_sequence, visual_mock, …)."""
    qwen_call_count = 0
    qwen_success_count = 0
    qwen_failure_count = 0
    if client is not None and hasattr(client, "call_count"):
        qwen_call_count = client.call_count
        qwen_success_count = getattr(client, "success_count", 0)
        qwen_failure_count = getattr(client, "failure_count", 0)

    return RunAuditContext(
        episode_id=episode_id,
        output_dir=output_dir,
        env_name="visual_sequence",
        mode="visual",
        success=success,
        validation_status=validation_status,
        vision_mode=True,
        image_path=image_path,
        image_dir=image_dir,
        vision_call_success=vision_call_success,
        vision_parse_success=vision_parse_success,
        start_time=start_time,
        duration_seconds=duration_seconds,
        fallback_used=fallback_used,
        qwen_call_count=qwen_call_count,
        qwen_call_success_count=qwen_success_count,
        qwen_call_failure_count=qwen_failure_count,
        extra=extra or {},
    )


# ---------------------------------------------------------------------------
# Failure audit — unified path for all failure scenarios
# ---------------------------------------------------------------------------


def write_failure_audit(
    output_dir: Path,
    episode_id: str,
    env_name: str,
    mode: str,
    error: str,
    *,
    start_time: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    warnings: Optional[List[str]] = None,
    fallback_used: bool = False,
    client: Any | None = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write a standardised ``run_audit.json`` for a failed run.

    Creates *output_dir* if necessary.  Returns the dict that was written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    qwen_call_count = 0
    qwen_success_count = 0
    qwen_failure_count = 0
    if client is not None and hasattr(client, "call_count"):
        qwen_call_count = client.call_count
        qwen_success_count = getattr(client, "success_count", 0)
        qwen_failure_count = getattr(client, "failure_count", 0)

    ctx = RunAuditContext(
        episode_id=episode_id,
        output_dir=output_dir,
        env_name=env_name,
        mode=mode,
        success=False,
        validation_status={"status": "not_run", "reason": "environment_error"},
        errors=[error],
        warnings=warnings or [],
        start_time=start_time,
        duration_seconds=duration_seconds,
        fallback_used=fallback_used,
        qwen_call_count=qwen_call_count,
        qwen_call_success_count=qwen_success_count,
        qwen_call_failure_count=qwen_failure_count,
        extra=extra or {},
    )

    audit = build_run_audit_from_context(ctx)
    audit_path = output_dir / "run_audit.json"
    import json as _json
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(_json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    return audit
