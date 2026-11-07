# Evidence Result — data contract v0.1.0

Purpose: report a scoped verdict with assertion provenance and explicit limits.

| Required field | Meaning |
| --- | --- |
| schema_version, result_id, scenario_id, run_id | Version and correlation |
| started_at, finished_at | RFC3339 instants in nondecreasing order |
| verdict | One of the six outcomes below |
| provenance | observed / reference / mock |
| assertions | Assertion ID, expectation, outcome, verifier and evidence_refs |
| observation_scope | Nonempty visible and not_visible descriptions |
| artifacts | Unique artifact IDs, type, logical locator, redaction state; optional real SHA-256 |
| runner, adapter | Logical IDs and versions, not support certifications |
| limitations, summary | Nonempty limitations and readable scoped explanation |

## Verdict semantics and consistency

| Verdict | Meaning and local validation |
| --- | --- |
| passed | Nonempty assertions, all passed, each with resolvable evidence |
| failed | At least one failed assertion; no assertion with error |
| inconclusive | Insufficient evidence; no failed/error assertions; empty assertions allowed |
| unsupported | Required implementation unavailable; only unsupported/skipped assertions |
| skipped | Deliberately not run; only skipped assertions |
| error | Harness execution/evaluation failed; may retain earlier assertion outcomes |

Assertion IDs and artifact IDs must be unique within their collections. All
assertion evidence_refs must resolve locally. A passed assertion requires
evidence even in a non-passed overall result. An error assertion requires the
overall verdict error. No assertions cannot yield a pass. Assertion-level
outcomes use the same six labels but are distinct from the overall verdict.

Every referenced assertion should match its scenario expectation and verifier;
matching against a separately supplied scenario requires bundle-level checking.
The foundation's linked fixture test checks its own example, not arbitrary
imported scenario/result pairs.

## Provenance and artifacts

observed means the producer claims direct observation; validators do not
authenticate that claim. reference/mock describe illustrative or simulated
records and must never be presented as executed integration evidence. A passed
reference payload demonstrates serialization only. Consumers must retain this
provenance in later reports rather than displaying its verdict alone.

Artifact locators are opaque `artifact://` references. Foundation validation
does not dereference them, check existence, verify hashes or authenticate
contents. SHA-256 is optional and may be recorded only when actually computed
from the referenced bytes. Default redaction states are redacted or synthetic;
no unredacted/raw secret artifact state is offered.

A passed observed result means only the defined observable assertions held in
that environment. It never establishes global agent safety, complete authority
visibility, perfect isolation or reproducibility.
