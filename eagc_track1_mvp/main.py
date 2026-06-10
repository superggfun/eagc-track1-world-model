import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

from env_adapters.ai2thor_adapter import AI2ThorAdapter, AI2ThorAdapterError
from clients.mock_llm_client import MockLLMClient
from clients.qwen_client import QwenClient, QwenClientError
from env_adapters.local_sim_env import LocalSimEnv
from env_adapters.local_sim_generator import generate_random_local_sim_episode
from env_adapters.mock_env import MockEnv
from env_adapters.visual_mock_env import VisualMockEnv
from env_adapters.visual_sequence_env import VisualSequenceEnv
from executor.action_executor import ActionExecutor
from logging_utils.episode_logger import EpisodeLogger
from perception.prompts import PROMPT_VERSION
from perception.vlm_extractor import VLMExtractor
from planner.replanner import Replanner
from planner.rule_planner import RulePlanner
from scoring.track1_score import compute_track1_score, write_track1_score
from task_evaluator.task_evaluator import evaluate_task_status
from track1_runner import Track1ProcedureRunner
from validators.validate_episode_log import validate as validate_episode_log
from validators.validate_semantic_consistency import validate as validate_semantic_consistency
from validators.validate_task_status import validate as validate_task_status
from validators.validate_vision_extraction import validate as validate_vision_extraction
from validators.validate_world_model import validate as validate_world_model
from visual_runner import VisualLocalHybridRunner
from world_model.action_effects import apply_action_effect, apply_exception_effect
from world_model.store import WorldModelStore
from world_model.update import apply_environment_context, apply_frame_visibility, update_agent_state


PROJECT_ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    current_section: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_section:
            stripped_child = line.strip()
            if ":" not in stripped_child:
                continue
            child_key, child_value = stripped_child.split(":", 1)
            section = config.setdefault(current_section, {})
            if isinstance(section, dict):
                section[child_key.strip()] = _parse_scalar(child_value.strip())
            continue
        stripped = line.strip()
        key, value = stripped.split(":", 1)
        key = key.strip()
        if value.strip() == "":
            config[key] = {}
            current_section = key
        else:
            config[key] = _parse_scalar(value.strip())
            current_section = None
    return config


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value.replace(".", "", 1).isdigit() and value.count(".") <= 1:
        return float(value) if "." in value else int(value)
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the EAGC Track 1 MVP demo.")
    parser.add_argument("--episode-id", help="Mock episode id. Defaults to config.yaml episode_id.")
    parser.add_argument("--run-id", help="Stable run id for output directory naming.")
    parser.add_argument("--output-dir", help="Directory for this run's artifacts.")
    parser.add_argument("--validate", action="store_true", help="Run validators after the episode.")
    parser.add_argument("--use-mock-llm", action="store_true", help="Use deterministic mock LLM instead of vLLM.")
    parser.add_argument(
        "--env",
        choices=["mock", "visual_mock", "visual_sequence", "ai2thor", "local_sim", "local_sim_random"],
        default="mock",
    )
    parser.add_argument("--seed", type=int, default=1, help="Random LocalSim seed for --env local_sim_random.")
    parser.add_argument("--difficulty", choices=["easy", "medium"], default="easy", help="Random LocalSim difficulty.")
    parser.add_argument("--scene", default="FloorPlan1", help="AI2-THOR scene for --env ai2thor.")
    parser.add_argument("--vision", action="store_true", help="Run the visual mock episode with image input.")
    parser.add_argument("--image-path", help="Local image path for --vision runs.")
    parser.add_argument("--image-dir", help="Local image directory for --env visual_sequence.")
    parser.add_argument("--max-steps", type=int, help="Maximum LocalSim steps or legacy visual sequence frames.")
    parser.add_argument("--max-frames", type=int, help="Maximum visual sequence frames to process.")
    parser.add_argument("--visual-local-hybrid", action="store_true", help="Use visual sequence world model for symbolic task planning/evaluation.")
    parser.add_argument("--visual-task", help="Task to evaluate after visual world model construction.")
    parser.add_argument(
        "--track1-procedure",
        action="store_true",
        help="Run the official-style Track 1 phase procedure for LocalSim.",
    )
    return parser.parse_args()


