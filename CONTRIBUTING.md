# Contributing locally

Read the [architecture](docs/ARCHITECTURE.md), the contracts and
[security model](docs/SECURITY_MODEL.md). Keep the two products independently
installable. Do not add cross-product runtime imports, execute selected agent code
on the host, interpret scenario prose as commands or report missing coverage as
success. Major boundary/contract changes need a reviewed ADR.

Use Python 3.11-compatible source. The local release checks use patched Python
3.11 and 3.12 interpreters plus uv. Root dependencies are development tooling;
each product has its own lock/environment. Typical setup from the Labs root:

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --frozen --python 3.12.16
uv sync --project products/permissions --frozen --python 3.12.16
uv sync --project products/crashlab --frozen --python 3.12.16
uv run --frozen pytest -q
uv run --project products/permissions --frozen pytest -q products/permissions/tests
uv run --project products/crashlab --frozen iops-crashlab prepare --pull
uv run --project products/crashlab --frozen pytest -q products/crashlab/tests --docker
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv run --frozen python scripts/sync_contracts.py --check
```

Downloads need network: a clean machine needs one `uv sync` with network access to
warm the locked artifacts. After that the commands above run from that cache, and
repeating them with `--offline` checks that nothing reaches the network. Product
READMEs describe standalone operation. Requested Docker cases fail when prerequisites are absent;
default skips never count as passing execution evidence.

Use a separate branch or worktree when more than one person or agent is working.
Preserve prior work, and the review steps that sit in front of a release. Report
exact tests, changed files, limits and next tasks. Nothing here authorizes
publishing, cloud use or spending: a local passing test says the code works on
your machine, and nothing else.
