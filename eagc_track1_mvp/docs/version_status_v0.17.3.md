# v0.17.3 Version Status: Official Simulator Adapter Interface Freeze

v0.17.3 is a small interface-freeze release. It does not add a new simulator integration, does not train a model, and does not run AI2-THOR, Habitat, ProcTHOR, VirtualHome, or lightweight vLLM.

## What Changed

- `env_adapters/base.py` now documents the frozen adapter interface:
  - `reset()`
  - `observe()`
  - `get_scene_graph()`
  - `capture_frame()`
  - `execute_action(action)`
  - `get_agent_state()`
  - `close()`
  - `capabilities()`
- `env_adapters/registry.py` provides static backend capability records without starting simulators.
- `tools/list_env_adapters.py` writes adapter capability reports under `outputs/adapter_capabilities/`.
- Reserved Habitat and ProcTHOR stubs were added without importing heavy simulator dependencies.
- AI2-THOR action execution now returns an explicit unvalidated blocker rather than a fake success packet.

## Backend Status

Validated:

- LocalSim: validated local Track 1 MVP backend.
- VirtualHome: validated Windows manual-play backend for scene graph, frame export, and action-program smoke.

Offline:

- ALFRED offline: validated for the synthetic fixture only.

Reserved but not validated:

- AI2-THOR: Windows/WSL/cloud rendering stack unresolved.
- Habitat: EGL/Vulkan/headless rendering unresolved.
- ProcTHOR: depends on AI2-THOR/ProcTHOR runtime availability.

## Submission Framing

The architecture is backend-agnostic, but only LocalSim and VirtualHome should be described as validated simulator backends. Rendering blockers were diagnosed and documented rather than hidden or bypassed. The official EAGC runtime remains unvalidated because it has not been provided.

## Validation Scope

Required checks for this release:

```powershell
python -m compileall .
python tools/run_test_suite.py --tier fast
python tools/list_env_adapters.py
python tools/pre_submission_audit.py
```

No aggregate targeted, standard, full, simulator, or training tests are part of this release.
