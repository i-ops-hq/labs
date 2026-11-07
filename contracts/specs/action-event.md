# Action Event — data contract v0.1.0

Purpose: distinguish intent, an attempted tool action, reported completion and
evidence-backed observations. The schema defines the exact wire shape.

| Required field | Meaning |
| --- | --- |
| schema_version | Exact supported wire version |
| event_id, run_id, agent_id, adapter_id | Stable logical identifiers |
| occurred_at | RFC3339 timestamp with offset |
| sequence | Nonnegative ordering within a run |
| stage | proposed / permission_decision / attempted / completed / side_effect_observed / verification |
| action | kind, operation, resource type and logical/redacted identifier |
| source | Capture kind and scope describing visibility limits |
| outcome.status | unknown / not_executed / succeeded / failed / blocked |

Optional correlation_id and parent_event_id link related events; optional
artifact_refs link observations to evidence in the associated result bundle.
permission_decision requires policy_decision (allowed / denied /
requires_approval / unknown). Extensions are non-semantic metadata only.

## Stage rules

- proposed and attempted permit unknown/not_executed only; an attempt cannot
  carry a success claim.
- permission_decision permits unknown/not_executed/blocked. This records the
  decision, not a verified OS/runtime barrier.
- completed permits unknown/succeeded/failed. A successful tool return still
  does not prove its claimed side effect occurred.
- side_effect_observed and verification require nonempty artifact_refs,
  succeeded/failed, and verifier/tool_dispatch/trace_import provenance. The
  capture scope must explain the measured property and evidence limitations.

Across a complete imported bundle, event IDs and sequence numbers must be unique
per run, parent references must resolve without cycles, and artifact references
must resolve. Foundation validation checks one event at a time; whole-run bundle
validation/replay is not implemented. Consumers must not infer those guarantees
from a valid individual event.

Never put raw prompts, API keys or unrestricted argument dumps in extensions.
Identifiers/locators are data; validators do not open or execute them. Fixtures
illustrate attempted, completed, denied and verified stages without real runs.
