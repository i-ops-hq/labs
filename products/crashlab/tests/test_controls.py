import copy
import os
import sys

import pytest
from iops_crashlab.docker import Docker, RunnerError, RunnerUnsupported, command
from iops_crashlab.reference.verifier import bounded_read
from iops_crashlab.runner import (
    assertions,
    create_arguments,
    ready_projection,
    state_projection,
    verify_guest,
)


def test_fixed_container_arguments_have_no_host_mount_or_scenario_command(protected):
    args = create_arguments(
        "test-name", "run-id", "sha256:" + "a" * 64, protected["safety"]["limits"]
    )
    assert "--network=none" in args and "--read-only" in args and "--cap-drop=ALL" in args
    assert "--user=65532:65532" in args
    assert not any(value in args for value in ("--privileged", "--volume", "--mount", "--env-file"))
    assert args[-1] == "sha256:" + "a" * 64


@pytest.mark.parametrize(
    "variable", ["DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"]
)
def test_endpoint_overrides_are_rejected_before_contact(monkeypatch, variable):
    monkeypatch.setenv(variable, "SYNTHETIC_PRIVATE_REMOTE")
    with pytest.raises(RunnerUnsupported, match="override_not_supported") as caught:
        Docker()
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)


def test_control_command_timeout_and_capture_bounds():
    # Trusted host test of the subprocess utility, not execution of an agent.
    with pytest.raises(RunnerError, match="timeout"):
        command([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    with pytest.raises(RunnerError, match="output_limit"):
        command([sys.executable, "-c", "print('x' * 4096)"], limit=128)
    assert command([sys.executable, "-c", "print('bounded')"]).output.strip() == b"bounded"


def test_safe_verifier_read_refuses_symlinks_and_oversized_files(tmp_path):
    target = tmp_path / "state"
    target.write_bytes(b"synthetic")
    assert bounded_read(target, 16) == b"synthetic"
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(OSError):
        bounded_read(link, 16)
    with pytest.raises(ValueError):
        bounded_read(target, 2)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX verifier boundary")
def test_safe_verifier_fifo_read_is_nonblocking(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        bounded_read(fifo, 16)


def test_measured_controls_include_real_cgroup_limits(valid_state, protected):
    state = state_projection(valid_state)
    verify_guest(state, protected["safety"]["limits"])
    state["cgroup_memory_max"] = "max"
    with pytest.raises(RunnerError):
        state_projection(state)
    state = copy.deepcopy(valid_state)
    state["cgroup_memory_max"] = "99999999"
    with pytest.raises(RunnerError, match="cgroup"):
        verify_guest(state, protected["safety"]["limits"])


@pytest.mark.parametrize(
    "field",
    [
        "uid",
        "root_write_denied",
        "network_probe_denied",
        "host_secret_inherited",
        "package_installer_present",
        "non_loopback_interfaces_up",
    ],
)
def test_controls_fail_closed(valid_state, protected, field):
    valid_state[field] = {
        "uid": 0,
        "root_write_denied": False,
        "network_probe_denied": False,
        "host_secret_inherited": True,
        "package_installer_present": True,
        "non_loopback_interfaces_up": 1,
    }[field]
    with pytest.raises(RunnerError, match="controls_mismatch"):
        verify_guest(valid_state, protected["safety"]["limits"])


def test_guest_metadata_cannot_smuggle_free_text(valid_state):
    valid_state["SYNTHETIC_PRIVATE_FIELD"] = "SYNTHETIC_PRIVATE_VALUE"
    with pytest.raises(RunnerError) as caught:
        state_projection(valid_state)
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
    with pytest.raises(RunnerError):
        ready_projection({"channel": "ready", "exit_code": "SYNTHETIC_PRIVATE"}, False)


def test_missing_attempt_cannot_pass_state_assertion(protected, valid_state, baselines):
    agent = {
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "rejected_events": False,
    }
    checked = assertions(protected, valid_state, {"agent": agent}, [], baselines)
    assert checked[0]["outcome"] == "inconclusive"
    assert checked[1]["outcome"] == "failed"
