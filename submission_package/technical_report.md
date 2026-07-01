# EAGC 2026 Track 1 Technical Report

## Summary

This repository contains a local Track 1 MVP for observation-driven world-model construction, task execution, recovery handling, and evidence packaging. The current build is intended as a reproducible local submission bundle, not an official hidden-evaluation score.

Validated final sample evidence in this build covers:

- LocalSim Track 1 closed-loop task execution.
- Visual evidence demo over compact synthetic image fixtures.
- Maze topology stress evidence.
- Maze anti-loop and dead-end recovery evidence.
- Docker/source-package smoke and reproducibility checks.

VirtualHome final evidence is not included in this build. VirtualHome mock replay and partial live diagnostics, when present, are copied only under `submission_bundle/optional_diagnostics/` and are not counted as final Track 1 evidence.

## System Overview

The system follows a flat `src/` layout. Runtime code is separated into environment adapters, perception, planning, execution, world-model updates, scoring, validators, and harness entrypoints.

Core runtime flow:

1. Receive task and initial observation from an environment adapter.
2. Extract or normalize observation evidence.
3. Update the world model with objects, states, relations, topology, uncertainty, and recovery evidence.
4. Select and translate actions through bounded planner/executor logic.
5. Record episode logs, task status, run audit, score, and validation artifacts.

The source package includes the official-runtime adapter boundary, but official hidden evaluation results are not included because the official runtime/API is not available in this local build.

## World Model

The world model is stored as JSON artifacts for evaluation and review. It includes:

- `objects`: entity identifiers, names, categories, and structured locations.
- `relations`: active/stale/inferred relation records with confidence and evidence steps.
- `states`: entity attribute-value facts.
- `topology`: discovered rooms/frontiers/connectivity evidence where available.
- `exceptions`: controlled failures and recovery plans.
- `uncertainty`: unresolved or lower-confidence observations.

Indexes such as `WorldModelIndex` are runtime-only helpers. They are not persisted into `world_model.json` and do not change the artifact schema.

## Evidence Levels

The bundle distinguishes final sample outputs from optional diagnostics:

- `sample_outputs/`: local final evidence included in this build.
- `optional_diagnostics/`: non-final diagnostics for debugging and reproducibility notes.
- `source/`: source zip for reproducibility.
- `docker/`: Docker rebuild instructions and examples.

VirtualHome scene graph/reference data, when used in diagnostics, is treated as a local answer key for validation/debug only. It is not used to generate predicted world models, and these diagnostics are not official hidden-evaluation scores.

## LocalSim Evidence

The LocalSim sample demonstrates the Track 1 closed-loop procedure:

- task reception,
- partial observation,
- world-model construction,
- action selection/execution,
- recovery handling,
- final task-status evaluation,
- run audit and scoring.

The final sample output is copied to:

`submission_bundle/sample_outputs/local_sim_track1_demo/`

## Visual Evidence Demo

The visual evidence demo uses compact synthetic image fixtures for reproducible local validation. It is intended to show the visual artifact path and task-result schema without relying on online APIs or large redistributed image/video assets.

The final sample output is copied to:

`submission_bundle/sample_outputs/visual_evidence_demo/`

If `qwen_response_summary.json` is absent, the manifest records it as optional rather than silently claiming it exists.

## Maze Stress Evidence

The maze stress outputs validate topology construction and comparison against local reference mazes. These are synthetic local evidence cases, not hidden-evaluation results.

The blocked shortcut scenario prioritizes safe recovery over exhaustive map completion; the agent avoids spurious edges while maintaining high topology recall.

The final sample output is copied to:

`submission_bundle/sample_outputs/maze_stress/`

## Maze Anti-Loop Evidence

Maze anti-loop evidence includes loop lure, dead-end comb, blocked shortcut, and unreachable goal cases.

The `dead_end_comb_maze` intentionally causes repeated dead-end discovery and backtracking. The agent path is longer than the shortest path, but oscillation remains zero and the goal is reached.

The `unreachable_goal_maze` is an expected no-goal case. Its status artifacts record that the goal is not reachable, the goal is not reached, and the expected outcome is met.

The final sample output is copied to:

`submission_bundle/sample_outputs/maze_anti_loop/`

## VirtualHome Diagnostics

VirtualHome final evidence is not included in this build.

Optional diagnostics may include:

- `submission_bundle/optional_diagnostics/virtualhome_mock_replay/`
- `submission_bundle/optional_diagnostics/virtualhome_partial_live/`

These diagnostics are explicitly non-final. Mock replay uses compact replay fixtures and mock extraction for CI/smoke validation. Partial live diagnostics may record runtime connection or grounding failures. Neither should be interpreted as official score or final Track 1 evidence.

Full VirtualHome/Unity runtime assets are not redistributed unless explicitly included. The submitted source zip does not bundle the full VirtualHome runtime or large raw video frame dumps.

## Docker And Reproducibility

Docker image tar files are not included in the bundle. Reviewers can rebuild from the root `Dockerfile`; the bundle also includes:

- `docker/Dockerfile`
- `docker/README_DOCKER.md`
- `docker/docker_run_examples.md`
- `docker/README_IMAGE_TAR.md`

The source package is checked by `tools/check_source_package_repro.py` to confirm it can compile and run the fast smoke tier from the packaged source zip.

## Submission Bundle Structure

The generated bundle is organized as:

```text
submission_bundle/
├── sample_outputs/
├── optional_diagnostics/
├── reports/
├── disclosures/
├── checksums/
├── source/
└── docker/
```

`outputs/`, `dist/`, and `submission_bundle/` remain local build artifacts and are ignored by git.

## Limitations

- No official hidden-evaluation score is included.
- Real VirtualHome closed-loop final evidence is not included in this build.
- ProcTHOR, Habitat, and AI2-THOR remain adapter or smoke-test paths rather than official validated evaluation environments.
- Visual fixtures are compact and synthetic; they are designed for reproducibility rather than dataset-scale visual diversity.
- The current `run_demo` entrypoint remains large and is a known technical-debt target for a future behavior-preserving split.

## Verification

The current pre-submission validation workflow is:

```bash
python -m compileall src tests tools
python -m pytest -q
python tools/package_source.py
python tools/check_source_package_repro.py --zip-path dist/source.zip
python tools/create_submission_bundle.py
python tools/run_test_suite.py --tier docker-smoke --timeout-seconds 300
```

These checks validate source packaging, sample artifact generation, semantic consistency, Docker smoke behavior, and bundle creation.
