import json
from pathlib import Path

import pytest
from iops_crashlab import prepare_reference_image, run_scenario
from iops_crashlab.cli import verify_artifacts
from iops_crashlab.docker import Docker

from ..conftest import assert_artifacts

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def actual_image():
    # Requested integration checks fail if the local engine/base image is unavailable.
    return prepare_reference_image()


@pytest.mark.parametrize(
    ("fixture", "variant", "verdict"),
    [
        ("protected", "respect", "passed"),
        ("protected", "violate", "failed"),
        ("fake_api", "respect", "passed"),
        ("fake_api", "violate", "failed"),
        ("budget", "timeout", "failed"),
        ("budget", "noisy", "failed"),
        ("protected", "silent", "failed"),
        ("budget", "silent", "inconclusive"),
    ],
)
def test_actual_behavior_and_consequences(
    request, tmp_path, fixture, variant, verdict, monkeypatch
):
    scenario = request.getfixturevalue(fixture)
    monkeypatch.setenv("CRASHLAB_HOST_SENTINEL", "SYNTHETIC_PRIVATE_NOT_FOR_GUEST")
    outside = tmp_path / "outside"
    outside.write_text("SYNTHETIC_HOST_UNCHANGED")
    output = tmp_path / "result"
    result = run_scenario(scenario, output, variant=variant)
    assert result["verdict"] == verdict, result["summary"]
    events, execution = assert_artifacts(result, output)
    assert execution["cleanup"] == "confirmed"
    assert execution["controls"]["host_mounts"] == 0
    assert verify_artifacts(result, output)
    assert "[state.json](state.json)" in (output / "report.md").read_text()
    state = json.loads((output / "state.json").read_text())
    assert state["host_secret_inherited"] is False
    assert state["uid"] == 65532 and state["non_loopback_interfaces_up"] == 0
    assert state["process_security"]["CapEff"] == "0000000000000000"
    assert outside.read_text() == "SYNTHETIC_HOST_UNCHANGED"
    assert (
        not Docker()
        .call(
            [
                "container",
                "ls",
                "--all",
                "--filter",
                "label=org.iops.crashlab.run=" + result["run_id"],
                "--format",
                "{{.ID}}",
            ]
        )
        .output.strip()
    )
    if fixture == "fake_api":
        assert state["mutation_count"] == (1 if variant == "respect" else 2)
        assert state["injected_fault_count"] == 1
        assert state["service_call_count"] == 2
        completions = [
            event["outcome"]["status"] for event in events if event["stage"] == "completed"
        ]
        assert completions == ["failed", "succeeded"]
    if fixture == "budget" and variant in {"timeout", "noisy"}:
        assert execution["agent"]["timed_out" if variant == "timeout" else "output_limited"]
    public = "".join(file.read_text() for file in Path(output).iterdir())
    assert "SYNTHETIC_PRIVATE_NOT_FOR_GUEST" not in public
    assert result["provenance"] == "observed"
    assert not any(event["stage"] == "side_effect_observed" for event in events)


def test_actual_container_loss_is_harness_error_not_agent_failure(protected, tmp_path, monkeypatch):
    original = Docker.call
    removed = []

    def lose_owned_container_before_verification(self, args, **kwargs):
        if args[0] == "exec":
            inspected = self.json(["container", "inspect", args[1]])[0]
            assert inspected["Name"].startswith("/iops-crashlab-")
            assert inspected["Config"]["Labels"]["org.iops.crashlab.run"].startswith("run-")
            original(self, ["container", "rm", "--force", args[1]])
            removed.append(args[1])
        return original(self, args, **kwargs)

    monkeypatch.setattr(Docker, "call", lose_owned_container_before_verification)
    result = run_scenario(protected, tmp_path / "result")
    assert removed
    assert result["verdict"] == "error" and result["assertions"] == []
    _, execution = assert_artifacts(result, tmp_path / "result")
    assert execution["cleanup"] == "confirmed"
