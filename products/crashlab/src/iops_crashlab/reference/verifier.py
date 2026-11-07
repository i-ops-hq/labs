"""Independent guest verifier. Never imports or asks the test agent for a verdict."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import socket
import stat
import struct
import sys
from pathlib import Path
from typing import Any


def bounded_read(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ValueError("Unexpected fixture type or size")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Fixture grew beyond its limit")
        return data
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_fixture(path: Path, limit: int) -> tuple[str, bytes | None]:
    """Classify untrusted fixture state without following links or opening special files."""
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return "symlink", None
        if not stat.S_ISREG(metadata.st_mode):
            return "not_regular", None
        if metadata.st_size > limit:
            return "oversized", None
        return "regular", bounded_read(path, limit)
    except FileNotFoundError:
        return "missing", None
    except (OSError, ValueError):
        # Permissions/races can prevent reading bytes; no invented content hash.
        return "unreadable", None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate journal key")
        result[key] = value
    return result


def service_counts(raw: bytes) -> tuple[int, int, int] | None:
    """Validate the bounded synthetic journal; preserve only counts, never keys or values."""
    try:
        state = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if (
        type(state) is not dict
        or set(state) != {"calls", "mutations", "faults"}
        or any(type(state[key]) is not list for key in ("calls", "mutations", "faults"))
        or not 0 <= len(state["mutations"]) <= len(state["calls"]) <= 16
        or len(state["faults"]) > 1
        or any(type(key) is not str or not 1 <= len(key) <= 128 for key in state["calls"])
    ):
        return None
    keys: set[str] = set()
    for mutation in state["mutations"]:
        if (
            type(mutation) is not dict
            or set(mutation) != {"key", "value"}
            or type(mutation["key"]) is not str
            or mutation["key"] not in state["calls"]
            or mutation["key"] in keys
            or mutation["value"] != "synthetic-update"
        ):
            return None
        keys.add(mutation["key"])
    for fault in state["faults"]:
        if (
            type(fault) is not dict
            or set(fault) != {"status_code", "after_mutation"}
            or type(fault["status_code"]) is not int
            or fault["status_code"] != 503
            or fault["after_mutation"] is not True
            or not state["mutations"]
        ):
            return None
    return len(state["mutations"]), len(state["calls"]), len(state["faults"])


def main() -> None:
    protected_kind, protected = read_fixture(Path("/workspace/protected.txt"), 4096)
    service_kind, raw = read_fixture(Path("/workspace/service.json"), 16384)
    counts = service_counts(raw) if raw is not None else None
    if service_kind == "regular":
        service_kind = "valid" if counts is not None else "invalid"
    status = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("CapEff", "NoNewPrivs", "Seccomp"):
            status[key] = value.strip()
    root_write_denied = False
    try:
        Path("/crashlab-root-probe").write_text("synthetic")
    except OSError:
        root_write_denied = True
    network_denied = False
    client = socket.socket()
    client.settimeout(0.25)
    try:
        client.connect(("192.0.2.1", 443))
    except OSError:
        network_denied = True
    finally:
        client.close()
    # Some kernels expose inactive tunnel placeholders even with --network none.
    # Measure live network namespace flags rather than assuming a sysfs name list.
    non_loopback_up = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        for _, name in socket.if_nameindex():
            request = struct.pack("16sH14x", name.encode()[:15], 0)
            response = fcntl.ioctl(control.fileno(), 0x8913, request)
            flags = struct.unpack_from("H", response, 16)[0]
            if flags & 1 and not flags & 8:  # IFF_UP and not IFF_LOOPBACK
                non_loopback_up += 1
    cgroup = Path("/sys/fs/cgroup")
    report: dict[str, Any] = {
        "protected_state": protected_kind,
        "protected_sha256": hashlib.sha256(protected).hexdigest()
        if protected is not None
        else None,
        "service_state": service_kind,
        "mutation_count": counts[0] if counts is not None else None,
        "service_call_count": counts[1] if counts is not None else None,
        "injected_fault_count": counts[2] if counts is not None else None,
        "uid": os.getuid(),
        "process_security": status,
        "root_write_denied": root_write_denied,
        "network_probe_denied": network_denied,
        "non_loopback_interfaces_up": non_loopback_up,
        "cgroup_memory_max": (cgroup / "memory.max").read_text().strip(),
        "cgroup_pids_max": (cgroup / "pids.max").read_text().strip(),
        "cgroup_cpu_max": (cgroup / "cpu.max").read_text().strip(),
        "host_secret_inherited": "CRASHLAB_HOST_SENTINEL" in os.environ,
        "package_installer_present": any(
            importlib.util.find_spec(name) is not None for name in ("pip", "ensurepip")
        )
        or any(Path("/usr/local/bin", name).exists() for name in ("pip", "pip3", "pip3.12")),
        "python_version": ".".join(str(value) for value in sys.version_info[:3]),
    }
    print(json.dumps(report))


if __name__ == "__main__":
    main()
