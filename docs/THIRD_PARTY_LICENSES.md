# Third-party dependency review — local alpha

The two product wheels contain first-party code and versioned schema data; they
do not vendor the Python runtime dependencies. Each product declares and locks
the following independently downloaded runtime packages. Actual installed license
metadata and included license-file hashes were inspected in both product
environments.

| Package | Locked version | Observed license |
| --- | --- | --- |
| attrs | 26.1.0 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| referencing | 0.37.0 | MIT |
| rfc3339-validator | 0.1.4 | MIT, classifier and included LICENSE |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT, classifier and included LICENSE |
| typing_extensions | 4.16.0 | PSF-2.0 |

The included license/copyright notices remain in the dependency distributions;
do not strip them during any later bundling. Root development/audit tools are
separate from product dependencies, and the OSV scan covers all applicable
locked tools and runtime versions. Installed
metadata is evidence of declared terms, not a complete audit of every compiled
or vendored transitive component. If a future release vendors dependencies or
publishes an image, review that changed distribution separately.

The default image carries its own OS and Python license inventory. No Docker
daemon, third-party package, model provider or service is relicensed by this
project's licence. The Apache-2.0 choice applies only when
actually selected and added to source/distribution metadata.
