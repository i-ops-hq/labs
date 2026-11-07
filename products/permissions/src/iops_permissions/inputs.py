"""Private product input formats, separate from the shared Labs data contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from referencing import Registry

from .matching import identifier_supported, pattern_supported
from .validation import (
    MAX_ISSUES,
    ContractValidationError,
    ValidationIssue,
    _check_tree,
    _loads_object,
    _property_names,
    _safe_path,
)


def input_error(code: str, path: str = "$") -> NoReturn:
    messages = {
        "invalid_policy": "The policy does not meet the supported local format.",
        "invalid_action_request": "The action request does not meet the supported local format.",
        "invalid_fixture_descriptor": "The fixture does not meet the supported local format.",
        "duplicate_rule_id": "Policy rule identifiers must be unique.",
        "unsupported_policy_pattern": "A policy pattern uses unsupported matching syntax.",
        "agent_mismatch": "The manifest and request must describe the same agent.",
        "unsupported_version": "The schema version is not supported.",
    }
    raise ContractValidationError((ValidationIssue(code, path, messages[code]),)) from None


@lru_cache(maxsize=3)
def _input_validator(kind: str) -> tuple[Draft202012Validator, set[str]]:
    schema = json.loads(
        files(__package__)
        .joinpath("_schemas", "permissions-v0.1", kind + ".schema.json")
        .read_text()
    )
    Draft202012Validator.check_schema(schema)
    # An explicit empty registry refuses unknown references; all schemas are self-contained.
    return Draft202012Validator(schema, registry=Registry()), _property_names(schema)


def validate_input(kind: str, payload: object) -> None:
    codes = {
        "policy": "invalid_policy",
        "action-request": "invalid_action_request",
        "fixture-descriptor": "invalid_fixture_descriptor",
    }
    code = codes[kind]
    _check_tree(payload)
    if type(payload) is not dict:
        input_error(code)
    if "schema_version" in payload and payload["schema_version"] != "0.1.0":
        input_error("unsupported_version")
    validator, names = _input_validator(kind)
    issues = []
    for error in validator.iter_errors(payload):
        issues.append(
            ValidationIssue(
                code,
                _safe_path(error.absolute_path, names),
                "A field does not meet the supported local format.",
            )
        )
        if len(issues) >= MAX_ISSUES:
            break
    if issues:
        raise ContractValidationError(tuple(issues))
    if kind == "policy":
        ids = [rule["rule_id"] for rule in payload["rules"]]
        if len(set(ids)) != len(ids):
            input_error("duplicate_rule_id", "$.rules")
        if any(
            not pattern_supported(pattern)
            for rule in payload["rules"]
            for pattern in rule["resource_patterns"]
        ):
            input_error("unsupported_policy_pattern", "$.rules")
    elif kind == "fixture-descriptor":
        fixture_id = payload["fixture_id"]
        resource = payload["protected_resource"]
        if (
            not identifier_supported(fixture_id)
            or not identifier_supported(resource)
            or fixture_id.endswith("/")
            or not resource.startswith(fixture_id + "/")
        ):
            input_error(code)


def _load(kind: str, data: str | bytes) -> dict[str, Any]:
    document = _loads_object(data)
    validate_input(kind, document)
    return document


def loads_policy(data: str | bytes) -> dict[str, Any]:
    return _load("policy", data)


def loads_action_request(data: str | bytes) -> dict[str, Any]:
    return _load("action-request", data)


def loads_fixture_descriptor(data: str | bytes) -> dict[str, Any]:
    return _load("fixture-descriptor", data)
