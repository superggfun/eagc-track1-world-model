# Demo Commands

Run from the project root:

```powershell
cd "C:\Users\Alphay\Documents\New project\eagc_track1_mvp"
```

## Fast Gate

```powershell
python tools/run_test_suite.py --tier fast
```

## Targeted Gate

```powershell
python tools/run_test_suite.py --list-tiers
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-local-sim --timeout-seconds 600
```

Aggregate targeted smoke is available, but may take several minutes:

```powershell
python tools/run_test_suite.py --tier targeted --timeout-seconds 900 --continue-on-failure
```

## Standard Gate

```powershell
python tools/run_test_suite.py --tier standard
```

## LocalSim Track 1 Demo

```powershell
python main.py --env local_sim --episode-id local-explore-book-relocated --track1-procedure --validate
```

Key outputs:

- `outputs/world_model.json`
- `outputs/episode_log.jsonl`
- `outputs/run_audit.json`
- `track1_score.json` in the isolated run directory

## Visual Evidence Demo

```powershell
python main.py --env visual_sequence --image-dir assets/test_sequences/bedroom_sequence --max-frames 3 --visual-local-hybrid --visual-task "Is the laptop on the chair?" --validate
python -m validators.validate_visual_task_evidence outputs/visual_task_result.json outputs/run_audit.json
```

Key outputs:

- `outputs/world_model.json`
- `outputs/episode_log.jsonl`
- `outputs/run_audit.json`
- `outputs/visual_task_result.json`

## Demo Snapshot

```powershell
python tools/create_demo_snapshot.py
```

Expected output:

- `outputs/demo_snapshot/local_sim_track1_demo/`
- `outputs/demo_snapshot/visual_evidence_demo/`
- `outputs/demo_snapshot/README_demo.md`

## Report And Source Package

```powershell
python tools/generate_project_report.py
python tools/package_source.py
python tools/create_submission_bundle.py
python tools/pre_submission_audit.py
```

Expected output:

- `reports/v0.8.4_technical_report.md`
- `dist/eagc_track1_mvp_source.zip`
