from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit.builder import RunAuditContext, build_run_audit_from_context, write_failure_audit
from clients.mock_llm_client import MockLLMClient
from entrypoints import main as project_main
from env_adapters.official_env import OfficialEnvAdapter, OfficialRuntimeUnavailable
from harness._common import elapsed, resolve_project_path, write_harness_result
from harness.validate_outputs import validate_output_dir
from logging_utils.episode_logger import EpisodeLogger
from perception.prompts import PROMPT_VERSION
from perception.vlm_extractor import VLMExtractor
from track1_runner import Track1ProcedureRunner
from world_model.store import WorldModelStore


def run_official(
    *,
    env: str = "official",
    episode_id: str = "",
    output_dir: str | Path = "outputs/official",
    validate: bool = False,
    use_mock_llm: bool = False,
    config_path: str | Path | None = None,
    action_schema_path: str | Path | None = None,
) -> int:
    if env != "official":
        print("harness.run_official supports --env official only.", file=sys.stderr)
        return 2

    resolved_output_dir = resolve_project_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    episode = episode_id or os.environ.get("EAGC_EPISODE_ID", "official-episode")

    try:
        adapter = OfficialEnvAdapter(
            episode_id=episode,
            output_dir=resolved_output_dir,
            config_path=config_path,
            action_schema_path=action_schema_path,
        )
    except (OfficialRuntimeUnavailable, RuntimeError) as exc:
        message = str(exc)
        _write_official_failure(
            resolved_output_dir,
            episode_id=episode,
            error=message,
            started=started,
            validation_requested=validate,
        )
        print(message, file=sys.stderr)
        return 1

    return run_official_with_adapter(
        adapter=adapter,
        episode_id=episode,
        output_dir=resolved_output_dir,
        validate=validate,
        use_mock_llm=use_mock_llm,
        started=started,
    )


