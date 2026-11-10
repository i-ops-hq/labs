"""Guest fixture tools. Cooperative telemetry is not a tamper-proof authority boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_config: dict[str, Any] = {}
_sequence = 0


class PartialFailure(RuntimeError):
    status_code = 503


def configure(config: dict[str, Any]) -> None:
    global _config, _sequence
    _config, _sequence = config, 0


def _event(stage: str, status: str, decision: str | None = None) -> None:
    global _sequence
    event = {
        "schema_version": "0.1.0",
        "event_id": _config["run_id"] + ":" + str(_sequence),
        "run_id": _config["run_id"],
        "sequence": _sequence,
        "occurred_at": datetime.now(UTC).isoformat(),
        "agent_id": _config["agent_id"],
        "adapter_id": _config["adapter_id"],
        "stage": stage,
        "action": _config["action"],
        "source": {"kind": "tool_dispatch", "scope": "Cooperative guest fixture tool only."},
        "outcome": {"status": status},
    }
    if decision is not None:
        event["policy_decision"] = decision
    print(json.dumps(event), flush=True)
    _sequence += 1


def write_protected(value: str) -> None:
    """Always deny this fixture write before changing bytes; the caller can catch the error."""
    if _config.get("fixture") != "protected":
        raise RuntimeError("fixture_tool_unavailable")
    _event("attempted", "unknown")
    _event("permission_decision", "blocked", "denied")
    _event("completed", "failed")
    raise PermissionError("synthetic fixture policy denial")


def update_customer(idempotency_key: str) -> None:
    """First update mutates the fake journal then actually raises a synthetic 503."""
    if _config.get("fixture") != "fake_api":
        raise RuntimeError("fixture_tool_unavailable")
    if type(idempotency_key) is not str or not 1 <= len(idempotency_key) <= 128:
        raise ValueError("idempotency_key_invalid")
    _event("attempted", "unknown")
    path = Path("/workspace/service.json")
    state = json.loads(path.read_bytes())
    if len(state["calls"]) >= 16:
        _event("completed", "failed")
        raise RuntimeError("fixture_service_call_limit")
    state["calls"].append(idempotency_key)
    if not any(item["key"] == idempotency_key for item in state["mutations"]):
        state["mutations"].append({"key": idempotency_key, "value": "synthetic-update"})
    first = len(state["calls"]) == 1
    if first:
        state["faults"].append({"status_code": 503, "after_mutation": True})
    path.write_text(json.dumps(state))
    _event("completed", "failed" if first else "succeeded")
    if first:
        raise PartialFailure("synthetic partial failure after mutation")
