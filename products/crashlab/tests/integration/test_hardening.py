import json
from pathlib import Path

import pytest
from iops_crashlab import AgentBundle, prepare_agent_image, run_scenario
from iops_crashlab.cli import load_scenario, verify_artifacts

from ..conftest import assert_artifacts

pytestmark = pytest.mark.integration
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DENIED_CALL = (
    "from crashlab_tools import write_protected\n"
    "try:\n write_protected('synthetic')\nexcept PermissionError:\n pass\n"
)


@pytest.mark.parametrize(
    ("change", "kind", "outcome"),
    [
        ("path.unlink()", "missing", "failed"),
        ("path.unlink();path.symlink_to('/etc/passwd')", "symlink", "failed"),
        ("path.unlink();os.mkfifo(path)", "not_regular", "failed"),
        ("path.unlink();path.mkdir()", "not_regular", "failed"),
        ("path.write_bytes(b'X'*4097)", "oversized", "failed"),
        ("path.chmod(0)", "unreadable", "inconclusive"),
    ],
)
def test_actual_protected_file_replacement_is_observed_state(change, kind, outcome, tmp_path):
    script = DENIED_CALL + "import os\nfrom pathlib import Path\n"
    script += "path=Path('/workspace/protected.txt')\n" + change + "\n"
    agent = AgentBundle(
        "custom-ops-agent", "python_tools", ("agent.py",), (("agent.py", script.encode()),)
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "python-agent/protected-scenario.json"))
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == outcome, result["summary"]
    assert result["assertions"][0]["outcome"] == outcome
    state = json.loads((tmp_path / "result/state.json").read_text())
    assert state["protected_state"] == kind and state["protected_sha256"] is None
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["cleanup"] == "confirmed" and verify_artifacts(result, tmp_path / "result")


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ("path.unlink()", "missing"),
        ("path.write_text('not JSON')", "invalid"),
        ('path.write_text(\'{"calls":[],"calls":[],"mutations":[],"faults":[]}\')', "invalid"),
        ("path.unlink();path.symlink_to('/etc/passwd')", "symlink"),
        ("path.unlink();os.mkfifo(path)", "not_regular"),
        ("path.write_bytes(b'X'*16385)", "oversized"),
    ],
)
def test_actual_malformed_journal_is_inconclusive_not_harness_crash(change, kind, tmp_path):
    script = (EXAMPLES / "python-agent/retry.py").read_text()
    script += "\nimport os\nfrom pathlib import Path\npath=Path('/workspace/service.json')\n"
    script += change + "\n"
    agent = AgentBundle(
        "custom-ops-agent", "python_tools", ("agent.py",), (("agent.py", script.encode()),)
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "python-agent/api-scenario.json"))
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == "inconclusive", result["summary"]
    state = json.loads((tmp_path / "result/state.json").read_text())
    assert state["service_state"] == kind
    assert all(
        state[key] is None
        for key in ("mutation_count", "service_call_count", "injected_fault_count")
    )
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["cleanup"] == "confirmed"


def test_actual_ambiguous_python_telemetry_cannot_make_a_positive_result(tmp_path):
    script = DENIED_CALL + 'print(\'{"stage":"attempted","stage":"completed"}\')\n'
    agent = AgentBundle(
        "custom-ops-agent", "python_tools", ("agent.py",), (("agent.py", script.encode()),)
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "python-agent/protected-scenario.json"))
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == "inconclusive", result["summary"]
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["agent"]["invalid_output"] and execution["cleanup"] == "confirmed"


def test_actual_detached_descendant_is_bounded_and_removed(tmp_path):
    script = (
        "import subprocess,sys\n"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
        "start_new_session=True)\n"
    )
    agent = AgentBundle(
        "custom-command-agent",
        "command",
        ("/usr/local/bin/python", "-I", "/opt/agent/agent.py"),
        (("agent.py", script.encode()),),
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "command-agent/scenario.json"))
    scenario["safety"]["limits"]["timeout_seconds"] = 1
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == "failed", result["summary"]
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["agent"]["timed_out"] and execution["cleanup"] == "confirmed"


def test_generic_command_has_empty_stdin_and_preserves_fast_exit_status(tmp_path):
    script = "import sys\ndata=sys.stdin.buffer.read(1024)\nraise SystemExit(91 if data else 7)\n"
    agent = AgentBundle(
        "custom-command-agent",
        "command",
        ("/usr/local/bin/python", "-I", "/opt/agent/agent.py"),
        (("agent.py", script.encode()),),
    )
    prepare_agent_image(agent)
    scenario = load_scenario(str(EXAMPLES / "command-agent/scenario.json"))
    result = run_scenario(scenario, tmp_path / "result", agent=agent)
    assert result["verdict"] == "failed", result["summary"]
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["agent"]["exit_code"] == 7 and execution["cleanup"] == "confirmed"
