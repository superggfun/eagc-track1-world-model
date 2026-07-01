from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from validators.validate_maze_outputs import validate_detailed


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def maze_output(tmp_path: Path) -> Path:
    output_dir = tmp_path / "maze_stress"
    completed = _run(
        [
            sys.executable,
            "tools/run_maze_stress_test.py",
            "--episode",
            "simple_t_maze",
            "--difficulty",
            "easy",
            "--max-steps",
            "80",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return output_dir


def test_maze_reference_and_comparison_are_generated(maze_output: Path) -> None:
    reference = json.loads((maze_output / "reference_maze.json").read_text(encoding="utf-8"))
    comparison = json.loads((maze_output / "comparison_report.json").read_text(encoding="utf-8"))
    audit = json.loads((maze_output / "run_audit.json").read_text(encoding="utf-8"))

    assert reference["source"] == "maze_sim_reference_spec"
    assert reference["used_for_generation"] is False
    assert reference["used_for_validation"] is True
    assert comparison["reference_used_for_generation"] is False
    assert audit["world_model_source"] == "agent_exploration"
    assert audit["reference_used_for_generation"] is False
    assert validate_detailed(maze_output)["errors"] == []


def test_maze_validator_fails_if_reference_used_for_generation_is_true(maze_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "bad_reference_generation"
    shutil.copytree(maze_output, bad_output)
    audit_path = bad_output / "run_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["reference_used_for_generation"] = True
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    summary = validate_detailed(bad_output)

    assert any("reference_used_for_generation" in error for error in summary["errors"])


def test_maze_validator_fails_if_verified_edge_uses_reference_spec(maze_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "bad_reference_edge"
    shutil.copytree(maze_output, bad_output)
    world_model_path = bad_output / "world_model.json"
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    world_model["topology_edges"][0]["evidence_source"] = "reference_spec"
    world_model_path.write_text(json.dumps(world_model, indent=2), encoding="utf-8")

    summary = validate_detailed(bad_output)

    assert any("reference_spec" in error for error in summary["errors"])


def test_maze_validator_fails_if_reference_topology_has_no_step_evidence(maze_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "bad_copied_topology"
    shutil.copytree(maze_output, bad_output)
    reference = json.loads((bad_output / "reference_maze.json").read_text(encoding="utf-8"))
    world_model_path = bad_output / "world_model.json"
    world_model = json.loads(world_model_path.read_text(encoding="utf-8"))
    world_model["topology_edges"] = [
        {"from": edge[0], "to": edge[1], "relation": "connected_to", "status": "verified"}
        for edge in reference["edges"]
    ]
    world_model_path.write_text(json.dumps(world_model, indent=2), encoding="utf-8")

    summary = validate_detailed(bad_output)

    assert any("lacks per-edge step evidence" in error for error in summary["errors"])
    assert any("requires step/action/evidence_source" in error for error in summary["errors"])


def test_maze_anti_loop_recursive_outputs_include_reference_and_comparison(tmp_path: Path) -> None:
    output_dir = tmp_path / "maze_anti_loop"
    completed = _run(
        [
            sys.executable,
            "tools/run_maze_anti_loop_test.py",
            "--max-steps",
            "120",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    for directory in [output_dir, output_dir / "loop_lure_maze", output_dir / "unreachable_goal_maze"]:
        assert (directory / "reference_maze.json").exists()
        assert (directory / "comparison_report.json").exists()
        assert (directory / "run_audit.json").exists()
    unreachable_status = json.loads((output_dir / "unreachable_goal_maze" / "status.json").read_text(encoding="utf-8"))
    unreachable_audit = json.loads((output_dir / "unreachable_goal_maze" / "run_audit.json").read_text(encoding="utf-8"))
    for payload in [unreachable_status, unreachable_audit]:
        assert payload["expected_goal_reachable"] is False
        assert payload["goal_reached"] is False
        assert payload["expected_outcome_met"] is True
    summary = validate_detailed(output_dir, recursive=True)
    assert summary["errors"] == []


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
