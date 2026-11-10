"""Breadth that means breadth, and a decision whose text form carries the whole finding.

Two measured defects. The policy saying nothing about an action AND the agent declaring a
capability that covers it is the pair a reviewer wants, and only one half reached the
format a person reads. Separately, the one breadth rule tested for a pattern that is
literally "*", so every realistically broad declaration was invisible.
"""

import copy
import json

import pytest
from iops_permissions import cli, simulator
from iops_permissions.matching import matches
from iops_permissions.simulator import covers, evaluate, inspect_manifest

from .conftest import EXAMPLES

BROAD = "run-arbitrary-shell"


def load(name):
    return json.loads((EXAMPLES / ("declared-breadth-" + name + ".json")).read_text())


@pytest.fixture
def breadth_manifest():
    return load("manifest")


@pytest.fixture
def breadth_policy():
    return load("policy")


@pytest.fixture
def breadth_action():
    return load("action")


def subsumption(report):
    return [f for f in report["findings"] if f["finding_id"] == "capability-subsumes-capability"]


def capability(identifier, kinds, patterns, basis="declared"):
    return {
        "capability_id": identifier,
        "action_kinds": kinds,
        "resource_patterns": patterns,
        "basis": basis,
        "approval_required": False,
    }


def manifest_of(*capabilities):
    return {
        "schema_version": "0.1.0",
        "manifest_id": "synthetic-breadth",
        "agent_id": "shell-capable-fixture",
        "captured_at": "2026-11-09T00:00:00Z",
        "source_adapter": {"adapter_id": "hand-written-from-docs", "version": "0.0.0"},
        "capabilities": list(capabilities),
        "unknowns": ["Nothing here is observed."],
        "coverage": {
            "observability": "declared_only",
            "scope": "Synthetic declarations for a shape test.",
            "limitations": ["Nothing was inspected."],
        },
    }


# --- 1. the measured manifest produces the finding ---------------------------------


def test_a_broad_declaration_is_reported_as_covering_the_narrow_ones(breadth_manifest):
    """Counterfactual: drop run-arbitrary-shell from the manifest and the finding goes with
    it, which is the second half of this test rather than a separate one.
    """
    found = subsumption(inspect_manifest(breadth_manifest))
    assert len(found) == 1
    assert found[0]["covering_capability_id"] == BROAD
    assert found[0]["covered_capability_ids"] == ["git-commit", "run-test-command"]
    assert found[0]["severity"] == "review"
    assert [item["capability_id"] for item in found[0]["capabilities"]] == [
        "git-commit",
        BROAD,
        "run-test-command",
    ]

    narrowed = copy.deepcopy(breadth_manifest)
    narrowed["capabilities"] = [
        cap for cap in narrowed["capabilities"] if cap["capability_id"] != BROAD
    ]
    assert subsumption(inspect_manifest(narrowed)) == []


def test_the_literal_all_resources_rule_is_untouched(breadth_manifest):
    """The measured manifest has no pattern that is exactly "*", so the shipped rule stays
    silent on it, and the new rule is what speaks. Both still fire where they should.
    """
    report = inspect_manifest(breadth_manifest)
    assert [f["finding_id"] for f in report["findings"]] == ["capability-subsumes-capability"]

    everything = manifest_of(capability("anything", ["process"], ["*"]))
    assert [f["finding_id"] for f in inspect_manifest(everything)["findings"]] == [
        "all-resource-pattern"
    ]


# --- 2. overlap is not subsumption -------------------------------------------------


def test_two_declarations_that_overlap_without_covering_produce_no_finding():
    """The guard against a rule that fires on any intersection. "a-*" and the pair
    {a-one, b-two} both admit a-one and neither admits everything the other does.

    Counterfactual: relax _subsumes from all() to any() over the narrow patterns and this
    goes red. The asymmetry is deliberate and was found by running that counterfactual: an
    earlier version of this test used two capabilities sharing one exact pattern, where
    any() makes each cover the other, and the strict-coverage check then suppressed the
    finding anyway. The test passed under the mutation it existed to catch.
    """
    overlapping = manifest_of(
        capability("broad-prefix", ["process"], ["fixture://process/a-*"]),
        capability(
            "two-exact", ["process"], ["fixture://process/a-one", "fixture://process/b-two"]
        ),
    )
    assert subsumption(inspect_manifest(overlapping)) == []


