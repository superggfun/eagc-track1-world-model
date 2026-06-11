# System Limitations

This project is a local MVP and should not be presented as a final official EAGC Track 1 system.

Known limitations:

- LocalSim is not official hidden evaluation.
- LocalSim is a self-built environment and is simpler than realistic embodied simulators.
- The visual-local hybrid module is symbolic and does not perform physical manipulation.
- Physical actions in visual-only mode are intentionally unsupported.
- AI2-THOR / Habitat / ProcTHOR environment integration remains blocked or unvalidated and is not part of the validated path.
- AI2-THOR, Habitat, and ProcTHOR adapters are reserved interface targets only. They report capabilities and graceful blockers but are not validated backends.
- ALFRED support is currently an offline trajectory parser only; it does not run AI2-THOR or validate online closed-loop execution.
- ALFRED offline conversion is approximate and may not expose complete visual state, object locations, or simulator metadata.
- The included ALFRED-like fixture is synthetic and only verifies adapter mechanics.
- Real ALFRED dataset conversion has not been validated on this machine.
- VirtualHome manual-play Windows simulator smoke has succeeded for scene graph extraction, four fixed household task executions, frame export, single-frame Qwen vision comparison, and multi-frame grounding, but it still requires manual Play and is not an official runtime.
- The official EAGC runtime, official hidden evaluation environments, and official scoring are not available in this local package.
- There is no trained student model.
- No model fine-tuning or distillation has been performed.
- Performance is not yet optimized.
- No full benchmark-scale evaluation has been completed.
- `local_heuristic_score` is a local debugging metric, not an official score.
- Visual evidence depends on real Qwen vision extraction, so object/relation counts may vary across runs.
- VirtualHome single-frame and selected multi-frame observations cannot cover the full symbolic scene graph; scene graph-only objects are treated as not visible rather than Qwen errors.
- VirtualHome unmatched visual objects are warnings in the evidence report, not hard failures of the symbolic simulator pipeline.
- No long-horizon video policy has been validated.
- VirtualHome runtime outputs, exported frames, and raw Qwen responses are not redistributed in git.
- The source package is not a final Docker submission.
- The Docker image packages the agent code only and does not include Qwen model weights.
- The final model endpoint, mounted model, or organizer-hosted inference strategy requires organizer clarification.
- The official submission portal and official runtime schema are not available yet.
- Docker has been prepared for mock-mode agent smoke testing; real vLLM access depends on host/container networking.
- The v0.17 resource profile is a local workstation snapshot and is not a guarantee of performance under official infrastructure.
- The current pipeline works with the existing long-context vLLM endpoint, but longer VirtualHome episodes, more frames, or concurrent workloads may require a separate lightweight endpoint in the future.

Current safest claim:

The system is a backend-agnostic local Track 1 MVP and readiness baseline that demonstrates auditable world-model construction, planning, exception recovery, visual evidence reporting, and reproducible local testing on validated LocalSim and VirtualHome paths.
