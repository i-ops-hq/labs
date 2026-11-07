import copy
import itertools
import json
import socket

import iops_permissions as api
import pytest


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("allowed", "allowed"),
        ("denied", "denied"),
        ("approval", "requires_approval"),
        ("unknown", "unknown"),
        ("api", "allowed"),
    ],
)
def test_example_decisions(policy, capabilities, example, name, expected):
    result = api.evaluate(policy, example("action-" + name), capabilities)
    assert result.decision == expected
    assert "Declared policy simulation only" in result.limitations[0]


def test_synthetic_coding_agent_is_equally_supported(policy, example):
    result = api.evaluate(policy, example("action-coding"), example("coding-manifest"))
    assert result.decision == "allowed"
    assert result.agent_id == "coding-fixture"


@pytest.mark.parametrize(
    "order", list(itertools.permutations(["allowed", "unknown", "requires_approval", "denied"]))
)
def test_rule_order_never_weakens_denial(policy, action_request, order):
    template = policy["rules"][0]
    policy["rules"] = [
        dict(copy.deepcopy(template), rule_id=effect, effect=effect) for effect in order
    ]
    result = api.evaluate(policy, action_request)
    assert result.decision == "denied"
    assert result.matched_rule_ids == tuple(sorted(order))


@pytest.mark.parametrize(
    ("effects", "expected"),
    [
        (["allowed", "unknown"], "unknown"),
        (["allowed", "requires_approval"], "requires_approval"),
        (["unknown", "requires_approval"], "requires_approval"),
    ],
)
def test_conflict_precedence(policy, action_request, effects, expected):
    template = policy["rules"][0]
    policy["rules"] = [
        dict(copy.deepcopy(template), rule_id=effect, effect=effect) for effect in effects
    ]
    assert api.evaluate(policy, action_request).decision == expected


@pytest.mark.parametrize("decision", ["allowed", "denied", "requires_approval", "unknown"])
def test_explicit_defaults_are_explained(policy, action_request, decision):
    policy["rules"] = []
    policy["default_decision"] = decision
    result = api.evaluate(policy, action_request)
    assert result.decision == decision
    assert "explicit_policy_default" in result.reason_codes
    assert result.matched_rule_ids == ()
    assert result.scope == "declared_policy_only"


@pytest.mark.parametrize(
    "dimension", ["action_kinds", "operations", "resource_types", "resource_patterns"]
)
def test_selector_dimensions_are_conjoined(policy, action_request, dimension):
    rule = copy.deepcopy(policy["rules"][0])
    rule[dimension] = {
        "action_kinds": ["api"],
        "operations": ["delete"],
        "resource_types": ["record"],
        "resource_patterns": ["fixture://elsewhere/*"],
    }[dimension]
    policy["rules"] = [rule]
    assert api.evaluate(policy, action_request).decision == "unknown"


def test_selector_values_are_disjoined_and_wildcards_explicit(policy, action_request):
    policy["rules"] = [
        dict(
            policy["rules"][0],
            action_kinds=["api", "filesystem"],
            operations=["write", "read"],
            resource_types=["*"],
        )
    ]
    assert api.evaluate(policy, action_request).decision == "allowed"


def test_directory_prefix_does_not_match_sibling(policy, action_request):
    action_request["action"]["resource"]["identifier"] = (
        "fixture://protected-workspace-evil/readme.txt"
    )
    assert api.evaluate(policy, action_request).decision == "unknown"


def test_exact_pattern_does_not_match_children(policy, action_request):
    policy["rules"] = [
        dict(policy["rules"][0], resource_patterns=["fixture://protected-workspace/readme.txt"])
    ]
    assert api.evaluate(policy, action_request).decision == "allowed"
    action_request["action"]["resource"]["identifier"] += "/child"
    assert api.evaluate(policy, action_request).decision == "unknown"


@pytest.mark.parametrize(
    "identifier",
    [
        "/workspace/../secret",
        "/workspace/./file",
        "/workspace//file",
        "//server/share",
        "fixture://workspace/%2e%2e/secret",
        "https://user@host/path",
        "https://host/path?key=secret",
        "https://host/path#fragment",
        "C:\\workspace\\file",
        "/workspace/\nfile",
        "fixture://",
        "/workspace/[ab]",
        "/workspace/*",
        " fixture://workspace/file",
    ],
)
def test_ambiguous_resources_never_receive_allow(policy, action_request, identifier):
    policy["rules"] = [dict(policy["rules"][0], resource_patterns=["*"])]
    policy["default_decision"] = "allowed"
    action_request["action"]["resource"]["identifier"] = identifier
    result = api.evaluate(policy, action_request)
    assert result.decision == "unknown"
    assert "unsupported_resource_identifier" in result.reason_codes


