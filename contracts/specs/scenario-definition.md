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
