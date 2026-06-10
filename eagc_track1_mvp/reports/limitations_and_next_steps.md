# Limitations and Next Steps

## Limitations

- LocalSim is a self-built local environment, not an official Track 1 runtime.
- ProcTHOR and AI2-THOR are not integrated into the stable evaluation path.
- AI2-THOR remains experimental in this repository because Windows/WSL rendering smoke tests did not pass reliably.
- Vision support covers single-image smoke testing and a local three-frame visual sequence smoke validation. It is still not a full embodied simulator integration.
- Qwen is used only for inference through local vLLM. No model training, fine-tuning, or distillation has been performed.
- LocalSim is intentionally simpler than real embodied simulation environments.
- `local_heuristic_score` is a local debugging and comparison metric, not an official EAGC score.

## Next Steps

- v0.9.1: multi-frame visual sequence smoke validation is complete for a local three-image bedroom sequence.
- v1.0: retry ProcTHOR / AI2-THOR environment integration using Docker/Linux or another stable rendering setup.
- v1.1: failure-driven planner improvements based on replay diagnostics.
- v1.2: consider training or distillation only after data, tasks, and evaluation are stable.
- v1.3: performance profiling for latency, Qwen call budget, and long-run robustness.