def test_agent_scope_and_manifest_identity(policy, action_request, capabilities):
    policy["agent_ids"] = ["unrelated-agent"]
    assert api.evaluate(policy, action_request).decision == "unknown"
    capabilities["agent_id"] = "unrelated-agent"
    with pytest.raises(api.ContractValidationError, match="agent_mismatch"):
        api.evaluate(policy, action_request, capabilities)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("empty", "no_declared_capability_match"),
        ("inferred", "inferred_capability_only"),
        ("constraints", "uninterpreted_capability_constraints"),
        ("pattern", "unsupported_capability_pattern"),
    ],
)
def test_visibility_gaps_stay_unknown(policy, action_request, capabilities, change, reason):
    if change == "empty":
        capabilities["capabilities"] = []
    elif change == "inferred":
        capabilities["capabilities"][0]["basis"] = "inferred"
    elif change == "constraints":
        capabilities["capabilities"][0]["constraints"] = ["SYNTHETIC_PRIVATE free text"]
    else:
        capabilities["capabilities"][0]["resource_patterns"] = ["fixture://protected-workspace/**"]
    result = api.evaluate(policy, action_request, capabilities)
    assert result.policy_decision == "allowed"
    assert result.decision == "unknown"
    assert reason in result.reason_codes
    assert "SYNTHETIC_PRIVATE" not in json.dumps(result.to_dict())


def test_manifest_approval_cannot_be_bypassed(policy, action_request, capabilities):
    capabilities["capabilities"][0]["approval_required"] = True
    result = api.evaluate(policy, action_request, capabilities)
    assert result.policy_decision == "allowed"
    assert result.decision == "requires_approval"
    assert "declared_approval_required" in result.reason_codes


def test_explicit_denial_survives_missing_capability_coverage(policy, capabilities, example):
    capabilities["capabilities"] = []
    assert api.evaluate(policy, example("action-denied"), capabilities).decision == "denied"


def test_outputs_omit_untrusted_free_text_and_identifiers(policy, action_request, capabilities):
    capabilities["coverage"]["scope"] = "SYNTHETIC_PRIVATE_SCOPE"
    capabilities["unknowns"] = ["SYNTHETIC_PRIVATE_UNKNOWN"]
    capabilities["identity_refs"] = ["SYNTHETIC_PRIVATE_CREDENTIAL_REFERENCE"]
    action_request["action"]["resource"]["identifier"] = (
        "fixture://protected-workspace/PRIVATE_RESOURCE"
    )
    result = api.evaluate(policy, action_request, capabilities)
    summary = api.inspect_manifest(capabilities)
    public = json.dumps([result.to_dict(), summary])
    assert "SYNTHETIC_PRIVATE" not in public
    assert "PRIVATE_RESOURCE" not in public
    assert result.unknown_count == 1
    assert summary["coverage"]["completeness"] == "not_asserted"


def test_findings_are_bounded_and_preserve_basis(capabilities):
    capabilities["capabilities"][1]["basis"] = "inferred"
    capabilities["capabilities"][1]["resource_patterns"] = ["*"]
    summary = api.inspect_manifest(capabilities)
    assert {finding["finding_id"] for finding in summary["findings"]} == {
        "filesystem-and-network",
        "process-and-network",
        "all-resource-pattern",
    }
    filesystem = summary["findings"][0]
    assert "No chain, write access" in filesystem["limitation"]
    assert {item["capability_id"]: item["basis"] for item in filesystem["capabilities"]}[
        "fake-api"
    ] == "inferred"


def test_no_findings_does_not_assert_safety(capabilities):
    capabilities["capabilities"] = capabilities["capabilities"][:1]
    summary = api.inspect_manifest(capabilities)
    assert summary["findings"] == []
    assert summary["coverage"]["completeness"] == "not_asserted"


def test_inputs_unchanged_and_network_unused(policy, action_request, capabilities, monkeypatch):
    before = copy.deepcopy([policy, action_request, capabilities])

    def forbidden(*args, **kwargs):
        pytest.fail("Simulator attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    api.evaluate(policy, action_request, capabilities)
    api.inspect_manifest(capabilities)
    api.export_scenario(policy, action_request, capabilities)
    assert before == [policy, action_request, capabilities]