def test_an_exact_declaration_is_never_reported_as_covering_a_wildcard_one():
    """The finding this rule must never produce. two-exact admits exactly two identifiers;
    one-wildcard admits every identifier starting with fixture://process/one, including
    fixture://process/onething, which two-exact does not. inspect reported two-exact as
    covering one-wildcard until 2026-11-09 - a finding contradicting what evaluate decides
    on that identifier, which is the exact failure the one-matcher rule exists to prevent.

    Counterfactual: drop the wildcard condition from covers() and this goes red.
    """
    crossed = manifest_of(
        capability("two-exact", ["process"], ["fixture://process/one", "fixture://process/two"]),
        capability("one-wildcard", ["process"], ["fixture://process/one*"]),
    )
    assert subsumption(inspect_manifest(crossed)) == []
    # And the honest direction still reports, so the rule has not simply gone quiet.
    honest = manifest_of(
        capability("all-process", ["process"], ["fixture://process/*"]),
        capability("one-wildcard", ["process"], ["fixture://process/one*"]),
    )
    found = subsumption(inspect_manifest(honest))
    assert len(found) == 1 and found[0]["covering_capability_id"] == "all-process"


def test_mutual_coverage_is_a_duplicate_rather_than_a_swallowing():
    """Two declarations covering each other are duplicates of one another. Reporting that
    here would make one finding mean two things, so the rule is strict coverage.
    """
    twins = manifest_of(
        capability("first", ["process"], ["fixture://process/*"]),
        capability("second", ["process"], ["fixture://process/*"], basis="configured"),
    )
    assert subsumption(inspect_manifest(twins)) == []


# --- 3. action kinds are a containment test ---------------------------------------


def test_a_filesystem_pattern_never_swallows_an_identical_process_pattern():
    """Counterfactual: delete the action-kinds check and this goes red - identical strings
    under different kinds would then be reported as coverage. Note it is NOT sensitive to
    swapping issubset for an intersection, because these two kinds are disjoint and both
    rules refuse; the test below is the one that catches that mutation.
    """
    crossed = manifest_of(
        capability("files", ["filesystem"], ["fixture://thing/*"]),
        capability("processes", ["process"], ["fixture://thing/one"]),
    )
    assert subsumption(inspect_manifest(crossed)) == []

    same_kind = manifest_of(
        capability("files", ["filesystem"], ["fixture://thing/*"]),
        capability("one-file", ["filesystem"], ["fixture://thing/one"]),
    )
    found = subsumption(inspect_manifest(same_kind))
    assert len(found) == 1 and found[0]["covering_capability_id"] == "files"


def test_a_declaration_is_not_covered_unless_all_of_its_kinds_are():
    broad_one_kind = manifest_of(
        capability("process-only", ["process"], ["fixture://thing/*"]),
        capability("two-kinds", ["process", "network"], ["fixture://thing/one"]),
    )
    assert subsumption(inspect_manifest(broad_one_kind)) == []


# --- the one matcher, one semantics property ---------------------------------------


