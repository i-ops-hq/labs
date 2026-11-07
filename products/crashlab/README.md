# Crash Lab — controlled local agent tests

Run controlled fault scenarios against reference or explicitly selected custom
agents in disposable local Docker containers. Capture scoped tool events,
measure fixture state with a separate verifier process, and generate readable
and machine-readable evidence reports. Permission Simulator is optional.

**Scope:** bundled reference agents, cooperative custom Python fixture tools,
and a generic command adapter with process-boundary visibility. Custom code runs
only inside Docker. Vendor/framework adapters are unverified. Docker is not a
containment guarantee for hostile code. Distribution
name `iops-crashlab` and Apache-2.0 were selected for local candidate 0.1.0a1.

## Local use

Requirements: Python 3.11+, uv, a running local Unix-socket Linux Docker engine
with cgroup v2 and default seccomp, and the pinned official Python base image.
The verified setup is Docker Desktop Engine 29.8.0 on macOS arm64. Other host
platforms/engine versions have not been verified.

```sh
export UV_CACHE_DIR="$PWD/../../.cache/uv"
uv sync --python 3.12 --frozen
uv run --frozen iops-crashlab examples
uv run --frozen iops-crashlab prepare --pull
uv run --frozen iops-crashlab validate builtin:protected-file-write
uv run --frozen iops-crashlab test builtin:protected-file-write --output /tmp/crashlab-protected
uv run --frozen iops-crashlab report /tmp/crashlab-protected/result.json --verify-artifacts
```

Use a new output directory. `prepare --pull` explicitly downloads the pinned
base image and builds a minimal reference image locally; normal runs never pull.
No repository directory, Docker socket, secret store or host environment is
mounted or forwarded into the container. The product does not start Docker
Desktop or alter engine configuration automatically.

```sh
# A controlled violating test subject: expected exit 1 / failed state assertion.
uv run --frozen iops-crashlab test builtin:protected-file-write --reference-variant violate --output /tmp/crashlab-protected-failed
# Fake API: mutate, return a synthetic 503, retry idempotently; no real service.
uv run --frozen iops-crashlab test builtin:fake-api-partial-failure --output /tmp/crashlab-retry
# Known timeout subject: expected failed budget assertion and confirmed cleanup.
uv run --frozen iops-crashlab test builtin:execution-budget --reference-variant timeout --output /tmp/crashlab-timeout
```

A JSON scenario path can replace a builtin name. The examples in `scenarios/`
are independently authored local inputs; they need no Permission Simulator.
Unknown adapters/fixtures/faults/assertion meanings are unsupported before
execution. The current verifier registry requires exact documented assertion
IDs, methods and expectations; it does not interpret prose as executable logic.
`--skip` records deliberate nonexecution without touching Docker.

Exit codes for test: passed 0, failed 1, error/input/I/O 2, inconclusive 3,
unsupported 4, skipped 5. A harness/cleanup failure is error, not an agent failure.
A denied synthetic tool call may be the expected behavior of a passing case.
Tool scenarios require selected-action evidence to pass. Command scenarios can
pass a process-status assertion without claiming internal tool visibility.
Reports retain provenance;
reference/mock imported results are clearly labeled as non-executed evidence.

## The first run

A bare `iops-crashlab`, run by a person at a terminal, opens a short wizard:
prepare the pinned reference image, choose a scenario, run it, and see the
verdict. Arrow keys choose, Enter confirms, Esc cancels and exits 130 having
changed nothing. The preselected answer to every question is the one that neither
writes a report directory nor pulls an image, so holding Enter down finishes the
wizard without touching the machine. A verdict keeps its declared exit code, so a
skipped, unsupported or inconclusive run is never reported here as a pass.

A bare run that is **not** a person is unchanged. The wizard needs both stdin and
stdout to be terminals, no `CI` in the environment, `TERM` other than `dumb`, and
no `IOPS_NO_WIZARD`; anything else prints the `invalid_arguments` JSON error and
exits 2, exactly as before. These commands run inside CI and inside other agents'
harnesses, where a prompt is a hang and a hang is worse than an error. Set
`IOPS_NO_WIZARD=1` to suppress it on an interactive terminal, and `NO_COLOR` to
drop the colour. Every subcommand, flag, JSON payload and exit code is untouched.

## Python API

