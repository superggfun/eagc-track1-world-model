# v0.16.6 Version Status: VirtualHome Episode-Level Multi-Frame Grounding

## Scope

v0.16.6 extends the v0.16.5 single-frame VirtualHome Qwen vision comparison into an episode-level multi-frame grounding smoke.

This version does not:

- train or fine-tune models,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion,
- claim official EAGC hidden evaluation.

## Commands

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-frame --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-vision --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-multiframe --timeout-seconds 600
python tools/build_virtualhome_evidence_report.py
python -m validators.validate_virtualhome_multiframe_grounding outputs/virtualhome_spike/multiframe_qwen_status.json
```

## Artifacts

Task frame export writes:

- `outputs/virtualhome_spike/task_frames/*.png`
- `outputs/virtualhome_spike/task_frame_export_status.json`

Multi-frame Qwen vision writes:

- `outputs/virtualhome_spike/multiframe_qwen_status.json`
- `outputs/virtualhome_spike/multiframe_qwen_vision.json`
- `outputs/virtualhome_spike/multiframe_qwen_raw_responses.json`

Episode-level comparison writes:

- `outputs/virtualhome_spike/episode_visual_symbolic_comparison.json`
- `outputs/virtualhome_spike/episode_visual_symbolic_comparison.md`

The evidence report is enriched with:

- `multiframe_available`
- `multiframe_count`
- `successful_vision_frame_count`
- `unique_visible_objects`
- `average_qwen_latency`
- `episode_visual_symbolic_comparison_path`

## Semantics

The comparison is conservative:

- selected task frames do not need to cover the full scene graph,
- scene graph-only objects are recorded as not visible, not as Qwen errors,
- unmatched visual objects are warnings,
- per-frame Qwen failures are recorded independently,
- all-frame Qwen failure becomes a graceful blocker rather than a failure of the VirtualHome symbolic/frame pipeline.

## Latest Local Smoke Result

Run date: 2026-06-11.

- VirtualHome manual-play connection: success.
- Household task smoke: 4/4 tasks succeeded.
- Task frame export: success.
- Exported task frames: 5 (`initial`, `sit_on_sofa`, `grab_object`, `open_object`, `place_object`).
- Multi-frame Qwen vision: 5/5 frames succeeded.
- Total visible object mentions: 40.
- Unique visible objects: 32.
- Matched object count: 33.
- Unmatched visual object count: 7.
- Action evidence count: 5.
- Relation match count: 8.
- Average Qwen latency: 2.784 seconds per frame.

These numbers are local smoke-test diagnostics only. They are not official EAGC scores.

## Remaining Limitations

- Multi-frame grounding uses selected snapshots, not full video.
- Qwen vision is not trained or fine-tuned for VirtualHome.
- Evidence matching is approximate and name/relation based.
- This remains a local simulator smoke test, not official EAGC runtime validation.
