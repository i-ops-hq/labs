# Permission Simulator changelog

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
