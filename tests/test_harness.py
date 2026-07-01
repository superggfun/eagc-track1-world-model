from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from test_virtualhome_final_evidence import _write_virtualhome_artifacts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def valid_track1_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("harness_track1") / "local_sim_track1_demo"
    completed = _run(
        [
            sys.executable,
            "-m",
            "harness.run_track1",
            "--env",
            "local_sim",
            "--episode-id",
            "local-explore-book-relocated",
            "--output-dir",
            str(output_dir),
            "--validate",
            "--mock",
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return output_dir


def test_validate_outputs_accepts_valid_sample(valid_track1_output: Path) -> None:
    completed = _run(
        [
            sys.executable,
            "-m",
            "harness.validate_outputs",
            "--output-dir",
            str(valid_track1_output),
            "--mode",
            "track1",
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["passed"] is True
    assert summary["errors"] == []


def test_run_track1_smoke_generates_required_artifacts(valid_track1_output: Path) -> None:
    for name in ["world_model.json", "episode_log.jsonl", "run_audit.json", "harness_result.json", "track1_score.json"]:
        assert (valid_track1_output / name).exists()
    audit = json.loads((valid_track1_output / "run_audit.json").read_text(encoding="utf-8"))
    assert audit["success"] is True
    assert audit["output_dir"] == "."
    assert audit["world_model_path"] == "world_model.json"
    assert audit["episode_log_path"] == "episode_log.jsonl"
    assert audit["track1_score_path"] == "track1_score.json"
    result = json.loads((valid_track1_output / "harness_result.json").read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["output_dir"] == "."
    assert result["world_model_path"] == "world_model.json"
    assert result["episode_log_path"] == "episode_log.jsonl"
    assert result["run_audit_path"] == "run_audit.json"
    assert result["track1_score_path"] == "track1_score.json"


def test_validate_outputs_rejects_absolute_path(valid_track1_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "absolute_path_case"
    shutil.copytree(valid_track1_output, bad_output)
    audit_path = bad_output / "run_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["world_model_path"] = r"C:\tmp\secret\world_model.json"
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    completed = _run(
        [
            sys.executable,
            "-m",
            "harness.validate_outputs",
            "--output-dir",
            str(bad_output),
            "--mode",
            "track1",
        ]
    )
    assert completed.returncode != 0
    assert "local absolute path" in completed.stdout


def test_validate_outputs_rejects_harness_result_absolute_path(valid_track1_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "absolute_harness_result_case"
    shutil.copytree(valid_track1_output, bad_output)
    result_path = bad_output / "harness_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["output_dir"] = "/tmp/eagc_track1_mvp/outputs/demo"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    completed = _run(
        [
            sys.executable,
            "-m",
            "harness.validate_outputs",
            "--output-dir",
            str(bad_output),
            "--mode",
            "track1",
        ]
    )
    assert completed.returncode != 0
    assert "harness_result.json contains local absolute path" in completed.stdout


def test_validate_outputs_rejects_missing_world_model(valid_track1_output: Path, tmp_path: Path) -> None:
    bad_output = tmp_path / "missing_world_model_case"
    shutil.copytree(valid_track1_output, bad_output)
    (bad_output / "world_model.json").unlink()

    completed = _run(
        [
            sys.executable,
            "-m",
            "harness.validate_outputs",
            "--output-dir",
            str(bad_output),
            "--mode",
            "track1",
        ]
    )
    assert completed.returncode != 0
    assert "Missing required artifact: world_model.json" in completed.stdout


def test_create_submission_bundle_collects_outputs_and_checksums(tmp_path: Path) -> None:
    snapshot = _run([sys.executable, "tools/create_demo_snapshot.py"])
    assert snapshot.returncode == 0, snapshot.stdout + snapshot.stderr
    maze_stress = _run(
        [
            sys.executable,
            "tools/run_maze_stress_test.py",
            "--episode",
            "generated_grid_maze",
            "--seed",
            "42",
            "--difficulty",
            "medium",
            "--max-steps",
            "200",
            "--output-dir",
            "outputs/maze_stress",
        ]
    )
    assert maze_stress.returncode == 0, maze_stress.stdout + maze_stress.stderr
    maze_anti_loop = _run(
        [
            sys.executable,
            "tools/run_maze_anti_loop_test.py",
            "--episode",
            "all",
            "--max-steps",
            "300",
            "--output-dir",
            "outputs/maze_anti_loop",
        ]
    )
    assert maze_anti_loop.returncode == 0, maze_anti_loop.stdout + maze_anti_loop.stderr
    virtualhome_mock = _run(
        [
            sys.executable,
            "-m",
            "harness.run_virtualhome_replay",
            "--frames",
            "assets/test_sequences/virtualhome_exploration/frames",
            "--manifest",
            "assets/test_sequences/virtualhome_exploration/frame_manifest.json",
            "--output-dir",
            "outputs/virtualhome_exploration",
            "--prediction-input-mode",
            "mock_visual_extraction",
            "--validate",
        ]
    )
    assert virtualhome_mock.returncode == 0, virtualhome_mock.stdout + virtualhome_mock.stderr

    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("README.txt", "test source package\n")

    bundle_dir = PROJECT_ROOT / "outputs" / "pytest_submission_bundle"
    completed_with_mock = _run(
        [
            sys.executable,
            "tools/create_submission_bundle.py",
            "--output-dir",
            str(bundle_dir),
            "--source-zip",
            str(source_zip),
        ]
    )
    assert completed_with_mock.returncode == 0, completed_with_mock.stdout + completed_with_mock.stderr
    manifest = json.loads((bundle_dir / "sample_outputs" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["virtualhome_final_evidence"]["included"] is False
    assert "No validated continuous closed-loop VirtualHome + VLM evidence" in manifest["virtualhome_final_evidence"]["reason"]
    assert not (bundle_dir / "sample_outputs" / "virtualhome_exploration").exists()
    assert (bundle_dir / "optional_diagnostics" / "virtualhome_mock_replay" / "run_audit.json").exists()
    required_virtualhome = _run(
        [
            sys.executable,
            "tools/create_submission_bundle.py",
            "--output-dir",
            str(bundle_dir),
            "--source-zip",
            str(source_zip),
            "--require-virtualhome-final",
        ]
    )
    assert required_virtualhome.returncode != 0
    assert "No validated continuous closed-loop VirtualHome + VLM evidence" in (
        required_virtualhome.stdout + required_virtualhome.stderr
    )

    shutil.rmtree(PROJECT_ROOT / "outputs" / "virtualhome_exploration", ignore_errors=True)
    _write_virtualhome_artifacts(PROJECT_ROOT / "outputs", case_name="virtualhome_exploration")

    completed = _run(
        [
            sys.executable,
            "tools/create_submission_bundle.py",
            "--output-dir",
            str(bundle_dir),
            "--source-zip",
            str(source_zip),
        ]
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    required = [
        "sample_outputs/local_sim_track1_demo/world_model.json",
        "sample_outputs/local_sim_track1_demo/episode_log.jsonl",
        "sample_outputs/local_sim_track1_demo/run_audit.json",
        "sample_outputs/local_sim_track1_demo/harness_result.json",
        "sample_outputs/local_sim_track1_demo/track1_score.json",
        "sample_outputs/visual_evidence_demo/world_model.json",
        "sample_outputs/visual_evidence_demo/episode_log.jsonl",
        "sample_outputs/visual_evidence_demo/run_audit.json",
        "sample_outputs/visual_evidence_demo/harness_result.json",
        "sample_outputs/visual_evidence_demo/visual_task_result.json",
        "sample_outputs/maze_stress/world_model.json",
        "sample_outputs/maze_stress/episode_log.jsonl",
        "sample_outputs/maze_stress/run_audit.json",
        "sample_outputs/maze_stress/maze_metrics.json",
        "sample_outputs/maze_stress/status.json",
        "sample_outputs/maze_stress/reference_maze.json",
        "sample_outputs/maze_stress/comparison_report.json",
        "sample_outputs/maze_anti_loop/world_model.json",
        "sample_outputs/maze_anti_loop/episode_log.jsonl",
        "sample_outputs/maze_anti_loop/run_audit.json",
        "sample_outputs/maze_anti_loop/maze_metrics.json",
        "sample_outputs/maze_anti_loop/status.json",
        "sample_outputs/maze_anti_loop/reference_maze.json",
        "sample_outputs/maze_anti_loop/comparison_report.json",
        "sample_outputs/maze_anti_loop/anti_loop_report.md",
        "sample_outputs/maze_anti_loop/loop_lure_maze/reference_maze.json",
        "sample_outputs/maze_anti_loop/loop_lure_maze/comparison_report.json",
        "sample_outputs/maze_anti_loop/loop_lure_maze/run_audit.json",
        "sample_outputs/virtualhome_exploration/world_model.json",
        "sample_outputs/virtualhome_exploration/reference_world_model.json",
        "sample_outputs/virtualhome_exploration/comparison_report.json",
        "sample_outputs/virtualhome_exploration/episode_log.jsonl",
        "sample_outputs/virtualhome_exploration/run_audit.json",
        "sample_outputs/virtualhome_exploration/visual_task_result.json",
        "sample_outputs/virtualhome_exploration/frame_manifest.json",
        "sample_outputs/virtualhome_exploration/coverage_report.json",
        "sample_outputs/virtualhome_exploration/dedup_report.json",
        "sample_outputs/virtualhome_exploration/virtualhome_exploration_report.md",
        "sample_outputs/virtualhome_exploration/frames/frame_000.jpg",
        "sample_outputs/virtualhome_exploration/frames/frame_011.jpg",
        "sample_outputs/manifest.json",
        "docker/Dockerfile",
        "docker/README_DOCKER.md",
        "docker/docker_run_examples.md",
        "reports/technical_report_build_status.json",
        "source/source.zip",
    ]
    for rel in required:
        assert (bundle_dir / rel).exists(), rel

    checksums = (bundle_dir / "checksums" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    for rel in required:
        assert f"  {rel}" in checksums
    report = (bundle_dir / "sample_outputs" / "virtualhome_exploration" / "virtualhome_exploration_report.md").read_text(
        encoding="utf-8"
    )
    assert "## Prediction Input Mode" in report
    assert "prediction_input_mode: `vlm_frame_extraction`" in report
    manifest = json.loads((bundle_dir / "sample_outputs" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["virtualhome_final_evidence"]["included"] is True
    assert manifest["sample_outputs"]["virtualhome_exploration"]["prediction_input_mode"] == "vlm_frame_extraction"
    assert manifest["sample_outputs"]["virtualhome_exploration"]["evidence_level"] == "closed_loop_final_evidence"
    shutil.rmtree(PROJECT_ROOT / "outputs" / "virtualhome_exploration", ignore_errors=True)
    shutil.rmtree(PROJECT_ROOT / "outputs" / "virtualhome_continuous", ignore_errors=True)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=_subprocess_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(PROJECT_ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join([src_path, existing]) if existing else src_path
    return env
