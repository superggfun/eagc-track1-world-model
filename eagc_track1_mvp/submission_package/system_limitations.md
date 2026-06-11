# System Limitations

This project is a local MVP and should not be presented as a final official EAGC Track 1 system.

Known limitations:

- LocalSim is not official hidden evaluation.
- LocalSim is a self-built environment and is simpler than realistic embodied simulators.
- The visual-local hybrid module is symbolic and does not perform physical manipulation.
- Physical actions in visual-only mode are intentionally unsupported.
- AI2-THOR / ProcTHOR environment integration remains blocked and is not part of the validated path.
- ALFRED support is currently an offline trajectory parser only; it does not run AI2-THOR or validate online closed-loop execution.
- ALFRED offline conversion is approximate and may not expose complete visual state, object locations, or simulator metadata.
- There is no trained student model.
- No model fine-tuning or distillation has been performed.
- Performance is not yet optimized.
- No full benchmark-scale evaluation has been completed.
- `local_heuristic_score` is a local debugging metric, not an official score.
- Visual evidence depends on real Qwen vision extraction, so object/relation counts may vary across runs.
- The source package is not a final Docker submission.
- The Docker image packages the agent code only and does not include Qwen model weights.
- The final model endpoint, mounted model, or organizer-hosted inference strategy requires organizer clarification.
- The official submission portal and official runtime schema are not available yet.
- Docker has been prepared for mock-mode agent smoke testing; real vLLM access depends on host/container networking.

Current safest claim:

The system is a local Track 1 MVP and readiness baseline that demonstrates auditable world-model construction, planning, exception recovery, visual evidence reporting, and reproducible local testing.
