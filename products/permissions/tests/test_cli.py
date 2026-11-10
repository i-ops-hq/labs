import json
import os
import stat
import subprocess
import sys

import pytest

from .conftest import EXAMPLES


def command(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "iops_permissions", *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def evaluate_args(name):
    return [
        "--policy",
        EXAMPLES / "policy.json",
        "--action",
        EXAMPLES / ("action-" + name + ".json"),
        "--manifest",
        EXAMPLES / "operations-manifest.json",
    ]


@pytest.mark.parametrize(
    ("name", "exit_code", "decision"),
    [
        ("allowed", 0, "allowed"),
        ("denied", 3, "denied"),
        ("approval", 4, "requires_approval"),
        ("unknown", 5, "unknown"),
    ],
)
def test_real_cli_decision_exit_codes(tmp_path, name, exit_code, decision):
    result = command("evaluate", *evaluate_args(name), cwd=tmp_path)
    assert result.returncode == exit_code, result.stderr
    report = json.loads(result.stdout)
    assert report["decision"] == decision
    assert report["explanations"]
    assert result.stderr == ""


def test_cli_inspect_and_human_output(tmp_path):
    result = command("inspect", EXAMPLES / "operations-manifest.json", cwd=tmp_path)
    assert result.returncode == 0
    assert len(json.loads(result.stdout)["findings"]) == 2
    text = command("evaluate", *evaluate_args("denied"), "--format", "text", cwd=tmp_path)
    assert text.returncode == 3
    assert "Decision: denied" in text.stdout
    assert "no action was executed" in text.stdout


def test_cli_export_is_private_valid_and_refuses_overwrite(tmp_path):
    output = tmp_path / "scenario.json"
    args = [
        "export",
        *evaluate_args("denied"),
        "--fixture",
        EXAMPLES / "protected-file-fixture.json",
        "--output",
        output,
    ]
    first = command(*args, cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["execution_status"] == "not_executed"
    assert json.loads(output.read_text())["mode"] == "isolated_execution"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    second = command(*args, cwd=tmp_path)
    assert second.returncode == 2
    assert output.read_bytes() == before
    assert list(tmp_path.glob(".iops-permissions-*")) == []


def test_cli_refuses_existing_output_symlink(tmp_path):
    target = tmp_path / "protected.json"
    target.write_text("SYNTHETIC_DO_NOT_CHANGE")
    output = tmp_path / "scenario.json"
    output.symlink_to(target)
    result = command("export", *evaluate_args("denied"), "--output", output, cwd=tmp_path)
    assert result.returncode == 2
    assert target.read_text() == "SYNTHETIC_DO_NOT_CHANGE"
    assert output.is_symlink()


def test_unsupported_export_writes_nothing(tmp_path):
    output = tmp_path / "scenario.json"
    result = command(
        "export",
        *evaluate_args("allowed"),
        "--fixture",
        EXAMPLES / "protected-file-fixture.json",
        "--output",
        output,
        cwd=tmp_path,
    )
    assert result.returncode == 6
    assert json.loads(result.stdout)["status"] == "unsupported"
    assert not output.exists()


@pytest.mark.parametrize(
    "args",
    [["evaluate", "--format", "SYNTHETIC_PRIVATE"], ["inspect", "SYNTHETIC_PRIVATE_MISSING_FILE"]],
)
def test_errors_do_not_echo_argument_or_file_values(tmp_path, args):
    result = command(*args, cwd=tmp_path)
    assert result.returncode == 2
    assert "SYNTHETIC_PRIVATE" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX input boundary test")
def test_fifo_input_is_rejected_without_blocking(tmp_path):
    fifo = tmp_path / "input.json"
    os.mkfifo(fifo)
    result = command("inspect", fifo, cwd=tmp_path)
    assert result.returncode == 2


def test_malformed_policy_is_never_reported_as_a_decision(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text('{"SYNTHETIC_PRIVATE_FIELD":"SYNTHETIC_PRIVATE_VALUE"}')
    result = command(
        "evaluate", "--policy", policy, "--action", EXAMPLES / "action-allowed.json", cwd=tmp_path
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "SYNTHETIC_PRIVATE" not in result.stderr


def test_version_and_help(tmp_path):
    assert command("--version", cwd=tmp_path).returncode == 0
    result = command("--help", cwd=tmp_path)
    assert result.returncode == 0
    assert "inspect" in result.stdout


def test_text_output_escapes_control_characters_in_logical_ids(tmp_path):
    policy = json.loads((EXAMPLES / "policy.json").read_text())
    policy["rules"][0]["rule_id"] = "workspace\n"
    file = tmp_path / "policy.json"
    file.write_text(json.dumps(policy))
    result = command(
        "evaluate",
        "--policy",
        file,
        "--action",
        EXAMPLES / "action-allowed.json",
        "--format",
        "text",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert 'Matched rules: ["workspace\\n"]' in result.stdout
