# v0.17 Version Status: VirtualHome + vLLM Resource Profile

## Scope

v0.17 adds a read-only resource profile and coexistence audit for the validated VirtualHome manual-play pipeline and the already-running local Qwen/vLLM endpoint.

This version does not:

- train or fine-tune models,
- start lightweight vLLM,
- stop, restart, delete, rebuild, or reconfigure the original Qwen/vLLM Docker container,
- run AI2-THOR, Habitat, or ProcTHOR,
- add a new simulator adapter,
- claim official EAGC hidden evaluation.

## Why This Audit Exists

v0.16.5 and v0.16.6 showed that the existing local Qwen/vLLM endpoint can complete VirtualHome single-frame and episode-level multi-frame vision grounding. v0.17 records the resource conditions around that pipeline so the result is easier to reproduce and explain.

## New Commands

```powershell
python tools/profile_virtualhome_vllm_resources.py
python tools/test_virtualhome_vllm_resource_smoke.py
python tools/run_test_suite.py --tier targeted-resource-profile --timeout-seconds 300
```

The tier is optional. It is not part of `fast` and is not part of aggregate `targeted`.

## Outputs

The resource profile writes:

- `outputs/resource_profile/virtualhome_vllm_resource_profile.json`
- `outputs/resource_profile/virtualhome_vllm_resource_profile.md`

The coexistence smoke writes:

- `outputs/resource_profile/coexistence_smoke_status.json`

These files are runtime diagnostics and should remain ignored by git.

## Recorded Signals

The resource profile records:

- GPU memory total/used/free from `nvidia-smi`,
- GPU compute process list,
- Docker availability and running container summaries,
- whether an `openclaw-vllm` or vLLM-like container appears to be running,
- whether VirtualHome `127.0.0.1:8080` is listening,
- whether the Qwen `/models` endpoint is reachable.

The coexistence smoke records:

- GPU memory before and after,
- VirtualHome frame readiness,
- minimal Qwen text latency,
- minimal Qwen vision latency on a VirtualHome frame when available,
- success, skip, or blocker reason.

## Lightweight vLLM Recommendation

Lightweight vLLM remains a fallback, not the default route.

Current recommendation:

- Keep using the existing endpoint for the validated VirtualHome evidence smoke if it remains stable.
- Do not modify or restart the original long-context Qwen/vLLM container for this audit.
- Consider a separate lite profile only if longer episodes, more frames, or concurrent workloads become unstable.

## Latest Local Audit Result

Run date: 2026-06-11.

- GPU: NVIDIA GeForce RTX 5090.
- GPU memory during profile: 32607 MiB total, 31674 MiB used, 514 MiB free.
- Existing vLLM-like container: running.
- Container image: `vllm/vllm-openai:v0.20.0`.
- Port mapping: `127.0.0.1:8000->8000/tcp`.
- VirtualHome manual-play port `127.0.0.1:8080`: listening.
- Qwen endpoint `/models`: available.
- Model id: `qwen3.6-35b-nvfp4`.
- Resource smoke text latency: 0.141 seconds.
- Resource smoke frame vision latency: 0.696 seconds.
- Resource smoke visible object count: 7.
- Multi-frame VirtualHome grounding rerun: 5/5 frames succeeded.
- Multi-frame average Qwen latency: 2.722 seconds per frame.
- Latest multi-frame relation match count: 12.

Interpretation: the original long-context vLLM profile has high memory residency, but the current VirtualHome evidence pipeline still completed the text, frame-vision, and multi-frame grounding checks. A lightweight vLLM profile is therefore not required for the current smoke pipeline.

Suggested future fallback profile, if explicitly allowed:

- `max_model_len = 16384` or `32768`
- `gpu_memory_utilization = 0.76` to `0.80`
- `max_num_seqs = 1`
- separate host port such as `8001`
- separate container name

## Remaining Limitations

- The resource profile is a local workstation audit, not an official benchmark.
- VirtualHome still requires manual Play mode.
- The smoke uses selected frames, not long-horizon video.
- Qwen vision output can vary slightly across runs.
- Runtime outputs, frames, and raw responses are not redistributed in git.

## v0.17.1 Dry-Run Follow-Up

v0.17.1 does not add new runtime functionality. It packages the v0.17 resource conclusion into final submission dry-run materials:

- `submission_package/final_submission_checklist.md`
- `submission_package/submission_email_draft.md`
- refreshed technical report, reproducibility, training disclosure, limitations, checklist, and demo commands
- final pre-submission audit checks for source package, submission bundle, technical report build status, and resource profile helpers

The v0.17 conclusion remains unchanged: the current VirtualHome evidence pipeline works with the existing long-context vLLM endpoint, and lightweight vLLM is a fallback only.
