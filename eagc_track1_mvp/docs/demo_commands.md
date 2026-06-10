# Demo Commands

Run commands from the project directory:

```powershell
cd "C:\Users\Alphay\Documents\New project\eagc_track1_mvp"
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

## One Random LocalSim Episode

```powershell
python main.py --env local_sim_random --seed 6 --difficulty medium --track1-procedure --validate
```

## Track 1 Procedure Demo

```powershell
python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
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
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --visual-local-hybrid --visual-task "Find the laptop." --validate
python -m validators.validate_visual_local_hybrid outputs/world_model.json outputs/run_audit.json outputs/episode_log.jsonl
python tests/smoke_test_visual_local_hybrid.py --image-dir assets/test_sequences/bedroom_sequence --max-frames 3
```

The smoke test runs:

- `Find the laptop.`
- `Identify where the book is.`
- `Is the laptop on the chair?`
- `Find the chair near the bed.`

This path performs symbolic plan-level execution only. It does not perform real physical manipulation, does not represent ProcTHOR or the official runtime, and does not train a model.
