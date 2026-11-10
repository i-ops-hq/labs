# Scenario Definition — data contract v0.1.0

Purpose: portable test data authored independently for Crash Lab or exported by
Permission Simulator. Serialization validity never grants permission to run it.

| Required field | Meaning |
| --- | --- |
| schema_version, scenario_id, title | Version and human-readable identity |
| category | permission / fault / recovery |
| mode | policy_simulation / isolated_execution |
| requirements | Adapter feature list, runner and runtime declaration |
| environment | Logical fixture ID, fresh_copy reset and fake service IDs |
| action_selector | Structured kind, operation and resource selector |
| policy_constraints | Explicit operation/resource/decision declarations |
| assertions | Nonempty uniquely identified expectations and verifier methods |
| safety | Fixture scope, permissions, network off, cleanup and finite limits |
| metadata | Author, manual/simulator source, explanation; optional manifest_id |

isolated_execution additionally requires target agent/adapter IDs and runner
docker. policy_simulation uses runner none and may omit target. Optional fault
declares denied_operation or api_failure, a finite trigger match count, and
optional simulated error status. No command, script, production endpoint,
arbitrary host mount, or shell-string field exists.

Assertions declare file_state, fake_service_state, event_query or policy_decision
verification. Expectations are descriptions, not executable expressions. The
future runner must implement specific verifier semantics and refuse unsupported
requirements before execution. Do not convert expectation strings into code.

## Safety and execution negotiation

v0.1.0 scenarios declare fixture_only filesystem access, network off, mandatory
cleanup and bounded time/output/memory/CPU/pids. Schema maxima are portability
bounds, not recommended allocations or guarantees of runner enforcement.
Fixtures use `fixture://` logical identifiers; they are not host paths. The fake
API example is in-process fixture state, not a real network service.

Missing fixture, adapter capability or runner maps to unsupported; unavailable
observation needed to decide an assertion maps to inconclusive; harness failure
maps to error. None maps to passed. Foundation validates declarations only and
does not perform runtime preflight, fixture lookup, policy evaluation or tests.

The protected-file case links a synthetic manifest to illustrative evidence.
The partial API failure case requires checking fake service mutation counts and
bounded retries. These contract examples are illustrative; current implemented
runner/fixture coverage and actual execution evidence are documented in
`docs/INTEGRATIONS.md`. Validation alone executes neither.

## v0.2.0 — observations and author-written postconditions

v0.1.0 is unchanged and stays byte-identical. A reader selects the schema by the
document's own `schema_version` and refuses any version it does not hold. These
schemas are `additionalProperties: false`, so a new property is a new document
shape; calling it 0.1.0 would make one version string mean two incompatible
things. A 0.1.0 scenario therefore refuses `observations` and `predicate` with
`schema_violation`, which is correct rather than unfortunate.

v0.2.0 adds one optional top-level block and one optional assertion property.

`observations` declares, before the run, which fixture paths a verifier process
should read. At most 32 entries. `kind` is an enum whose only value today is
`file`, so adding `directory` later is an addition rather than a redesign.
`path` is relative to the fixture root — no leading separator, no `..`, every
component matching the same rule the runner applies to bundle files, bounded at
200 characters — and `max_bytes` is bounded at 1048576. Each entry carries an
`observation_id` unique within the document; `uniqueItems` cannot express that,
because two entries sharing an identifier and differing elsewhere are not equal,
so duplicate identifiers are reported as `duplicate_id`.

The guest reports, per observation, a `state` in `{regular, missing, symlink,
not_regular, oversized, unreadable}` and a `sha256` that is null unless the state
is `regular`. It is a loop over a declared list, not new logic. A report whose
identifiers are not exactly the declared set is a protocol error, not an
assertion outcome: a guest that could drop an observation could choose which
postconditions get decided.

`assertions[].predicate` is a closed four-field tuple:

```json
{"source": "file_observation", "selector": "the-file-i-care-about", "op": "unchanged"}
```

`source` is one of `file_observation`, `run_state`, `service_state`,
`event_count`. `op` is one of `unchanged`, `changed`, `equals`, `at_most`,
`at_least`, `absent`, `present`; the first schema rule is arity — `equals`,
`at_most` and `at_least` require `value`, and the rest forbid it. `selector` is
drawn from a closed set per source: a declared `observation_id`; or
`exit_code`, `timed_out`, `output_limited`, `invalid_output`, `rejected_events`,
`captured_bytes`; or `mutation_count`, `service_call_count`,
`injected_fault_count`, `service_state`; or an event stage in `{proposed,
attempted, permission_decision, completed}`.

**There is no expression, no path language and no regular expression over
content, and this is the load-bearing decision rather than a simplification.**
The predicate is the one component the acting worker must not be able to
influence, and an executed string would put an injection surface in exactly the
place that has to be trustworthy. Every operator is host code over a projection
that was already validated. A predicate whose operator cannot apply to its
selector's type is refused before the run with a reason code
(`predicate_type_mismatch`), never discovered halfway through a container.

An assertion with a predicate is decided by that predicate. An assertion without
one must still be a recognised identifier with matching prose, so the existing
refusal is unchanged; the two may be mixed in one document. `method` stays
required and descriptive — it is not cross-checked against `source`, because a
mapping invented between them would add a refusal with no safety value.
