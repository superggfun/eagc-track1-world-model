# Final Artifact Manifest

This manifest describes the intended v0.17.2 final handoff artifacts for the EAGC Track 1 local MVP dry run. It is a source-controlled checklist; generated runtime artifacts remain outside git.

## Core Submission Artifacts

- Source package zip: `dist/eagc_track1_mvp_source.zip`
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
- Intended handoff tag: `v0.17.2-final-submission-handoff`
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

## Handoff Notes

- The v0.17 resource profile found that the existing long-context `openclaw-vllm` endpoint can support the current VirtualHome evidence pipeline.
- Lightweight vLLM is documented only as a fallback.
- No local vLLM container changes were made.
- No model training or fine-tuning was performed.
