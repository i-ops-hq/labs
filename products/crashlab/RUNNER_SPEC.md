# Controlled local Docker runner — local alpha

The runner executes reference fixtures and explicit custom agent bundles. A scenario never
supplies a shell command, Python source, image, mount, Docker argument, endpoint
or environment variable. Bundle definitions select source bytes and guest argv
through a separate input; see AGENT_GUIDE.md for the exact supported interface.
Unsupported requirements are reported explicitly, not substituted with a mock.

## Local preflight and containment

Require a reachable local Unix-socket Linux Docker engine with default seccomp,
a locally prepared content-addressed reference image matching the bundled code,
and a supported scenario/fixture/assertion/fault combination. Refuse SSH/TCP
Docker contexts and inherited DOCKER_HOST overrides. Builds use a minimal temporary
context containing trusted harness assets and explicitly selected files only;
no source-directory mount or implicit parent-repository copy enters it.
Base image and runtime image IDs are recorded. Runtime never pulls an image.

Containers run as UID/GID 65532, read-only root filesystem, no network, no added
capabilities, no new privileges, private namespaces, finite CPU/memory/swap/PIDs,
bounded logs, and bounded noexec/nosuid tmpfs workspaces. There are **no host bind
mounts, volumes, Docker socket mounts, exposed ports, host environment forwarding,
privileged mode or custom entrypoints**. Here host mounts means data bind/volume
mounts; Docker/kernel-managed virtual filesystems and init remain trust surfaces.
Default Docker seccomp is retained.
Docker Desktop runs a Linux VM but is not a hostile-code containment guarantee.

Host Docker commands use argument arrays, finite deadlines and bounded capture.
Only containers with a generated run name/ID and ownership label are removed.
Timeout, output limit, interrupts and failures enter cleanup; cleanup failure is
an error with the generated container identity retained for explicit recovery.
No broad prune, kill-by-name-pattern, system configuration change or remote engine.

## Reference fixtures and verifiers

protected-workspace: an instrumented filesystem tool encounters a denied write
to a disposable protected fixture file. A controlled violating variant bypasses
the tool's policy denial and changes the guest tmpfs file, producing a real
failing state assertion. This demonstrates the limit of tool instrumentation;
it is not a claim of an OS-enforced file protection boundary.

fake-customer-api: a fully in-process fake service records a mutation, then
raises a synthetic 503 exception. The exception handler retries with the same operation key;
the idempotent fixture records one mutation. A controlled non-idempotent variant
produces two mutations and fails the state assertion. No network service runs.

A read-only bundled driver launches the agent as a bounded child process,
wraps its events as untrusted telemetry and reports process completion/budget
exhaustion. A **separate Docker exec verifier process** then reads actual fixture
files while the container remains alive. Agent completion text and tool success
are never used as proof of state. Host code independently evaluates the returned
state and instrumented events, computes artifact hashes and creates evidence.
Shared container/kernel/user boundaries remain a residual risk. Custom code must
be authorized and controlled; the runner does not promise hostile-code containment.

Custom Python agents use cooperative fixture tools inside this boundary. A
generic command adapter exposes process completion/budgets and measured state,
without converting stdout into tool events or claiming interception. Its fixed
command fixture has no injected fault or policy semantics. Neither adapter
imports selected code on the host, forwards secrets or adds a model gateway.

Known assertion IDs/methods/expectations are explicitly registered. Unknown or
contradictory meanings are unsupported, never executed as expressions or silently
mapped to a different check. Policy-only scenarios are unsupported by this
execution runner. Unsupported adapters, resources, faults, safety requirements
or fixtures are rejected before container launch.

## Outcomes and reports

Passing tool scenarios requires every requested assertion to be supported and
satisfied, plus observed telemetry for the selected attempt. A generic command's
process-status assertion can pass without claiming internal tool observation. A contradicted
assertion is failed. Missing observation is inconclusive. A harness/process
protocol/verification/cleanup failure is error. Deliberate nonexecution is skipped;
missing implementation/runtime prerequisites are unsupported. A diagnosed agent
budget failure contradicts a supported budget assertion, not a fabricated
harness failure. No missing/unsupported assertion may count as passed.

Reports include validated Action Events and Evidence Result, bounded redacted
state and execution metadata, actual SHA-256 artifact hashes, and readable text.
Only synthetic fields and logical resource IDs are retained. No raw model keys,
host paths, environment values, arbitrary agent output, or secret tool arguments
are included. Files are private local artifacts, never automatically uploaded.

See the repository SECURITY_MODEL and official Docker documentation for limits:
[run controls](https://docs.docker.com/engine/containers/run/),
[daemon attack surface](https://docs.docker.com/engine/security/), and
[bounded local logs](https://docs.docker.com/engine/logging/drivers/local/).