@pytest.mark.parametrize(
    ("broad", "narrow", "expected"),
    [
        ("*", "fixture://process/one", True),
        ("*", "*", True),
        ("fixture://process/one", "*", False),
        ("fixture://process/*", "*", False),
        ("fixture://process/*", "fixture://process/one", True),
        ("fixture://process/*", "fixture://process/sub/one", True),
        ("fixture://process/*", "fixture://process/g*", True),
        ("fixture://process/g*", "fixture://process/*", False),
        ("fixture://process/one", "fixture://process/one", True),
        ("fixture://process/one", "fixture://process/two", False),
        ("fixture://process/one", "fixture://process/*", False),
        ("fixture://repo/*", "fixture://process/one", False),
        ("fixture://process/*", "not a supported identifier", False),
        ("*ambiguous*", "fixture://process/one", False),
        # These five are what reusing the matcher buys, and nothing else in this table
        # distinguishes it from a hand-rolled prefix test. Every one of them is accepted
        # by `narrow.startswith(broad[:-1])` and refused by matching.py's lexical
        # vocabulary, so a second engine would report coverage over a traversal, a
        # backslash, a query character, an empty path component or a mid-pattern wildcard.
        ("fixture://process/*", "fixture://process/../escape", False),
        ("fixture://process/*", "fixture://process/a\\b", False),
        ("fixture://process/*", "fixture://process/with?query", False),
        ("fixture://process/*", "fixture://process//double", False),
        ("fixture://*/one*", "fixture://*/one-thing", False),
        # An exact pattern admits one identifier and a wildcard admits unboundedly many,
        # so this direction can never be coverage. It answered True until 2026-11-09,
        # because the broad literal does match the narrow pattern's prefix string.
        ("fixture://process/one", "fixture://process/one*", False),
        ("fixture://process/one", "fixture://process/one-two*", False),
    ],
)
def test_coverage_is_decided_by_the_one_matcher(broad, narrow, expected):
    """Counterfactual: replace covers()'s body with a prefix engine that does not consult
    matching.py at all - guards included - and the five unsupported-pattern rows go red.

    Swapping ONLY the matches() call leaves those five green, and an earlier version of
    this docstring claimed otherwise. pattern_supported refuses all five before the matcher
    is reached, so the engine is never consulted for them. That is not a weakness of the
    rows: the guards are part of the matcher's semantics rather than scaffolding around it,
    and inheriting its refusals is most of what reusing it buys. The rows that exercise the
    matcher call itself are the wildcard-against-wildcard ones, and the last two are here
    because reusing the matcher is necessary without being sufficient - it also has to be
    asked the right question.
    """
    assert covers(broad, narrow) is expected


PATTERN_UNIVERSE = (
    "*",
    "fixture://process/*",
    "fixture://process/one",
    "fixture://process/one*",
    "fixture://process/one-two",
    "fixture://process/one-two*",
    "fixture://process/two",
    "fixture://process/sub/*",
    "fixture://process/sub/deep",
    "fixture://repo/*",
    "fixture://repo/file.txt",
)
IDENTIFIER_UNIVERSE = (
    "fixture://process/one",
    "fixture://process/onething",
    "fixture://process/one-two",
    "fixture://process/one-two-three",
    "fixture://process/two",
    "fixture://process/sub/deep",
    "fixture://process/sub/deeper",
    "fixture://repo/file.txt",
    "fixture://repo/other.txt",
    "fixture://other/thing",
)


@pytest.mark.parametrize("broad", PATTERN_UNIVERSE)
def test_a_covering_pattern_admits_everything_the_covered_one_admits(broad):
    """The property that keeps a finding and a decision from ever disagreeing: wherever
    covers() reports coverage, every identifier evaluate() would match against the narrow
    pattern it also matches against the broad one.

    Every pair in the universe, not only pairs already known to cover, and that is the
    difference that matters. The earlier version asserted covers() first and then checked
    the implication, so it could only confirm pairs it already believed and never looked at
    ("fixture://process/one", "fixture://process/one*"), which was a false positive.
    Counterfactual: drop the wildcard condition from covers() and this goes red naming the
    pair and the identifier that breaks it - fixture://process/onething.
    """
    for narrow in PATTERN_UNIVERSE:
        if not covers(broad, narrow):
            continue
        for identifier in IDENTIFIER_UNIVERSE:
            if matches(narrow, identifier):
                assert matches(broad, identifier), (broad, narrow, identifier)


# --- 4 and 5. the text format carries the whole decision ---------------------------


def emit_text(report, capsys):
    cli._emit(report, "text")
    return capsys.readouterr().out


def tokens(value):
    """Every string a reader should be able to find, read off the report, not the renderer.

    Tuples as well as lists: asdict keeps the dataclass's tuples, which JSON serialises as
    arrays but which str() would render as "()".
    """
    if isinstance(value, (list, tuple)):
        return [token for item in value for token in tokens(item)]
    if isinstance(value, dict):
        return [str(item) for item in value.values()]
    return [str(value)]


