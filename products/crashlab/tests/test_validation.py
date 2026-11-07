import copy
import json

import iops_crashlab as api
import pytest
from iops_crashlab import validation


@pytest.fixture
def manifest():
    return {
        "schema_version": "0.1.0",
        "manifest_id": "synthetic-manifest",
        "agent_id": "synthetic-agent",
        "captured_at": "2026-11-04T02:00:00Z",
        "source_adapter": {"adapter_id": "synthetic", "version": "0.0.0"},
        "capabilities": [],
        "unknowns": ["Effective authority is unknown."],
        "coverage": {
            "observability": "declared_only",
            "scope": "Synthetic test only.",
            "limitations": ["No actual integration."],
        },
    }


def test_valid_manifest_and_serialized_input(manifest):
    api.validate_document("capability-manifest", manifest)
    assert api.loads_document("capability-manifest", json.dumps(manifest)) == manifest
    assert api.loads_document("capability-manifest", json.dumps(manifest).encode()) == manifest


@pytest.mark.parametrize(
    "bad",
    [
        b"invalid SYNTHETIC_PRIVATE",
        b"\xff",
        "{",
        "[]",
        "null",
        '{"schema_version":"0.1.0","schema_version":"9.0.0"}',
        '{"schema_version":"0.1.0","extensions":{"n":NaN}}',
        '{"schema_version":"0.1.0","extensions":{"n":Infinity}}',
        '{"schema_version":"0.1.0","extensions":{"n":1e9999}}',
    ],
)
def test_rejects_malformed_json_without_value_leak(bad):
    with pytest.raises(api.ContractValidationError) as caught:
        api.loads_document("capability-manifest", bad)
    assert "SYNTHETIC_PRIVATE" not in str(caught.value) + repr(caught.value.issues)


@pytest.mark.parametrize("version", ["9.0.0", "0.2.0", "0.1.1", None, 1, True])
def test_explicit_version_failure(manifest, version):
    manifest["schema_version"] = version
    with pytest.raises(api.ContractValidationError, match="unsupported_version"):
        api.validate_document("capability-manifest", manifest)


def test_rejects_naive_timestamp(manifest):
    manifest["captured_at"] = "2026-11-04T02:00:00"
    with pytest.raises(api.ContractValidationError):
        api.validate_document("capability-manifest", manifest)


def test_unknown_contract_is_redacted():
    with pytest.raises(api.ContractValidationError) as caught:
        api.validate_document("SYNTHETIC_PRIVATE", {})
    assert caught.value.issues[0].code == "unknown_contract"
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)


def test_unknown_fields_and_values_are_redacted(manifest):
    manifest["SYNTHETIC_PRIVATE_FIELD"] = "SYNTHETIC_PRIVATE_VALUE"
    with pytest.raises(api.ContractValidationError) as caught:
        api.validate_document("capability-manifest", manifest)
    assert "SYNTHETIC_PRIVATE" not in str(caught.value) + repr(caught.value.issues)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object(), {1: "value"}, "\ud800"])
def test_non_json_python_values_rejected(manifest, bad):
    manifest["extensions"] = {"value": bad}
    with pytest.raises(api.ContractValidationError):
        api.validate_document("capability-manifest", manifest)


def test_cyclic_python_input_rejected(manifest):
    manifest["extensions"] = manifest
    with pytest.raises(api.ContractValidationError, match="invalid_json"):
        api.validate_document("capability-manifest", manifest)


def test_byte_limit_and_depth_limit(manifest):
    with pytest.raises(api.ContractValidationError, match="input_limit"):
        api.loads_document("capability-manifest", " " * (validation.MAX_DOCUMENT_BYTES + 1))
    value = {}
    for _ in range(validation.MAX_DEPTH + 1):
        value = {"child": value}
    manifest["extensions"] = value
    with pytest.raises(api.ContractValidationError, match="input_limit"):
        api.validate_document("capability-manifest", manifest)


def test_multibyte_input_limit_is_preserved():
    data = json.dumps({"extensions": {"text": "é" * 600_000}}, ensure_ascii=False)
    with pytest.raises(api.ContractValidationError, match="input_limit"):
        api.loads_document("capability-manifest", data)


def test_node_limit_and_diagnostic_limit(manifest):
    manifest["extensions"] = {"nodes": [None] * validation.MAX_NODES}
    with pytest.raises(api.ContractValidationError, match="input_limit"):
        api.validate_document("capability-manifest", manifest)
    manifest.pop("extensions")
    manifest["capabilities"] = [{} for _ in range(100)]
    with pytest.raises(api.ContractValidationError) as caught:
        api.validate_document("capability-manifest", manifest)
    assert len(caught.value.issues) == validation.MAX_ISSUES


def test_validation_does_not_mutate_input(manifest):
    before = copy.deepcopy(manifest)
    api.validate_document("capability-manifest", manifest)
    assert manifest == before
