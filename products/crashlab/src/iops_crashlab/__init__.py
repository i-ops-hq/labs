"""Controlled local reference execution with explicit evidence and limits."""

from ._version import VERSION as __version__
from .agents import AgentBundle, load_agent
from .docker import prepare_agent_image, prepare_reference_image
from .runner import run_scenario
from .validation import (
    SCHEMA_VERSION,
    SCHEMA_VERSIONS,
    ContractValidationError,
    ValidationIssue,
    loads_document,
    validate_document,
)

__all__ = [
    "__version__",
    "SCHEMA_VERSION",
    "SCHEMA_VERSIONS",
    "ContractValidationError",
    "ValidationIssue",
    "loads_document",
    "validate_document",
    "prepare_reference_image",
    "run_scenario",
    "AgentBundle",
    "load_agent",
    "prepare_agent_image",
]
