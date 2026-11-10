# Contracts — v0.1.0 foundation, v0.2.0 postconditions

These interfaces are experimental and versioned.
Changes require a reviewed ADR and explicit compatibility treatment.

| Contract | Specification | Machine representation |
| --- | --- | --- |
| Agent Adapter | [agent-adapter](specs/agent-adapter.md) | Typed reference protocol in reference/python |
| Action Event | [action-event](specs/action-event.md) | schemas/v0.1/action-event.schema.json |
| Capability Manifest | [capability-manifest](specs/capability-manifest.md) | schemas/v0.1/capability-manifest.schema.json |
| Scenario Definition | [scenario-definition](specs/scenario-definition.md) | schemas/v0.1 and schemas/v0.2/scenario-definition.schema.json |
| Evidence Result | [evidence-result](specs/evidence-result.md) | schemas/v0.1 and schemas/v0.2/evidence-result.schema.json |

Each version is its own directory and each schema is `additionalProperties:
false`, so a new property is a new document shape rather than a looser old one.
A reader selects a schema by the document's own `schema_version` and refuses a
version it does not hold; v0.1.0 is byte-identical to what it always was. v0.2.0
adds declared `observations` and author-written `predicate` postconditions to
the two contracts that carry them.

The JSON Schemas are authoritative for field types, requiredness, enum values,
lengths and numeric bounds; the specs add semantic invariants that JSON Schema
cannot express. docs/COMPATIBILITY.md defines reader behavior, input limits,
version negotiation and diagnostic rules. These file contracts do not install
a shared runtime engine or a third product.

`examples/index.json` lists all 21 positive and 38 negative fixtures with their
contract and, for negative examples, expected error code. Those two counts are
checked against the index by the contract matrix, because a number written in
prose beside the thing it counts drifts on its own. All examples use
synthetic identities. Every result is hand-authored reference data, explicitly
marked as not executed; artifact locators are illustrative and no hash is
invented. Positive/negative validity refers to serialization, not agent safety.

The linked example is custom-python-manifest → protected-file-write →
reference-result-passed, with attempted-write/completed-write/verified-state
illustrating distinct event stages. fake-api-partial-failure models an in-process
fake service and duplicate retry assertions without any real endpoint.

Run the source-tree contract matrix from the Labs root with `uv run --frozen
pytest -q`. Run `uv run python scripts/sync_contracts.py --check` to confirm that
the data-only schema copies each product carries are byte-identical to the
canonical ones here. Neither executes an agent or demonstrates an enforcement
integration.

Current product execution coverage and observed reports are documented in
docs/INTEGRATIONS.md. Contract fixtures remain illustrative;
they are not relabeled as executed evidence when an implementation is added.
