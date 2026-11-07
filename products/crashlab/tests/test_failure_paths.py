"""Simulated harness failures only; real behavior is covered by --docker tests."""

import json

import pytest
from iops_crashlab.docker import CommandResult, RunnerError
from iops_crashlab.runner import run_scenario


class FakeDocker:
    version = "synthetic-not-an-integration"

    def __init__(self, state):
        self.state = state
        self.exists = False
        self.remove_failed = self.query_failed = self.create_timed_out = False
        self.unowned = False
        self.removed = False
        self.run_id = ""

    def image(self):
        return "sha256:" + "a" * 64

    def call(self, args, **kwargs):
        if args[0] == "create":
            self.exists = True
            self.run_id = args[args.index("--label") + 1].split("=", 1)[1]
            if self.create_timed_out:
                raise RunnerError("docker_command_timeout")
        elif args[:2] == ["container", "rm"]:
            assert not self.unowned, "Attempted removal of unowned container"
            if self.remove_failed:
                raise RunnerError("docker_command_failed")
            self.exists = False
            self.removed = True
        elif args[:2] == ["container", "ls"]:
            if self.query_failed:
                raise RunnerError("docker_command_failed")
            return CommandResult(0, b"owned-id" if self.exists and not self.unowned else b"")
        elif args[0] == "exec":
            return CommandResult(0, json.dumps(self.state).encode())
        return CommandResult(0, b"")

    def json(self, args):
        if not self.exists:
            raise RunnerError("docker_command_failed")
        return [
            {
                "Id": "b" * 64,
                "HostConfig": {},
                "Config": {
                    "Labels": {
                        "org.iops.crashlab.run": "someone-else" if self.unowned else self.run_id
                    }
                },
            }
        ]


@pytest.fixture
def fake_runner(monkeypatch, valid_state):
    engine = FakeDocker(valid_state)
    monkeypatch.setattr("iops_crashlab.runner.Docker", lambda: engine)
    monkeypatch.setattr("iops_crashlab.runner.inspect_controls", lambda *args: {"synthetic": True})
    ready = {
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "rejected_events": False,
    }
    monkeypatch.setattr("iops_crashlab.runner._collect", lambda *args: ([], ready))
    return engine


@pytest.mark.parametrize("failure", ["remove_failed", "query_failed"])
def test_unconfirmed_cleanup_is_harness_error_not_agent_failure(
    fake_runner, protected, tmp_path, failure
):
    setattr(fake_runner, failure, True)
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "error"
    assert result["summary"] == "cleanup_not_confirmed"
    assert result["assertions"] == []
    execution = json.loads((tmp_path / "result/execution.json").read_text())
    assert execution["cleanup"] == "failed"


def test_ambiguous_create_timeout_still_removes_owned_container(fake_runner, protected, tmp_path):
    fake_runner.create_timed_out = True
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "error"
    assert fake_runner.removed and not fake_runner.exists
    assert json.loads((tmp_path / "result/execution.json").read_text())["cleanup"] == "confirmed"


def test_unowned_container_is_never_removed(fake_runner, protected, tmp_path, monkeypatch):
    # Force the run to stop at the control check, then exercise real ownership cleanup.
    import importlib

    module = importlib.import_module("iops_crashlab.runner")
    fake_runner.unowned = True

    def reject_controls(*args):
        raise RunnerError("container_controls_mismatch")

    monkeypatch.setattr(module, "inspect_controls", reject_controls)
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "error"
    assert not fake_runner.removed and fake_runner.exists


def test_keyboard_interrupt_cleans_up(fake_runner, protected, tmp_path, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr("iops_crashlab.runner._collect", interrupt)
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "error" and result["summary"] == "interrupted"
    assert fake_runner.removed


def test_untrusted_verifier_fields_are_never_persisted(fake_runner, protected, tmp_path):
    fake_runner.state = {"SYNTHETIC_PRIVATE_FIELD": "SYNTHETIC_PRIVATE_VALUE"}
    result = run_scenario(protected, tmp_path / "result")
    assert result["verdict"] == "error"
    public = "".join(file.read_text() for file in (tmp_path / "result").iterdir())
    assert "SYNTHETIC_PRIVATE" not in public


def test_budget_pass_without_selected_action_is_inconclusive(fake_runner, budget, tmp_path):
    result = run_scenario(budget, tmp_path / "result")
    assert result["assertions"][0]["outcome"] == "passed"
    assert result["verdict"] == "inconclusive"
