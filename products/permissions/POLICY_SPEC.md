# Permission Simulator local inputs and behavior — v0.1.0

These product-specific inputs do not change the five shared Labs contracts.
The bundled private schemas define their complete shape. JSON only; no code,
expressions, external references, YAML, environment expansion or policy plugins.
All inputs use the existing bounded JSON parser and redacted diagnostics.

## Policy and structured action request

A policy contains schema_version, policy_id, agent_ids (IDs or `*`), an explicit
default_decision, and up to 256 rules. Each rule has a unique rule_id, effect,
action_kinds, operations, resource_types and resource_patterns. Selector arrays
are disjunctions; dimensions are conjunctions. `*` selects all kinds/operations/
types. Resource patterns are exact strings or literal prefixes with one trailing
`*`. No regex, glob character classes, `?`, normalization or filesystem access.

An action request contains schema_version, request_id, agent_id and the same
structured action shape used in Action Event. It is a proposed input only and
contains no stage or outcome. A supplied manifest must describe the same agent.

All matching rules participate. Precedence is denied > requires_approval >
unknown > allowed, independent of rule order. The default is used only when no
rule matches. Explicit default allowed is possible and is reported as a default,
not an inferred grant. An out-of-scope agent yields unknown. Missing/invalid
policy, duplicate rule IDs, malformed selectors and unknown fields are errors.

Evaluation uses case-sensitive lexical identifiers only. Dot segments, repeated
path separators, backslashes, control characters, percent escapes, query strings,
fragments and user-info markers are unsupported because their interpretation
could differ from the declared pattern. They yield unknown, never an allow.
Canonical-looking paths still do not resolve symlinks, OS permissions, endpoint
authority or indirect effects. A prefix must include `/` when a directory boundary
is intended: `/workspace/*` differs from `/workspace*`.

## Optional manifest guards and output

The result preserves policy_decision separately from the final scoped decision.
No manifest means policy-only analysis; it does not assert actual capability.
With a manifest, a non-denied/non-unknown policy decision requires a supported
kind/resource capability match. No match, inferred-only matches, unsupported
patterns in relevant declarations, or uninterpreted constraint text yields
unknown. A matching approval_required declaration upgrades allowed to approval.
Explicit denial remains denial regardless of missing capability coverage.

Results include matched rule IDs, matching capability IDs/bases, fixed explanation
codes and coverage counts/labels. They omit raw resources, patterns, descriptions,
unknown text, credential references and extensions by default. Logical IDs must
not contain secrets; the tool is not a general secret detector.

## Bounded findings

Inspect validates a declared manifest and reports: filesystem plus network/API
coexistence, process plus network/API coexistence, and a literal all-resources
pattern (`*`). Findings include contributing capability IDs and provenance,
and say that a chain, write access, exfiltration or actual side effect has not
been demonstrated. Filesystem action kinds alone do not establish write access.
Empty results mean these specific checks found nothing, not global safety.

## Scenario export

An explicit policy/action pair exports a deterministic policy_simulation scenario
using the shared Scenario Definition schema. It records the expected scoped
decision in its policy constraint and assertion; non-semantic extensions retain
source IDs and execution/readiness labels. The source policy remains external
for later re-evaluation; the exported expectation is not an executable policy. The
`fixture://policy-only` environment is a logical input fixture; no runtime is
required or executed. Unknown outcomes remain explicitly unknown.

Supplying a fixture descriptor explicitly requests an isolated-execution export.
The only initial template is protected-file-write: it requires the matching
agent, an explicit fixture:// identifier and protected resource, a supported
runtime declaration, an exact selected filesystem write to that protected file,
and an explicit denied policy decision. Export declares runner/adapter/fixture
requirements and both a protected-state assertion and an attempted-write assertion,
so unchanged state alone cannot establish that the test action was exercised.
These are declarative verifier requirements, not an implemented verifier or a
claim prerequisites are installed or verified. Mismatches yield a
typed unsupported export with no scenario and no silent policy-only fallback.
No export emits an Evidence Result or claims execution success.

## CLI

`iops-permissions inspect MANIFEST`, `evaluate --policy POLICY --action REQUEST
[--manifest MANIFEST]`, and `export --policy POLICY --action REQUEST
[--manifest MANIFEST] [--fixture DESCRIPTOR] --output SCENARIO`.
JSON is default; `--format text` provides a concise human report. Output errors
are redacted. Evaluation exit codes: allowed 0, denied 3, approval 4, unknown 5;
input/I/O/usage error 2; unsupported export 6. Inspect/export success is 0.
Export writes a private local file atomically and refuses overwrite, including
existing symlinks. Input file reads are bounded and require regular files.

This is a local simulator, not an enforcement integration. No agents, commands,
fixtures, model calls or artifact references are executed by these commands.
