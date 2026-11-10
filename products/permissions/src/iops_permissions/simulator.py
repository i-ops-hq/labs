"""Deterministic declared-policy analysis. Never launches or authorizes real execution."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

from .inputs import input_error, validate_input
from .matching import identifier_supported, matches, pattern_supported
from .validation import validate_document

Decision = Literal["allowed", "denied", "requires_approval", "unknown"]
PRECEDENCE = {"allowed": 0, "unknown": 1, "requires_approval": 2, "denied": 3}
EXPLANATIONS = {
    "policy_agent_out_of_scope": "This policy does not declare coverage of the requested agent.",
    "unsupported_resource_identifier": (
        "The resource identifier has an ambiguous or unsupported lexical form."
    ),
    "explicit_policy_default": "No rule matched; the explicit default decision was used.",
    "matching_rules": "The listed policy rules match the structured action selectors.",
    "deny_approval_unknown_allow_precedence": (
        "Matching decisions are combined in deny, approval, unknown, then allow order."
    ),
    "unsupported_capability_pattern": (
        "Relevant capability declarations contain patterns this simulator cannot interpret."
    ),
    "no_declared_capability_match": "No supported capability declaration matches the action scope.",
    "inferred_capability_only": "Only inferred declarations match; declared authority is unknown.",
    "uninterpreted_capability_constraints": (
        "Matching declarations contain constraint text that is not executable policy."
    ),
    "declared_approval_required": "A matching capability declaration explicitly requires approval.",
    "no_manifest_policy_only": "No manifest was supplied; this decision evaluates policy only.",
}
# Keys a reader needs in order to act on a decision. Declared once here, and the CLI's
# text rendering is generated FROM this tuple, so a key cannot join the report and skip the
# only format a person reads. reason_codes is deliberately absent: it is machine-facing and
# `explanations` already carries the same content as prose.
DECISION_RELEVANT = (
    "decision",
    "policy_decision",
    "matched_rule_ids",
    "capabilities",
    "scope",
)
LIMITATIONS = (
    "Declared policy simulation only; no action was executed or enforced.",
    "Configuration and tool declarations do not establish complete effective permissions.",
    "Lexical selectors do not resolve symlinks, identity authority or indirect effects.",
)


@dataclass(frozen=True)
class CapabilityEvidence:
    capability_id: str
    basis: str


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    policy_decision: Decision
    policy_id: str
    request_id: str
    agent_id: str
    matched_rule_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    capabilities: tuple[CapabilityEvidence, ...]
    scope: str
    unknown_count: int
    limitations: tuple[str, ...] = LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report["explanations"] = [EXPLANATIONS[code] for code in self.reason_codes]
        return report


def _selected(selector: list[str], value: str) -> bool:
    return "*" in selector or value in selector


def _policy_decision(
    policy: dict[str, Any], request: dict[str, Any]
) -> tuple[Decision, tuple[str, ...], list[str]]:
    if not _selected(policy["agent_ids"], request["agent_id"]):
        return "unknown", (), ["policy_agent_out_of_scope"]
    action = request["action"]
    if not identifier_supported(action["resource"]["identifier"]):
        return "unknown", (), ["unsupported_resource_identifier"]
    matched = [
        rule
        for rule in policy["rules"]
        if _selected(rule["action_kinds"], action["kind"])
        and _selected(rule["operations"], action["operation"])
        and _selected(rule["resource_types"], action["resource"]["type"])
        and any(
            matches(pattern, action["resource"]["identifier"])
            for pattern in rule["resource_patterns"]
        )
    ]
    if not matched:
        return cast(Decision, policy["default_decision"]), (), ["explicit_policy_default"]
    effect = max((rule["effect"] for rule in matched), key=lambda value: PRECEDENCE[value])
    return (
        cast(Decision, effect),
        tuple(sorted(rule["rule_id"] for rule in matched)),
        ["matching_rules", "deny_approval_unknown_allow_precedence"],
    )


def evaluate(
    policy: dict[str, Any], request: dict[str, Any], manifest: dict[str, Any] | None = None
) -> DecisionResult:
    """Return a scoped declared decision after validating every supplied input."""
    validate_input("policy", policy)
    validate_input("action-request", request)
    if manifest is not None:
        validate_document("capability-manifest", manifest)
        if manifest["agent_id"] != request["agent_id"]:
            input_error("agent_mismatch")
    policy_decision, matched_rules, reasons = _policy_decision(policy, request)
    decision = policy_decision
    capabilities: list[dict[str, Any]] = []
    if manifest is not None:
        action = request["action"]
        relevant = [
            cap for cap in manifest["capabilities"] if action["kind"] in cap["action_kinds"]
        ]
        unsupported = any(
            not pattern_supported(pattern)
            for cap in relevant
            for pattern in cap["resource_patterns"]
        )
        capabilities = [
            cap
            for cap in relevant
            if any(
                matches(pattern, action["resource"]["identifier"])
                for pattern in cap["resource_patterns"]
            )
        ]
        if decision not in ("denied", "unknown"):
            guards = []
            if unsupported:
                guards.append("unsupported_capability_pattern")
            if not capabilities:
                guards.append("no_declared_capability_match")
            elif all(cap["basis"] == "inferred" for cap in capabilities):
                guards.append("inferred_capability_only")
            if any(cap.get("constraints") for cap in capabilities):
                guards.append("uninterpreted_capability_constraints")
            if guards:
                decision = "unknown"
                reasons.extend(guards)
            elif decision == "allowed" and any(
                cap.get("approval_required") for cap in capabilities
            ):
                decision = "requires_approval"
                reasons.append("declared_approval_required")
    else:
        reasons.append("no_manifest_policy_only")
    return DecisionResult(
        decision,
        policy_decision,
        policy["policy_id"],
        request["request_id"],
        request["agent_id"],
        matched_rules,
        tuple(reasons),
        tuple(
            CapabilityEvidence(cap["capability_id"], cap["basis"])
            for cap in sorted(capabilities, key=lambda cap: cap["capability_id"])
        ),
        "declared_policy_and_manifest" if manifest is not None else "declared_policy_only",
        len(manifest["unknowns"]) if manifest is not None else 1,
    )


def covers(broad: str, narrow: str) -> bool:
    """Does every identifier the narrow pattern admits also satisfy the broad one?

    Decided by matching.matches and nothing else. A second pattern engine would eventually
    disagree with what evaluate() decides, and a finding that contradicts the decision is
    worse than no finding. The supported vocabulary is "*", a literal, or a literal
    followed by "*", so the question reduces to a matcher call against the narrow
    pattern's own literal part: anything the narrow pattern admits starts with that
    literal. The "*" cases are named here rather than passed through the matcher, because
    identifier_supported refuses any identifier containing "*".

    Using the one matcher is necessary and not sufficient - it also has to be asked the
    right question. A wildcard narrow admits an unbounded set, so only another wildcard can
    contain it: an exact pattern admits exactly one identifier. Without that condition
    covers("fixture://process/one", "fixture://process/one*") answered True, because the
    broad literal does match the narrow pattern's prefix string, and inspect then reported
    an exact declaration as covering a wildcard one that evaluate() matches more widely.
    """
    if not pattern_supported(broad) or not pattern_supported(narrow):
        return False
    if broad == "*":
        return True
    if narrow == "*":
        return False
    if narrow.endswith("*"):
        return broad.endswith("*") and matches(broad, narrow[:-1])
    return matches(broad, narrow)


def _subsumes(broad: dict[str, Any], narrow: dict[str, Any]) -> bool:
    """Whether the broad declaration grants everything the narrow one declares.

    Action kinds are a containment test rather than an intersection: a declaration that
    covers the narrow one's patterns but not all of its kinds leaves authority the narrow
    one still has. That is also why a filesystem pattern never swallows a process pattern
    even when the two strings are identical.
    """
    if not set(narrow["action_kinds"]).issubset(broad["action_kinds"]):
        return False
    return all(
        any(covers(wide, tight) for wide in broad["resource_patterns"])
        for tight in narrow["resource_patterns"]
    )


def inspect_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Summarize declarations without printing free text or sensitive resource patterns."""
    validate_document("capability-manifest", manifest)
    capabilities = manifest["capabilities"]
    findings = []
    network = [cap for cap in capabilities if set(cap["action_kinds"]) & {"network", "api"}]
    for kind in ("filesystem", "process"):
        local = [cap for cap in capabilities if kind in cap["action_kinds"]]
        if local and network:
            contributing = {cap["capability_id"]: cap for cap in (*local, *network)}
            findings.append(
                {
                    "finding_id": kind + "-and-network",
                    "severity": "review",
                    "description": f"Declared {kind} and network/API capabilities coexist.",
                    "capabilities": [
                        {"capability_id": cap_id, "basis": contributing[cap_id]["basis"]}
                        for cap_id in sorted(contributing)
                    ],
                    "limitation": (
                        "No chain, write access, transfer or side effect has been demonstrated."
                    ),
                }
            )
    by_id = {cap["capability_id"]: cap for cap in capabilities}
    for wide in sorted(capabilities, key=lambda cap: cap["capability_id"]):
        # Strict coverage only. Two declarations that cover each other are duplicates of one
        # another, which is a different observation from one swallowing another, and
        # reporting it here would make a single finding mean two things.
        covered = sorted(
            tight["capability_id"]
            for tight in capabilities
            if tight["capability_id"] != wide["capability_id"]
            and _subsumes(wide, tight)
            and not _subsumes(tight, wide)
        )
        if not covered:
            continue
        named = sorted({wide["capability_id"], *covered})
        findings.append(
            {
                "finding_id": "capability-subsumes-capability",
                "severity": "review",
                "description": (
                    "One declaration's resource patterns cover another declaration's, "
                    "within the same declared action kinds."
                ),
                "capabilities": [
                    {"capability_id": cap_id, "basis": by_id[cap_id]["basis"]} for cap_id in named
                ],
                "covering_capability_id": wide["capability_id"],
                "covered_capability_ids": covered,
                "limitation": (
                    "Lexical coverage is not effective authority; a declaration is not a "
                    "permission, and no narrowing by configuration or host policy is modelled."
                ),
            }
        )
    broad = sorted(
        (cap for cap in capabilities if "*" in cap["resource_patterns"]),
        key=lambda cap: cap["capability_id"],
    )
    if broad:
        findings.append(
            {
                "finding_id": "all-resource-pattern",
                "severity": "review",
                "description": (
                    "At least one declaration contains the literal all-resources pattern."
                ),
                "capabilities": [
                    {"capability_id": cap["capability_id"], "basis": cap["basis"]} for cap in broad
                ],
                "limitation": "A broad declaration does not establish effective authority.",
            }
        )
    return {
        "manifest_id": manifest["manifest_id"],
        "agent_id": manifest["agent_id"],
        "capability_count": len(capabilities),
        "basis_counts": dict(Counter(cap["basis"] for cap in capabilities)),
        "coverage": {
            "observability": manifest["coverage"]["observability"],
            "unknown_count": len(manifest["unknowns"]),
            "limitation_count": len(manifest["coverage"]["limitations"]),
            "completeness": "not_asserted",
        },
        "findings": findings,
        "limitations": list(LIMITATIONS),
    }
