# Crash Lab changelog

## 0.1.0a4 — local candidate, unreleased

- **A packaged example that shows the conditions can be yours.**
  `iops-crashlab examples` now lists `builtin:user-authored-postcondition`, a 0.2.0
  scenario that declares two fixture observations and writes four of its own
  predicates: `unchanged` and `present` over the files it names, `equals` over the
  agent process's exit status, and `at_most` over a count of attempted writes. Its
  fifth assertion carries no predicate, which shows that built-in identifiers and
  your own conditions mix in one scenario.
- Why this is a release of its own: 0.1.0a3 shipped the capability and left it
  invisible. The three listed scenarios all used the six built-in assertion
  identifiers, so a reader could take in the whole listing and conclude the product
  only checks conditions we had chosen for them. A capability absent from the
  surface a user reads is one they are right to conclude does not exist.
- The example is held to being a template rather than a token: a test reads every
  listed built-in and requires that at least one declares observations, draws on
  three different predicate sources and mixes in a built-in identifier. Removing the
  predicates, narrowing it to one source, dropping its built-in assertion or
  unlisting it each turn that test red.
- It also has to be able to fail. Run against the reference agent that respects the
  policy it passes; run against the one that writes anyway it fails on the file
  predicate and on the built-in check of the same file, which agree. A template that
  passes whatever the agent does would teach nothing about what a predicate is for.
- No library, CLI, schema or contract change. Permission Simulator is untouched and
  stays at `0.1.0a3`: the two products are separate distributions with separate locks
  and separate names, and bumping the one that did not change would misdescribe it.
  This is the first release where their versions differ.

## 0.1.0a3 — local candidate, unreleased

- **The definition of done is now the author's, not ours.** A scenario may
  declare the fixture paths to watch and write its own postconditions, so the
  six built-in assertion identifiers stop being the only things a run can check.
  Until this release a user could bring their own agent but not their own
  definition of done, and for a product whose claim is *declared postconditions,
  authored by code that is not the worker* that was the gap that mattered.
- A postcondition is a closed four-field tuple — `source`, `selector`, `op`,
  optional `value` — drawn from named sets and evaluated by host code. There is
  no expression, no path language and no pattern over file content, and that is
  the load-bearing decision: the check is the one component the tested agent must
  not be able to influence, and an executed string would put an injection surface
  in exactly that place.
- A tuple that cannot be evaluated is refused before the run with its own reason
  code — `predicate_type_mismatch`, `predicate_op_not_supported`,
  `predicate_selector_not_supported`, `predicate_value_arity_mismatch`,
  `predicate_value_not_supported`, `observation_not_supported` — never discovered
  halfway through a container.
- **Unobservable is never a pass.** A path the guest never reported, an
  unreadable file, a comparison with no baseline, a count over an event stream
  that had packets rejected: each is `inconclusive`, and each has a test whose
  counterfactual is "return passed here" and goes red.
- `unchanged` now compares against a reading the host takes inside the container
  after the fixture is written and **before any agent process starts**, so it
  proves the bytes did not change during this run rather than that they equal a
  constant we shipped. `PROTECTED_SHA` is gone; the built-in
  `protected-unchanged` check uses the same captured baseline. The guest is never
  sent the baseline, and the agent is never told which paths are watched.
- The guest observation loop refuses to read through a symbolic link at **any**
  path component, not only the last one, so a declared nested path cannot be
  redirected out of the fixture by something the agent plants.
- A guest report whose observation identifiers are not exactly the declared set
  is `verifier_protocol_error`, not an assertion outcome: a guest that could drop
  an observation could choose which postconditions get decided.
- The evidence record carries the evaluated tuple and one bounded typed observed
  value — a digest, an integer, a state or a boolean, never file content — so a
  reader can disagree with an outcome instead of taking it on trust. `verifier`
  reads `independent-guest-state-and-host-predicates-v0.2` for such a run.
- Contract schemas v0.2.0 for `scenario-definition` and `evidence-result`, in
  their own directory. v0.1.0 is **byte-identical**: a 0.1.0 scenario still
  validates, still runs, still gets a 0.1.0 result with the old verifier string
  and gains no new field anywhere, and an unrecognised assertion identifier is
  still the clean `assertion_not_supported` refusal rather than a crash.
- Not delivered, deliberately: bring-your-own-fixture. `negotiate` still refuses
  any fixture but the built-in ones, so the workspace is still ours even though
  the postcondition is yours.

## 0.1.0a2 — local candidate, unreleased

- A bare `iops-crashlab` run by a person at a terminal now opens a first-run
  wizard: prepare the pinned image, choose a scenario, run it, see the verdict.
  The preselected answer to every question neither writes nor reaches Docker.
- A bare run that is not a person is unchanged, byte for byte. The wizard needs
  both stdin and stdout to be terminals, no `CI` in the environment, `TERM` other
  than `dumb` and no `IOPS_NO_WIZARD`; anything else still prints the
  `invalid_arguments` error and exits 2, because a prompt in a pipeline is a hang.
- A verdict keeps its declared exit code, so a skipped, unsupported, inconclusive
  or error outcome in the wizard can never be read as a pass. An absent daemon is
  `unsupported`, a broken one is `error`, and neither is a failed agent.
- Esc or Ctrl-C leaves the terminal as it was found and exits 130 having changed
  nothing. A console with no byte for a block character gets an ASCII wordmark.
- No new dependencies: the three declared schema packages are unchanged.
- Every existing subcommand, flag, JSON payload and exit code is unchanged.
- Not a gate-reviewed candidate. 0.1.0a1 remains the reviewed one, and the
  artifact and verification records still describe it.

## 0.1.0a1 — local candidate, unreleased

- Independently installed CLI/API, manual scenarios and real simulator exports.
- Restricted local Docker runner with measured controls and owned cleanup.
- Reference agents, cooperative custom Python fixture tools and generic commands
  with explicitly different tool/process visibility.
- Genuine denied-write and partial fake-API faults, retry and duplicate controls,
  separate state verification and evidence-linked readable/JSON reports.
- Alpha hardening: missing/replaced/oversized protected files are failed state
  assertions; unreadable bytes and invalid service journals are inconclusive.
  Harness/cleanup failures remain errors. Ambiguous guest JSON is rejected.
- Pinned minimal Alpine Python image, trusted network-off installer removal before
  agent COPY, and content identity covering the entire recipe/guest bundle.

No live Claude Code/framework adapter, arbitrary dependency/image installation,
real model/API access, remote execution or hostile-code containment guarantee.
Default source/argument image-cache persistence and same-UID/kernel observation
limits remain explicit. Human license/name and release decisions are separate.
