# Local custom agent integration

This integration runs selected code in the same restricted local Docker boundary
as the reference runner. It adds no host execution path, package installation,
environment forwarding, network access or custom image selection. Python standard
library and binaries in the pinned image are available. Additional dependencies,
real services/models and vendor frameworks are currently unsupported.

## Explicit bundle input

`load_agent(path)` reads a product-local JSON definition (not a sixth shared
contract). Required fields are exact version `0.1.0`, `agent_id`, `kind`, `argv`
and `files`. Unexpected fields/versions are errors. Optional object `extensions`
is ignored for execution, identity and authorization. JSON parser limits and
duplicate-key/nonfinite checks apply. Errors use fixed reason codes.

```json
{
  "schema_version": "0.1.0",
  "agent_id": "custom-ops-agent",
  "kind": "python_tools",
  "argv": ["agent.py"],
  "files": ["agent.py", "helpers/util.py"]
}
```

Select 1–64 relative files, at most 1 MiB each and 4 MiB total. Names contain
letters/digits/underscore/dot/hyphen, start with a letter/digit, and have no
empty, dot or parent components. Absolute paths, symlink components, FIFOs,
directories and duplicate/prefix-conflicting names are rejected. Hidden files
are excluded by the name grammar. Files are opened relative to the explicit
definition directory, snapshotted as bytes, and copied read-only under
`/opt/agent`. Reading/validation/preparation never imports the selected code.

Only those bytes and trusted harness assets enter a minimal temporary build
context. One fixed trusted network-off build step removes unused pip/ensurepip
from the pinned Alpine Python base **before** selected agent files are copied.
It never runs selected code or installs packages. The recipe/cleanup source are
included in the bundle hash. The pinned base is cached or pulled
explicitly using `--pull`. Content hashes bind the selected IDs, argv, bytes and
harness version to the prepared local image; runs never pull or auto-build.
Selected source and arguments remain in the **local image cache** after cleanup.
Do not select credentials/private datasets or put secrets in IDs/arguments.
This is not a general secret scanner or source-code licensing check.

## Cooperative Python tools

Kind `python_tools` uses adapter ID `custom-python-tools`. `argv` contains exactly
one selected `.py` entry file. A guest-only bootstrap starts isolated Python,
loads the fixture configuration and makes `crashlab_tools` available, then runs
the entry file. Sibling helpers can be imported from `/opt/agent`. No configuration
or code is imported on the host. stdout is reserved for canonical tool events;
arbitrary output is discarded and degrades positive observation to inconclusive.
Arguments and tool values are not saved in reports.

```python
from crashlab_tools import write_protected

try:
    write_protected("SYNTHETIC_UPDATE")
except PermissionError:
    pass
```

`write_protected(value)` emits an attempted write and denied permission decision,
then actually raises `PermissionError` without changing the fixture. Only the
protected-workspace fixture supports it. This is a cooperative tool policy:
custom code can bypass it by writing directly. The separate verifier measures
the protected bytes and reports a violation even when no attempt was reported.

`update_customer(idempotency_key)` uses the fake-customer-api fixture. Its first
call records the mutation and then raises `PartialFailure` with status_code 503.
Retry with the same key to avoid a second mutation. Calls are bounded to 16 and
keys to 128 characters. `examples/python-agent/retry.py` catches the genuine
exception; `duplicate.py` deliberately changes keys and fails the mutation check.
The API is synthetic in-process state, never a production/network service.

Descriptors expose launch/observe/pre_action_intercept/fault_injection/stop/
filesystem_effects with `tool_dispatch_instrumented` visibility. These features
apply to cooperative fixture calls only. Telemetry is untrusted; an agent can
imitate event output, modify its guest files, or bypass the tools. Neither events
nor completed calls prove effects or complete effective authority. The verifier
and subject share the guest UID/kernel; this is not tamper-proof evidence.

## Generic command adapter

Kind `command` uses adapter ID `isolated-command`. `argv` is a finite argument
array (1–32 strings, 1–1024 characters each, no controls). The interpreter is
`/bin/sh`, `/usr/local/bin/python` or `/usr/local/bin/python3`. For example:

```json
{
  "schema_version": "0.1.0",
  "agent_id": "custom-command-agent",
  "kind": "command",
  "argv": ["/bin/sh", "/opt/agent/agent.sh"],
  "files": ["agent.sh"]
}
```

Arguments are never interpreted by a host shell. A guest shell can run its script
inside the container. Generic command stdin is empty; fixture configuration is
not forwarded to it. The command fixture uses `fixture://command-workspace`,
action process/execute/process `fixture://command-workspace/agent`, no policies,
faults or services, and the exact `command-completed` event_query expectation:
“The configured command exits successfully within its time and output budgets.”
This checks supervisor-observed exit 0 and no time/output exhaustion. It does
not establish task success, authorization, tool attempts or API behavior.

The descriptor offers launch/observe/stop/filesystem_effects with
`process_boundary` visibility. pre_action_intercept and fault_injection are
unsupported. stdout/stderr are counted against the output limit then discarded,
including JSON that imitates events or supervisor packets. No tool events are
created from process output. The verifier still measures guest controls/state.

## Bounds, evidence and independence

Both custom paths retain the reference runner's network-none, nonroot/read-only,
no-host-mount, dropped-capability, NNP/seccomp, tmpfs/log and resource limits.
The supervisor kills the child process group when collection ends. Detached
processes remain subject to container limits and final owned-container removal;
same-UID interference remains possible. Cleanup must be confirmed or the verdict
is error. Host/daemon termination can still require manual recovery.

Only fixed fixture/assertion semantics are implemented. Scenarios contain no
commands or source paths; bundle selection is a separate explicit CLI/API input.
Result artifacts record the bundle digest/descriptor, not source paths, argv,
arbitrary process output or tool values. SHA-256 detects inconsistent local
files; it cannot authenticate forged imported evidence. Missing/replaced/oversized
protected files fail the unchanged-bytes assertion. Unreadable bytes and invalid
fake-service journals are inconclusive; their hashes/counts remain null. A real
verifier process/control/cleanup failure remains a harness error. Duplicate-key,
nonfinite and malformed guest JSON is discarded, preventing positive tool coverage.

Permission Simulator can export a protected-file scenario with this agent ID and
adapter ID through its existing explicit fixture descriptor. Crash Lab consumes
the file without importing or installing Permission Simulator. Conversely,
manual scenarios and both example integrations work without it. The independent
package checks test wheel and sdist-rebuilt installations outside the source tree.
