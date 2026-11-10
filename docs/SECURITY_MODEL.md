# Security model

## Current trust boundaries

Agent output, scenarios, imported events/results, traces and extensions are
untrusted data. Validators parse bounded JSON against bundled trusted schemas
and documented consistency rules; validation itself launches no agent or remote
schema fetch. Permission Simulator evaluates declarations only. Crash Lab's
separate explicit execution path runs reference or explicitly selected custom
agent bundles in a restricted local Docker container, then separately verifies
guest state. Bundle input snapshots selected bounded regular files; build steps
copy selected bytes without executing agent code. A fixed trusted network-off
cleanup removes unused package installers before those bytes enter the image;
the full recipe is hashed. Custom images, host mounts, external package
installation, real service/model access and environment forwarding are unsupported.

Errors expose fixed messages and sanitized paths. Validation is not secret
detection: accepted documents remain caller-supplied data in memory. Callers
must not log parsed payloads, exception internals, or raw tool arguments blindly.
Fixtures are synthetic and contain no credentials or real production targets.

## Threats and current evidence

| Threat | Current control/evidence | Residual limitation |
| --- | --- | --- |
| Malformed/oversized JSON, excessive nesting, duplicate keys, nonfinite numbers | Parser limits and negative tests | This is not a general adversarial parser audit |
| Secrets reflected through diagnostics | Fixed messages, known-field projections, sanitized paths and host-secret sentinel tests | No general secret scanner; logical IDs/config artifacts must not contain secret values |
| Remote schema retrieval | Bundled schemas, explicit offline registry, blocked-socket tests | Package/dependency integrity remains a supply-chain boundary |
| False positive evidence verdict | Separate state verifier, source/action coverage, exact predicate registry, failure/control subjects and hash checks | Forged imported reports can still validate; hashes establish consistency, not authenticity |
| Scenario command/path injection | Exact fixture/action/fault/assertion registry; separate explicit bundle input; no host shell, scenario command/image/mount arguments; bounded nofollow component reads | Guest commands can execute selected controlled code; this is not hostile-code containment |
| Host data access, symlinks and subprocess escalation | No host data mounts, read-only guest root, nonroot UID, dropped capabilities/NNP/seccomp; regular nofollow/nonblocking verifier reads; measured cgroup limits | Daemon/runtime/kernel virtual mounts remain trusted surfaces; no hostile breakout testing |
| Remote egress, production access, cost loops | Runtime network none, measured active-interface/connection denial, no real API/model calls, finite time/output/CPU/memory/PIDs | Network probe/config checks do not prove universal security against kernel flaws |
| Harness/cleanup failures | Simulated fault-path tests plus real owned-container-loss, timeout/output and owned-removal checks | Host SIGKILL, daemon failure and uncertain asynchronous requests can require manual recovery |

## Execution defaults

The reference and custom adapters retain the following defaults. Real
tests exercise custom Python denial/bypass/retry behavior and command budgets,
host-file/secret omission and cleanup. These controlled cases do not establish
security for arbitrary hostile programs or future framework adapters.

Use disposable synthetic fixtures, restricted mounts, minimal privileges,
network off by default, finite CPU/memory/pid/time/output limits, child-process
termination, and cleanup on success, failure, timeout and harness exception.
Never mount the Docker socket or sensitive host directories by default. Docker
alone does not prove safe containment of hostile code. No convenience unsafe
execution path without human review.

Before execution ships, test host access boundaries, symlink/path traversal,
secret inheritance, subprocess behavior, egress, runaway output/loops, artifact
tampering and misleading agent claims. Use only authorized controlled fixtures.
No production payment, email, customer database, cloud or other live endpoints.
Harness faults produce `error`; unavailable features produce `unsupported`;
insufficient evidence produces `inconclusive`. None may be counted as passing.

## Current measured evidence and residual risks

Live Docker tests verify actual read-only/nonroot/capability/NNP/seccomp behavior,
memory.max/pids.max/cpu.max values, no active non-loopback interface and a denied
TEST-NET connection attempt, no forwarded host sentinel, pass/fail fixture state,
time/output termination and owned-container absence after cleanup. This is a
controlled test suite, not a penetration test or hostile-code audit.
Inactive kernel tunnel placeholders are not treated as active network egress.

The supervisor, agent and separate verifier share the guest kernel and UID.
Read-only bundled code and process separation reduce accidental self-reporting
errors; they are not a tamper-proof boundary against arbitrary hostile guest
code. The local Docker daemon and selected pinned image are trusted. No user
data binds/volumes are configured; kernel/daemon-managed virtual filesystems
and init still exist. Engine/admin compromise and container escape remain risks.

Custom agent stdout is untrusted. Python tool events are cooperative claims;
generic command output is counted and discarded even when it imitates canonical
events or supervisor JSON. Process exit alone does not establish task success.
Generic command stdin is empty. Docker/client/driver stderr diagnostics are
separate from protocol stdout, bounded and discarded; only an observed-status
flag is retained. Diagnostics alone cannot establish readiness or a passing case.
Selected source/argv persist in prepared **local image caches**, even after
container cleanup. Callers must exclude private data; no secret scanner examines
source files. Runtime reports omit code, source paths, argv and arbitrary output.
Missing/replaced/oversized protected files are measured failed assertions.
Unreadable bytes and invalid/missing fake-service journals are inconclusive, with
no fabricated hashes/counts. Actual verifier process/control failures remain
harness errors. Ambiguous duplicate-key/nonfinite guest JSON is rejected.

All scenario cleanup is bounded and limited to an exact generated container ID
with the matching run label. An observed empty owned-label query confirms current
absence, not perfect cleanup under every host/daemon crash or delayed request.
Unconfirmed cleanup is an error and records the generated container name for
manual recovery. No broad prune or unrelated container modification is performed.

Image and Python dependencies receive known-advisory scans and recorded license
metadata review; these are not complete source or legal audits. The minimal
pinned base removes unused installers before agent COPY. See
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for dependency scope. Reports
written by an actual controlled run are the only ones treated as evidence;
reference and mock payloads are never relabelled as observed results.

## Operations

Permission Simulator's CLI reads explicit bounded regular input files
and writes an explicitly requested local scenario file. Export uses mode 0600
and atomic creation without replacing existing files/symlinks. It never resolves
fixture/artifact identifiers, runs agent code, calls models or opens network
connections. Policy selectors are a fixed lexical vocabulary, not expressions.
Ambiguous identifiers and insufficient declared coverage cannot yield allow.
Default reports omit free text and resource/credential references; text-mode
logical IDs are escaped. Export artifacts retain the chosen resource identifier
and should be handled as potentially sensitive configuration. The private policy
format is strict; malformed policies are errors, not authorization decisions.

Dependency downloads are developer setup, not scenario network access. Locks
record exact resolutions; build tools are constrained. No cloud resources,
paid APIs, publishing, deployment, telemetry, or persistent background services
are created by this phase. Review licensing and dependencies before release.

For this local task, the already-installed Docker Desktop engine was started
because it was stopped, and official base/reference images were cached locally.
The product does not start Desktop automatically. No cloud VM or paid service
was provisioned. Owned scenario containers are removed; image/dependency caches
remain for local development and are not evidence of a running workload.