```python
from iops_crashlab import loads_document, prepare_reference_image, run_scenario
from iops_crashlab.cli import load_scenario

# Run prepare_reference_image(pull=True) once if the pinned base is not cached.
scenario = load_scenario("builtin:protected-file-write")
result = run_scenario(scenario, "/tmp/crashlab-python-case")
assert result["provenance"] == "observed"
print(result["verdict"])
```

`loads_document` / `validate_document` still implement all four shared data
contracts. Malformed inputs raise redacted ContractValidationError. Unsupported
runtime requirements produce a validated unsupported Evidence Result. Output
creation refuses an existing directory and uses private permissions.

## Custom agents

Use an explicit bundle definition; it selects files rather than mounting a source
directory. Builds copy bytes and run no agent code or package installation.

Unlike the commands above, which name packaged `builtin:` scenarios, the bundles
and scenarios below are example files in this repository and are not included in
an installed package. Point these commands at your own bundle, or run them from a
checkout.

```sh
uv run --frozen iops-crashlab describe-agent examples/python-agent/agent.json
uv run --frozen iops-crashlab prepare --agent examples/python-agent/agent.json
uv run --frozen iops-crashlab test examples/python-agent/protected-scenario.json --agent examples/python-agent/agent.json --output /tmp/crashlab-custom
# Negative control: this agent bypasses the tool denial and changes the file.
uv run --frozen iops-crashlab prepare --agent examples/python-agent/bypass.json
uv run --frozen iops-crashlab test examples/python-agent/protected-scenario.json --agent examples/python-agent/bypass.json --output /tmp/crashlab-bypass
# Generic commands expose exit/time/output status, not their internal tool calls.
uv run --frozen iops-crashlab prepare --agent examples/command-agent/agent.json
uv run --frozen iops-crashlab test examples/command-agent/scenario.json --agent examples/command-agent/agent.json --output /tmp/crashlab-command
```

The Python API adds `load_agent(path)`, `prepare_agent_image(bundle)`, and
`run_scenario(scenario, output, agent=bundle)`. A changed source bundle requires
preparation of its new image. Target IDs and required features must match the
selected adapter; unsupported requirements never fall back to a reference agent.
See [AGENT_GUIDE.md](https://github.com/i-ops-hq/labs/blob/main/products/crashlab/AGENT_GUIDE.md) for the input format, tool API, retry example,
visibility limits and file/image-cache handling.

## Reclaiming what it builds

Every image this product builds carries the label `org.iops.crashlab.bundle-sha256`,
and an agent image additionally carries `org.iops.crashlab.agent-sha256`. That label
is what makes a safe, exact cleanup expressible, because it matches this product's
images and nothing else on the machine:

```sh
docker image prune --filter label=org.iops.crashlab.bundle-sha256
```

`prepare` is content-addressed, so preparing the same bundle twice builds nothing the
second time and running the same scenario repeatedly costs one image, not one per run.
What does accumulate is editing an agent bundle: each distinct bundle is a distinct
image, so a cycle of edit-and-prepare leaves one behind per edit. Containers are
removed as each run ends and the run report records whether that cleanup was
confirmed; images are deliberately kept, because rebuilding them is the slow part.

## Evidence and security boundaries

Each report directory contains result.json, report.md, events.jsonl, state.json
and execution.json. Assertions link to actual artifacts with computed SHA-256.
The independent verifier reads bounded regular guest files without following
symlinks, measures process/cgroup controls, and the host evaluates predicates.
Tool success and agent text are not accepted as proof of state. Hash checks
establish local consistency, not authenticity of an arbitrary imported result.

No host mounts; network off; UID/GID 65532; read-only root; all capabilities
dropped; no-new-privileges; finite CPU/memory/swap/PIDs; bounded tmpfs, logs,
subprocess output, deadlines and owned-container cleanup. Reference tools can be
bypassed by the violating subject inside its disposable fixture; this is a test
of declared tool policy, not proof of OS-enforced authority. See
[RUNNER_SPEC.md](https://github.com/i-ops-hq/labs/blob/main/products/crashlab/RUNNER_SPEC.md) and repository security/validation documents.

```sh
# Unit/validation tests only: real integration cases are explicitly skipped.
uv run --frozen pytest -q
# Requires the actual local engine/base; missing prerequisites fail this check.
uv run --frozen pytest -q --docker
```

Unit fault injections are explicitly simulated and are not advertised as real
integrations. The separate live suite tests pass/fail consequences, retry state,
time/output budgets, guest controls, host-secret omission, no-action handling
and confirmed cleanup. No model API, real customer service, production endpoint,
remote Docker host, VM manager or cloud service is supported here.
