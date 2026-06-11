# Local vLLM Lightweight Profile

This note is for local VirtualHome coexistence testing on a single RTX 5090 32GB workstation.

## Why A Lightweight Profile Is Needed

The original Qwen vLLM container is configured for a long context workload, including a 262K context profile. That profile can reserve most of the RTX 5090 VRAM for model weights and KV cache. It is not suitable for testing a Unity-based simulator at the same time.

Do not delete, overwrite, restart, or reconfigure the original Qwen vLLM Docker container for the VirtualHome spike.

## Suggested Lightweight Settings

If a separate vLLM container is needed for coexistence testing, use a separate container name and port, for example:

```text
container name: eagc-vllm-qwen36-vh-lite
host port: 8001
model: qwen3.6-35b-nvfp4
```

Recommended profiles:

```text
max_model_len = 16384 or 32768
gpu_memory_utilization = 0.65 to 0.75
max_num_seqs = 1
```

Start from the smaller profile when `nvidia-smi` shows less than 4 GB free VRAM.

## Runtime Checks

Latest local probe on 2026-06-11 showed approximately 31,768 MiB used and 420 MiB free on the RTX 5090. That is not enough headroom for a Unity simulator plus Qwen inference, so coexistence testing should wait until VRAM is freed or a separate lightweight endpoint is deliberately started.

Check local GPU state:

```powershell
python tools/check_local_gpu_runtime.py
```

Check a vLLM endpoint without sending a large request:

```powershell
python tools/check_vllm_endpoint.py --base-url http://127.0.0.1:8000/v1
```

Check VirtualHome plus a tiny text-only vLLM request only after VirtualHome itself has succeeded:

```powershell
python tools/test_virtualhome_vllm_coexistence.py --base-url http://127.0.0.1:8000/v1
```

This coexistence check does not send images and does not use long context. It only calls `/models` and a tiny chat completion request.

## If Coexistence Fails

If VirtualHome and vLLM cannot share GPU memory reliably:

1. Run VirtualHome alone to produce `scene_graph.json`, `program_log.json`, and optional frames.
2. Stop VirtualHome.
3. Run Qwen / vLLM post-processing afterward.

This time-sliced workflow is preferred over modifying the original long-context vLLM container.

## v0.16.7 Status

The lightweight vLLM profile is documentation only and was not started for the VirtualHome evidence refresh. The original local Qwen vLLM Docker container should not be modified, restarted, deleted, or managed by this project automation.

Current validated VirtualHome vision tiers use the existing external endpoint only:

- `targeted-virtualhome-vision`
- `targeted-virtualhome-multiframe`

The latest multi-frame grounding smoke used the already-running endpoint, processed 5/5 VirtualHome task frames, and averaged about 2.8 seconds per frame. It did not start lightweight vLLM and did not change GPU memory settings.
