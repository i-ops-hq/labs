# Verified integration scope — local alpha

| Path | Current behavior | Visibility and evidence |
| --- | --- | --- |
| Standalone reference Python | Three packaged scenarios, synthetic denial/partial API fault, positive and negative subjects | Scoped tool telemetry plus separate state verifier |
| Custom Python/API fixture tools | Explicit selected Python code uses guest `crashlab_tools`; denial and real 503 exception/retry | Cooperative instrumented calls; actual protected bytes and fake mutation counts measured separately |
| Generic isolated command | Selected script and argv executed only inside restricted local image | Process exit/time/output status and guest controls/state; no internal tool observation/interception |
| Permission Simulator → Crash Lab | Installed CLI exports a versioned file for a custom Python target, isolated receiving CLI executes it | Actual positive/negative evidence, local hash verification and return-result validation in producer environment |
| Claude Code | **Deferred / unsupported** | Official interfaces inspected; no real workload/hook enforcement test performed |
| Other frameworks, trace/OTel, remote runners | **Unsupported** | No integration claims |

## Actual tests and reproducible exchange

The release verifier builds wheel and source distributions,
rebuilds each sdist into a wheel, then installs in separate temporary environments
outside the repository. Each checks the other product and source modules are
absent. Installed Crash Lab probes run reference pass/fail, custom Python and
generic command cases; the latter two prepare content-identified local images.

For both wheel origins, separate product CLIs exchange scenario JSON only. The
input manifest is a synthetic declaration, not a live inspection of complete
authority. The policy denies the protected write. The exported scenario requires
both unchanged bytes and an attempted write. A custom cooperative agent passes;
a custom bypassing agent changes the file and fails. Actual returned results
are artifact-verified and accepted by Permission Simulator's standalone result
validator. There is no automatic result-analysis UI or shared runtime dependency.

These exchanges are repeated on host Python 3.11 and 3.12. The commands that
reproduce them are in the root README.
Seven CLI cases are exercised, including fake-API retry and duplication,
command execution, missing-file failure and the invalid-journal inconclusive
state. Earlier recorded results describe the version they were taken on.

## Claude Code assessment — 2026-11-04

Local read-only checks found Claude Code **2.1.277** and confirmed relevant
settings/tool-selection flags in `claude --help`. No authentication status,
credentials, user settings or project-specific private configuration was read.

The current official documentation describes PreToolUse input/decision hooks,
including denial, and a non-conversational `--init-only` lifecycle check.
Post-tool hooks cannot establish that every indirect file effect was captured.
Documentation alone does not verify behavior in the installed version or a
container. See [hooks reference](https://code.claude.com/docs/en/hooks) and
[CLI reference](https://code.claude.com/docs/en/cli-reference), consulted on the
assessment date. Current docs include newer-version features; they are not
treated as proof of 2.1.277 behavior.

No Claude binary, account configuration or credentials were copied into the
runner. The default image has no vendor adapter; network is off and this phase
made no model calls. A host CLI version/help check is **not** a safely isolated
agent integration or hook enforcement test. No payload simulation is presented
as a real lifecycle test. A full integration needs a pinned distributable Linux
CLI, reviewed runtime/dependency/license requirements, controlled hook settings,
measured denial/effects and cleanup, and explicit authorization before any paid
model or external-service access. No model gateway is proposed.

Where an integration cannot be verified safely, it is deferred rather than
claimed. Claude support is therefore excluded from the alpha's claims until it
has been separately tested. **That is a statement about what we have verified,
not an assertion that Claude hooks are incapable of interception.**

## Remaining limits

Only the documented fixture/action/fault/assertion vocabulary executes. Generic
commands cannot satisfy pre_action_intercept or fault_injection requirements;
process success is not task/authorization success. Python events are cooperative,
untrusted telemetry, and tool configuration is not complete effective authority.
The subject and verifier share guest UID/kernel. No hostile-code containment,
arbitrary dependencies/images, real API/model access or broad portability claim.
Selected code/arguments persist in local image caches; private inputs must be
excluded by the caller. See product AGENT_GUIDE and SECURITY_MODEL.
