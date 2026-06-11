# EAGC Track 1 Pre-Submission Readiness Package

This folder contains a pre-submission readiness package for the current EAGC Track 1 local MVP. It is intended for internal review, teacher discussion, technical report drafting, and future qualification submission preparation.

Current project stage: `v0.16.7` submission readiness refresh with VirtualHome evidence pipeline documentation.

Current system scope:

- LocalSim Track 1-style MVP for exploration, world-model construction, planning, execution, and recovery.
- Visual-local hybrid prototype for multi-frame image observation, world-model update, symbolic visual task answering, evidence explanation, and uncertainty reporting.
- Real local Qwen3.6 vLLM inference integration.
- VirtualHome manual-play Windows simulator evidence smoke with scene graph extraction, fixed household program execution, frame export, single-frame Qwen vision comparison, and episode-level multi-frame grounding.
- No model training or fine-tuning.
- No official runtime/API integration yet.
- No validated AI2-THOR or ProcTHOR path yet.

Documents in this package:

- `technical_report_draft.md`: draft technical report structure and current results.
- `training_resource_disclosure.md`: model, data, simulator, and training disclosure.
- `reproducibility_statement.md`: environment assumptions and reproduction commands.
- `system_limitations.md`: known limitations and risks.
- `demo_commands.md`: command set for local demonstrations.
- `checklist.md`: current readiness against likely EAGC submission items.
- `open_source_statement.md`: source release and dependency redistribution statement.

Important framing:

- LocalSim is a self-built local evaluation environment, not official hidden evaluation.
- `local_heuristic_score` is a local debugging metric, not an official score.
- Visual-local hybrid tasks are symbolic world-model queries; they do not perform physical manipulation.
- VirtualHome is an optional local simulator evidence path and does not replace official EAGC runtime validation.
- The current package is a readiness artifact, not a final qualification submission.
