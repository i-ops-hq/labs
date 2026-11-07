# Capability Manifest — data contract v0.1.0

Purpose: record bounded claims about access to actions/resources with provenance
and explicit unknowns, without equating tool configuration with effective OS,
identity or service authority.

| Required field | Meaning |
| --- | --- |
| schema_version, manifest_id, agent_id | Wire version and logical identity |
| captured_at | RFC3339 capture timestamp |
| source_adapter | Adapter ID and version, without credentials |
| capabilities | Zero or more bounded capability declarations |
| unknowns | Known visibility gaps; may be empty only with honest coverage |
| coverage | Observability, scope and nonempty limitations |

Each capability requires capability_id, nonempty action_kinds, nonempty
resource_patterns and basis (declared/configured/observed/inferred). IDs are
unique within the manifest. Optional constraints are explanatory strings,
approval_required is a declaration, and optional confidence requires both a
qualitative level and its meaning. Confidence is not a calibrated probability
or authorization decision. Optional identity_refs contain references only.

Resource patterns are opaque declarations at this phase. No glob expansion,
filesystem lookup, credential resolution or capability analysis occurs.
Constraints do not silently become executable policy rules. Observed access to
one resource does not establish authority over every matching resource.

Distinguish configured agent policy from actual runtime permissions. Unknown
side effects and inherited credentials remain unknown. No secret-value field
exists, but string fields are not a general secret detector; producers must
redact before serialization. Coverage has no global-completeness flag.
