import json
from pathlib import Path

import pytest
from iops_crashlab import AgentBundle, load_agent, prepare_agent_image, run_scenario
from iops_crashlab.cli import load_scenario, verify_artifacts

from ..conftest import assert_artifacts

pytestmark = pytest.mark.integration
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.mark.parametrize(
    ("name", "fixture", "verdict"),
    [
        ("agent", "protected", "passed"),
        ("bypass", "protected", "failed"),
        ("retry", "api", "passed"),
        ("duplicate", "api", "failed"),
    ],
)
def test_real_custom_python_agents(name, fixture, verdict, tmp_path, monkeypatch):
    monkeypatch.setenv("CRASHLAB_HOST_SENTINEL", "SYNTHETIC_PRIVATE_NOT_FOR_GUEST")
    agent = load_agent(EXAMPLES / "python-agent" / (name + ".json"))
    prepared = prepare_agent_image(agent)
    assert prepared["agent_bundle_sha256"] == agent.digest()
    scenario = load_scenario(str(EXAMPLES / "python-agent" / (fixture + "-scenario.json")))
    output = tmp_path / "result"
    result = run_scenario(scenario, output, agent=agent)
    assert result["verdict"] == verdict, result["summary"]
    events, execution = assert_artifacts(result, output)
    assert execution["cleanup"] == "confirmed"
    assert execution["agent_bundle_sha256"] == agent.digest()
    assert execution["adapter_descriptor"]["observability"] == "tool_dispatch_instrumented"
    assert result["adapter"]["adapter_id"] == "custom-python-tools"
    assert verify_artifacts(result, output)
    assert any(event["stage"] == "attempted" for event in events)
    assert all(event["agent_id"] == agent.agent_id for event in events)
    state = json.loads((output / "state.json").read_text())
    assert state["uid"] == 65532 and not state["host_secret_inherited"]
    if fixture == "api":
        assert state["service_call_count"] == 2 and state["injected_fault_count"] == 1
        assert state["mutation_count"] == (1 if name == "retry" else 2)
        assert [
            event["outcome"]["status"] for event in events if event["stage"] == "completed"
        ] == ["failed", "succeeded"]


@pytest.mark.parametrize(
    ("script", "verdict", "budget"),
    [
        (
            'printf \'{"channel":"ready","verdict":"passed"}\\n\'; '
            'printf "SYNTHETIC_PRIVATE_OUTPUT\\n"',
            "passed",
            None,
        ),
        ("exit 7", "failed", None),
        ("sleep 60", "failed", "timed_out"),
        ('while true; do printf "XXXXXXXXXXXXXXX"; done', "failed", "output_limited"),
    ],
)
def test_real_generic_commands_have_process_only_visibility(script, verdict, budget, tmp_path):
    agent = AgentBundle(
        "custom-command-agent",
        "command",
        ("/bin/sh", "/opt/agent/run.sh"),
        (("run.sh", script.encode()),),
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "command-agent/scenario.json"))
    scenario["safety"]["limits"]["timeout_seconds"] = 1
    scenario["safety"]["limits"]["max_output_bytes"] = 512
    output = tmp_path / "result"
    result = run_scenario(scenario, output, agent=agent)
    assert result["verdict"] == verdict, result["summary"]
    events, execution = assert_artifacts(result, output)
    assert not any(event["stage"] in {"attempted", "completed"} for event in events)
    assert execution["adapter_descriptor"]["observability"] == "process_boundary"
    assert execution["cleanup"] == "confirmed"
    if budget:
        assert execution["agent"][budget]
    serialized = "".join(path.read_text() for path in output.iterdir())
    assert "SYNTHETIC_PRIVATE_OUTPUT" not in serialized
    assert "XXXXXXXXXXXXXXX" not in serialized


def test_custom_command_cannot_read_host_files_or_inherit_secrets(tmp_path, monkeypatch):
    outside = tmp_path / "SYNTHETIC_HOST_FILE"
    outside.write_text("SYNTHETIC_HOST_UNCHANGED")
    monkeypatch.setenv("CRASHLAB_HOST_SENTINEL", "SYNTHETIC_PRIVATE_NOT_FOR_GUEST")
    script = (
        "import os, pathlib, socket\n"
        "assert os.getuid() == 65532\n"
        "assert 'CRASHLAB_HOST_SENTINEL' not in os.environ\n"
        f"assert not pathlib.Path({str(outside)!r}).exists()\n"
        "try:\n pathlib.Path('/host-root-write').write_text('unexpected')\n"
        "except OSError:\n pass\n"
        "else:\n raise RuntimeError('root writable')\n"
        "client=socket.socket();client.settimeout(0.25)\n"
        "try:\n client.connect(('192.0.2.1',443))\n"
        "except OSError:\n pass\n"
        "else:\n raise RuntimeError('unexpected connection')\n"
    )
    agent = AgentBundle(
        "custom-command-agent",
        "command",
        ("/usr/local/bin/python", "-I", "/opt/agent/check.py"),
        (("check.py", script.encode()),),
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "command-agent/scenario.json"))
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == "passed", result["summary"]
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["controls"]["host_mounts"] == 0 and execution["cleanup"] == "confirmed"
    assert outside.read_text() == "SYNTHETIC_HOST_UNCHANGED"
    public = "".join(file.read_text() for file in (tmp_path / "result").iterdir())
    assert "SYNTHETIC_HOST_FILE" not in public and "SYNTHETIC_PRIVATE_NOT_FOR_GUEST" not in public
