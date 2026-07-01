# v0.16.4 Version Status: VirtualHome Frame Export and Visual-Symbolic Evidence

## Scope

v0.16.4 extends the validated VirtualHome manual-play route with an optional frame export probe and a visual-symbolic evidence report.

This version does not:

- train or fine-tune models,
- call Qwen or Qwen vision,
- start lightweight vLLM,
- modify, restart, delete, or manage the existing Qwen vLLM Docker container,
- run AI2-THOR, Habitat, ProcTHOR, or ALFRED real data conversion.

## Manual-Play Route

The known-good setup remains:

1. Start `VirtualHome.exe`.
2. Select Windowed mode if prompted.
3. Press Play.
4. Confirm `127.0.0.1:8080` is listening.

Run the manual program regression:

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-manual --timeout-seconds 300
```

Run the frame export and evidence report probe:

```powershell
python tools/run_test_suite.py --tier targeted-virtualhome-frame --timeout-seconds 300
```

Both tiers skip gracefully if the manual Play port is not listening.

## Frame Export

Frame export uses VirtualHome's documented camera API:

- `camera_count()`
- `camera_image([camera_index], mode="normal", image_width=640, image_height=480)`

Expected artifacts:

- `outputs/virtualhome_spike/frame_export_status.json`
- `outputs/virtualhome_spike/frame_000.png` if export succeeds

Latest run:

- frame export: success
- frame dimensions: 640x480
- camera index: 86 of 87 cameras
- task success count: 4
- scene graph object count: 444
- scene graph relation count: 932
- converted world-model object count: 440
- converted world-model relation count: 932

If frame export fails, the failure is recorded in `frame_export_status.json` with a reason such as:

- `virtualhome_frame_api_unavailable`
- `virtualhome_camera_not_configured`
- `virtualhome_frame_export_timeout`
- `virtualhome_frame_export_unsupported`

Frame export failure does not invalidate the already-validated scene graph and program execution pipeline.

## Evidence Report

v0.16.4 adds:

```powershell
python tools/build_virtualhome_evidence_report.py
```

The report writes:

- `outputs/virtualhome_spike/visual_symbolic_evidence_report.json`
- `outputs/virtualhome_spike/visual_symbolic_evidence_report.md`

It summarizes:

- scene graph object and relation counts,
- converted world-model object and relation counts,
- executed and successful task counts,
- frame availability and dimensions if available,
- limitations of symbolic simulator state versus visual observation.

## Remaining Limitations

- Automated Unity startup is still not validated.
- The VirtualHome frame is not yet compared with Qwen vision output.
- The frame export path is a smoke test, not video generation or dataset creation.
- VirtualHome remains an optional Windows simulator spike, not an official EAGC environment.
