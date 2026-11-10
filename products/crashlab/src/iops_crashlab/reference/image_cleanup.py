"""Trusted image-build-only removal of unused package installers, before agent COPY."""

import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "linux" or os.getuid() != 0 or not Path("/.dockerenv").is_file():
        raise RuntimeError("image_build_only")
    library = Path("/usr/local/lib/python3.12")
    targets = [
        library / "site-packages/pip",
        library / "ensurepip",
        *sorted((library / "site-packages").glob("pip-*.dist-info")),
        *(Path("/usr/local/bin") / name for name in ("pip", "pip3", "pip3.12")),
    ]
    for target in targets:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
