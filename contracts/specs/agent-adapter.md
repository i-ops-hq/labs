# Agent Adapter — interface contract v0.1.0

Purpose: inspect or instrument an existing agent without a provider-specific
runtime assumption. The typed reference is `contracts/reference/python/agent_adapter.py`;
it is not an installed dependency of either product and implements no adapter.

## Descriptor and core protocol

`describe() -> AdapterDescriptor` returns a stable adapter ID/version, supported
agent types, required runtime, verified feature set, observability label and
limitations. `inspect(Target) -> Success[manifest] | Unsupported | AdapterError`
returns a best-effort capability manifest conforming to the data contract.
An inspection result must not claim complete effective authority.

Verified features are `inspect`, `launch`, `observe`, `pre_action_intercept`,
`fault_injection`, `stop`, `filesystem_effects`, `network_effects`, `trace_import`.
Unlisted features are unsupported, not optimistic defaults. The descriptor is
an adapter implementation claim, not independently proven enforcement.
`negotiate(descriptor, required)` returns success only when the required set is
contained in verified features; otherwise typed `Unsupported` is returned.

## Optional protocols

`ManagedAdapter` adds prepare/start/observe/stop/cleanup. Context contains only
run, scenario and fixture IDs. Prepare returns success after actual preparation;
start returns a run ID; observe returns a finite tuple of Action Events;
stop/cleanup return success only when their documented operation completes.

`InterceptingAdapter.before_action(context, event)` may return an authorization
decision only with verified lifecycle hooks. `unknown` and `requires_approval`
must not be treated as execution authorization. A returned decision alone does
not establish that the host agent enforced it.

Callers preflight features and optional protocol availability before invoking
optional operations. They must not blindly invoke missing methods. Implemented
operations return explicit unsupported results for targets/features they cannot
handle; no silent no-op, mock success, or inferred feature fallback is allowed.

## Observability and errors

Observability labels are declared_only, hook_visible,
tool_dispatch_instrumented, process_boundary, and trace_import. Descriptors must
explain what is invisible. Process launch alone does not expose internal tool
calls; trace import does not enable interception. Observed calls do not prove
effects. Returned manifests/events must pass data and semantic validation.

Result statuses are immutable `ok`, `unsupported`, and `error`. Error metadata
contains operation, static reason code and retryability, never raw exceptions,
credentials or tool arguments. Runtime failures are distinct from unsupported
features; neither is a successful behavior test. The reference defines types,
not runtime validation of third-party descriptors or exception containment.

Adapters consume existing redacted local configuration when eventually needed;
they must not request/log model keys. Opaque fixture IDs cannot be interpreted
as host commands. No vendor integration is implemented or certified here.
