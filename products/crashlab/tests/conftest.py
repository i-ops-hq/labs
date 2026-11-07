import json
from pathlib import Path

import pytest
from iops_crashlab.cli import load_scenario


def pytest_addoption(parser):
    parser.addoption(
        "--docker", action="store_true", help="Require actual local Docker integration tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: actual isolated Docker execution")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--docker"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --docker to require live integration"))


@pytest.fixture
def protected():
    return load_scenario("builtin:protected-file-write")


@pytest.fixture
def fake_api():
    return load_scenario("builtin:fake-api-partial-failure")


@pytest.fixture
def budget():
    return load_scenario("builtin:execution-budget")


@pytest.fixture
def valid_state():
    from iops_crashlab.runner import PROTECTED_SHA

    return {
        "protected_state": "regular",
        "service_state": "valid",
        "protected_sha256": PROTECTED_SHA,
        "mutation_count": 1,
        "service_call_count": 2,
        "injected_fault_count": 1,
        "uid": 65532,
        "process_security": {"CapEff": "0000000000000000", "NoNewPrivs": "1", "Seccomp": "2"},
        "root_write_denied": True,
        "network_probe_denied": True,
        "host_secret_inherited": False,
        "package_installer_present": False,
        "non_loopback_interfaces_up": 0,
        "cgroup_memory_max": "134217728",
        "cgroup_pids_max": "32",
        "cgroup_cpu_max": "100000 100000",
        "python_version": "3.12.0",
    }


def assert_artifacts(result, output):
    import hashlib

    from iops_crashlab import validate_document

    validate_document("evidence-result", result)
    for artifact in result["artifacts"]:
        file = Path(output) / artifact["locator"].rsplit("/", 1)[1]
        assert hashlib.sha256(file.read_bytes()).hexdigest() == artifact["sha256"]
    events = [json.loads(line) for line in (Path(output) / "events.jsonl").read_text().splitlines()]
    for index, event in enumerate(events):
        validate_document("action-event", event)
        assert event["sequence"] == index
        assert event["run_id"] == result["run_id"]
    execution = json.loads((Path(output) / "execution.json").read_text())
    assert execution["cleanup"] in {"confirmed", "not_required"}
    return events, execution
