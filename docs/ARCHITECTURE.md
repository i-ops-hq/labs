# Architecture

## Boundaries

`products/permissions` and `products/crashlab` are independent setuptools
distributions using src layouts. Each has its own uv project, runtime
dependencies, tests, lock, environment, and build artifacts. The root project
contains development tools only and declares no uv workspace members.

Canonical JSON Schema files and examples live in `contracts`. Each product
ships a data-only copy of all four schemas; `scripts/sync_contracts.py --check`
and package checks detect drift. The small validation implementations are
independent, intentionally initially similar, and import no other product code.
There is no shared runtime or cross-product orchestration engine.
Permission Simulator's evaluator and Crash Lab's narrow reference runner are
private to their respective products. The adapter
reference is a specification artifact, not a runtime
dependency of either distribution.

## Current public APIs

Each product exports `SCHEMA_VERSION`, `ValidationIssue`,
`ContractValidationError`, `validate_document(contract, payload) -> None`, and
`loads_document(contract, data) -> dict`. Success means structural and documented
semantic consistency only. Errors contain bounded tuples of fixed codes,
sanitized paths, and fixed messages. They never include submitted values.
See COMPATIBILITY.md for limits and exceptions to raw schema-only validation.

Permission Simulator additionally exposes evaluate, inspect_manifest,
export_scenario and three product-local input loaders, with typed decision/export
results. Its separate policy, action-request and fixture-descriptor schemas are
bundled private inputs, not new shared Labs contracts. A standard-library CLI
adds inspect/evaluate/export commands. See products/permissions/POLICY_SPEC.md.

Crash Lab adds prepare_reference_image, load_agent, prepare_agent_image and
run_scenario APIs and a CLI for
builtin/file validation, controlled tests and evidence reports. A pinned official
base plus a content-identified bundle forms a minimal reference image. A guest
supervisor bounds an instrumented benign agent; a separate guest verifier reads
real fixture state. Host code checks returned state, observed controls and
defined predicates, writes hashed evidence and removes only the owned container.
No source folder is mounted into a workload. A separate bounded AgentBundle
input snapshots explicit selected files, IDs and argv; preparation copies these
bytes without running selected agent code or installing packages. A fixed trusted
network-off cleanup removes unused installers from the pinned Alpine base before
agent COPY; the recipe and cleanup source are hashed too. Its digest binds the prepared
image to the selected bundle. The Python guest bootstrap supplies cooperative
fixture tools. Generic commands retain process-boundary visibility and cannot
claim interception. Descriptors and feature negotiation remain product-local;
the typed adapter reference introduces no shared runtime dependency.
See `products/crashlab/RUNNER_SPEC.md` and `products/crashlab/AGENT_GUIDE.md`.

## Intended data flow

Declared manifest + policy → Permission Simulator decision/finding → optional
versioned scenario file → Crash Lab preflight + isolated fixture execution →
action events + independently checked state → evidence result and report.

Permission Simulator now implements the first decision/finding/export steps.
Crash Lab validates exported files and executes supported protected-file cases
with a matching reference or custom Python target. Independent installed CLIs
exchange files and validate real positive/negative evidence. A manual fake API
retry case and generic process fixture work without the simulator. Vendor/framework
integrations are deferred; see INTEGRATIONS.md. Historical reference evidence remains illustrative;
actual runs produce separate observed records rather than rewriting those examples.
Future components must validate both imported input and generated output.
Artifact and fixture locators are opaque references, never host paths to open
or commands to execute during validation.

## Toolchain and change control

Python 3.11-compatible code, uv locks, setuptools builds, pytest, JSON Schema
Draft 2020-12, Ruff, and mypy provide a small inspectable foundation. Dependency
versions and metadata licenses are recorded separately. Format validation is
explicit, and schema resolution is offline.

Minor implementation choices implement the approved plan. Changes to contract
semantics, a shared runtime engine, remote runners, or new trust boundaries need
a proposed ADR and human review before implementation. No such departure was
implemented in the foundation.
