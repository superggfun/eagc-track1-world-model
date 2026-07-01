# vLLM / VirtualHome GPU Budget

This note records the local GPU-sharing plan for the optional VirtualHome Windows spike.

## Constraint

The current workstation uses a single RTX 5090 32GB GPU. The original long-context vLLM container can consume nearly all available VRAM through model weights and KV cache reservation. That profile is useful for long-context agent runs, but it is not a good default when a Unity-based simulator also needs graphics memory.

Do not delete, overwrite, or reconfigure the original vLLM container for this spike.

## Lightweight vLLM Goal

The lightweight profile is a separate optional container intended to reduce KV cache and scheduler memory so VirtualHome / Unity has more room. It should run on a different host port, such as `8001`, while preserving the original endpoint on `8000`.

Recommended initial profile:

```text
served_model_name = qwen3.6-35b-nvfp4
max_model_len = 32768
gpu_memory_utilization = 0.80
max_num_seqs = 1
host port = 8001
container port = 8000
```

If remaining free VRAM is below roughly 4 GB after startup, try a smaller profile:

```text
max_model_len = 16384
gpu_memory_utilization = 0.76 to 0.78
max_num_seqs = 1
```

If VirtualHome and Qwen still cannot run at the same time, switch to a time-sliced workflow:

1. Run VirtualHome first to generate scene graphs, program logs, frames, and videos.
2. Stop the simulator.
3. Run Qwen vision / world-model extraction as post-processing.

## Tools

Check current GPU memory and processes:

```powershell
python tools/check_gpu_budget.py
```

Start the optional lightweight vLLM profile:

```powershell
scripts/start_vllm_qwen36_vh_lite.ps1
```

The start script is dry-run by default. It inspects existing Docker containers read-only, tries to identify the original vLLM image and mounts, and refuses to create a new container if inference is ambiguous. To actually create the separate container after reviewing the plan:

```powershell
scripts/start_vllm_qwen36_vh_lite.ps1 -ForceRun
```

Test the optional endpoint:

```powershell
python tools/test_vllm_lite_endpoint.py
```

Stop only the optional lightweight container:

```powershell
scripts/stop_vllm_qwen36_vh_lite.ps1
```

The stop script only stops `eagc-vllm-qwen36-vh-lite`; it does not remove or modify the original vLLM container.

## Current Local Probe

Latest local probe on 2026-06-11:

- `python tools/check_gpu_budget.py` succeeded.
- The RTX 5090 reported 32,607 MB total memory and less than 1 GB free during the probe.
- This confirms the original long-context vLLM / desktop workload profile leaves too little headroom for a Unity simulator in the current state.
- `scripts/start_vllm_qwen36_vh_lite.ps1` dry-run successfully identified the existing read-only candidate vLLM container as `openclaw-vllm` using image `vllm/vllm-openai:v0.20.0`.
- No new container was created during the dry-run.
- `python tools/test_vllm_lite_endpoint.py` wrote `outputs/vllm_lite_test/status.json`; the default `http://127.0.0.1:8001/v1` endpoint returned HTTP 401 in this probe, so a usable lightweight endpoint is not currently validated.

Do not start the optional lightweight container until the GPU budget and port/auth behavior are reviewed.
