import ast
import copy
import importlib
import json
import re
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


SCHEMAS = sorted(
    (version, path)
    for version in ("v0.1", "v0.2")
    for path in (ROOT / "contracts/schemas" / version).glob("*.json")
)


@pytest.mark.parametrize("version,schema", SCHEMAS, ids=lambda item: str(item))
def test_schema_and_bundled_snapshots(version, schema):
    canonical = json.loads(schema.read_text())
    Draft202012Validator.check_schema(canonical)
    assert canonical["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert canonical["properties"]["schema_version"]["const"] == version[1:] + ".0"
    assert canonical["$id"].endswith(":" + version[1:] + ".0")

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
        bundled = ROOT / "products" / product / "src" / package / "_schemas" / version / schema.name
        assert bundled.read_bytes() == schema.read_bytes()


# Each contract version is a separate document shape, so the only safe way to add a
# property is a new directory. This holds the relationship between the two: v0.2 must be
# v0.1 with exactly these additions and nothing else, or a 0.1.0 reader and a 0.2.0 reader
# stop agreeing about the fields they share.
V2_ADDITIONS = {
    "scenario-definition": {
        "$.properties.observations",
        "$.properties.assertions.items.properties.predicate",
    },
    "evidence-result": {
        "$.properties.assertions.items.properties.predicate",
        "$.properties.assertions.items.properties.observed",
    },
}


@pytest.mark.parametrize("contract", sorted(V2_ADDITIONS))
def test_v0_2_is_v0_1_plus_exactly_the_declared_additions(contract):
    """Counterfactual: add any other property to a v0.2 schema, or change a shared one,
    and this goes red naming the path - which is the difference between a version bump and
    a silent reshaping of a document two products already exchange.
    """
    name = contract + ".schema.json"
    first = json.loads((ROOT / "contracts/schemas/v0.1" / name).read_text())
    second = json.loads((ROOT / "contracts/schemas/v0.2" / name).read_text())

    def differences(left, right, path="$"):
        if isinstance(left, dict) and isinstance(right, dict):
            found = set()
            for key in set(left) | set(right):
                child = f"{path}.{key}"
                if key not in left:
                    found.add(child)
                elif key not in right:
                    found.add(child)
                else:
                    found |= differences(left[key], right[key], child)
            return found
        return set() if left == right else {path}

    expected = V2_ADDITIONS[contract] | {"$.$id", "$.properties.schema_version.const"}
    assert differences(first, second) == expected


def test_the_readme_counts_match_the_index():
    """Counterfactual: add a fixture without touching the README and this goes red naming
    both numbers. A count written in prose next to the thing it counts drifts on its own,
    and the repository has shipped that defect twice before.
    """
    readme = (ROOT / "contracts/README.md").read_text()
    stated = re.search(r"all (\d+) positive and (\d+) negative fixtures", readme)
    assert stated, "the README no longer states the fixture counts it is checked against"
    assert (int(stated[1]), int(stated[2])) == (len(INDEX["valid"]), len(INDEX["invalid"]))


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


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
def test_no_network_during_validation(api, monkeypatch, result_payload, version):
    def forbidden(*args, **kwargs):
        pytest.fail("Validation attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result_payload["schema_version"] = version
    api.validate_document("evidence-result", result_payload)
    module = importlib.import_module(api.__name__ + ".validation")
    validator, _ = module._validator("evidence-result", version)
    from referencing.exceptions import NoSuchResource

    with pytest.raises(NoSuchResource):
        validator._registry.get_or_retrieve("https://example.invalid/never-fetch")


@pytest.mark.parametrize("contract", ["scenario-definition", "evidence-result"])
def test_a_version_a_reader_does_not_know_is_refused_rather_than_guessed(api, contract):
    """Both products exchange these documents as files, so a 0.2.0 result must be readable
    by the simulator that did not write it, and a 9.0.0 one must be refused by both.
    """
    assert api.SCHEMA_VERSIONS[contract] == ("0.1.0", "0.2.0")
    assert api.SCHEMA_VERSIONS["action-event"] == ("0.1.0",)


@pytest.mark.parametrize(
    ("product", "package"), [("permissions", "iops_permissions"), ("crashlab", "iops_crashlab")]
)
def test_every_schema_directory_is_declared_as_package_data(product, package):
    """A schema directory absent from package-data is absent from the wheel, and every
    document at that version then fails to validate in an installed product while passing
    in the source tree. Counterfactual: pin the pattern back to a single version directory
    and this goes red naming the one that would not ship.
    """
    config = (ROOT / "products" / product / "pyproject.toml").read_text()
    patterns = re.search(rf"^{package} = \[(.*?)\]", config, re.M | re.S)
    assert patterns, "package-data no longer declares this package"
    globs = re.findall(r'"([^"]+)"', patterns[1])
    root = ROOT / "products" / product / "src" / package / "_schemas"
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        wanted = {p.name for p in directory.glob("*.json")}
        assert wanted, f"{directory.name} holds no schema"
        covered = {
            p.name
            for pattern in globs
            for p in (root.parent).glob(pattern)
            if p.parent == directory
        }
        assert covered == wanted, f"{product}: {directory.name} is not fully packaged"


@pytest.mark.parametrize(
    ("product", "package"), [("permissions", "iops_permissions"), ("crashlab", "iops_crashlab")]
)
def test_the_package_version_and_the_project_version_agree(product, package, api):
    """Each product states its version twice - in pyproject.toml and in the module - and
    the packaging gate asserts they match inside an installed wheel. That gate takes
    minutes and needs Docker, so the disagreement is caught here too: this release bumped
    pyproject.toml and missed iops_permissions.__init__, and only the slow gate noticed.
    Counterfactual: change one of the two and this goes red in under a second.
    """
    declared = re.search(
        r'^version = "([^"]+)"', (ROOT / "products" / product / "pyproject.toml").read_text(), re.M
    )
    assert declared, "pyproject.toml no longer declares a version"
    module = importlib.import_module(package)
    assert module.__version__ == declared[1]


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
