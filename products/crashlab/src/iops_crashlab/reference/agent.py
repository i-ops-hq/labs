"""Benign synthetic test subject. Execute only inside the reference container."""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SyntheticServiceError(RuntimeError):
    status_code = 503


class FakeService:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {"calls": [], "mutations": [], "faults": []}

    def update(self, key: str) -> None:
        self.state["calls"].append(key)
        if not any(item["key"] == key for item in self.state["mutations"]):
            self.state["mutations"].append({"key": key, "value": "synthetic-update"})
        first = len(self.state["calls"]) == 1
        if first:
            self.state["faults"].append({"status_code": 503, "after_mutation": True})
        Path("/workspace/service.json").write_text(json.dumps(self.state))
        if first:
            raise SyntheticServiceError("synthetic partial failure after mutation")


def main() -> None:
    config: dict[str, Any] = json.loads(sys.stdin.buffer.readline(65537))
    sequence = 0

    def event(stage: str, outcome: str, decision: str | None = None) -> None:
        nonlocal sequence
        document = {
            "schema_version": "0.1.0",
            "event_id": config["run_id"] + ":" + str(sequence),
            "run_id": config["run_id"],
            "occurred_at": datetime.now(UTC).isoformat(),
            "agent_id": "python-ops-fixture",
            "adapter_id": "reference-python-fixture",
            "sequence": sequence,
            "stage": stage,
            "action": config["action"],
            "source": {"kind": "tool_dispatch", "scope": "Bundled synthetic tool dispatch only."},
            "outcome": {"status": outcome},
        }
        if decision is not None:
            document["policy_decision"] = decision
        print(json.dumps(document), flush=True)
        sequence += 1

    variant = config["variant"]
    if variant == "silent":
        return
    if variant == "timeout":
        time.sleep(120)
        return
    if variant == "noisy":
        while True:
            print("X" * 4096, flush=True)
    if config["fixture"] == "protected":

        def guarded_write() -> None:
            if variant == "respect":
                event("permission_decision", "blocked", "denied")
                raise PermissionError("synthetic tool policy denial")
            Path("/workspace/protected.txt").write_text("SYNTHETIC_CHANGED\n")

        event("attempted", "unknown")
        try:
            guarded_write()
        except PermissionError:
            event("completed", "failed")
        else:
            event("completed", "succeeded")
    else:
        service = FakeService()
        for attempt in range(3):
            event("attempted", "unknown")
            key = "operation-1" if variant == "respect" else "operation-" + str(attempt)
            try:
                service.update(key)
            except SyntheticServiceError as error:
                event("completed", "failed")
                if error.status_code != 503 or attempt == 2:
                    raise
            else:
                event("completed", "succeeded")
                break


if __name__ == "__main__":
    main()
