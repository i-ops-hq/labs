import copy
import json
import os
from pathlib import Path

import pytest
from iops_crashlab import AgentBundle, load_agent, run_scenario
from iops_crashlab.catalog import negotiate
from iops_crashlab.docker import RunnerError, RunnerUnsupported, image_tag

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def definition(tmp_path, **changes):
    raw = {
        "schema_version": "0.1.0",
        "agent_id": "custom-agent",
        "kind": "python_tools",
        "argv": ["agent.py"],
        "files": ["agent.py"],
    }
    raw.update(changes)
    (tmp_path / "agent.py").write_text("raise RuntimeError('MUST_NOT_RUN_ON_HOST')")
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(raw))
    return path


def test_snapshot_never_imports_code_and_only_reads_explicit_files(tmp_path):
    path = definition(tmp_path)
    (tmp_path / ".env").write_text("SYNTHETIC_PRIVATE")
    bundle = load_agent(path)
    before = bundle.digest()
    (tmp_path / "agent.py").write_text("changed")
    assert bundle.digest() == before
    assert bundle.files[0][0] == "agent.py" and len(bundle.files) == 1
    assert b"SYNTHETIC_PRIVATE" not in bundle.files[0][1]
    assert "MUST_NOT_RUN_ON_HOST" not in json.dumps(bundle.describe())


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "1.0.0"},
        {"extra": "SYNTHETIC_PRIVATE"},
        {"kind": "host"},
        {"agent_id": "id\n"},
        {"agent_id": 7},
        {"argv": []},
        {"argv": ["missing.py"]},
        {"argv": ["agent.py", "arg"]},
        {"files": ["../private"]},
        {"files": ["/private"]},
        {"files": [".env"]},
        {"files": ["a//b"]},
        {"files": ["agent.py", "agent.py"]},
        {"files": ["a", "a/b"]},
        {"argv": ["a\u0000"]},
        {"extensions": []},
        {"kind": "command", "argv": ["/host/executable"]},
    ],
)
def test_invalid_definitions_are_redacted(tmp_path, changes):
    with pytest.raises(RunnerError) as caught:
        load_agent(definition(tmp_path, **changes))
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("style", ["leaf", "parent", "fifo", "large"])
def test_bundle_file_boundaries(tmp_path, style):
    path = definition(tmp_path)
    if style == "leaf":
        (tmp_path / "agent.py").unlink()
        (tmp_path / "agent.py").symlink_to("missing-secret")
    elif style == "parent":
        (tmp_path / "nested").symlink_to(tmp_path, target_is_directory=True)
        raw = json.loads(path.read_text())
        raw.update(files=["nested/agent.py"], argv=["nested/agent.py"])
        path.write_text(json.dumps(raw))
    elif style == "fifo":
        (tmp_path / "agent.py").unlink()
        os.mkfifo(tmp_path / "agent.py")
    else:
        (tmp_path / "agent.py").write_bytes(b"x" * 1_048_577)
    with pytest.raises(RunnerError):
        load_agent(path)


def test_duplicate_keys_and_nonfinite_json_are_rejected(tmp_path):
    path = definition(tmp_path)
    for data in ('{"kind":1,"kind":2}', '{"value":NaN}'):
        path.write_text(data)
        with pytest.raises((RunnerError, ValueError)):
            load_agent(path)


def test_missing_definition_directory_is_redacted(tmp_path):
    with pytest.raises(RunnerError) as caught:
        load_agent(tmp_path / "SYNTHETIC_PRIVATE" / "agent.json")
    assert str(caught.value) == "agent_file_unavailable"


def test_agent_identity_and_features_are_negotiated(protected, tmp_path):
    agent = load_agent(definition(tmp_path))
    with pytest.raises(RunnerUnsupported, match="adapter_target"):
        negotiate(protected, "respect", agent)
    protected["target"] = {"agent_id": agent.agent_id, "adapter_id": agent.adapter_id}
    assert negotiate(protected, "respect", agent) == "protected"
    protected["requirements"]["adapter_features"].append("network_effects")
    with pytest.raises(RunnerUnsupported):
        negotiate(protected, "respect", agent)
    result = run_scenario(protected, tmp_path / "unsupported", agent=agent)
    assert result["verdict"] == "unsupported"
    assert not json.loads((tmp_path / "unsupported/execution.json").read_text())[
        "container_created"
    ]


def test_reference_variant_is_not_a_custom_agent_override(protected, tmp_path):
    agent = load_agent(definition(tmp_path))
    with pytest.raises(RunnerUnsupported, match="reference_variant_with_custom"):
        negotiate(protected, "violate", agent)


def test_command_has_no_pre_action_interception(protected, tmp_path):
    agent = load_agent(
        definition(tmp_path, kind="command", argv=["/bin/sh", "/opt/agent/agent.py"])
    )
    assert agent.describe()["observability"] == "process_boundary"
    assert "pre_action_intercept" not in agent.describe()["features"]
    protected["target"] = {"agent_id": agent.agent_id, "adapter_id": agent.adapter_id}
    with pytest.raises(RunnerUnsupported, match="requirements"):
        negotiate(protected, "respect", agent)


def test_digest_binds_identity_argv_and_bytes(tmp_path):
    agent = load_agent(definition(tmp_path))
    other = AgentBundle("other-agent", agent.kind, agent.argv, agent.files)
    assert other.digest() != agent.digest()
    assert image_tag(other) != image_tag(agent)
    raw = json.loads((tmp_path / "agent.json").read_text())
    raw["extensions"] = {"command": "SYNTHETIC_NEVER_EXECUTE"}
    (tmp_path / "agent.json").write_text(json.dumps(raw))
    assert load_agent(tmp_path / "agent.json").digest() == agent.digest()


def test_examples_negotiate_without_runtime():
    from iops_crashlab.cli import load_scenario

    for name in ("agent", "bypass", "retry", "duplicate"):
        agent = load_agent(EXAMPLES / "python-agent" / (name + ".json"))
        scenario = load_scenario(
            str(
                EXAMPLES
                / "python-agent"
                / (
                    "api-scenario.json"
                    if name in {"retry", "duplicate"}
                    else "protected-scenario.json"
                )
            )
        )
        assert negotiate(scenario, "respect", agent) in {"protected", "fake_api"}
    agent = load_agent(EXAMPLES / "command-agent/agent.json")
    scenario = load_scenario(str(EXAMPLES / "command-agent/scenario.json"))
    assert negotiate(scenario, "respect", agent) == "command"
    scenario = copy.deepcopy(scenario)
    scenario["fault"] = {"kind": "api_failure", "after_matches": 1, "response_code": 503}
    with pytest.raises(RunnerUnsupported, match="configuration"):
        negotiate(scenario, "respect", agent)


def test_measured_file_violation_does_not_require_a_reported_attempt(
    protected, valid_state, baselines
):
    from iops_crashlab.runner import assertions

    protected["assertions"] = protected["assertions"][:1]
    ready = {
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "rejected_events": False,
    }
    valid_state["protected_sha256"] = "0" * 64
    checked = assertions(protected, valid_state, {"agent": ready}, [], baselines)
    assert checked[0]["outcome"] == "failed"
