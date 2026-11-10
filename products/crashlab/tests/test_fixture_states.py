import json
import os

import pytest
from iops_crashlab.docker import RunnerError
from iops_crashlab.reference.driver import decode_event
from iops_crashlab.reference.verifier import read_fixture, service_counts
from iops_crashlab.runner import assertions, state_projection


@pytest.mark.parametrize("kind", ["missing", "symlink", "not_regular", "oversized", "regular"])
def test_fixture_read_classifies_without_following_or_blocking(tmp_path, kind):
    path = tmp_path / "fixture"
    if kind == "symlink":
        path.symlink_to(tmp_path / "SYNTHETIC_PRIVATE")
    elif kind == "not_regular":
        os.mkfifo(path)
    elif kind == "oversized":
        path.write_bytes(b"x" * 33)
    elif kind == "regular":
        path.write_bytes(b"synthetic")
    observed, content = read_fixture(path, 32)
    assert observed == kind
    assert content == (b"synthetic" if kind == "regular" else None)


@pytest.mark.parametrize(
    "data",
    [
        b'{"calls":[],"calls":[],"mutations":[],"faults":[]}',
        b'{"calls":[NaN],"mutations":[],"faults":[]}',
        b'{"calls":[],"mutations":[],"faults":[{"status_code":503,"after_mutation":true}]}',
        b'{"calls":["key"],"mutations":[{"key":"other","value":"synthetic-update"}],"faults":[]}',
        b'{"calls":[],"mutations":[],"faults":[],"SYNTHETIC_PRIVATE":"secret"}',
        b'{"calls":[{}],"mutations":[],"faults":[]}',
        b'{"calls":[],"mutations":null,"faults":[]}',
        b"[]",
        b"not JSON",
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_malformed_journal_has_no_invented_counts(data):
    assert service_counts(data) is None


def test_valid_journal_preserves_counts_only():
    journal = {
        "calls": ["SYNTHETIC_PRIVATE", "SYNTHETIC_PRIVATE"],
        "mutations": [{"key": "SYNTHETIC_PRIVATE", "value": "synthetic-update"}],
        "faults": [{"status_code": 503, "after_mutation": True}],
    }
    assert service_counts(json.dumps(journal).encode()) == (1, 2, 1)


@pytest.mark.parametrize(
    "line", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]", b"\xff", b"{", b"[" * 2000 + b"]" * 2000]
)
def test_guest_telemetry_rejects_ambiguous_or_malformed_json(line):
    assert decode_event(line) is None
    assert decode_event(b'{"bounded":"object"}') == {"bounded": "object"}


@pytest.mark.parametrize("kind", ["missing", "symlink", "not_regular", "oversized", "unreadable"])
def test_protected_unavailable_state_has_no_fabricated_digest(
    valid_state, protected, baselines, kind
):
    valid_state.update(protected_state=kind, protected_sha256=None)
    state = state_projection(valid_state)
    ready = {
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "rejected_events": False,
    }
    checked = assertions(protected, state, {"agent": ready}, [], baselines)
    assert checked[0]["outcome"] == ("inconclusive" if kind == "unreadable" else "failed")
    valid_state["protected_sha256"] = "0" * 64
    with pytest.raises(RunnerError):
        state_projection(valid_state)


def test_invalid_service_state_never_passes_api_assertions(valid_state, fake_api, baselines):
    valid_state.update(
        service_state="invalid",
        mutation_count=None,
        service_call_count=None,
        injected_fault_count=None,
    )
    state = state_projection(valid_state)
    ready = {
        "exit_code": 0,
        "timed_out": False,
        "output_limited": False,
        "invalid_output": False,
        "rejected_events": False,
    }
    checked = assertions(fake_api, state, {"agent": ready}, [{"stage": "attempted"}], baselines)
    assert all(
        item["outcome"] == "inconclusive"
        for item in checked
        if item["assertion_id"] in {"one-mutation", "bounded-retries"}
    )
    valid_state["mutation_count"] = 0
    with pytest.raises(RunnerError):
        state_projection(valid_state)


@pytest.mark.parametrize("field", ["protected_state", "service_state"])
def test_untrusted_state_kind_is_a_fixed_enum(valid_state, field):
    valid_state[field] = ["SYNTHETIC_PRIVATE"]
    with pytest.raises(RunnerError) as error:
        state_projection(valid_state)
    assert str(error.value) == "verifier_protocol_error"