def test_the_text_decision_names_the_capability_that_covers_the_action(
    breadth_policy, breadth_action, breadth_manifest, capsys
):
    """The measured defect: this pair is the finding, and run-arbitrary-shell appeared only
    in JSON. Counterfactual: delete the "capabilities" entry from cli.TEXT_RENDERERS and
    _emit raises instead of quietly dropping the line.
    """
    report = evaluate(breadth_policy, breadth_action, breadth_manifest).to_dict()
    text = emit_text(report, capsys)
    assert BROAD in text
    assert "Matching declared capabilities: " + BROAD + " (declared)" in text
    assert "Observation scope: declared_policy_and_manifest" in text
    assert "Decision: unknown" in text


@pytest.mark.parametrize("action", ["declared-breadth-action", "action-allowed"])
def test_every_decision_relevant_value_reaches_the_text_format(
    breadth_policy, breadth_manifest, example, action, capsys
):
    """Read off the report rather than off the renderer, so this is not circular."""
    request = json.loads((EXAMPLES / (action + ".json")).read_text())
    policy, manifest = breadth_policy, breadth_manifest
    if action == "action-allowed":
        policy = copy.deepcopy(policy)
        policy["agent_ids"] = [request["agent_id"]]
        manifest = copy.deepcopy(manifest)
        manifest["agent_id"] = request["agent_id"]
    report = evaluate(policy, request, manifest).to_dict()
    text = emit_text(report, capsys)
    for key in simulator.DECISION_RELEVANT:
        assert key in report, key
        for token in tokens(report[key]):
            assert token in text, (key, token)


def test_a_decision_relevant_key_cannot_be_added_without_a_rendering(
    breadth_policy, breadth_action, breadth_manifest, monkeypatch, capsys
):
    """THE test that stops defect 1 recurring, in two halves.

    The declared set and the renderers must agree, which is the static half. And because
    _emit walks the declared set rather than a hand-written list, a key with no renderer
    raises rather than printing nothing, which is the half that cannot be forgotten.
    Counterfactual: go back to a text branch that prints three keys by name and the first
    assertion has nothing to compare, while a new key silently never appears.
    """
    assert set(cli.TEXT_RENDERERS) == set(simulator.DECISION_RELEVANT)
    report = evaluate(breadth_policy, breadth_action, breadth_manifest).to_dict()
    assert emit_text(report, capsys)

    monkeypatch.setattr(cli, "DECISION_RELEVANT", (*simulator.DECISION_RELEVANT, "new_signal"))
    with pytest.raises(KeyError):
        cli._emit({**report, "new_signal": "SYNTHETIC_UNRENDERED"}, "text")


def test_reason_codes_stay_out_of_the_declared_set_deliberately():
    """Not every key belongs: reason_codes is machine-facing and explanations already
    carries the same content as prose, which the text form does print.
    """
    assert "reason_codes" not in simulator.DECISION_RELEVANT
    assert "explanations" not in simulator.DECISION_RELEVANT


# --- 6. a finding never leaks a pattern or free text ------------------------------


def test_inspect_output_names_identifiers_and_never_patterns(breadth_manifest, capsys):
    """The docstring promise is to summarize declarations without printing free text or
    sensitive resource patterns. Counterfactual: add the covering patterns to the finding
    and both the JSON and the text assertion go red.
    """
    report = inspect_manifest(breadth_manifest)
    rendered = json.dumps(report)
    cli._emit(report, "text")
    text = capsys.readouterr().out
    for cap in breadth_manifest["capabilities"]:
        for pattern in cap["resource_patterns"]:
            assert pattern not in rendered, pattern
            assert pattern not in text, pattern
        for constraint in cap["constraints"]:
            assert constraint not in rendered
            assert constraint not in text
    for unknown in breadth_manifest["unknowns"]:
        assert unknown not in rendered
    assert breadth_manifest["coverage"]["scope"] not in rendered
    # The identifiers are what a reader acts on, so those must be there.
    assert BROAD in rendered and BROAD in text


def test_a_broad_wildcard_pattern_is_never_echoed_even_when_it_is_the_finding():
    everything = manifest_of(capability("anything", ["process"], ["*"]))
    rendered = json.dumps(inspect_manifest(everything))
    assert '"*"' not in rendered
    assert "anything" in rendered