def run_official_with_adapter(
    *,
    adapter: Any,
    episode_id: str,
    output_dir: str | Path,
    validate: bool = False,
    use_mock_llm: bool = True,
    started: float | None = None,
) -> int:
    resolved_output_dir = resolve_project_path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    started = started if started is not None else time.perf_counter()
    started_wall = datetime.now(timezone.utc)
    world_model_path = resolved_output_dir / "world_model.json"
    episode_log_path = resolved_output_dir / "episode_log.jsonl"
    qwen_calls_path = resolved_output_dir / "qwen_calls.jsonl"
    qwen_response_summary_path = resolved_output_dir / "qwen_response_summary.json"
    audit_path = resolved_output_dir / "run_audit.json"

    client: Any
    if use_mock_llm:
        client = MockLLMClient()
    else:
        config = project_main.load_config(project_main.PROJECT_ROOT / "config.yaml")
        client = project_main.create_client(config, False, qwen_calls_path)

    try:
        logger = EpisodeLogger(episode_log_path)
        store = WorldModelStore(world_model_path)
        extractor = VLMExtractor(
            client,
            debug_output_path=resolved_output_dir / "debug_qwen_raw.txt",
            response_summary_path=qwen_response_summary_path,
        )
        runner = Track1ProcedureRunner(
            env=adapter,
            extractor=extractor,
            store=store,
            logger=logger,
            output_dir=resolved_output_dir,
        )
        result = runner.run_episode(episode_id)
        capabilities = _safe_capabilities(adapter)
        validation_status: Any = "not_requested"
        ctx = RunAuditContext(
            episode_id=episode_id,
            output_dir=resolved_output_dir,
            env_name="official",
            mode="official",
            start_time=started_wall.isoformat(),
            duration_seconds=time.perf_counter() - started,
            success=True,
            validation_status=validation_status,
            use_mock_llm=use_mock_llm,
            model="deterministic-mock-llm" if use_mock_llm else getattr(client, "model", ""),
            base_url="mock://local" if use_mock_llm else getattr(client, "base_url", ""),
            prompt_version=PROMPT_VERSION,
            qwen_call_count=getattr(client, "call_count", 0),
            qwen_call_success_count=getattr(client, "success_count", 0),
            qwen_call_failure_count=getattr(client, "failure_count", 0),
            fallback_used=extractor.fallback_used,
            track1_score_path="track1_score.json",
            extra={
                "official_runtime_adapter": True,
                "official_hidden_evaluation": True,
                "official_runtime_capabilities": capabilities,
                "reference_used_for_generation": False,
                "uses_hidden_ground_truth": False,
                "evidence_level": "official_runtime_run",
                **result.get("audit_updates", {}),
            },
        )
        audit = build_run_audit_from_context(ctx)
        project_main.write_run_audit(audit_path, audit)
        write_harness_result(
            resolved_output_dir,
            mode="official",
            success=True,
            errors=[],
            extra={"track1_score_path": "track1_score.json"},
        )
        if validate:
            validation_status = validate_output_dir(resolved_output_dir, "official")
            audit["validation_status"] = validation_status
            audit["success"] = bool(validation_status.get("passed"))
            audit["errors"] = list(validation_status.get("errors", []))
            project_main.write_run_audit(audit_path, audit)
            write_harness_result(
                resolved_output_dir,
                mode="official",
                success=bool(validation_status.get("passed")),
                validation_status=validation_status,
                errors=list(validation_status.get("errors", [])),
                extra={"track1_score_path": "track1_score.json"},
            )
            print(json.dumps(validation_status, ensure_ascii=False, indent=2))
            return 0 if validation_status.get("passed") else 1
        return 0
    except Exception as exc:  # noqa: BLE001 - runner failure must produce audit artifacts.
        message = str(exc) or exc.__class__.__name__
        _write_official_failure(
            resolved_output_dir,
            episode_id=episode_id,
            error=message,
            started=started,
            validation_requested=validate,
            client=client,
        )
        print(message, file=sys.stderr)
        return 1
    finally:
        close = getattr(adapter, "close", None)
        if callable(close):
            close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Track 1 pipeline against an official runtime adapter.")
    parser.add_argument("--env", default="official", choices=["official"])
    parser.add_argument("--episode-id", default=os.environ.get("EAGC_EPISODE_ID", "official-episode"))
    parser.add_argument("--output-dir", default=os.environ.get("EAGC_OUTPUT_DIR", "outputs/official"))
    parser.add_argument("--config-path", default=os.environ.get("EAGC_CONFIG_PATH", ""))
    parser.add_argument("--action-schema-path", default=os.environ.get("EAGC_ACTION_SCHEMA_PATH", ""))
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock LLM for adapter-boundary tests only.")
    args = parser.parse_args(argv)

    return run_official(
        env=args.env,
        episode_id=args.episode_id,
        output_dir=args.output_dir,
        validate=bool(args.validate),
        use_mock_llm=bool(args.mock),
        config_path=args.config_path or None,
        action_schema_path=args.action_schema_path or None,
    )


def _write_official_failure(
    output_dir: Path,
    *,
    episode_id: str,
    error: str,
    started: float,
    validation_requested: bool,
    client: Any | None = None,
) -> None:
    extra = {
        "official_runtime_adapter": True,
        "official_hidden_evaluation_results_included": False,
        "official_runtime_unavailable": True,
        "reference_used_for_generation": False,
        "uses_hidden_ground_truth": False,
        "fallback_to_local_sim": False,
        "evidence_level": "official_runtime_unavailable",
        "validation_requested": validation_requested,
    }
    write_failure_audit(
        output_dir,
        episode_id=episode_id,
        env_name="official",
        mode="official",
        error=error,
        duration_seconds=elapsed(started),
        client=client,
        extra=extra,
    )
    write_harness_result(
        output_dir,
        mode="official",
        success=False,
        validation_status={"passed": False, "errors": [error], "reason": "official_runtime_unavailable"},
        errors=[error],
        extra=extra,
    )


def _safe_capabilities(adapter: Any) -> dict[str, Any]:
    capabilities = getattr(adapter, "capabilities", None)
    if not callable(capabilities):
        return {}
    try:
        payload = capabilities()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc) or exc.__class__.__name__}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