def run_demo(args: argparse.Namespace | None = None) -> Dict[str, Any]:
    args = args or argparse.Namespace(
        episode_id=None,
        run_id=None,
        output_dir=None,
        validate=False,
        use_mock_llm=False,
        env="mock",
        scene="FloorPlan1",
        vision=False,
        image_path=None,
        image_dir=None,
        max_steps=None,
        max_frames=None,
        visual_local_hybrid=False,
        visual_task=None,
        track1_procedure=False,
        seed=1,
        difficulty="easy",
    )
    config = load_config(PROJECT_ROOT / "config.yaml")
    output_root = _resolve_output_path(str(config.get("output_dir", "outputs")))

    env_name = "visual_mock" if args.vision else str(getattr(args, "env", "mock"))
    vision_mode = env_name in {"visual_mock", "visual_sequence", "ai2thor"}
    image_path = _resolve_image_path(args.image_path) if env_name == "visual_mock" else None
    image_dir = _resolve_image_dir(args.image_dir) if env_name == "visual_sequence" else None
    max_sequence_steps = int(args.max_frames or args.max_steps) if (args.max_frames or args.max_steps) else None
    scene = str(getattr(args, "scene", "FloorPlan1"))
    if env_name == "ai2thor":
        episode_id = f"ai2thor-smoke-{scene}"
    elif env_name == "visual_sequence":
        episode_id = f"visual-sequence-{(image_dir or Path('sequence')).name}"
    elif env_name == "visual_mock":
        episode_id = "visual-bedroom-smoke"
    elif env_name == "local_sim_random":
        episode_id = f"random-local-sim-seed-{int(getattr(args, 'seed', 1)):04d}"
    elif env_name == "local_sim":
        episode_id = args.episode_id or "local-explore-book-relocated"
    else:
        episode_id = args.episode_id or str(config.get("episode_id", "mock-bedroom-relocated"))
    use_mock_llm = bool(args.use_mock_llm or config.get("use_mock_llm", False))
    oracle_metadata_mode = bool(config.get("oracle_metadata_mode", False))
    max_recovery_steps = int(config.get("max_recovery_steps", 6))
    track1_procedure = bool(getattr(args, "track1_procedure", False))
    track1_budgets = config.get("track1_budgets", {})
    if not isinstance(track1_budgets, dict):
        track1_budgets = {}
    started_wall = datetime.now(timezone.utc)
    started = time.perf_counter()
    run_id = args.run_id or _default_run_id(started_wall)
    output_dir = _select_output_dir(args.output_dir, output_root, run_id, episode_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    world_model_path = output_dir / "world_model.json"
    episode_log_path = output_dir / "episode_log.jsonl"
    audit_path = output_dir / "run_audit.json"
    qwen_calls_path = output_dir / "qwen_calls.jsonl"
    qwen_response_summary_path = output_dir / "qwen_response_summary.json"
    validation_status: Dict[str, Any] | str = "not_requested"
    client: QwenClient | MockLLMClient | None = None
    extractor: VLMExtractor | None = None
    env: MockEnv | VisualMockEnv | VisualSequenceEnv | AI2ThorAdapter | LocalSimEnv | None = None
    ai2thor_start_success = False
    ai2thor_error_message = ""
    simulator_frame_path: Path | None = None
    simulator_metadata_path: Path | None = None
    processed_frames: list[str] = []
    frame_count = 0
    generated_episode_spec: Dict[str, Any] | None = None
    generated_episode_spec_path: Path | None = None
    evaluator_context: Dict[str, Any] = {}

    try:
        if env_name == "ai2thor":
            env = AI2ThorAdapter(
                output_dir=output_dir,
                scene=scene,
                oracle_metadata_mode=oracle_metadata_mode,
            )
        elif env_name == "visual_sequence":
            env = VisualSequenceEnv(
                image_dir or PROJECT_ROOT / "assets" / "test_sequences" / "bedroom_sequence",
                max_steps=max_sequence_steps,
            )
        elif env_name == "visual_mock":
            env = VisualMockEnv(image_path or PROJECT_ROOT / "assets" / "test_images" / "bedroom.png")
        elif env_name == "local_sim_random":
            generated_episode_spec = generate_random_local_sim_episode(
                seed=int(getattr(args, "seed", 1)),
                difficulty=str(getattr(args, "difficulty", "easy")),
            )
            episode_id = str(generated_episode_spec["episode_id"])
            generated_episode_spec_path = output_dir / "generated_episode_spec.json"
            generated_episode_spec_path.write_text(
                json.dumps(generated_episode_spec, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            evaluator_context = dict(generated_episode_spec.get("hidden_spec", {}))
            env = LocalSimEnv.from_generated_episode(generated_episode_spec)
            track1_procedure = True
        elif env_name == "local_sim":
            env = LocalSimEnv(episode_id)
        else:
            env = MockEnv(episode_id)
        if track1_procedure:
            if env_name not in {"local_sim", "local_sim_random"} or not isinstance(env, LocalSimEnv):
                raise ValueError("--track1-procedure currently requires --env local_sim or --env local_sim_random.")
            logger = EpisodeLogger(episode_log_path)
            store = WorldModelStore(world_model_path)
            client = create_client(config, use_mock_llm, qwen_calls_path)
            extractor = VLMExtractor(
                client,
                debug_output_path=output_dir / "debug_qwen_raw.txt",
                response_summary_path=qwen_response_summary_path,
            )
            runner = Track1ProcedureRunner(
                env=env,
                extractor=extractor,
                store=store,
                logger=logger,
                output_dir=output_dir,
                budgets=track1_budgets,
                evaluator_context=evaluator_context,
            )
            result = runner.run_episode(episode_id)
            audit = build_run_audit(
                config=config,
                run_id=run_id,
                episode_id=episode_id,
                output_dir=output_dir,
                use_mock_llm=use_mock_llm,
                started_wall=started_wall,
                latency_seconds=time.perf_counter() - started,
                client=client,
                fallback_used=extractor.fallback_used,
                debug_raw_path=output_dir / "debug_qwen_raw.txt",
                world_model_path=world_model_path,
                episode_log_path=episode_log_path,
                validation_status=validation_status,
                prompt_version=PROMPT_VERSION,
                qwen_response_summary_path=qwen_response_summary_path,
                env_name=env_name,
                scene=scene,
                vision_mode=False,
                image_path=None,
                vision_call_success=False,
                vision_parse_success=False,
                simulator_frame_path=None,
                simulator_metadata_path=None,
                ai2thor_start_success=False,
                ai2thor_error_message="",
                oracle_metadata_mode=oracle_metadata_mode,
                frame_count=0,
                image_dir=None,
                processed_frames=[],
            )
            if generated_episode_spec:
                _add_generated_audit_fields(
                    audit,
                    generated_episode_spec,
                    generated_episode_spec_path,
                    seed=int(getattr(args, "seed", 1)),
                    difficulty=str(getattr(args, "difficulty", "easy")),
                )
            audit.update(result["audit_updates"])
            audit["track1_score_path"] = str(result["track1_score_path"])
            audit["track1_total_score"] = result["track1_score"]["total_score"]
            if generated_episode_spec:
                _mark_generated_acceptance(audit, result["world_model"], generated_episode_spec)
            write_run_audit(audit_path, audit)
            if args.validate:
                validation_status = run_validators(
                    world_model_path,
                    episode_log_path,
                    audit_path,
                    False,
                    env_name,
                    track1_procedure=True,
                )
                audit["validation_status"] = validation_status
                score = compute_track1_score(
                    json.loads(world_model_path.read_text(encoding="utf-8")),
                    read_episode_rows(episode_log_path),
                    audit,
                    validation_status=validation_status,
                )
                score_path = Path(audit["track1_score_path"])
                write_track1_score(score_path, score)
                audit["track1_total_score"] = score["total_score"]
                if generated_episode_spec:
                    _mark_generated_acceptance(
                        audit,
                        json.loads(world_model_path.read_text(encoding="utf-8")),
                        generated_episode_spec,
                    )
                write_run_audit(audit_path, audit)
            write_latest_artifacts(output_root, world_model_path, episode_log_path, audit_path)
            print(f"Demo complete. Wrote {world_model_path}")
            print(f"Demo complete. Wrote {episode_log_path}")
            print(f"Run audit written to {audit_path}")
            print(f"Track 1 score written to {audit.get('track1_score_path')}")
            if args.validate and isinstance(validation_status, dict) and not validation_status.get("passed", False):
                raise SystemExit(1)
            return audit
        initial = env.reset()
        ai2thor_start_success = bool(getattr(env, "start_success", False))
        if env_name == "ai2thor":
            simulator_frame_path = Path(initial.get("image_path", ""))
            simulator_metadata_path = Path(initial.get("metadata_path", ""))
            image_path = simulator_frame_path
        if env_name == "visual_sequence":
            frame_count = getattr(env, "frame_count", 0)
        observation_for_log = _render_observation(initial["observation"])

        logger = EpisodeLogger(episode_log_path)
        store = WorldModelStore(world_model_path)
        world_model = store.initialize(initial["episode_id"])
        world_model = apply_environment_context(world_model, initial)

        logger.log(
            step=0,
            event_type="observation",
            observation=observation_for_log,
            notes=f"Task: {initial['task']}",
        )

        client = create_client(config, use_mock_llm, qwen_calls_path)
        extractor = VLMExtractor(
            client,
            debug_output_path=output_dir / "debug_qwen_raw.txt",
            response_summary_path=qwen_response_summary_path,
        )

        if env_name == "visual_sequence":
            if bool(getattr(args, "visual_local_hybrid", False)):
                visual_task = str(getattr(args, "visual_task", "") or "Find the laptop.")
                runner = VisualLocalHybridRunner(
                    env=env,
                    extractor=extractor,
                    store=store,
                    logger=logger,
                    output_dir=output_dir,
                )
                result = runner.run(initial, visual_task)
                audit = build_run_audit(
                    config=config,
                    run_id=run_id,
                    episode_id=initial["episode_id"],
                    output_dir=output_dir,
                    use_mock_llm=use_mock_llm,
                    started_wall=started_wall,
                    latency_seconds=time.perf_counter() - started,
                    client=client,
                    fallback_used=extractor.fallback_used,
                    debug_raw_path=output_dir / "debug_qwen_raw.txt",
                    world_model_path=world_model_path,
                    episode_log_path=episode_log_path,
                    validation_status=validation_status,
                    prompt_version=PROMPT_VERSION,
                    qwen_response_summary_path=qwen_response_summary_path,
                    env_name="visual_sequence",
                    scene="",
                    vision_mode=True,
                    image_path=Path(result["processed_frames"][-1]) if result["processed_frames"] else None,
                    vision_call_success=bool(result["processed_frames"]),
                    vision_parse_success=bool(result["processed_frames"]) and not extractor.fallback_used,
                    simulator_frame_path=None,
                    simulator_metadata_path=None,
                    ai2thor_start_success=False,
                    ai2thor_error_message="",
                    oracle_metadata_mode=oracle_metadata_mode,
                    frame_count=frame_count,
                    image_dir=image_dir or PROJECT_ROOT / "assets" / "test_sequences" / "bedroom_sequence",
                    processed_frames=result["processed_frames"],
                )
                audit.update(
                    {
                        "visual_local_hybrid": True,
                        "visual_task": visual_task,
                        "visual_task_result_path": result["visual_task_result_path"],
                        "visual_task_status": result["task_status"],
                        "visual_task_confidence": result["task_status"].get("confidence", 0.0),
                        "symbolic_action_count": result["symbolic_action_count"],
                        "unsupported_physical_action_count": result["unsupported_physical_action_count"],
                        "evidence_count": result["evidence_count"],
                        "supporting_evidence_count": result["supporting_evidence_count"],
                        "contradicting_evidence_count": result["contradicting_evidence_count"],
                        "missing_evidence_count": result["missing_evidence_count"],
                    }
                )
                write_run_audit(audit_path, audit)
                if args.validate:
                    validation_status = run_validators(
                        world_model_path,
                        episode_log_path,
                        audit_path,
                        True,
                        "visual_sequence",
                        visual_local_hybrid=True,
                    )
                    audit["validation_status"] = validation_status
                    write_run_audit(audit_path, audit)
                write_latest_artifacts(output_root, world_model_path, episode_log_path, audit_path)
                visual_result_path = Path(result["visual_task_result_path"])
                if visual_result_path.exists():
                    shutil.copy2(visual_result_path, output_root / "visual_task_result.json")
                print(f"Demo complete. Wrote {world_model_path}")
                print(f"Demo complete. Wrote {episode_log_path}")
                print(f"Run audit written to {audit_path}")
                if args.validate and isinstance(audit.get("validation_status"), dict) and not audit["validation_status"].get("passed", False):
                    raise SystemExit(1)
                return audit
            audit = run_visual_sequence_episode(
                config=config,
                run_id=run_id,
                output_dir=output_dir,
                env=env,
                initial=initial,
                logger=logger,
                store=store,
                world_model=world_model,
                extractor=extractor,
                client=client,
                started_wall=started_wall,
                started=started,
                validation_requested=bool(args.validate),
                audit_path=audit_path,
                world_model_path=world_model_path,
                episode_log_path=episode_log_path,
                qwen_response_summary_path=qwen_response_summary_path,
                use_mock_llm=use_mock_llm,
                image_dir=image_dir or PROJECT_ROOT / "assets" / "test_sequences" / "bedroom_sequence",
                frame_count=frame_count,
            )
            write_latest_artifacts(output_root, world_model_path, episode_log_path, audit_path)
            print(f"Demo complete. Wrote {world_model_path}")
            print(f"Demo complete. Wrote {episode_log_path}")
            print(f"Run audit written to {audit_path}")
            if args.validate and isinstance(audit.get("validation_status"), dict) and not audit["validation_status"].get("passed", False):
                raise SystemExit(1)
            return audit

        extraction = extractor.extract(initial["observation"], initial["task"])
        world_model = store.update_from_extraction(extraction)
        world_model = apply_environment_context(world_model, initial)
        logger.log(
            step=1,
            event_type="perception",
            observation=observation_for_log,
            model_update=extraction,
            notes="Vision perception extraction completed." if vision_mode else "Text-only perception extraction completed.",
        )
        logger.log(
            step=2,
            event_type="world_model_update",
            observation=observation_for_log,
            model_update=extraction,
            notes="Initial extraction applied.",
        )

        planner = RulePlanner()
        plan = planner.plan(initial["task"], world_model)
        update_agent_state(world_model, step=3, last_action="", mode="planning")
        store.add_plan(plan)
        logger.log(step=3, event_type="planning", model_update=plan, notes="Initial rule plan.")

        executor = ActionExecutor(env)
        replanner = Replanner()

        step = 4
        plan_actions = planner.next_actions(plan)
        for action_index, action in enumerate(plan_actions):
            result = executor.execute(action)
            if result.get("success", False):
                apply_action_effect(world_model, action, result, step)
            update_agent_state(
                world_model,
                step=step,
                last_action=action,
                mode="executing" if result.get("success", False) else "exception",
                result=result.get("result", ""),
            )
            logger.log(
                step=step,
                event_type="action",
                observation=result.get("observation", ""),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            step += 1
            if env_name == "local_sim":
                step = sync_post_action_observation(
                    result=result,
                    extractor=extractor,
                    store=store,
                    world_model=world_model,
                    logger=logger,
                    start_step=step,
                )

            if not result.get("success", False):
                apply_exception_effect(world_model, result, step)
                logger.log(
                    step=step,
                    event_type="execution_exception",
                    observation=result.get("observation", ""),
                    model_update=result.get("exception", {}),
                    action=action,
                    result=result.get("result", ""),
                    notes=result.get("message", ""),
                )
                step += 1
                recovery_plan = replanner.recover(result, world_model)
                update_agent_state(world_model, step=step, last_action=action, mode="replanning")
                logger.log(
                    step=step,
                    event_type="replanning",
                    observation=result.get("observation", ""),
                    model_update=recovery_plan,
                    action=action,
                    result="recovery_plan_created",
                    notes="Exception handled; recovery plan created.",
                )
                step += 1
                step, recovery_complete = execute_recovery_plan(
                    recovery_plan=recovery_plan,
                    executor=executor,
                    world_model=world_model,
                    logger=logger,
                    start_step=step,
                    max_recovery_steps=max_recovery_steps,
                    post_action_hook=_local_sim_sync_hook(env_name, extractor, store, world_model, logger),
                )
                if recovery_complete:
                    current_status = update_task_status(
                        world_model,
                        initial["task"],
                        initial["episode_id"],
                        evaluator_context=evaluator_context,
                    )
                    if current_status["status"] not in {"complete", "blocked_recovered"}:
                        step = execute_resume_actions(
                            actions=plan_actions[action_index + 1 :],
                            executor=executor,
                            world_model=world_model,
                            logger=logger,
                            start_step=step,
                            post_action_hook=_local_sim_sync_hook(env_name, extractor, store, world_model, logger),
                        )
                break

        final_status = update_task_status(world_model, initial["task"], initial["episode_id"], evaluator_context=evaluator_context)
        logger.log(
            step=step,
            event_type="task_status",
            model_update=world_model["task_status"],
            result=final_status["status"],
            notes=final_status["reason"],
        )
        if env_name == "local_sim":
            step += 1
            logger.log(
                step=step,
                event_type="task_evaluation",
                model_update=world_model["task_status"],
                result=final_status["status"],
                notes=final_status["reason"],
            )
        store.save()

        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=initial["episode_id"],
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=extractor.fallback_used,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status=validation_status,
            prompt_version=PROMPT_VERSION,
            qwen_response_summary_path=qwen_response_summary_path,
            env_name=env_name,
            scene=scene,
            vision_mode=vision_mode,
            image_path=image_path,
            vision_call_success=bool(extractor.last_call_success) if extractor else False,
            vision_parse_success=bool(extractor.last_parse_success) if extractor else False,
            simulator_frame_path=simulator_frame_path,
            simulator_metadata_path=simulator_metadata_path,
            ai2thor_start_success=ai2thor_start_success,
            ai2thor_error_message=ai2thor_error_message,
            oracle_metadata_mode=oracle_metadata_mode,
            frame_count=frame_count,
            image_dir=image_dir,
            processed_frames=processed_frames,
        )
        write_run_audit(audit_path, audit)
        if args.validate:
            validation_status = run_validators(world_model_path, episode_log_path, audit_path, vision_mode, env_name)
            audit["validation_status"] = validation_status
            write_run_audit(audit_path, audit)
        write_latest_artifacts(output_root, world_model_path, episode_log_path, audit_path)
        print(f"Demo complete. Wrote {world_model_path}")
        print(f"Demo complete. Wrote {episode_log_path}")
        print(f"Run audit written to {audit_path}")
        if args.validate and isinstance(validation_status, dict) and not validation_status.get("passed", False):
            raise SystemExit(1)
        return audit
    except AI2ThorAdapterError as exc:
        ai2thor_error_message = str(exc)
        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=episode_id,
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=False,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status={"status": "not_run", "reason": "ai2thor_adapter_error"},
            prompt_version=PROMPT_VERSION,
            qwen_response_summary_path=qwen_response_summary_path,
            env_name=env_name,
            scene=scene,
            vision_mode=vision_mode,
            image_path=image_path,
            vision_call_success=False,
            vision_parse_success=False,
            simulator_frame_path=simulator_frame_path,
            simulator_metadata_path=simulator_metadata_path,
            ai2thor_start_success=ai2thor_start_success,
            ai2thor_error_message=ai2thor_error_message,
            oracle_metadata_mode=oracle_metadata_mode,
            frame_count=frame_count,
            image_dir=image_dir,
            processed_frames=processed_frames,
        )
        audit["error_message"] = ai2thor_error_message
        write_run_audit(audit_path, audit)
        raise SystemExit(
            "\n[ERROR] Could not start or observe AI2-THOR.\n"
            f"{exc}\n\n"
            "If AI2-THOR is not installed, run: pip install ai2thor\n"
            "If it is installed, check the local Unity/OpenGL/graphics environment.\n"
        ) from exc
    except ValueError as exc:
        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=episode_id,
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=False,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status={"status": "not_run", "reason": "environment_error"},
            prompt_version=PROMPT_VERSION,
            qwen_response_summary_path=qwen_response_summary_path,
            env_name=env_name,
            scene=scene,
            vision_mode=vision_mode,
            image_path=image_path,
            vision_call_success=False,
            vision_parse_success=False,
            simulator_frame_path=simulator_frame_path,
            simulator_metadata_path=simulator_metadata_path,
            ai2thor_start_success=ai2thor_start_success,
            ai2thor_error_message=ai2thor_error_message,
            oracle_metadata_mode=oracle_metadata_mode,
            frame_count=frame_count,
            image_dir=image_dir,
            processed_frames=processed_frames,
        )
        audit["error_message"] = str(exc)
        write_run_audit(audit_path, audit)
        raise SystemExit(f"\n[ERROR] Environment setup failed.\n{exc}\n") from exc
    except QwenClientError as exc:
        audit = build_run_audit(
            config=config,
            run_id=run_id,
            episode_id=episode_id,
            output_dir=output_dir,
            use_mock_llm=use_mock_llm,
            started_wall=started_wall,
            latency_seconds=time.perf_counter() - started,
            client=client,
            fallback_used=False,
            debug_raw_path=output_dir / "debug_qwen_raw.txt",
            world_model_path=world_model_path,
            episode_log_path=episode_log_path,
            validation_status={"status": "not_run", "reason": "qwen_client_error"},
            prompt_version=PROMPT_VERSION,
            qwen_response_summary_path=qwen_response_summary_path,
            env_name=env_name,
            scene=scene,
            vision_mode=vision_mode,
            image_path=image_path,
            vision_call_success=False,
            vision_parse_success=False,
            simulator_frame_path=simulator_frame_path,
            simulator_metadata_path=simulator_metadata_path,
            ai2thor_start_success=ai2thor_start_success,
            ai2thor_error_message=ai2thor_error_message,
            oracle_metadata_mode=oracle_metadata_mode,
            frame_count=frame_count,
            image_dir=image_dir,
            processed_frames=processed_frames,
        )
        audit["error_message"] = str(exc)
        write_run_audit(audit_path, audit)
        raise SystemExit(
            "\n[ERROR] Could not complete perception extraction via local vLLM.\n"
            f"{exc}\n\n"
            "Please check that vLLM is running at the configured base_url and that "
            "the configured model name is served.\n"
        ) from exc
    finally:
        if env is not None and hasattr(env, "close"):
            env.close()


def run_validators(
    world_model_path: Path,
    episode_log_path: Path,
    audit_path: Path | None = None,
    vision_mode: bool = False,
    env_name: str = "mock",
    track1_procedure: bool = False,
    visual_local_hybrid: bool = False,
) -> Dict[str, Any]:
    checks = {
        "world_model": validate_world_model(world_model_path),
        "semantic_consistency": validate_semantic_consistency(world_model_path),
        "episode_log": validate_episode_log(episode_log_path),
        "task_status": validate_task_status(world_model_path, episode_log_path),
    }
    if vision_mode and audit_path is not None:
        checks["vision_extraction"] = validate_vision_extraction(world_model_path, audit_path)
    if env_name == "ai2thor" and audit_path is not None:
        from validators.validate_ai2thor_smoke import validate as validate_ai2thor_smoke

        checks["ai2thor_smoke"] = validate_ai2thor_smoke(world_model_path, audit_path)
    if env_name == "visual_sequence" and audit_path is not None:
        from validators.validate_visual_sequence import validate as validate_visual_sequence

        checks["visual_sequence"] = validate_visual_sequence(world_model_path, audit_path, episode_log_path)
    if visual_local_hybrid and audit_path is not None:
        from validators.validate_visual_local_hybrid import validate as validate_visual_local_hybrid
        from validators.validate_visual_task_evidence import validate as validate_visual_task_evidence

        checks["visual_local_hybrid"] = validate_visual_local_hybrid(world_model_path, audit_path, episode_log_path)
        checks["visual_task_evidence"] = validate_visual_task_evidence(world_model_path.parent / "visual_task_result.json", audit_path)
    if env_name in {"local_sim", "local_sim_random"} and audit_path is not None:
        from validators.validate_local_sim_run import validate as validate_local_sim_run

        checks["local_sim"] = validate_local_sim_run(world_model_path, audit_path, episode_log_path)
    if env_name == "local_sim_random" and audit_path is not None:
        from validators.validate_random_local_sim_run import validate as validate_random_local_sim_run
        from validators.validate_no_hidden_spec_leakage import validate as validate_no_hidden_spec_leakage

        checks["random_local_sim"] = validate_random_local_sim_run(world_model_path, audit_path, episode_log_path)
        checks["no_hidden_spec_leakage"] = validate_no_hidden_spec_leakage(world_model_path, audit_path, episode_log_path)
    if track1_procedure and audit_path is not None:
        from validators.validate_track1_procedure import validate as validate_track1_procedure

        checks["track1_procedure"] = validate_track1_procedure(world_model_path, audit_path, episode_log_path)
    status = {
        name: {"passed": not errors, "errors": errors}
        for name, errors in checks.items()
    }
    status["passed"] = all(item["passed"] for item in status.values() if isinstance(item, dict))
    for name, item in status.items():
        if isinstance(item, dict):
            print(f"Validation {name}: {'passed' if item['passed'] else 'failed'}")
            for error in item["errors"]:
                print(f"- {error}")
    return status


def create_client(config: Dict[str, Any], use_mock_llm: bool, qwen_calls_path: Path) -> QwenClient | MockLLMClient:
    if use_mock_llm:
        return MockLLMClient(model="deterministic-mock-llm", base_url="mock://local")
    return QwenClient(
        base_url=str(config["base_url"]),
        model=str(config["model"]),
        temperature=float(config["temperature"]),
        max_tokens=int(config["max_tokens"]),
        audit_path=qwen_calls_path,
    )


def read_episode_rows(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_visual_sequence_episode(
    config: Dict[str, Any],
    run_id: str,
    output_dir: Path,
    env: VisualSequenceEnv,
    initial: Dict[str, Any],
    logger: EpisodeLogger,
    store: WorldModelStore,
    world_model: Dict[str, Any],
    extractor: VLMExtractor,
    client: QwenClient | MockLLMClient,
    started_wall: datetime,
    started: float,
    validation_requested: bool,
    audit_path: Path,
    world_model_path: Path,
    episode_log_path: Path,
    qwen_response_summary_path: Path,
    use_mock_llm: bool,
    image_dir: Path,
    frame_count: int,
) -> Dict[str, Any]:
    packet = initial
    processed_frames: list[str] = []
    step = 1
    frame_index = 0
    while True:
        observation_for_log = _render_observation(packet["observation"])
        if frame_index > 0:
            logger.log(
                step=step,
                event_type="observation",
                observation=observation_for_log,
                notes=f"Visual sequence frame {frame_index}.",
            )
            step += 1

        extraction = extractor.extract(packet["observation"], packet["task"])
        world_model = store.update_from_extraction(extraction)
        world_model = apply_environment_context(world_model, packet)
        observed_names = _extraction_object_names(extraction)
        world_model = apply_frame_visibility(world_model, observed_names, frame_index)
        update_agent_state(world_model, step=step, last_action="", mode="perceiving")
        processed_frames.append(str(packet["observation"]["image_path"]))

        logger.log(
            step=step,
            event_type="perception",
            observation=observation_for_log,
            model_update=extraction,
            notes=f"Vision sequence extraction completed for frame {frame_index}.",
        )
        step += 1
        logger.log(
            step=step,
            event_type="world_model_update",
            observation=observation_for_log,
            model_update={
                "frame_index": frame_index,
                "observed_objects": observed_names,
                "world_model_object_count": len(world_model.get("objects", [])),
                "world_model_relation_count": len(world_model.get("relations", [])),
            },
            notes=f"Incremental world model update applied for frame {frame_index}.",
        )
        step += 1

        result = env.step("next_frame")
        if not result.get("success"):
            break
        packet = result["observation"]
        frame_index += 1

    planner = RulePlanner()
    plan = planner.plan(initial["task"], world_model)
    update_agent_state(world_model, step=step, last_action="", mode="planning")
    store.add_plan(plan)
    logger.log(step=step, event_type="planning", model_update=plan, notes="Visual sequence summary plan.")
    step += 1

    final_status = update_task_status(world_model, initial["task"], initial["episode_id"])
    logger.log(
        step=step,
        event_type="task_status",
        model_update=world_model["task_status"],
        result=final_status["status"],
        notes=final_status["reason"],
    )
    store.save()

    validation_status: Dict[str, Any] | str = "not_requested"
    audit = build_run_audit(
        config=config,
        run_id=run_id,
        episode_id=initial["episode_id"],
        output_dir=output_dir,
        use_mock_llm=use_mock_llm,
        started_wall=started_wall,
        latency_seconds=time.perf_counter() - started,
        client=client,
        fallback_used=extractor.fallback_used,
        debug_raw_path=output_dir / "debug_qwen_raw.txt",
        world_model_path=world_model_path,
        episode_log_path=episode_log_path,
        validation_status=validation_status,
        prompt_version=PROMPT_VERSION,
        qwen_response_summary_path=qwen_response_summary_path,
        env_name="visual_sequence",
        scene="",
        vision_mode=True,
        image_path=Path(processed_frames[-1]) if processed_frames else None,
        vision_call_success=bool(processed_frames),
        vision_parse_success=bool(processed_frames) and not extractor.fallback_used,
        simulator_frame_path=None,
        simulator_metadata_path=None,
        ai2thor_start_success=False,
        ai2thor_error_message="",
        oracle_metadata_mode=bool(config.get("oracle_metadata_mode", False)),
        frame_count=frame_count,
        image_dir=image_dir,
        processed_frames=processed_frames,
    )
    write_run_audit(audit_path, audit)
    if validation_requested:
        validation_status = run_validators(world_model_path, episode_log_path, audit_path, True, "visual_sequence")
        audit["validation_status"] = validation_status
        write_run_audit(audit_path, audit)
    return audit


def execute_recovery_plan(
    recovery_plan: Dict[str, Any],
    executor: ActionExecutor,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
    start_step: int,
    max_recovery_steps: int,
    post_action_hook: Callable[[Dict[str, Any], int], int] | None = None,
) -> tuple[int, bool]:
    step = start_step
    actions = list(recovery_plan.get("actions", []))[:max_recovery_steps]
    for action in actions:
        result = executor.execute(action)
        if result.get("success", False):
            apply_action_effect(world_model, action, result, step)
        update_agent_state(
            world_model,
            step=step,
            last_action=action,
            mode="recovering" if result.get("success", False) else "recovery_failed",
            result=result.get("result", ""),
        )
        logger.log(
            step=step,
            event_type="recovery_action",
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        step += 1
        if post_action_hook is not None:
            step = post_action_hook(result, step)
        if not result.get("success", False):
            logger.log(
                step=step,
                event_type="recovery_failed",
                observation=result.get("observation", ""),
                model_update=result.get("exception", {}),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            update_agent_state(world_model, step=step, last_action=action, mode="recovery_failed")
            return step + 1, False

    logger.log(
        step=step,
        event_type="recovery_complete",
        model_update=recovery_plan,
        result="success",
        notes=f"Executed {len(actions)} recovery actions.",
    )
    update_agent_state(world_model, step=step, last_action="", mode="recovery_complete")
    return step + 1, True


def execute_resume_actions(
    actions: list[str],
    executor: ActionExecutor,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
    start_step: int,
    post_action_hook: Callable[[Dict[str, Any], int], int] | None = None,
) -> int:
    step = start_step
    for action in actions:
        result = executor.execute(action)
        if result.get("success", False):
            apply_action_effect(world_model, action, result, step)
        update_agent_state(
            world_model,
            step=step,
            last_action=action,
            mode="resuming" if result.get("success", False) else "resume_failed",
            result=result.get("result", ""),
        )
        logger.log(
            step=step,
            event_type="resume_action",
            observation=result.get("observation", ""),
            action=action,
            result=result.get("result", ""),
            notes=result.get("message", ""),
        )
        step += 1
        if post_action_hook is not None:
            step = post_action_hook(result, step)
        if not result.get("success", False):
            logger.log(
                step=step,
                event_type="resume_failed",
                observation=result.get("observation", ""),
                model_update=result.get("exception", {}),
                action=action,
                result=result.get("result", ""),
                notes=result.get("message", ""),
            )
            update_agent_state(world_model, step=step, last_action=action, mode="resume_failed")
            return step + 1
    return step


def _local_sim_sync_hook(
    env_name: str,
    extractor: VLMExtractor | None,
    store: WorldModelStore,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
) -> Callable[[Dict[str, Any], int], int] | None:
    if env_name != "local_sim" or extractor is None:
        return None

    def _hook(result: Dict[str, Any], start_step: int) -> int:
        return sync_post_action_observation(result, extractor, store, world_model, logger, start_step)

    return _hook


def sync_post_action_observation(
    result: Dict[str, Any],
    extractor: VLMExtractor,
    store: WorldModelStore,
    world_model: Dict[str, Any],
    logger: EpisodeLogger,
    start_step: int,
) -> int:
    packet = result.get("observation_packet")
    if not isinstance(packet, dict):
        return start_step
    observation = packet.get("observation", "")
    task = str(packet.get("task", ""))
    extraction = extractor.extract(observation, task)
    store.update_from_extraction(extraction)
    apply_environment_context(world_model, packet)
    update_agent_state(
        world_model,
        step=start_step,
        last_action=str(result.get("action", "")),
        mode="observing",
        result=str(result.get("result", "")),
    )
    logger.log(
        step=start_step,
        event_type="perception",
        observation=_render_observation(observation),
        model_update=extraction,
        action=str(result.get("action", "")),
        result=str(result.get("result", "")),
        notes="LocalSim post-action observation extraction completed.",
    )
    logger.log(
        step=start_step + 1,
        event_type="world_model_update",
        observation=_render_observation(observation),
        model_update=world_model,
        action=str(result.get("action", "")),
        result=str(result.get("result", "")),
        notes="World model merged LocalSim post-action observation.",
    )
    return start_step + 2


def update_task_status(
    world_model: Dict[str, Any],
    task: str,
    episode_id: str,
    evaluator_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    evaluated = evaluate_task_status(task, world_model, episode_id, evaluator_context=evaluator_context)
    status = {
        "status": evaluated["task_status"],
        "success": evaluated["success"],
        "reason": evaluated["reason"],
        "evidence": evaluated["evidence"],
    }
    world_model["task_status"] = status
    return status


def build_run_audit(
    config: Dict[str, Any],
    run_id: str,
    episode_id: str,
    output_dir: Path,
    use_mock_llm: bool,
    started_wall: datetime,
    latency_seconds: float,
    client: QwenClient | MockLLMClient | None,
    fallback_used: bool,
    debug_raw_path: Path,
    world_model_path: Path,
    episode_log_path: Path,
    validation_status: Dict[str, Any] | str,
    prompt_version: str,
    qwen_response_summary_path: Path,
    env_name: str,
    scene: str,
    vision_mode: bool,
    image_path: Path | None,
    vision_call_success: bool,
    vision_parse_success: bool,
    simulator_frame_path: Path | None,
    simulator_metadata_path: Path | None,
    ai2thor_start_success: bool,
    ai2thor_error_message: str,
    oracle_metadata_mode: bool,
    frame_count: int,
    image_dir: Path | None,
    processed_frames: list[str],
) -> Dict[str, Any]:
    ended = datetime.now(timezone.utc)
    qwen_call_count = 0 if use_mock_llm or client is None else client.call_count
    qwen_success_count = 0 if use_mock_llm or client is None else client.success_count
    qwen_failure_count = 0 if use_mock_llm or client is None else client.failure_count
    return {
        "run_id": run_id,
        "episode_id": episode_id,
        "output_dir": str(output_dir),
        "model": "deterministic-mock-llm" if use_mock_llm else config.get("model"),
        "base_url": "mock://local" if use_mock_llm else config.get("base_url"),
        "use_mock_llm": use_mock_llm,
        "env": env_name,
        "scene": scene,
        "prompt_version": prompt_version,
        "vision_mode": vision_mode,
        "image_path": str(image_path) if image_path else "",
        "image_exists": bool(image_path and image_path.exists()),
        "image_size_bytes": image_path.stat().st_size if image_path and image_path.exists() else 0,
        "vision_call_success": vision_call_success if vision_mode else False,
        "vision_parse_success": vision_parse_success if vision_mode else False,
        "simulator_frame_path": str(simulator_frame_path) if simulator_frame_path else "",
        "simulator_metadata_path": str(simulator_metadata_path) if simulator_metadata_path else "",
        "ai2thor_start_success": ai2thor_start_success if env_name == "ai2thor" else False,
        "ai2thor_error_message": ai2thor_error_message,
        "oracle_metadata_mode": oracle_metadata_mode,
        "frame_count": frame_count,
        "image_dir": str(image_dir) if image_dir else "",
        "processed_frames": processed_frames,
        "frame_paths": processed_frames,
        "start_time": started_wall.isoformat(),
        "end_time": ended.isoformat(),
        "latency_seconds": round(latency_seconds, 6),
        "qwen_call_count": qwen_call_count,
        "qwen_call_success_count": qwen_success_count,
        "qwen_call_failure_count": qwen_failure_count,
        "fallback_used": fallback_used,
        "debug_raw_path": str(debug_raw_path) if debug_raw_path.exists() else "",
        "qwen_response_summary_path": str(qwen_response_summary_path) if qwen_response_summary_path.exists() else "",
        "world_model_path": str(world_model_path),
        "episode_log_path": str(episode_log_path),
        "validation_status": validation_status,
    }


def _add_generated_audit_fields(
    audit: Dict[str, Any],
    episode_spec: Dict[str, Any],
    generated_episode_spec_path: Path | None,
    seed: int,
    difficulty: str,
) -> None:
    hidden_spec = episode_spec.get("hidden_spec", {})
    if not isinstance(hidden_spec, dict):
        hidden_spec = {}
    controlled_exception = hidden_spec.get("controlled_exception", episode_spec.get("controlled_exception", {}))
    if not isinstance(controlled_exception, dict):
        controlled_exception = {}
    audit.update(
        {
            "seed": seed,
            "difficulty": difficulty,
            "generated_episode_spec_path": str(generated_episode_spec_path) if generated_episode_spec_path else "",
            "controlled_exception_type": controlled_exception.get("type", ""),
            "expected_task_status": hidden_spec.get("expected_task_status", episode_spec.get("expected_task_status", "")),
            "recoverable": bool(hidden_spec.get("recoverable", episode_spec.get("recoverable", True))),
            "accepted_failure": False,
            "accepted_failure_reason": "",
        }
    )


def _mark_generated_acceptance(
    audit: Dict[str, Any],
    world_model: Dict[str, Any],
    episode_spec: Dict[str, Any],
) -> None:
    hidden_spec = episode_spec.get("hidden_spec", {})
    if not isinstance(hidden_spec, dict):
        hidden_spec = {}
    status = str(world_model.get("task_status", {}).get("status") or "")
    recoverable = bool(hidden_spec.get("recoverable", True))
    if not recoverable and status in {"failed", "blocked_recovered", "in_progress"}:
        audit["accepted_failure"] = True
        audit["accepted_failure_reason"] = f"Generated episode is marked unrecoverable; final status was {status}."


def write_run_audit(path: Path, audit: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")


def write_latest_artifacts(output_root: Path, world_model_path: Path, episode_log_path: Path, audit_path: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for source, name in [
        (world_model_path, "world_model.json"),
        (episode_log_path, "episode_log.jsonl"),
        (audit_path, "run_audit.json"),
    ]:
        if source.exists():
            shutil.copy2(source, output_root / name)


def _resolve_output_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _select_output_dir(output_dir_arg: str | None, output_root: Path, run_id: str, episode_id: str) -> Path:
    if output_dir_arg:
        return _resolve_output_path(output_dir_arg)
    return output_root / "runs" / f"{run_id}_{episode_id}"


def _default_run_id(started_wall: datetime) -> str:
    return started_wall.strftime("%Y%m%dT%H%M%S%fZ")


def _resolve_image_path(value: str | None) -> Path:
    path = Path(value or "assets/test_images/bedroom.png")
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _resolve_image_dir(value: str | None) -> Path:
    path = Path(value or "assets/test_sequences/bedroom_sequence")
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _render_observation(observation: Any) -> str:
    if isinstance(observation, str):
        return observation
    return json.dumps(observation, ensure_ascii=False)


def _extraction_object_names(extraction: Dict[str, Any]) -> list[str]:
    names = []
    for obj in extraction.get("objects", []):
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or obj.get("id")
        if name:
            names.append(str(name))
    return names


if __name__ == "__main__":
    run_demo(parse_args())
