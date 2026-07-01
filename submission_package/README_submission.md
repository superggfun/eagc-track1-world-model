# EAGC Track 1 Pre-Submission Readiness Package

This folder contains a pre-submission readiness package for the current EAGC Track 1 local MVP. It is intended for internal review, teacher discussion, technical report drafting, and future qualification submission preparation.

Current project stage: `v0.17.2` final submission handoff readiness, including dry-run submission materials, resource profile conclusions, source package reproducibility checks, GitHub readiness checks, and HTML/PDF technical report fallback handling.

Current system scope:

- LocalSim Track 1-style MVP for exploration, world-model construction, planning, execution, and recovery.
- Visual-local hybrid prototype for multi-frame image observation, world-model update, symbolic visual task answering, evidence explanation, and uncertainty reporting.
- Real local Qwen3.6 vLLM inference integration.
- VirtualHome manual-play Windows simulator evidence smoke with scene graph extraction, fixed household program execution, frame export, single-frame Qwen vision comparison, and episode-level multi-frame grounding.
- No model training or fine-tuning.
- No official runtime/API integration yet.
- A fail-closed official adapter boundary is implemented in `src/env_adapters/official_env.py`; official hidden results are not included.
- No validated AI2-THOR or ProcTHOR path yet.

Documents in this package:

- `technical_report_draft.md`: draft technical report structure and current results.
- `training_resource_disclosure.md`: model, data, simulator, and training disclosure.
- `reproducibility_statement.md`: environment assumptions and reproduction commands.
- `system_limitations.md`: known limitations and risks.
- `demo_commands.md`: command set for local demonstrations.
- `checklist.md`: current readiness against likely EAGC submission items.
- `final_submission_checklist.md`: final dry-run checklist for source package, report, disclosure, checksums, and optional evidence.
- `final_artifact_manifest.md`: local artifact inventory and exclusion list for handoff.
- `submission_email_draft.md`: placeholder email draft for official submission; it is not sent by any script.
- `open_source_statement.md`: source release and dependency redistribution statement.

Technical report export note:

- The source report is `submission_package/technical_report_draft.md`.
- The generated HTML fallback is `submission_bundle/reports/technical_report_draft.html`.
- If `submission_bundle/reports/technical_report_draft.pdf` is not generated automatically, open the HTML file in a browser, select Print, choose Save as PDF, save it as `technical_report_draft.pdf`, and place it in `submission_bundle/reports/`.
- The build status is recorded in `submission_bundle/reports/technical_report_build_status.json`.

Important framing:

- LocalSim is a self-built local evaluation environment, not official hidden evaluation.
- `local_heuristic_score` is a local debugging metric, not an official score.
- Visual-local hybrid tasks are symbolic world-model queries; they do not perform physical manipulation.
- Main final closed-loop Track 1 evidence is provided by LocalSim and MazeSim. VirtualHome is optional and is included in final `sample_outputs` only when it is a real continuous closed-loop Unity episode with `evidence_level=closed_loop_final_evidence`, `capture_mode=continuous_episode`, real frame images, real `vlm_frame_extraction`, and a predicted `world_model.json` generated from observations/action traces. The scene graph or explicit reference annotations are saved separately as `reference_world_model.json` for local validation only. Mock/synthetic/replay VirtualHome output is allowed only for CI/Docker smoke or optional diagnostics, not final evidence.
- MazeSim topology and anti-loop evidence use the same prediction-vs-reference framing: predicted `world_model.json` is generated from exploration observations and action results, while `reference_maze.json` is a local answer key used only for `comparison_report.json` and validation. MazeSim is synthetic and is not an official hidden-evaluation score.
- The current package is a readiness artifact, not a final qualification submission.

Optional strict VirtualHome final evidence command:

```powershell
python -m harness.run_virtualhome_continuous ^
  --virtualhome-exe "<YOUR_VIRTUALHOME_WINDOWS_EXEC_PATH>" ^
  --output-dir outputs/virtualhome_continuous ^
  --prediction-input-mode vlm_frame_extraction ^
  --max-steps 30 ^
  --target-room-coverage 0.8 ^
  --validate ^
  --final-submission
```

Replay validation:

```powershell
python -m harness.run_virtualhome_replay ^
  --frames "<EXPORTED_VIRTUALHOME_KEYFRAMES>" ^
  --manifest "<EXPORTED_VIRTUALHOME_KEYFRAMES>/frame_manifest.json" ^
  --output-dir outputs/virtualhome_exploration_replay ^
  --prediction-input-mode vlm_frame_extraction ^
  --validate
```

CI/Docker smoke replay uses the committed fixture frames explicitly as mock evidence:

```powershell
python -m harness.run_virtualhome_replay ^
  --frames assets/test_sequences/virtualhome_exploration/frames ^
  --manifest assets/test_sequences/virtualhome_exploration/frame_manifest.json ^
  --output-dir outputs/virtualhome_exploration_replay ^
  --prediction-input-mode mock_visual_extraction ^
  --validate
```
