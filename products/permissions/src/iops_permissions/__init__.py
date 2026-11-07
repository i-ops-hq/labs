"""Local declared-policy simulation; no execution or enforcement integration."""

from .export import ExportResult, export_scenario
from .inputs import loads_action_request, loads_fixture_descriptor, loads_policy
from .simulator import DecisionResult, evaluate, inspect_manifest
from .validation import (
    SCHEMA_VERSION,
    ContractValidationError,
    ValidationIssue,
    loads_document,
    validate_document,
)

__version__ = "0.1.0a2"
__all__ = [
    "SCHEMA_VERSION",
    "ContractValidationError",
    "ValidationIssue",
    "loads_document",
    "validate_document",
    "DecisionResult",
    "ExportResult",
    "evaluate",
    "export_scenario",
    "inspect_manifest",
    "loads_action_request",
    "loads_fixture_descriptor",
    "loads_policy",
]
