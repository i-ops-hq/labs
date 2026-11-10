"""Trusted control-client subprocess fixtures, not host agent execution."""

import json
import os
import sys
from types import SimpleNamespace

import pytest
from iops_crashlab.docker import RunnerError
from iops_crashlab.runner import _collect

READY = {
    "channel": "ready",
    "exit_code": 0,
    "timed_out": False,
    "output_limited": False,
    "invalid_output": False,
    "captured_bytes": 0,
}
# The guest supervisor announces the written fixture and waits; the host measures its
# baseline and answers with a start line. Every client below has to do that first.
PREPARED = (
    "import sys,json;sys.stdin.readline();"
    'print(json.dumps({"channel":"prepared"}),flush=True);'
    'assert sys.stdin.readline().strip() == \'{"channel":"start"}\';'
)


def control_client(code):
    return SimpleNamespace(prefix=[sys.executable, "-c", code], env=dict(os.environ))


def config():
    return {"run_id": "run-test", "timeout": 1, "action": {}}


def collect(code, capture=dict):
    return _collect(control_client(code), "unused", config(), capture)


def test_control_stderr_cannot_become_a_guest_protocol_packet():
    code = (
        PREPARED + "import time;"
        "sys.stderr.write('SYNTHETIC_PRIVATE_CLIENT_DIAGNOSTIC\\n');sys.stderr.flush();"
        "time.sleep(0.05);print(" + repr(json.dumps(READY)) + ",flush=True)"
    )
    events, status, baselines = collect(code)
    assert events == [] and status["exit_code"] == 0
    assert status["client_diagnostics_observed"]
    assert "SYNTHETIC_PRIVATE" not in repr(status)


def test_control_stderr_alone_never_counts_as_execution_ready():
    code = PREPARED + "sys.stderr.write('SYNTHETIC_PRIVATE\\n')"
    with pytest.raises(RunnerError, match="ended_before_verification") as error:
        collect(code)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


def test_invalid_control_stdout_still_fails_closed():
    code = PREPARED + "print('SYNTHETIC_PRIVATE',flush=True)"
    with pytest.raises(RunnerError, match="protocol_error") as error:
        collect(code)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


def test_the_host_measures_a_baseline_and_hands_it_back_from_collect():
    code = PREPARED + "print(" + repr(json.dumps(READY)) + ",flush=True)"
    measured = {"repo": {"state": "regular", "sha256": "a" * 64}}
    events, status, baselines = collect(code, lambda: measured)
    assert events == [] and status["exit_code"] == 0
    assert baselines == measured


def test_a_ready_packet_without_a_baseline_is_refused():
    """Counterfactual: drop the `if not prepared` guard on the ready branch and this run
    reports exit_code 0 with an empty baseline, which is how an unchanged assertion over an
    unmeasured file would silently become inconclusive-or-worse instead of a protocol error.
    """
    code = "import sys;sys.stdin.readline();print(" + repr(json.dumps(READY)) + ",flush=True)"
    with pytest.raises(RunnerError, match="guest_supervisor_protocol_error"):
        collect(code)


def test_a_second_baseline_announcement_is_refused():
    code = (
        PREPARED + PREPARED.split(";", 1)[1] + "print(" + repr(json.dumps(READY)) + ",flush=True)"
    )
    with pytest.raises(RunnerError, match="guest_supervisor_protocol_error"):
        collect(code)


def test_a_baseline_announcement_after_telemetry_is_refused():
    event = {"channel": "agent_event", "data": {"not": "validated here"}}
    code = (
        "import sys,json;sys.stdin.readline();"
        "print(" + repr(json.dumps(event)) + ",flush=True);"
        'print(json.dumps({"channel":"prepared"}),flush=True)'
    )
    with pytest.raises(RunnerError, match="guest_supervisor_protocol_error"):
        collect(code)


def test_extra_keys_on_the_baseline_announcement_are_refused():
    noisy = {"channel": "prepared", "baseline": {"repo": "SYNTHETIC_PRIVATE"}}
    code = "import sys;sys.stdin.readline();print(" + repr(json.dumps(noisy)) + ",flush=True)"
    with pytest.raises(RunnerError, match="guest_supervisor_protocol_error") as error:
        collect(code)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)
