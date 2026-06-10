# Architecture Overview

This project is a local EAGC Track 1 MVP baseline. It implements a complete local loop for exploration, world-model construction, task planning, closed-loop execution, exception recovery, and audit-friendly validation.

It does not depend on an official EAGC runtime/API/schema. It does not train models. The current simulator path is LocalSim, a controlled local environment used to exercise Track 1-style procedures before official infrastructure is available.

## Main Components

- `env_adapters/local_sim_env.py`: deterministic local simulator with rooms, topology, object state, partial observability, action execution, and controlled exceptions.
- `env_adapters/local_sim_generator.py`: randomized hidden-style LocalSim episode generation with public agent config and evaluator-only hidden spec separation.
- `track1_runner/procedure_runner.py`: official-style procedure runner with exploration, task reception/planning, execution, recovery, and local scoring.
- `clients/qwen_client.py`: OpenAI-compatible local vLLM client for Qwen text and vision calls, with call auditing.
- `perception/vlm_extractor.py`: converts text or vision observations into structured extraction JSON for the world model.
- `world_model/`: schema, store, incremental update, semantic consistency helpers, and action effects.
- `planner/rule_planner.py`: rule-based plan generation using the world model and action ontology.
- `planner/replanner.py`: exception-aware recovery planning for relocation, locked doors, unavailable containers, and tool substitution.
- `task_evaluator/`: local task completion and blocked-recovery evaluation.
- `validators/`: output, semantic, procedure, leakage, vision, and simulator smoke validators.
- `scoring/track1_score.py`: local heuristic score used only for debugging and comparison, not an official EAGC score.
- `diagnostics/` and `tools/replay_random_local_sim_failure.py`: failure replay and root-cause diagnostics for random LocalSim cases.

## Data Flow

1. The environment emits an agent-visible observation.
2. Qwen extracts structured perception from the observation.
3. The world model incrementally merges rooms, topology, objects, states, relations, uncertainty, plans, and exceptions.
4. The planner proposes actions from the action ontology.
5. The environment executes actions and returns success or structured exceptions.
6. The replanner generates recovery actions when needed.
7. Validators audit output structure, semantic consistency, leakage boundaries, and Track 1 procedure rules.

