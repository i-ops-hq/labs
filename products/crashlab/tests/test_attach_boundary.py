"""Trusted control-client subprocess fixtures, not host agent execution."""

import json
import os
import sys
from types import SimpleNamespace

import pytest
from iops_crashlab.docker import RunnerError
from iops_crashlab.runner import _collect


def control_client(code):
    return SimpleNamespace(prefix=[sys.executable, "-c", code], env=dict(os.environ))


def config():
    return {"run_id": "run-test", "timeout": 1, "action": {}}


def test_control_stderr_cannot_become_a_guest_protocol_packet():
    ready = {
        "channel": "ready",
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "captured_bytes": 0,
    }
    code = (
        "import sys,time;sys.stdin.readline();"
        "sys.stderr.write('SYNTHETIC_PRIVATE_CLIENT_DIAGNOSTIC\\n');sys.stderr.flush();"
        "time.sleep(0.05);print(" + repr(json.dumps(ready)) + ",flush=True)"
    )
    events, status = _collect(control_client(code), "unused", config())
    assert events == [] and status["exit_code"] == 0
    assert status["client_diagnostics_observed"]
    assert "SYNTHETIC_PRIVATE" not in repr(status)


def test_control_stderr_alone_never_counts_as_execution_ready():
    code = "import sys;sys.stdin.readline();sys.stderr.write('SYNTHETIC_PRIVATE\\n')"
    with pytest.raises(RunnerError, match="ended_before_verification") as error:
        _collect(control_client(code), "unused", config())
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


def test_invalid_control_stdout_still_fails_closed():
    code = "import sys;sys.stdin.readline();print('SYNTHETIC_PRIVATE',flush=True)"
    with pytest.raises(RunnerError, match="protocol_error") as error:
        _collect(control_client(code), "unused", config())
    assert "SYNTHETIC_PRIVATE" not in str(error.value)
