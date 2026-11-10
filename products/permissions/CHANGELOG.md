# Permission Simulator changelog

## 0.1.0a3 — local candidate, unreleased

- **`evaluate --format text` carried half the finding.** When the policy says nothing
  about an action AND the agent declares a capability that covers it, that pair is the
  observation a reviewer wants, and only the first half reached the only format a person
  reads: the text branch printed the decision, the policy decision and the matched rules,
  and never the matching capabilities or the observation scope. It now prints all five,
  and it prints them by walking a declared list of decision-relevant keys rather than a
  hand-written sequence, so a key cannot join the report and skip the human-readable
  output. `reason_codes` is deliberately outside that list: it is machine-facing and
  `explanations` already carries the same content as prose.
- **A new `capability-subsumes-capability` finding, severity `review`.** `inspect` could
  only see a resource pattern that was literally `*`, so a declaration of
  `fixture://process/*` sitting beside two narrow process capabilities produced
  `"findings": []`. A capability that swallows your narrow ones is the finding, and
  nothing computed it. The new rule reports one declaration whose resource patterns cover
  another's, within the same declared action kinds, naming capability identifiers and
  never the patterns themselves.
- An exact declaration is never reported as covering a wildcard one. Using the one matcher
  is necessary without being sufficient: it also has to be asked the right question.
  "Does the broad pattern admit the narrow pattern's prefix string" is true for
  `fixture://process/one` against `fixture://process/one*`, and an exact pattern admits one
  identifier while a wildcard admits unboundedly many - so `inspect` briefly reported the
  narrow declaration as covering the broad one, which contradicts what `evaluate` decides
  for `fixture://process/onething`. A wildcard can only be covered by another wildcard.
- Coverage is computed with the existing lexical matcher and no second pattern engine, so
  a finding can never disagree with what `evaluate` would decide. Different action kinds
  never subsume, and the containment is over all of the narrower declaration's kinds: a
  filesystem pattern does not swallow an identical-looking process pattern. Overlap is not
  subsumption, and two declarations that cover each other are duplicates rather than one
  swallowing the other, so neither case produces a finding.
- The finding carries a limitation in the existing register: lexical coverage is not
  effective authority, a declaration is not a permission, and no narrowing by
  configuration or host policy is modelled. The shipped `all-resource-pattern` rule is
  unchanged.
- `inspect --format text` now names the capability identifiers behind each finding. A
  finding that says some declaration covers some other is the same defect as a decision
  that hides which capability matched.
- Reads contract documents at `schema_version` 0.2.0 as well as 0.1.0, selecting
  the schema by the document's own version and refusing any other. This is what
  keeps the file exchange working now that Crash Lab can write a 0.2.0
  `evidence-result`: a simulator pinned to 0.1.0 would have refused a result it
  is meant to read back.
- Still authors 0.1.0 scenarios. `inspect`, `evaluate` and `export` are
  unchanged in behaviour, output and exit codes.
- Duplicate identifiers inside an optional document collection are now reported
  as `duplicate_id` rather than passing: a JSON Schema `uniqueItems` rule cannot
  reject two entries that share an identifier and differ elsewhere.
- Carries the v0.2 schema copies, data-only, held byte-identical to the
  canonical ones by `scripts/sync_contracts.py --check`. No shared runtime and no
  dependency on Crash Lab.

## 0.1.0a2 — local candidate, unreleased

- A bare `iops-permissions` run by a person at a terminal now opens a first-run
  wizard: choose a policy, evaluate one action, optionally export a scenario.
  The preselected answer to every question is the one that writes nothing.
- A bare run that is not a person is unchanged, byte for byte. The wizard needs
  both stdin and stdout to be terminals, no `CI` in the environment, `TERM` other
  than `dumb` and no `IOPS_NO_WIZARD`; anything else still prints the
  `invalid_arguments` error and exits 2, because a prompt in a pipeline is a hang.
- Esc or Ctrl-C leaves the terminal as it was found and exits 130 having changed
  nothing. A console with no byte for a block character gets an ASCII wordmark.
- No new dependencies: the three declared schema packages are unchanged.
- Every existing subcommand, flag, JSON payload and exit code is unchanged.
- Not a gate-reviewed candidate. 0.1.0a1 remains the reviewed one, and the
  artifact and verification records still describe it.

## 0.1.0a1 — local candidate, unreleased

- Independently installed CLI and Python API for explicit declared-policy analysis.
- Deterministic allow/deny/approval/unknown decisions with bounded explanations.
- Provenance-tagged capability findings without complete-authority claims.
- Policy-only export and explicit protected-file scenario export, verified through
  real Crash Lab execution using independent product environments.
- Bounded strict JSON, local schemas, redacted errors and private atomic output.

No execution/enforcement, model calls, framework certification, automatic result
analysis UI, hosted service or managed cloud. The project license/package name
decision and final human release approval are recorded separately. No release
date or published package is claimed by this candidate version.
