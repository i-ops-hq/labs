# Crash Lab changelog

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
