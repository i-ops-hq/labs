"""Closed declarative postconditions: the user authors the check, the host evaluates it.

No value here is ever executed, compiled or interpreted. A predicate is a four-field tuple
drawn from closed sets, and every operator is host Python over an already-validated
projection. The acting worker is the one component that must not be able to influence the
check, and an executed expression string would put an injection surface in exactly that
place.

Unobservable is never ``passed``. Every branch that cannot see what it was asked about
returns ``inconclusive``; a missing observation, an unreadable file, an absent baseline and
an untrustworthy event stream are all unobservable, not success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCES = ("file_observation", "run_state", "service_state", "event_count")
OPS = ("unchanged", "changed", "equals", "at_most", "at_least", "absent", "present")
VALUE_OPS = frozenset({"equals", "at_most", "at_least"})
ORDERED_OPS = frozenset({"equals", "at_most", "at_least"})
FILE_OPS = frozenset({"unchanged", "changed", "absent", "present"})

# Selector domains, each a closed set named here and nowhere else.
RUN_STATE_INTEGERS = ("exit_code", "captured_bytes")
RUN_STATE_BOOLEANS = ("timed_out", "output_limited", "invalid_output", "rejected_events")
SERVICE_INTEGERS = ("mutation_count", "service_call_count", "injected_fault_count")
SERVICE_STATES = (
    "valid",
    "invalid",
    "missing",
    "symlink",
    "not_regular",
    "oversized",
    "unreadable",
)
# Stages an adapter emits during the run. "verification" is appended by the host after
# assertions are decided, so it is not a countable stage here.
EVENT_STAGES = ("proposed", "attempted", "permission_decision", "completed")
FILE_STATES = ("regular", "missing", "symlink", "not_regular", "oversized", "unreadable")
MAX_PREDICATE_INTEGER = 2_147_483_647


@dataclass(frozen=True)
class Evidence:
    """Everything a predicate may read. Nothing here comes from the agent's own verdict."""

    observations: dict[str, dict[str, Any]] = field(default_factory=dict)
    baselines: dict[str, dict[str, Any]] = field(default_factory=dict)
    run_state: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    event_counts: dict[str, int] = field(default_factory=dict)
    events_trustworthy: bool = True


def evidence_ref(source: str) -> str:
    """The artifact a reader opens to check this predicate for themselves."""
    return {
        "file_observation": "state",
        "service_state": "state",
        "run_state": "execution",
        "event_count": "events",
    }[source]


def check(predicate: object, observation_ids: frozenset[str]) -> str | None:
    """Return a reason code if this predicate can never be evaluated, else None.

    Called before the run, from negotiate, so a type error is a refusal at validate time
    rather than something discovered halfway through a container.
    """
    if not isinstance(predicate, dict):
        return "predicate_not_supported"
    if set(predicate) - {"source", "selector", "op", "value"}:
        return "predicate_not_supported"
    if not {"source", "selector", "op"}.issubset(predicate):
        return "predicate_not_supported"
    source, selector, op = predicate["source"], predicate["selector"], predicate["op"]
    if source not in SOURCES:
        return "predicate_source_not_supported"
    if op not in OPS:
        return "predicate_op_not_supported"
    if ("value" in predicate) != (op in VALUE_OPS):
        return "predicate_value_arity_mismatch"
    value = predicate.get("value")
    if source == "file_observation":
        if selector not in observation_ids:
            return "predicate_selector_not_supported"
        return None if op in FILE_OPS else "predicate_type_mismatch"
    if source == "run_state":
        if selector in RUN_STATE_BOOLEANS:
            if op != "equals":
                return "predicate_type_mismatch"
            return None if type(value) is bool else "predicate_type_mismatch"
        if selector in RUN_STATE_INTEGERS:
            return _integer_value(op, value)
        return "predicate_selector_not_supported"
    if source == "service_state":
        if selector == "service_state":
            if op != "equals":
                return "predicate_type_mismatch"
            if type(value) is not str:
                return "predicate_type_mismatch"
            return None if value in SERVICE_STATES else "predicate_value_not_supported"
        if selector in SERVICE_INTEGERS:
            return _integer_value(op, value)
        return "predicate_selector_not_supported"
    if selector not in EVENT_STAGES:
        return "predicate_selector_not_supported"
    return _integer_value(op, value, minimum=0)


