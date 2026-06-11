# Final Submission Dry-Run Checklist

This checklist is for a local dry run before an official EAGC Track 1 qualification submission. It does not imply that an official portal or final submission schema has been released.

## Required Files

- [ ] Source package zip: `dist/eagc_track1_mvp_source.zip`
- [ ] Technical report draft: `submission_package/technical_report_draft.md`
- [ ] Technical report HTML/PDF fallback:
  - `submission_bundle/reports/technical_report_draft.html`
  - `submission_bundle/reports/technical_report_build_status.json`
  - PDF is included only if a local PDF backend is available.
  - If PDF generation is unavailable locally, open `submission_bundle/reports/technical_report_draft.html` in a browser, choose Print, Save as PDF, name it `technical_report_draft.pdf`, and place it in `submission_bundle/reports/`.
- [ ] Training resource disclosure: `submission_package/training_resource_disclosure.md`
- [ ] Reproducibility statement: `submission_package/reproducibility_statement.md`
- [ ] System limitations: `submission_package/system_limitations.md`
- [ ] Demo commands: `submission_package/demo_commands.md`
- [ ] Open-source statement: `submission_package/open_source_statement.md`
- [ ] Checksums: `submission_bundle/checksums/SHA256SUMS.txt`
- [ ] Final artifact manifest: `submission_package/final_artifact_manifest.md`
- [ ] Submission email draft: `submission_package/submission_email_draft.md`
- [ ] Docker instructions:
  - `Dockerfile`
  - `docker/README_DOCKER.md`
  - `submission_bundle/docker/`

## Optional Evidence

- [ ] VirtualHome evidence report:
  - `outputs/virtualhome_spike/visual_symbolic_evidence_report.json`
  - `outputs/virtualhome_spike/visual_symbolic_evidence_report.md`
- [ ] VirtualHome resource profile:
  - `outputs/resource_profile/virtualhome_vllm_resource_profile.json`
  - `outputs/resource_profile/virtualhome_vllm_resource_profile.md`
  - `outputs/resource_profile/coexistence_smoke_status.json`
- [ ] MazeSim topology stress outputs:
  - `outputs/maze_stress/world_model.json`
  - `outputs/maze_stress/episode_log.jsonl`
  - `outputs/maze_stress/maze_metrics.json`
  - `outputs/maze_stress/status.json`
- [ ] Test suite reports:
  - `outputs/test_suite_reports/*_fast_report.json`
  - `outputs/test_suite_reports/*_targeted-text_report.json`
  - `outputs/test_suite_reports/*_targeted-maze_report.json`
  - optional VirtualHome targeted reports if the simulator was manually running.

These optional evidence artifacts are local runtime outputs and are not committed to git. Include them only if the official submission instructions request runtime artifacts.

## Not Included

- [ ] Qwen model weights.
- [ ] Docker image tar, unless explicitly requested.
- [ ] VirtualHome executable or Unity assets.
- [ ] ALFRED dataset.
- [ ] ProcTHOR / AI2-THOR / Habitat assets.
- [ ] `outputs/` raw frames.
- [ ] `outputs/maze_stress/` runtime artifacts.
- [ ] Raw Qwen responses.
- [ ] `dist/` directory contents in git.
- [ ] `submission_bundle/` in git.
- [ ] `source_pack/`.

## Current Resource Conclusion

- Existing `openclaw-vllm` endpoint: works for current VirtualHome evidence smoke.
- Lightweight vLLM: documented as fallback only; not started.
- No container changes were made.
- No model training or fine-tuning was performed.
- MazeSim targeted topology stress passed with success=true, goal_found=true, steps_taken=28, shortest_path_length=14, map_coverage=0.88, blocked_edges_encountered=2, and replans=7.
- MazeSim is synthetic and does not claim official EAGC runtime validation.

## Final Local Checks

```powershell
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
python tools/create_submission_bundle.py
python tools/build_report_pdf.py
python tools/run_test_suite.py --tier fast
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-maze --timeout-seconds 300
python tools/pre_submission_audit.py
python tools/check_github_push_readiness.py
```

Do not run aggregate `targeted`, `standard`, or `full` unless explicitly requested.
