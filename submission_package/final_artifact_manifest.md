# Final Artifact Manifest

This manifest describes the intended v0.17.6 final handoff artifacts for the EAGC Track 1 local MVP dry run after the MazeSim anti-loop stress refresh. It is a source-controlled checklist; generated runtime artifacts remain outside git.

## Core Submission Artifacts

- Source package zip: `dist/source.zip`
- Submission bundle directory: `submission_bundle/`
- Technical report source: `submission_package/technical_report_draft.md`
- Technical report HTML fallback: `submission_bundle/reports/technical_report_draft.html`
- Technical report PDF: `submission_bundle/reports/technical_report_draft.pdf` if generated locally, otherwise export from HTML manually.
- Technical report build status: `submission_bundle/reports/technical_report_build_status.json`
- Training resource disclosure: `submission_package/training_resource_disclosure.md`
- Reproducibility statement: `submission_package/reproducibility_statement.md`
- System limitations: `submission_package/system_limitations.md`
- Demo commands: `submission_package/demo_commands.md`
- Final submission checklist: `submission_package/final_submission_checklist.md`
- Submission email draft: `submission_package/submission_email_draft.md`
- Open-source statement: `submission_package/open_source_statement.md`
- Checksums: `submission_bundle/checksums/SHA256SUMS.txt`

## Git State

- Baseline commit before this handoff: `64030ec`
- Baseline tag before this handoff: `v0.17.1-final-submission-dry-run`
- Intended handoff tag: `v0.17.6-final-submission-refresh-maze-anti-loop`
- For the exact handoff commit after tagging, run:

```powershell
git rev-parse --short HEAD
git tag --points-at HEAD
```

## Optional Evidence Artifacts

These artifacts are useful for review but are not committed to git:

- VirtualHome evidence report: `outputs/virtualhome_spike/visual_symbolic_evidence_report.md`
- VirtualHome resource profile: `outputs/resource_profile/virtualhome_vllm_resource_profile.md`
- Coexistence smoke status: `outputs/resource_profile/coexistence_smoke_status.json`
- MazeSim stress outputs: `outputs/maze_stress/world_model.json`, `episode_log.jsonl`, `run_audit.json`, `maze_metrics.json`, `status.json`, `reference_maze.json`, and `comparison_report.json`
- MazeSim anti-loop outputs: `outputs/maze_anti_loop/world_model.json`, `episode_log.jsonl`, `run_audit.json`, `maze_metrics.json`, `status.json`, `reference_maze.json`, `comparison_report.json`, per-scenario subdirectories, and `anti_loop_report.md`
- Test suite reports: `outputs/test_suite_reports/`
- Pre-submission audit: `outputs/pre_submission_audit/audit_report.md`
- GitHub readiness report: `outputs/final_submission/github_push_readiness.md`

## Not Included

- Qwen model weights.
- Docker image tar unless explicitly requested.
- VirtualHome executable, Unity assets, or local simulator install folders.
- ALFRED dataset.
- ProcTHOR, Habitat, or AI2-THOR assets.
- Runtime `outputs/`, including frames and raw Qwen responses.
- `dist/`, except as a generated local artifact.
- `submission_bundle/`, except as a generated local artifact.
- `source_pack/`.
- `outputs/maze_stress/` runtime artifacts.
- `outputs/maze_anti_loop/` runtime artifacts.

## Handoff Notes

- The v0.17 resource profile found that the existing long-context `openclaw-vllm` endpoint can support the current VirtualHome evidence pipeline.
- Lightweight vLLM is documented only as a fallback.
- No local vLLM container changes were made.
- No model training or fine-tuning was performed.
- MazeSim targeted topology stress passed with success=true, goal_found=true, steps_taken=28, shortest_path_length=14, map_coverage=0.88, blocked_edges_encountered=2, and replans=7.
- MazeSim anti-loop stress passed: loop_lure_maze succeeded in 8 steps, dead_end_comb_maze succeeded in 26 steps, blocked_shortcut_maze succeeded in 11 steps, and unreachable_goal_maze terminated gracefully with goal_unreachable_or_budget_exhausted in 3 steps.
- MazeSim is synthetic and does not claim official EAGC runtime validation.
