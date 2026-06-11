# v0.17.1 Version Status: Final Submission Dry-Run Package

## Scope

v0.17.1 prepares a final dry-run package for review before an official EAGC qualification submission. It does not add new agent features.

This version does not:

- train or fine-tune models,
- run AI2-THOR, Habitat, or ProcTHOR,
- start lightweight vLLM,
- modify, restart, delete, rebuild, or manage the existing local Qwen/vLLM Docker container,
- add a simulator adapter,
- send email.

## Included Dry-Run Materials

Submission-facing files now include:

- `submission_package/final_submission_checklist.md`
- `submission_package/submission_email_draft.md`
- `submission_package/technical_report_draft.md`
- `submission_package/training_resource_disclosure.md`
- `submission_package/reproducibility_statement.md`
- `submission_package/system_limitations.md`
- `submission_package/demo_commands.md`
- `submission_package/checklist.md`
- `submission_package/open_source_statement.md`

The email draft uses `[OFFICIAL_SUBMISSION_EMAIL]` and other placeholders. It is not sent by project automation.

## Resource Profile Conclusion

v0.17 resource profile result carried into this dry run:

- GPU: RTX 5090, 32607 MiB total.
- Profile snapshot: 31674 MiB used, 514 MiB free.
- Existing `openclaw-vllm`: running on `127.0.0.1:8000`.
- VirtualHome manual-play: listening on `127.0.0.1:8080`.
- Qwen model: `qwen3.6-35b-nvfp4`.
- Text smoke latency: about 0.141 seconds.
- Frame vision smoke latency: about 0.696 seconds.
- Multi-frame average Qwen latency: about 2.722 seconds per frame.

Conclusion: the current VirtualHome evidence pipeline works with the existing long-context vLLM endpoint. Lightweight vLLM is documented as fallback only and was not started.

## Package Outputs

The dry-run package generation uses:

```powershell
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/eagc_track1_mvp_source.zip
python tools/create_submission_bundle.py
python tools/build_report_pdf.py
```

If no local PDF backend is available, `tools/build_report_pdf.py` writes HTML fallback and `submission_bundle/reports/technical_report_build_status.json`.

## Exclusions

The following are not committed to git:

- `outputs/`
- `dist/`
- `submission_bundle/`
- raw frames
- raw Qwen responses
- model weights
- VirtualHome executable/assets
- ALFRED datasets
- Docker image tar unless explicitly requested

## Validation

Required dry-run checks:

```powershell
python -m compileall .
python tools/run_test_suite.py --tier fast
python tools/run_test_suite.py --tier targeted-text --timeout-seconds 300
python tools/pre_submission_audit.py
```

Aggregate `targeted`, `standard`, and `full` are intentionally not part of this dry run unless explicitly requested.
