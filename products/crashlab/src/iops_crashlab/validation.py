"""Bounded, offline validation only. No policy evaluation or execution."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from importlib.resources import files
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry
from referencing.exceptions import NoSuchResource

SCHEMA_VERSION = "0.1.0"
CONTRACTS = ("action-event", "capability-manifest", "scenario-definition", "evidence-result")
MAX_DOCUMENT_BYTES = 1_048_576
MAX_DEPTH = 64
MAX_NODES = 100_000
MAX_ISSUES = 32


@dataclass(frozen=True)
class ValidationIssue:
    """Messages and paths never contain submitted values or unknown property names."""

    code: str
    path: str
    message: str


class ContractValidationError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("Contract rejected: " + ", ".join(issue.code for issue in issues))


def _issue(code: str, path: str = "$") -> ValidationIssue:
    messages = {
        "unknown_contract": "The requested contract is not supported.",
        "unsupported_version": "The schema version is not supported.",
        "invalid_json": "A bounded, finite JSON object is required.",
        "input_limit": "The document exceeds validation limits.",
        "schema_violation": "A field does not meet the contract.",
        "duplicate_id": "Contract identifiers must be unique in their collection.",
        "invalid_reference": "An assertion references an undeclared artifact.",
        "verdict_mismatch": "The verdict is inconsistent with assertion outcomes.",
        "timestamp_order": "The finish time precedes the start time.",
        "unsupported_timestamp": "The timestamp cannot be compared by this implementation.",
    }
    return ValidationIssue(code, path, messages[code])


def _reject(code: str) -> NoReturn:
    raise ContractValidationError((_issue(code),)) from None


def _check_tree(payload: object) -> None:
    """Reject cycles, non-JSON Python objects, nonfinite numbers and excessive input."""
    pending = [(payload, 0)]
    seen: set[int] = set()
    nodes = 0
    string_bytes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            _reject("input_limit")
        if type(value) is str:
            if len(value) > MAX_DOCUMENT_BYTES:
                _reject("input_limit")
            try:
                string_bytes += len(value.encode("utf-8"))
            except UnicodeEncodeError:
                _reject("invalid_json")
            if string_bytes > MAX_DOCUMENT_BYTES:
                _reject("input_limit")
        elif type(value) is float:
            if not math.isfinite(value):
                _reject("invalid_json")
        elif value is None or type(value) in (bool, int):
            continue
        elif isinstance(value, (list, dict)) and type(value) in (list, dict):
            if id(value) in seen:
                _reject("invalid_json")
            seen.add(id(value))
            if len(value) + nodes + len(pending) > MAX_NODES:
                _reject("input_limit")
            if isinstance(value, dict):
                for key, child in value.items():
                    if type(key) is not str:
                        _reject("invalid_json")
                    pending.extend(((key, depth + 1), (child, depth + 1)))
            else:
                pending.extend((child, depth + 1) for child in value)
        else:
            _reject("invalid_json")


def _deny_retrieval(uri: str) -> Any:
    raise NoSuchResource(uri)


def _property_names(value: object) -> set[str]:
    if isinstance(value, dict):
        names = set(value.get("properties", {}))
        for child in value.values():
            names.update(_property_names(child))
        return names
    if isinstance(value, list):
        return set().union(*(_property_names(child) for child in value))
    return set()


@lru_cache(maxsize=4)
def _validator(contract: str) -> tuple[Draft202012Validator, set[str]]:
    schema = json.loads(
        files(__package__).joinpath("_schemas", "v0.1", contract + ".schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    return (
        Draft202012Validator(
            # referencing's attrs-generated keyword is valid at runtime but its
            # typing metadata currently exposes the backing field as _retrieve.
            schema,
            format_checker=FormatChecker(),
            registry=Registry(retrieve=_deny_retrieval),  # type: ignore[call-arg]
        ),
        _property_names(schema),
    )


def _safe_path(parts: Any, names: set[str]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += "." + (part if part in names else "<redacted>")
    return result


def _semantic_issues(contract: str, payload: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    collections = {
        "capability-manifest": (("capabilities", "capability_id"),),
        "scenario-definition": (("assertions", "assertion_id"),),
        "evidence-result": (("assertions", "assertion_id"), ("artifacts", "artifact_id")),
    }
    for collection, key in collections.get(contract, ()):
        ids = [entry[key] for entry in payload[collection]]
        if len(set(ids)) != len(ids):
            issues.append(_issue("duplicate_id", "$." + collection))
    if contract != "evidence-result":
        return issues
    try:
        start = datetime.fromisoformat(payload["started_at"].upper().replace("Z", "+00:00"))
        finish = datetime.fromisoformat(payload["finished_at"].upper().replace("Z", "+00:00"))
        if finish < start:
            issues.append(_issue("timestamp_order", "$.finished_at"))
    except (ValueError, TypeError):
        issues.append(_issue("unsupported_timestamp"))
    artifacts = {entry["artifact_id"] for entry in payload["artifacts"]}
    for index, assertion in enumerate(payload["assertions"]):
        if not set(assertion["evidence_refs"]).issubset(artifacts):
            issues.append(_issue("invalid_reference", f"$.assertions[{index}].evidence_refs"))
        if assertion["outcome"] == "passed" and not assertion["evidence_refs"]:
            issues.append(_issue("invalid_reference", f"$.assertions[{index}].evidence_refs"))
    outcomes = {entry["outcome"] for entry in payload["assertions"]}
    verdict = payload["verdict"]
    mismatch = (
        (verdict == "passed" and outcomes != {"passed"})
        or (verdict == "failed" and "failed" not in outcomes)
        or (verdict == "inconclusive" and bool(outcomes & {"failed", "error"}))
        or (verdict == "unsupported" and not outcomes.issubset({"unsupported", "skipped"}))
        or (verdict == "skipped" and not outcomes.issubset({"skipped"}))
        or ("error" in outcomes and verdict != "error")
    )
    if mismatch:
        issues.append(_issue("verdict_mismatch", "$.verdict"))
    return issues[:MAX_ISSUES]


def validate_document(contract: str, payload: object) -> None:
    """Validate one document or raise a redacted ContractValidationError.

    Does not authorize actions, open artifact locators, or verify evidence authenticity.
    """
    if contract not in CONTRACTS:
        _reject("unknown_contract")
    _check_tree(payload)
    if type(payload) is not dict:
        _reject("invalid_json")
    if "schema_version" in payload and payload["schema_version"] != SCHEMA_VERSION:
        _reject("unsupported_version")
    validator, names = _validator(contract)
    issues = []
    for error in validator.iter_errors(payload):
        issues.append(_issue("schema_violation", _safe_path(error.absolute_path, names)))
        if len(issues) >= MAX_ISSUES:
            break
    if not issues:
        issues = _semantic_issues(contract, payload)
    if issues:
        raise ContractValidationError(tuple(issues))


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject("invalid_json")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    _reject("invalid_json")


def loads_document(contract: str, data: str | bytes) -> dict[str, Any]:
    """Parse UTF-8 JSON with duplicate-key, size and structural checks."""
    if type(data) not in (str, bytes):
        _reject("invalid_json")
    if len(data) > MAX_DOCUMENT_BYTES:
        _reject("input_limit")
    try:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > MAX_DOCUMENT_BYTES:
            _reject("input_limit")
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
    except ContractValidationError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        # Do not expose JSONDecodeError excerpts, property names or submitted values.
        _reject("invalid_json")
    validate_document(contract, payload)
    return payload  # type: ignore[no-any-return]
