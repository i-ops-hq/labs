"""Copy canonical data-only schemas into each independent distribution."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {"permissions": "iops_permissions", "crashlab": "iops_crashlab"}
# Each contract version is its own directory; a reader selects one by the document's
# own schema_version. Adding a version here is the only way a copy may grow.
VERSIONS = {"v0.1": 4, "v0.2": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    args = parser.parse_args()
    drift = False
    for version, count in VERSIONS.items():
        canonical = ROOT / "contracts/schemas" / version
        sources = sorted(canonical.glob("*.json"))
        if len(sources) != count:
            parser.error(f"Expected exactly {count} canonical data schemas in {version}")
        for product, package in PRODUCTS.items():
            destination = ROOT / "products" / product / "src" / package / "_schemas" / version
            if not args.check:
                destination.mkdir(parents=True, exist_ok=True)
            elif {p.name for p in destination.glob("*.json")} != {p.name for p in sources}:
                print(f"Schema drift: {destination.relative_to(ROOT)} file set")
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
