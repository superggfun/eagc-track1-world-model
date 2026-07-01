# Demo Commands

Run commands from the project directory:

```powershell
cd <repo-root>
```

## Fast Test

```powershell
python tools/run_test_suite.py --tier fast
```

The fast tier compiles only source directories and runs mock smoke tests. It is the default check for documentation, report, demo command, and small script edits.

## Targeted Seed Replay

```powershell
python tools/run_test_suite.py --tier targeted --seed 6 --difficulty medium
```

Direct replay:

```powershell
python tools/replay_random_local_sim_failure.py --seed 6 --difficulty medium --mode real
```

## Standard Gate

```powershell
python tools/run_test_suite.py --tier standard
```

Run this only when explicitly requested before a release gate. It calls real Qwen and can take longer than routine documentation checks.

## Demo Snapshot

```powershell
python tools/create_demo_snapshot.py
```

This writes:

- `outputs/demo_snapshot/local_sim_track1_demo/`
- `outputs/demo_snapshot/visual_evidence_demo/`
- `outputs/demo_snapshot/README_demo.md`

## Report And Source Package

```powershell
python tools/generate_project_report.py
python tools/package_source.py
```

The source package is built from git tracked files plus the harness refresh files when they are still untracked locally, and excludes outputs, local images, `.venv-ai2thor`, `source_pack`, zip files, and `__pycache__`.

## One Random LocalSim Episode

```powershell
python main.py --env local_sim_random --seed 6 --difficulty medium --track1-procedure --validate
```

## Track 1 Procedure Demo

```powershell
python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir outputs/local_sim_track1_demo --validate
python -m harness.validate_outputs --output-dir outputs/local_sim_track1_demo --mode track1
```

## Vision Smoke Demo

Place a local bedroom scene image at `assets/test_images/bedroom.png`, then run:

```powershell
python tools/test_qwen_vision_call.py --image-path assets/test_images/bedroom.png
python main.py --vision --image-path assets/test_images/bedroom.png --validate
```

The vision smoke path is an interface test only. It is not ProcTHOR, AI2-THOR, or official EAGC runtime integration.

## Visual Sequence Smoke Demo

Place local frames in `assets/test_sequences/bedroom_sequence/`:

```text
frame_000.jpg
frame_001.jpg
frame_002.jpg
```

Then run:

```powershell
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --validate
python -m validators.validate_visual_sequence outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python tests/smoke_test_visual_sequence.py --image-dir assets/test_sequences/bedroom_sequence --max-frames 3
```

The visual sequence path tests incremental world-model updates over local static images. It is not ProcTHOR, AI2-THOR, official EAGC runtime integration, or training.

The v0.9.1 validated local run used three Pexels bedroom images and produced:

- `processed_frames=3`
- `qwen_call_count=3`
- `fallback_used=False`
- `vision_parse_success=True`
- `object_count=15`
- `relation_count=23`

Object and relation counts can vary slightly across real Qwen vision runs; the smoke validator checks the structural and temporal consistency conditions.

These local frame images are smoke-test resources and should remain untracked by git.

## Visual-Local Hybrid Demo

Use the visual sequence world model for symbolic planning and task evaluation:

```powershell
python -m harness.run_visual_demo --frames assets/test_sequences/bedroom_sequence --output-dir outputs/visual_evidence_demo --validate
python -m harness.validate_outputs --output-dir outputs/visual_evidence_demo --mode visual
python tests/smoke_test_visual_local_hybrid.py --image-dir assets/test_sequences/bedroom_sequence --max-frames 3
```

The smoke test runs:

- `Find the laptop.`
- `Identify where the book is.`
- `Is the laptop on the chair?`
- `Find the chair near the bed.`

This path performs symbolic plan-level execution only. It does not perform real physical manipulation, does not represent ProcTHOR or the official runtime, and does not train a model.

v0.10.1 adds evidence-based task explanations. Each run writes `visual_task_result.json` with:

- `supporting_evidence`
- `contradicting_evidence`
- `missing_evidence`
- `evidence_summary`
- `confidence`

For relation questions, the evaluator only returns `complete` when an explicit active relation supports the query. If the objects are visible but the relation is missing or stale, the result is `uncertain` with missing evidence. This is a conservative visual judgment, not a failed run.
