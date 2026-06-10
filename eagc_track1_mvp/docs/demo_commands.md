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
python main.py --env local_sim --episode-id random-local-sim --random-seed 6 --difficulty medium --track1-procedure --validate
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
