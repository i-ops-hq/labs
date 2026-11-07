"""Copy canonical data-only schemas into each independent distribution."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {"permissions": "iops_permissions", "crashlab": "iops_crashlab"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    args = parser.parse_args()
    canonical = ROOT / "contracts/schemas/v0.1"
    sources = sorted(canonical.glob("*.json"))
    if len(sources) != 4:
        parser.error("Expected exactly four canonical data schemas")
    drift = False
    for product, package in PRODUCTS.items():
        destination = ROOT / "products" / product / "src" / package / "_schemas/v0.1"
        destination.mkdir(parents=True, exist_ok=True) if not args.check else None
        if args.check and {p.name for p in destination.glob("*.json")} != {p.name for p in sources}:
            drift = True
        for source in sources:
            target = destination / source.name
            if args.check:
                if not target.is_file() or target.read_bytes() != source.read_bytes():
                    print(f"Schema drift: {target.relative_to(ROOT)}")
                    drift = True
            else:
                target.write_bytes(source.read_bytes())
    return int(drift)


if __name__ == "__main__":
    raise SystemExit(main())
