import ast
import copy
import importlib
import json
import socket

import pytest
from jsonschema import Draft202012Validator

from .conftest import INDEX, ROOT


@pytest.mark.parametrize("fixture", INDEX["valid"], ids=lambda item: item["file"])
def test_valid_fixtures(api, fixture):
    data = (ROOT / "contracts/examples" / fixture["file"]).read_bytes()
    api.loads_document(fixture["contract"], data)


@pytest.mark.parametrize("fixture", INDEX["invalid"], ids=lambda item: item["file"])
def test_invalid_fixtures(api, fixture):
    data = (ROOT / "contracts/examples" / fixture["file"]).read_bytes()
    with pytest.raises(api.ContractValidationError) as caught:
        api.loads_document(fixture["contract"], data)
    assert fixture["expected_code"] in {issue.code for issue in caught.value.issues}
    public = str(caught.value) + repr(caught.value.issues)
    assert "SYNTHETIC_PRIVATE_VALUE" not in public
    assert "SYNTHETIC_UNKNOWN_PROPERTY" not in public
    assert "SYNTHETIC_INVALID_ENUM" not in public


@pytest.mark.parametrize("schema", sorted((ROOT / "contracts/schemas/v0.1").glob("*.json")))
def test_schema_and_bundled_snapshots(schema):
    canonical = json.loads(schema.read_text())
    Draft202012Validator.check_schema(canonical)
    assert canonical["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert canonical["properties"]["schema_version"]["const"] == "0.1.0"

    # Every reference is internal; missing resources cannot induce network retrieval.
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                assert value["$ref"].startswith("#/")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(canonical)
    for product, package in (("permissions", "iops_permissions"), ("crashlab", "iops_crashlab")):
        bundled = ROOT / "products" / product / "src" / package / "_schemas/v0.1" / schema.name
        assert bundled.read_bytes() == schema.read_bytes()


def test_fixture_index_covers_all_files_and_contracts():
    listed = {item["file"] for group in INDEX.values() for item in group}
    actual = {
        str(path.relative_to(ROOT / "contracts/examples"))
        for kind in ("valid", "invalid")
        for path in (ROOT / "contracts/examples" / kind).glob("*.json")
    }
    assert listed == actual
    contracts = {"action-event", "capability-manifest", "scenario-definition", "evidence-result"}
    for group in INDEX.values():
        assert {item["contract"] for item in group} == contracts


def test_cross_product_reference_chain(api):
    def load(name):
        return json.loads((ROOT / "contracts/examples/valid" / (name + ".json")).read_text())

    manifest = load("custom-python-manifest")
    scenario = load("protected-file-write")
    result = load("reference-result-passed")
    event = load("verified-state")
    assert scenario["metadata"]["manifest_id"] == manifest["manifest_id"]
    assert scenario["target"]["agent_id"] == manifest["agent_id"]
    assert scenario["scenario_id"] == result["scenario_id"]
    assert event["run_id"] == result["run_id"]
    assert {a["assertion_id"] for a in result["assertions"]} == {
        a["assertion_id"] for a in scenario["assertions"]
    }
    assert set(event["artifact_refs"]) <= {a["artifact_id"] for a in result["artifacts"]}
    assert result["provenance"] == "reference"
    assert "ILLUSTRATIVE" in result["summary"]
    assert "sha256" not in result["artifacts"][0]
    api.validate_document("evidence-result", result)


@pytest.mark.parametrize(
    ("verdict", "outcome"),
    [
        ("failed", "error"),
        ("inconclusive", "failed"),
        ("unsupported", "passed"),
        ("skipped", "passed"),
        ("failed", "passed"),
    ],
)
def test_contradictory_verdicts_rejected(api, result_payload, verdict, outcome):
    result_payload["verdict"] = verdict
    result_payload["assertions"][0]["outcome"] = outcome
    with pytest.raises(api.ContractValidationError, match="verdict_mismatch"):
        api.validate_document("evidence-result", result_payload)


def test_no_vacuous_pass(api, result_payload):
    result_payload["assertions"] = []
    with pytest.raises(api.ContractValidationError):
        api.validate_document("evidence-result", result_payload)


def test_passed_assertion_always_requires_evidence(api, result_payload):
    result_payload["verdict"] = "inconclusive"
    result_payload["assertions"][0]["evidence_refs"] = []
    with pytest.raises(api.ContractValidationError, match="invalid_reference"):
        api.validate_document("evidence-result", result_payload)


def test_offset_timestamps_compare_as_instants(api, result_payload):
    result_payload["started_at"] = "2026-11-03T18:00:00-08:00"
    result_payload["finished_at"] = "2026-11-04T02:00:01Z"
    api.validate_document("evidence-result", result_payload)


def test_lowercase_rfc3339_is_supported(api, result_payload):
    result_payload["started_at"] = "2026-11-04t02:00:00z"
    result_payload["finished_at"] = "2026-11-04t02:00:01z"
    api.validate_document("evidence-result", result_payload)


@pytest.mark.parametrize(
    ("contract", "fixture", "collection"),
    [
        ("capability-manifest", "custom-python-manifest", "capabilities"),
        ("scenario-definition", "protected-file-write", "assertions"),
    ],
)
def test_unique_manifest_and_scenario_ids(api, contract, fixture, collection):
    payload = json.loads((ROOT / "contracts/examples/valid" / (fixture + ".json")).read_text())
    payload[collection].append(copy.deepcopy(payload[collection][0]))
    with pytest.raises(api.ContractValidationError, match="duplicate_id"):
        api.validate_document(contract, payload)


def test_extensions_do_not_override_core_validation(api, result_payload):
    result_payload["extensions"] = {"verdict": "passed", "command": "SYNTHETIC_NEVER_EXECUTE"}
    result_payload["verdict"] = "failed"
    with pytest.raises(api.ContractValidationError, match="verdict_mismatch"):
        api.validate_document("evidence-result", result_payload)


def test_no_network_during_validation(api, monkeypatch, result_payload):
    def forbidden(*args, **kwargs):
        pytest.fail("Validation attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    api.validate_document("evidence-result", result_payload)
    module = importlib.import_module(api.__name__ + ".validation")
    validator, _ = module._validator("evidence-result")
    from referencing.exceptions import NoSuchResource

    with pytest.raises(NoSuchResource):
        validator._registry.get_or_retrieve("https://example.invalid/never-fetch")


def test_products_do_not_import_each_other_or_reference_engine():
    for product, package, other in (
        ("permissions", "iops_permissions", "iops_crashlab"),
        ("crashlab", "iops_crashlab", "iops_permissions"),
    ):
        for source in (ROOT / "products" / product / "src" / package).glob("*.py"):
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imports = [node.module or ""]
                else:
                    continue
                assert all(not name.startswith((other, "contracts", "app.")) for name in imports)


def test_input_unchanged(api, result_payload):
    before = copy.deepcopy(result_payload)
    api.validate_document("evidence-result", result_payload)
    assert result_payload == before


def test_actual_permission_export_is_consumed_by_both_products():
    permissions = importlib.import_module("iops_permissions")
    crashlab = importlib.import_module("iops_crashlab")
    examples = ROOT / "products/permissions/examples"
    policy = permissions.loads_policy((examples / "policy.json").read_bytes())
    request = permissions.loads_action_request((examples / "action-denied.json").read_bytes())
    manifest = permissions.loads_document(
        "capability-manifest", (examples / "operations-manifest.json").read_bytes()
    )
    fixture = permissions.loads_fixture_descriptor(
        (examples / "protected-file-fixture.json").read_bytes()
    )
    for explicit_fixture in (None, fixture):
        exported = permissions.export_scenario(policy, request, manifest, explicit_fixture)
        assert exported.status == "exported"
        assert exported.execution_status == "not_executed"
        serialized = json.dumps(exported.scenario)
        assert crashlab.loads_document("scenario-definition", serialized) == exported.scenario
        assert permissions.loads_document("scenario-definition", serialized) == exported.scenario
