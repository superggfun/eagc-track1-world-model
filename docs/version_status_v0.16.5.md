# v0.16.5 Version Status: VirtualHome Qwen Vision Comparison

## Scope

v0.16.5 sends the already-exported VirtualHome frame through the existing local Qwen/vLLM vision path and compares the visual extraction with VirtualHome symbolic state.

This version does not:

- train or fine-tune models,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion,
- claim official EAGC runtime validation.

## Preconditions

The intended manual-play setup is:

1. Start `VirtualHome.exe`.
2. Select Windowed mode if prompted.
3. Press Play.
4. Confirm `127.0.0.1:8080` is listening.
5. Run `targeted-virtualhome-frame` first so `outputs/virtualhome_spike/frame_000.png` exists.
6. Confirm the existing local Qwen/vLLM endpoint is available.

## Commands

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-frame --timeout-seconds 300
python tools/run_test_suite.py --tier targeted-virtualhome-vision --timeout-seconds 300
python tools/build_virtualhome_evidence_report.py
python -m validators.validate_virtualhome_visual_symbolic_comparison outputs/virtualhome_spike/qwen_vision_status.json
```

## Artifacts

Qwen vision extraction writes:

- `outputs/virtualhome_spike/qwen_vision_status.json`
- `outputs/virtualhome_spike/qwen_vision_extraction.json`
- `outputs/virtualhome_spike/qwen_vision_raw_response.json`

Visual-symbolic comparison writes:

- `outputs/virtualhome_spike/visual_symbolic_comparison.json`
- `outputs/virtualhome_spike/visual_symbolic_comparison.md`

The existing evidence report is enriched with:

- `qwen_vision_available`
- `qwen_visible_object_count`
- `qwen_matched_object_count`
- `qwen_unmatched_visual_object_count`
- `visual_symbolic_comparison_path`

Latest run:

- Qwen vision extraction: success
- Qwen call count: 1
- Qwen latency: 2.821 seconds
- frame: 640x480
- Qwen visible object count: 7
- matched visible object count: 6
- unmatched visual object count: 1
- Qwen visible relation count: 6
- matched relation count: 2
- unmatched visual object was recorded as a warning, not a pipeline failure

## Comparison Semantics

The comparison is conservative:

- Qwen is only expected to describe the single rendered frame.
- Qwen is not expected to see all objects in the 440-object symbolic scene graph.
- A Qwen-visible object counts as supported if an approximately matching symbolic object exists.
- Scene graph objects not visible in the frame are not Qwen failures.
- Missing small visual objects are not hard failures.
- Hallucinated visual objects are warnings and do not invalidate the VirtualHome symbolic pipeline.

## Graceful Blockers

If Qwen is unavailable or unstable, the tier records a blocker in `qwen_vision_status.json` with a reason such as:

- `qwen_endpoint_unavailable`
- `qwen_vision_call_failed`
- `qwen_vision_parse_failed`
- `qwen_vision_timeout`

This does not invalidate the v0.16.4 VirtualHome symbolic/frame pipeline.

## Remaining Limitations

- This is a single-frame visual comparison, not video or multi-view perception.
- Qwen vision is not trained or fine-tuned on VirtualHome.
- The comparison is name/relation based and approximate.
- This is not official EAGC runtime validation.
