# Training Resource Disclosure

## Training Status

No model training or fine-tuning has been performed yet.

The current project uses inference only.

## Model Used For Inference

- Model family/name used locally: Qwen3.6-35B-A3B-NVFP4.
- Configured model identifier: `qwen3.6-35b-nvfp4`.
- Serving stack: local vLLM OpenAI-compatible endpoint.
- Default endpoint: `http://127.0.0.1:8000/v1`.

## Environment And Data Sources

- LocalSim: self-built symbolic/local environment for Track 1-style development and evaluation.
- Mock environments: deterministic text-only episodes for testing.
- Visual sequence smoke tests: local bedroom images placed under `assets/test_sequences/bedroom_sequence/`.
- The visual images are local smoke-test resources and are not committed to git.

## Simulator Status

AI2-THOR/ProcTHOR has not been validated in the stable path due to platform/runtime/rendering issues. AI2-THOR adapter code may exist as experimental work, but it is not part of the current validated submission path.

## Online API Use

No online model APIs are used during evaluation runs. The system is designed to call a local vLLM endpoint.

## Training Resources

Current training resource use:

- Training data: none.
- Fine-tuning data: none.
- Student model: none.
- Distillation: none.
- External online model calls: none during evaluation.

Hardware used for local development/testing:

- RTX 5090 32GB.
