# v0.16.7 Version Status: VirtualHome Evidence Submission Refresh

## Scope

v0.16.7 refreshes submission-facing documents and audit checks with the validated VirtualHome evidence pipeline from v0.16.2 through v0.16.6.

This version does not:

- train or fine-tune models,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing local Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion,
- add a new simulator adapter,
- claim official EAGC hidden evaluation.

## Validated VirtualHome Path

VirtualHome is currently validated through manual Play mode on Windows:

1. Start `VirtualHome.exe`.
2. Choose Windowed mode if prompted.
3. Press Play.
4. Run the project VirtualHome targeted tiers.

Validated results:

- Manual-play Windows VirtualHome simulator connected successfully.
- `127.0.0.1:8080` communication was validated.
- Scene graph extraction succeeded.
- Household program execution succeeded.
- 4/4 fixed household tasks succeeded.
- `converted_world_model.json` and `converted_episode_log.jsonl` were generated.

Automated VirtualHome startup is still not validated.

## Visual Observation And Grounding

Validated visual evidence:

- Frame export succeeded.
- Frame size: 640x480.
- Multi-frame task frames exported: 5.
- Existing local Qwen/vLLM endpoint was used.
- No new vLLM container was started.
- Lightweight vLLM was not started.
- Single-frame Qwen vision comparison succeeded.
- Episode-level multi-frame Qwen vision grounding succeeded.
- Multi-frame Qwen vision processed 5/5 frames.
- Average Qwen latency: about 2.8 seconds per frame.

Latest v0.16.7 refresh run:

- Multi-frame Qwen vision processed 5/5 frames.
- Total visible object mentions: 43.
- Unique visible objects: 36.
- Matched object count: 36.
- Unmatched visual object count: 7.
- Action evidence count: 7.
- Relation match count: 9.
- Average Qwen latency: 2.871 seconds per frame.

## Evidence Comparison Semantics

The comparison is evidence-driven and conservative:

- Visual objects are matched against simulator symbolic scene graph and converted world-model objects.
- Scene graph-only objects are treated as not visible in the selected frame(s), not as Qwen errors.
- Unmatched visual objects are warnings, not hard failures.
- Single-frame and selected multi-frame observations are not expected to cover the full symbolic scene graph.
- Raw Qwen responses and generated frame artifacts are runtime diagnostics and are not redistributed through git.

## Runtime Artifacts

When the local VirtualHome simulator is available, the optional evidence pipeline may write:

- `outputs/virtualhome_spike/scene_graph.json`
- `outputs/virtualhome_spike/program_log.json`
- `outputs/virtualhome_spike/converted_world_model.json`
- `outputs/virtualhome_spike/converted_episode_log.jsonl`
- `outputs/virtualhome_spike/frame_000.png`
- `outputs/virtualhome_spike/task_frames/`
- `outputs/virtualhome_spike/multiframe_qwen_status.json`
- `outputs/virtualhome_spike/episode_visual_symbolic_comparison.json`

These are runtime outputs. They should remain ignored by git and are not part of the source package.

## Remaining Limitations

- Manual Play is still required for the Windows VirtualHome simulator.
- There is no official EAGC runtime validation.
- ProcTHOR, Habitat, and AI2-THOR execution remain unvalidated in the main path.
- No model training or fine-tuning has been performed.
- There is no long-horizon video policy.
- This remains a simulator evidence smoke, not an official benchmark result.
