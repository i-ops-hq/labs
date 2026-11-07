# Compatibility — experimental contracts v0.1.0

## Version and schema rules

Four data contracts use Draft 2020-12 and exact `schema_version: "0.1.0"`.
Missing versions are invalid. Any unimplemented version, including `0.1.1`, is
explicitly rejected as `unsupported_version`; semantic version similarity does
not establish compatibility. Future revisions require an explicit reviewed
reader/writer compatibility policy and retained versioned schemas.

Unknown structural fields are rejected. Optional `extensions` is an open JSON
object for non-semantic metadata only. Its contents cannot override recognized
fields, add permission, enable a feature, or alter a verdict. Readers must not
execute extensions. Unknown data is not silently stripped or transformed.
JSON is the only implemented authoring format; YAML is future work.

Each product accepts `action-event`, `capability-manifest`,
`scenario-definition`, and `evidence-result` through its own validation API.
It uses bundled local schemas and refuses external reference retrieval.
Canonical schema URNs identify documents; they are not download URLs.

## Beyond JSON Schema

Schema shape checks are necessary but insufficient. Product validators also
check unique collection IDs, result artifact references, timestamp ordering,
passed-assertion evidence, and verdict consistency. Direct third-party schema
validation must implement these documented semantic checks separately.
Neither mechanism establishes artifact authenticity or actual enforcement.

RFC3339 format checks require timezone offsets. Python's timestamp comparison
cannot represent leap seconds; otherwise format-valid leap-second result
timestamps are rejected as `unsupported_timestamp`. Offsets compare as instants.

## Input and diagnostic limits

`loads_document` accepts UTF-8 bytes or text up to 1,048,576 encoded bytes and
rejects duplicate keys and non-finite values. Both APIs limit JSON trees to
depth 64, 100,000 nodes and 1,048,576 aggregate UTF-8 string bytes. The object API
accepts built-in JSON types only; cyclic or aliased containers are rejected.
At most 32 issues are returned, in traversal order. Diagnostic codes, known-field
paths and fixed messages exclude submitted values and unknown property names.
Error truncation is diagnostic only; it does not turn rejection into acceptance.

## Runtime and support claims

Python >=3.11 is declared, and 3.11 and 3.12 are the interpreters actually
tested. **Only a tested platform and version may be described as verified.**
The adapter protocol has no runtime framework integration. Permission Simulator
now offers a local CLI/API for declared policy evaluation, bounded capability
findings and scenario export. Its product-specific input schemas do not change
the shared contracts. Crash Lab now executes reference and explicit custom
Python/command agents in allowlisted fixtures, raises controlled tool faults
where instrumentation supports them and separately verifies state.
Its exact assertion/fixture/feature registry refuses unsupported semantics.
See products/crashlab/RUNNER_SPEC.md for limits and products/permissions/POLICY_SPEC.md
for conservative policy matching. Custom Python requires the cooperative fixture
API; generic commands expose only process status and measured fixture state.
Selected code is copied into a pinned local image, never run on the host.
No vendor framework integration, arbitrary dependencies/images, trace import,
remote runner or complete isolation guarantee is provided by this milestone.

Crash Lab requires a local Unix-socket Linux Docker engine with cgroup v2,
seccomp and memory/PID controls. The verified environment is Docker Desktop
Engine 29.8.0 on macOS arm64; host Python 3.11/3.12 is checked separately from
the pinned guest Python image. Preparation uses the local Engine legacy build
path to avoid configured remote buildx builders. Other engine/platform versions
and future removal of that build path require verification, not assumed support.
