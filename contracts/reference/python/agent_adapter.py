"""Experimental interface reference, deliberately not an installed shared engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, Protocol, TypeVar

Feature = Literal[
    "inspect",
    "launch",
    "observe",
    "pre_action_intercept",
    "fault_injection",
    "stop",
    "filesystem_effects",
    "network_effects",
    "trace_import",
]
Observability = Literal[
    "declared_only",
    "hook_visible",
    "tool_dispatch_instrumented",
    "process_boundary",
    "trace_import",
]
T = TypeVar("T")
Decision = Literal["allowed", "denied", "requires_approval", "unknown"]


@dataclass(frozen=True)
class Success(Generic[T]):
    value: T
    status: Literal["ok"] = field(default="ok", init=False)


@dataclass(frozen=True)
class Unsupported:
    operation: str
    reason_code: str
    status: Literal["unsupported"] = field(default="unsupported", init=False)


@dataclass(frozen=True)
class AdapterError:
    operation: str
    reason_code: str
    retryable: bool = False
    status: Literal["error"] = field(default="error", init=False)


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    version: str
    agent_types: tuple[str, ...]
    verified_features: frozenset[Feature]
    required_runtime: str
    observability: Observability
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Target:
    """Opaque, local fixture reference; never a command or a credential."""

    fixture_id: str


@dataclass(frozen=True)
class TestContext:
    run_id: str
    scenario_id: str
    fixture_id: str


class AgentAdapter(Protocol):
    def describe(self) -> AdapterDescriptor: ...

    def inspect(
        self, target: Target
    ) -> Success[dict[str, object]] | Unsupported | AdapterError: ...


class ManagedAdapter(AgentAdapter, Protocol):
    def prepare(self, context: TestContext) -> Success[None] | Unsupported | AdapterError: ...

    def start(self, context: TestContext) -> Success[str] | Unsupported | AdapterError: ...

    def observe(
        self, run_id: str
    ) -> Success[tuple[dict[str, object], ...]] | Unsupported | AdapterError: ...

    def stop(self, run_id: str) -> Success[None] | Unsupported | AdapterError: ...

    def cleanup(self, run_id: str) -> Success[None] | Unsupported | AdapterError: ...


class InterceptingAdapter(AgentAdapter, Protocol):
    def before_action(
        self, context: TestContext, event: dict[str, object]
    ) -> Success[Decision] | Unsupported | AdapterError: ...


def negotiate(
    descriptor: AdapterDescriptor, required: frozenset[Feature]
) -> Success[frozenset[Feature]] | Unsupported:
    """Preflight declared verified features; this does not prove enforcement."""
    if not required.issubset(descriptor.verified_features):
        return Unsupported("negotiate", "missing_verified_features")
    return Success(required)
