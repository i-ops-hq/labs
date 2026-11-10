# I-Ops Labs

> ### Status: in testing, not ready for public use
>
> Crash Lab is a local alpha at `0.1.0a4` and Permission Simulator at `0.1.0a3`.
> Both run, and the checks below reproduce that on your own machine. What neither
> has had is use by anyone outside the people who built them.
>
> Three things follow. Interfaces may change anywhere inside `0.1.x`;
> `docs/COMPATIBILITY.md` states what is and is not promised. No version has been
> through a release cycle. And a verdict from either product is a local result,
> not something to carry into a review or an audit.
>
> This notice goes when several more versions have been tested in the open, and
> the setup guide arrives with it. Until then the commands in this README assume
> a checkout of this repository, which is the fastest way to see what the products
> actually do.

Two independently useful products under development:

| Product | Intended purpose | Implemented now |
| --- | --- | --- |
| Permission Simulator | Explain declared authorization and export bounded policy tests | Local CLI/SDK, deterministic evaluation, bounded findings and scenario export |
| Crash Lab | Test observable agent behavior under controlled faults | Local reference/custom Python/command agents, fixture faults, separate verification and evidence reports |

Running either command with no arguments at a terminal opens a first-run wizard;
running it from a script is unchanged, byte for byte.

Both products operate independently. Crash Lab runs reference or explicit custom
agent bundles in restricted local containers. Vendor/framework integrations and
managed cloud are unavailable. Claude Code is explicitly deferred from support
claims; see [integration coverage](docs/INTEGRATIONS.md). Historical reference
results stay illustrative; actual controlled execution evidence is recorded
separately.

Labs complements Vinci Intelligence, Assurance, and Rooms. Neither package
requires those products or the other Labs package. Interoperability initially
uses versioned JSON files; no shared runtime engine is installed.

## Local development

Python 3.11 or 3.12, with [uv](https://docs.astral.sh/uv/). Each product has its
own environment; they are installed and tested independently, and neither needs
the other.

```sh
uv sync
uv run pytest -q
uv run --project products/permissions pytest products/permissions/tests -q
uv run --project products/crashlab pytest products/crashlab/tests -q
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/sync_contracts.py --check
```

Crash Lab's default test run skips the cases that need Docker. To exercise real
container execution, prepare its pinned image and pass `--docker`:

```sh
uv run --project products/crashlab iops-crashlab prepare --pull
uv run --project products/crashlab pytest products/crashlab/tests --docker
```

A missing prerequisite fails the check you asked for. **A skipped integration is
never counted as a pass.**

## Read first

- [Architecture](docs/ARCHITECTURE.md) and [security model](docs/SECURITY_MODEL.md).
- [Contract index](contracts/README.md) and [compatibility](docs/COMPATIBILITY.md).
- [Integration coverage](docs/INTEGRATIONS.md) — what is verified, and what is not.
- [Contributing](CONTRIBUTING.md).

Both products are Apache-2.0.
