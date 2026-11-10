import copy
from importlib.resources import files
from pathlib import Path

import pytest
from iops_crashlab import validate_document
from iops_crashlab.catalog import negotiate
from iops_crashlab.cli import BUILTINS, load_scenario
from iops_crashlab.docker import RunnerUnsupported


@pytest.mark.parametrize("name", BUILTINS)
def test_standalone_builtins_validate_and_negotiate(name):
    scenario = load_scenario("builtin:" + name)
    validate_document("scenario-definition", scenario)
    assert negotiate(scenario, "respect") in {"protected", "fake_api"}
    source = Path(__file__).resolve().parents[1] / "scenarios" / (name + ".json")
    assert (
        source.read_bytes()
        == files("iops_crashlab").joinpath("_scenarios", name + ".json").read_bytes()
    )


def test_a_listed_builtin_shows_that_the_conditions_can_be_yours():
    """The capability the 0.2.0 contract exists for has to be visible to someone who
    installs the package and looks around. Until 2026-11-09 `iops-crashlab examples` listed
    three scenarios and not one carried a predicate, so a reader could take in the whole
    listing and conclude the product only checks conditions we had chosen for them.

    The assertions below are what make the example a template rather than a token: it has
    to declare observations, draw on more than one predicate source, and mix at least one
    built-in identifier, because a scenario demonstrating a single operator teaches a user
    almost nothing.

    Counterfactual: drop the predicates from the scenario that has them, reduce it to one
    predicate source, remove its built-in assertion, or take it out of BUILTINS - each of
    those turns this red. Taking it out of `wizard.SCENARIOS` does NOT, and saying it did
    would be a claim about a check that never runs: that one is caught by
    `test_the_offered_scenarios_are_real_builtins`, which holds the two lists equal, and
    the counterfactual was run against that test rather than this one.
    """
    carrying = {}
    for name in BUILTINS:
        scenario = load_scenario("builtin:" + name)
        predicates = [item["predicate"] for item in scenario["assertions"] if "predicate" in item]
        if predicates:
            carrying[name] = (scenario, predicates)
    assert carrying, "no listed builtin shows a user that the conditions can be their own"
    for name, (scenario, predicates) in carrying.items():
        assert scenario["schema_version"] == "0.2.0", name
        assert scenario.get("observations"), name
        assert len({item["source"] for item in predicates}) >= 3, name
        assert any("predicate" not in item for item in scenario["assertions"]), name


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fixture", "fixture://unknown"),
        ("target", "unknown-adapter"),
        ("feature", "network_effects"),
        ("runtime", "shell"),
        ("resource", "fixture://protected-workspace/../secret"),
        ("permissions", "host_root_write"),
        ("memory", 4096),
        ("pids", 128),
        ("timeout", 3600),
        ("cpus", 4),
        ("assertion", "unknown-assertion"),
        ("expectation", "SYNTHETIC_NEVER_EXECUTE"),
        ("fault", "api_failure"),
        ("policy", "allowed"),
    ],
)
def test_unavailable_semantics_are_explicitly_unsupported(protected, field, value):
    if field == "fixture":
        protected["environment"]["fixture_id"] = value
    elif field == "target":
        protected["target"]["adapter_id"] = value
    elif field == "feature":
        protected["requirements"]["adapter_features"] = [value]
    elif field == "runtime":
        protected["requirements"]["runtime"] = value
    elif field == "resource":
        protected["action_selector"]["resource"]["identifier"] = value
    elif field == "permissions":
        protected["safety"]["permissions"] = [value]
    elif field in {"memory", "pids", "timeout", "cpus"}:
        key = {"memory": "memory_mb", "pids": "pids", "timeout": "timeout_seconds", "cpus": "cpus"}[
            field
        ]
        protected["safety"]["limits"][key] = value
    elif field in {"assertion", "expectation"}:
        protected["assertions"][0]["assertion_id" if field == "assertion" else "expectation"] = (
            value
        )
    elif field == "fault":
        protected["fault"] = {"kind": value, "after_matches": 1}
    else:
        protected["policy_constraints"][0]["decision"] = value
    validate_document("scenario-definition", protected)
    with pytest.raises(RunnerUnsupported):
        negotiate(protected, "respect")


def test_policy_only_mode_is_not_faked_as_execution(protected):
    protected["mode"] = "policy_simulation"
    protected["requirements"]["runner"] = "none"
    with pytest.raises(RunnerUnsupported):
        negotiate(protected, "respect")


def test_metadata_extensions_never_choose_a_variant_or_command(protected):
    before = copy.deepcopy(protected)
    protected["extensions"] = {"variant": "violate", "command": "SYNTHETIC_NEVER_EXECUTE"}
    assert negotiate(protected, "respect") == negotiate(before, "respect")
    with pytest.raises(RunnerUnsupported):
        negotiate(protected, "untrusted-command")


def test_fake_fault_is_exact_and_no_real_service_allowed(fake_api):
    fake_api["fault"]["response_code"] = 401
    with pytest.raises(RunnerUnsupported, match="fault_not_supported"):
        negotiate(fake_api, "respect")


def test_builtin_path_traversal_is_not_opened():
    from iops_crashlab import ContractValidationError

    with pytest.raises(ContractValidationError) as caught:
        load_scenario("builtin:../../SYNTHETIC_PRIVATE")
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