def _integer_value(op: str, value: object, *, minimum: int = -MAX_PREDICATE_INTEGER) -> str | None:
    if op not in ORDERED_OPS:
        return "predicate_type_mismatch"
    # bool is a subclass of int; an identity check keeps True out of an integer comparison.
    if type(value) is not int:
        return "predicate_type_mismatch"
    if not minimum <= value <= MAX_PREDICATE_INTEGER:
        return "predicate_value_not_supported"
    return None


def _ordered(op: str, observed: int, expected: int) -> bool:
    if op == "equals":
        return observed == expected
    if op == "at_most":
        return observed <= expected
    return observed >= expected


def compare_readings(baseline: dict[str, Any], final: dict[str, Any]) -> bool | None:
    """True/False when the two readings can be compared, None when they cannot.

    A differing state is a definite change: a regular file replaced by a symlink is not an
    unobserved file, it is a file that is gone. Two identical readings only prove the
    content is unchanged where the content was actually read, which is the regular case;
    two oversized or two symlink readings carry no content either time.
    """
    before, after = baseline.get("state"), final.get("state")
    if before not in FILE_STATES or after not in FILE_STATES:
        return None
    if "unreadable" in (before, after):
        return None
    if before != after:
        return True
    if after == "regular":
        return baseline.get("sha256") != final.get("sha256")
    if after == "missing":
        return False
    return None


def _file_observation(predicate: dict[str, Any], evidence: Evidence) -> tuple[str, Any]:
    op, selector = predicate["op"], predicate["selector"]
    final = evidence.observations.get(selector)
    if not isinstance(final, dict) or final.get("state") not in FILE_STATES:
        # The guest never reported this path. That is not a passed postcondition.
        return "inconclusive", None
    state = final["state"]
    observed = (
        {"sha256": final["sha256"]}
        if state == "regular" and type(final.get("sha256")) is str
        else {"state": state}
    )
    if op in ("absent", "present"):
        if state == "regular":
            return ("failed" if op == "absent" else "passed"), {"state": state}
        if state == "missing":
            return ("passed" if op == "absent" else "failed"), {"state": state}
        return "inconclusive", {"state": state}
    baseline = evidence.baselines.get(selector)
    if not isinstance(baseline, dict):
        # No baseline was captured, so "unchanged" has nothing to be unchanged from.
        return "inconclusive", observed
    changed = compare_readings(baseline, final)
    if changed is None:
        return "inconclusive", observed
    return ("passed" if (op == "changed") == changed else "failed"), observed


def evaluate(predicate: dict[str, Any], evidence: Evidence) -> tuple[str, Any]:
    """Evaluate one checked predicate against measured evidence.

    Returns the outcome and the single bounded observed value a reader needs to falsify it,
    or None where there is no value this code stands behind.
    """
    source, selector, op = predicate["source"], predicate["selector"], predicate["op"]
    if source == "file_observation":
        return _file_observation(predicate, evidence)
    if source == "run_state":
        value = evidence.run_state.get(selector)
        if selector in RUN_STATE_BOOLEANS:
            if type(value) is not bool:
                return "inconclusive", None
            return ("passed" if value == predicate["value"] else "failed"), {"boolean": value}
        if type(value) is not int:
            return "inconclusive", None
        return ("passed" if _ordered(op, value, predicate["value"]) else "failed"), {
            "integer": value
        }
    if source == "service_state":
        reported = evidence.state.get("service_state")
        if selector == "service_state":
            if type(reported) is not str:
                return "inconclusive", None
            return ("passed" if reported == predicate["value"] else "failed"), {"state": reported}
        value = evidence.state.get(selector)
        if type(value) is not int:
            # Counts are null unless the synthetic journal validated; say which state,
            # because the reason the count is missing is itself the observation.
            explanation = {"state": reported} if reported in SERVICE_STATES else None
            return "inconclusive", explanation
        return ("passed" if _ordered(op, value, predicate["value"]) else "failed"), {
            "integer": value
        }
    if not evidence.events_trustworthy:
        # Rejected or malformed guest output means the event list is incomplete, and a
        # count over an incomplete list is not an observation of that count.
        return "inconclusive", None
    count = evidence.event_counts.get(selector, 0)
    return ("passed" if _ordered(op, count, predicate["value"]) else "failed"), {"integer": count}
