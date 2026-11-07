# Permission Simulator — local development alpha

Inspect explicit capability declarations, evaluate structured actions against
deterministic policy, and export portable policy-oriented test scenarios.
This package works independently of Crash Lab and other I-Ops products.
It does not execute an agent or enforce actual runtime permissions.

This project is Apache-2.0 and ships as the distribution and CLI
`iops-permissions`. That name and licence were selected for local candidate
0.1.0a1.

## Install and try locally

From this product directory, with uv and Python 3.11+ installed. These commands
assume a checkout of this repository: the example files they read are part of the
source tree and are not included in an installed package.

```sh
export UV_CACHE_DIR="$PWD/../../.cache/uv"
uv sync --python 3.12 --frozen
uv run --frozen iops-permissions inspect examples/operations-manifest.json
uv run --frozen iops-permissions evaluate --policy examples/policy.json --action examples/action-allowed.json --manifest examples/operations-manifest.json
uv run --frozen iops-permissions evaluate --policy examples/policy.json --action examples/action-denied.json --format text
```

The last command intentionally exits **3** for denied. Evaluation exits are
allowed 0, denied 3, requires_approval 4 and unknown 5. Input/I/O errors exit 2;
unsupported exports exit 6. All decisions are scoped to declared policy and,
when supplied, manifest coverage. They are not effective permission guarantees.

`action-approval.json`, `action-unknown.json` and `action-api.json` exercise other
paths. `coding-manifest.json` plus `action-coding.json` demonstrates synthetic
coding-agent declarations, without claiming a real vendor integration.

```sh
# Policy-only scenario: requires no runner, adapter or physical test fixture.
uv run --frozen iops-permissions export --policy examples/policy.json --action examples/action-allowed.json --output /tmp/iops-policy-case.json
# Isolated test definition: explicitly declares its required fixture and adapter.
uv run --frozen iops-permissions export --policy examples/policy.json --action examples/action-denied.json --manifest examples/operations-manifest.json --fixture examples/protected-file-fixture.json --output /tmp/iops-protected-case.json
```

Exports refuse existing output files/symlinks, use private permissions and never
execute a test. Choose a fresh output filename if those example paths exist.
The supplied fixture descriptor is test metadata, not an installed fixture or
verified adapter. Unsupported fixture/action combinations produce no file.
Generated examples in this directory are actual CLI exports, not execution
results; their execution_status is not_executed.

## The first run

A bare `iops-permissions`, run by a person at a terminal, opens a short wizard:
choose a policy, evaluate one action, and optionally export the result as a
scenario Crash Lab can run. Arrow keys choose, Enter confirms, Esc cancels and
exits 130 having changed nothing. The preselected answer to every question is
the one that writes nothing, so holding Enter down finishes the wizard with the
working directory unchanged.

A bare run that is **not** a person is unchanged. The wizard needs both stdin and
stdout to be terminals, no `CI` in the environment, `TERM` other than `dumb`, and
no `IOPS_NO_WIZARD`; anything else prints the `invalid_arguments` JSON error and
exits 2, exactly as before. These commands run inside CI and inside other agents'
harnesses, where a prompt is a hang and a hang is worse than an error. Set
`IOPS_NO_WIZARD=1` to suppress it on an interactive terminal, and `NO_COLOR` to
drop the colour. Every subcommand, flag, JSON payload and exit code is untouched.

## Python API

As in the quickstart, the files read below are examples from this repository
rather than package data; substitute your own paths outside a checkout.

```python
from pathlib import Path
from iops_permissions import (
    evaluate,
    export_scenario,
    inspect_manifest,
    loads_policy,
    loads_action_request,
    loads_document,
    loads_fixture_descriptor,
)

policy = loads_policy(Path("examples/policy.json").read_bytes())
request = loads_action_request(Path("examples/action-denied.json").read_bytes())
manifest = loads_document(
    "capability-manifest", Path("examples/operations-manifest.json").read_bytes()
)
result = evaluate(policy, request, manifest)
assert result.decision == "denied"
print(result.to_dict())
exported = export_scenario(policy, request, manifest)
assert exported.execution_status == "not_executed"
```

All public input boundaries raise `ContractValidationError` with structured,
redacted issues. `validate_document` / `loads_document` still support all four
shared data contracts. `loads_policy`, `loads_action_request`, and
`loads_fixture_descriptor` validate this product's separate local input formats.
See [POLICY_SPEC.md](https://github.com/i-ops-hq/labs/blob/main/products/permissions/POLICY_SPEC.md) for selectors, precedence, conservative
manifest guards, limits and export semantics.

Default reports omit raw resource identifiers/patterns, unknown text, constraint
text and credential references. IDs must be logical references without secrets.
Exported scenario files necessarily retain their explicitly selected action
resource; treat those local artifacts as potentially sensitive configuration.

## Validation and boundaries

```sh
uv run --frozen pytest -q
uv build
```

The repository verifier additionally installs wheels and rebuilt source
distributions outside the source tree, tests SDK/CLI functionality without Crash
Lab, and checks matching shared schema bytes. Supported matching is lexical and
bounded; no regex policy language, path resolution, arbitrary static analysis,
runtime hooks, enforcement, model calls, gateway, or cloud service is provided.
