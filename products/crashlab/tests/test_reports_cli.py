import json
import os
import stat
import subprocess
import sys

import pytest
from iops_crashlab.cli import verify_artifacts
from iops_crashlab.docker import RunnerError, RunnerUnsupported
from iops_crashlab.runner import run_scenario

from .conftest import assert_artifacts


def command(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "iops_crashlab", *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_skip_is_explicit_nonexecution_and_private(protected, tmp_path, monkeypatch):
    monkeypatch.setattr("iops_crashlab.runner.Docker", lambda: pytest.fail("Skip touched Docker"))
    output = tmp_path / "skipped"
    result = run_scenario(protected, output, skip=True)
    assert result["verdict"] == "skipped" and result["assertions"] == []
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for file in output.iterdir():
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
    _, execution = assert_artifacts(result, output)
    assert execution["container_created"] is False
    assert not any("state read" in text for text in result["observation_scope"]["visible"])


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (RunnerUnsupported("docker_missing"), "unsupported"),
        (RunnerError("synthetic_harness_failure"), "error"),
        (ValueError("SYNTHETIC_PRIVATE_INTERNAL"), "error"),
    ],
)
def test_harness_and_unavailable_features_never_become_agent_pass_or_failure(
    protected, tmp_path, monkeypatch, exception, expected
):
    def unavailable():
        raise exception

    monkeypatch.setattr("iops_crashlab.runner.Docker", unavailable)
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == expected and result["assertions"] == []
    assert "SYNTHETIC_PRIVATE" not in json.dumps(result)


def test_unsupported_fixture_is_detected_without_contacting_docker(
    protected, tmp_path, monkeypatch
):
    protected["environment"]["fixture_id"] = "fixture://unknown"
    monkeypatch.setattr("iops_crashlab.runner.Docker", lambda: pytest.fail("Contacted Docker"))
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "unsupported"


def test_integrity_verification_detects_changes_and_never_follows_locator_paths(
    protected, tmp_path
):
    output = tmp_path / "result"
    result = run_scenario(protected, output, skip=True)
    assert verify_artifacts(result, output)
    (output / "state.json").write_text("SYNTHETIC_TAMPERED")
    assert not verify_artifacts(result, output)
    result["artifacts"][0]["locator"] = "artifact://../SYNTHETIC_PRIVATE"
    assert not verify_artifacts(result, output)


def test_no_overwrite_of_report_directory(protected, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "marker"
    marker.write_text("synthetic")
    with pytest.raises(FileExistsError):
        run_scenario(protected, output, skip=True)
    assert marker.read_text() == "synthetic"


def test_cli_builtins_validation_skip_and_integrity_report(tmp_path):
    assert command("examples", cwd=tmp_path).returncode == 0
    assert command("validate", "builtin:protected-file-write", cwd=tmp_path).returncode == 0
    output = tmp_path / "skipped"
    skipped = command(
        "test", "builtin:protected-file-write", "--skip", "--output", output, cwd=tmp_path
    )
    assert skipped.returncode == 5
    assert json.loads(skipped.stdout)["verdict"] == "skipped"
    report = command(
        "report", output / "result.json", "--verify-artifacts", "--format", "json", cwd=tmp_path
    )
    assert report.returncode == 0
    assert json.loads(report.stdout)["artifact_integrity"] == "verified"


def test_cli_reference_provenance_is_not_buried(tmp_path, protected):
    result = run_scenario(protected, tmp_path / "reference", skip=True)
    result["provenance"] = "reference"
    file = tmp_path / "reference.json"
    file.write_text(json.dumps(result))
    reported = command("report", file, cwd=tmp_path)
    assert reported.returncode == 0
    assert "NOT EXECUTED EVIDENCE" in reported.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["validate", "SYNTHETIC_PRIVATE_MISSING"],
        ["test", "builtin:../../SYNTHETIC_PRIVATE", "--output", "unused"],
        ["test", "--reference-variant", "SYNTHETIC_PRIVATE"],
    ],
)
def test_cli_errors_are_redacted(tmp_path, args):
    result = command(*args, cwd=tmp_path)
    assert result.returncode == 2
    assert "SYNTHETIC_PRIVATE" not in result.stderr + result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX CLI input boundary")
def test_cli_rejects_fifo_without_waiting(tmp_path):
    fifo = tmp_path / "input.json"
    os.mkfifo(fifo)
    assert command("validate", fifo, cwd=tmp_path).returncode == 2
