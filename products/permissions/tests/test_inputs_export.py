import copy
import json

import iops_permissions as api
import pytest
from iops_permissions.inputs import _input_validator
from jsonschema import Draft202012Validator


@pytest.mark.parametrize("kind", ["policy", "action-request", "fixture-descriptor"])
def test_private_schemas_valid(kind):
    validator, _ = _input_validator(kind)
    Draft202012Validator.check_schema(validator.schema)


@pytest.mark.parametrize("field", ["schema_version", "default_decision", "rules", "agent_ids"])
def test_missing_policy_fields_are_errors(policy, action_request, field):
    policy.pop(field)
    with pytest.raises(api.ContractValidationError):
        api.evaluate(policy, action_request)


@pytest.mark.parametrize(
    "pattern",
    [
        "**",
        "/workspace/**",
        "/workspace/[ab]",
        "/workspace/../*",
        "https://host/path?key=SYNTHETIC_PRIVATE",
        "a*b",
    ],
)
def test_unsupported_policy_syntax_is_an_error(policy, action_request, pattern):
    policy["rules"][0]["resource_patterns"] = [pattern]
    with pytest.raises(api.ContractValidationError, match="unsupported_policy_pattern") as caught:
        api.evaluate(policy, action_request)
    assert "SYNTHETIC_PRIVATE" not in repr(caught.value.issues)


def test_duplicate_ids_and_unsupported_version(policy, action_request):
    policy["rules"].append(copy.deepcopy(policy["rules"][0]))
    with pytest.raises(api.ContractValidationError, match="duplicate_rule_id"):
        api.evaluate(policy, action_request)
    policy["schema_version"] = "0.1.1"
    with pytest.raises(api.ContractValidationError, match="unsupported_version"):
        api.evaluate(policy, action_request)


def test_unknown_fields_and_duplicate_keys_cannot_allow(policy, action_request):
    policy["SYNTHETIC_PRIVATE_FIELD"] = "SYNTHETIC_PRIVATE_VALUE"
    with pytest.raises(api.ContractValidationError) as caught:
        api.evaluate(policy, action_request)
    assert "SYNTHETIC_PRIVATE" not in str(caught.value) + repr(caught.value.issues)
    with pytest.raises(api.ContractValidationError, match="invalid_json"):
        api.loads_policy('{"schema_version":"0.1.0","schema_version":"0.1.0"}')


@pytest.mark.parametrize(
    ("loader", "name"),
    [
        (api.loads_policy, "policy"),
        (api.loads_action_request, "action-allowed"),
        (api.loads_fixture_descriptor, "protected-file-fixture"),
    ],
)
def test_public_loaders(loader, name, example):
    document = example(name)
    assert loader(json.dumps(document)) == document
    with pytest.raises(api.ContractValidationError):
        loader(b"invalid SYNTHETIC_PRIVATE")


@pytest.mark.parametrize("name", ["allowed", "denied", "approval", "unknown"])
def test_policy_export_preserves_each_decision(policy, capabilities, example, name):
    action_request = example("action-" + name)
    result = api.export_scenario(policy, action_request, capabilities)
    assert result.status == "exported"
    assert result.execution_status == "not_executed"
    assert result.scenario["mode"] == "policy_simulation"
    assert result.scenario["requirements"]["runner"] == "none"
    assert (
        result.scenario["policy_constraints"][0]["decision"]
        == api.evaluate(policy, action_request, capabilities).decision
    )
    api.validate_document("scenario-definition", result.scenario)


def test_execution_export_requires_matching_explicit_fixture(policy, capabilities, example):
    action_request = example("action-denied")
    fixture = example("protected-file-fixture")
    before = copy.deepcopy([policy, action_request, capabilities, fixture])
    first = api.export_scenario(policy, action_request, capabilities, fixture)
    second = api.export_scenario(policy, action_request, capabilities, fixture)
    assert first == second
    assert first.scenario["mode"] == "isolated_execution"
    assert first.scenario["safety"]["network"] == "off"
    assert first.scenario["assertions"][0]["method"] == "file_state"
    assert {item["method"] for item in first.scenario["assertions"]} == {
        "file_state",
        "event_query",
    }
    assert any(
        item["assertion_id"] == "protected-write-attempted" for item in first.scenario["assertions"]
    )
    assert first.scenario["metadata"]["manifest_id"] == capabilities["manifest_id"]
    assert first.scenario["extensions"]["iops_permissions"]["runtime_readiness"] == "unverified"
    assert before == [policy, action_request, capabilities, fixture]


@pytest.mark.parametrize("name", ["allowed", "api", "approval"])
def test_execution_export_never_silently_falls_back(policy, example, name):
    result = api.export_scenario(
        policy, example("action-" + name), fixture=example("protected-file-fixture")
    )
    assert result.status == "unsupported"
    assert result.scenario is None
    assert result.execution_status == "not_executed"


def test_protected_fixture_is_not_exported_with_an_allow(policy, example):
    policy["rules"] = []
    policy["default_decision"] = "allowed"
    result = api.export_scenario(
        policy, example("action-denied"), fixture=example("protected-file-fixture")
    )
    assert result.status == "unsupported"
    assert result.reason_code == "protected_write_requires_explicit_denial"


def test_fixture_path_escape_rejected(policy, example):
    fixture = example("protected-file-fixture")
    fixture["protected_resource"] = "fixture://protected-workspace/../secret"
    with pytest.raises(api.ContractValidationError, match="invalid_fixture_descriptor"):
        api.export_scenario(policy, example("action-denied"), fixture=fixture)


def test_ambiguous_resource_is_not_exported(policy, action_request):
    action_request["action"]["resource"]["identifier"] = "https://host/path?SYNTHETIC_PRIVATE"
    result = api.export_scenario(policy, action_request)
    assert result.status == "unsupported"
    assert result.scenario is None
    assert "SYNTHETIC_PRIVATE" not in json.dumps(result.to_dict())


def test_nonsemantic_manifest_extensions_do_not_change_or_break_export(
    policy, action_request, capabilities
):
    original = api.export_scenario(policy, action_request, capabilities)
    # Valid object-API metadata must not be serialized into a scenario fingerprint.
    capabilities["extensions"] = {"large_integer": 10**5000}
    assert api.export_scenario(policy, action_request, capabilities) == original
