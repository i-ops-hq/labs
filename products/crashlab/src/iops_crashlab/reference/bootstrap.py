"""Guest-only bootstrap for cooperative Python agents; never imported on the host."""

import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, "/opt/crashlab")
import crashlab_tools  # type: ignore[import-not-found]  # noqa: E402


def main() -> None:
    config = json.loads(sys.stdin.buffer.readline(65537))
    spec = json.loads(Path("/opt/crashlab/agent-spec.json").read_bytes())
    crashlab_tools.configure(config)
    sys.path.insert(0, "/opt/agent")
    sys.argv = ["/opt/agent/" + spec["argv"][0]]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
