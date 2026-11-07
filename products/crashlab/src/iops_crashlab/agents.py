"""Explicit, bounded agent bundles. Reading a bundle never imports its code."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._version import VERSION
from .docker import RunnerError
from .validation import _check_tree

MAX_FILE_BYTES = 1_048_576
MAX_BUNDLE_BYTES = 4_194_304
ADAPTERS = {"python_tools": "custom-python-tools", "command": "isolated-command"}
PYTHON_FEATURES = frozenset(
    {"launch", "observe", "pre_action_intercept", "fault_injection", "stop", "filesystem_effects"}
)
COMMAND_FEATURES = frozenset({"launch", "observe", "stop", "filesystem_effects"})


def _relative(name: object) -> bool:
    return (
        isinstance(name, str)
        and len(name) <= 200
        and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", part) for part in name.split("/"))
    )


def read_bounded_at(root: int, name: str) -> bytes:
    """Open every relative component without following links, including parent directories."""
    if not _relative(name):
        raise RunnerError("agent_file_path_invalid")
    directory = os.dup(root)
    descriptor = -1
    try:
        parts = name.split("/")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FILE_BYTES:
            raise RunnerError("agent_file_not_bounded_regular")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise RunnerError("agent_file_not_bounded_regular")
        return data
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


@dataclass(frozen=True)
class AgentBundle:
    agent_id: str
    kind: str
    argv: tuple[str, ...]
    files: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        if (
            type(self.agent_id) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.agent_id) is None
            or type(self.kind) is not str
            or self.kind not in ADAPTERS
            or type(self.argv) is not tuple
            or not 1 <= len(self.argv) <= 32
            or any(
                type(value) is not str
                or not 1 <= len(value) <= 1024
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
                for value in self.argv
            )
            or type(self.files) is not tuple
            or not 1 <= len(self.files) <= 64
        ):
            raise RunnerError("agent_definition_invalid")
        names: set[str] = set()
        total = 0
        for item in self.files:
            if type(item) is not tuple or len(item) != 2:
                raise RunnerError("agent_definition_invalid")
            name, content = item
            if (
                not _relative(name)
                or name in names
                or type(content) is not bytes
                or len(content) > MAX_FILE_BYTES
            ):
                raise RunnerError("agent_definition_invalid")
            names.add(name)
            total += len(content)
        if total > MAX_BUNDLE_BYTES or any(
            name.startswith(other + "/") for name in names for other in names
        ):
            raise RunnerError("agent_definition_invalid")
        if self.kind == "python_tools" and (
            len(self.argv) != 1 or self.argv[0] not in names or not self.argv[0].endswith(".py")
        ):
            raise RunnerError("python_agent_entry_invalid")
        if self.kind == "command" and self.argv[0] not in {
            "/bin/sh",
            "/usr/local/bin/python",
            "/usr/local/bin/python3",
        }:
            raise RunnerError("command_interpreter_not_supported")

    @property
    def adapter_id(self) -> str:
        return ADAPTERS[self.kind]

    def configuration(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "agent_id": self.agent_id,
            "adapter_id": self.adapter_id,
            "argv": list(self.argv),
        }

    def digest(self) -> str:
        digest = hashlib.sha256(json.dumps(self.configuration(), sort_keys=True).encode())
        for name, content in sorted(self.files):
            digest.update(name.encode() + b"\0" + len(content).to_bytes(8, "big") + content)
        return digest.hexdigest()

    def describe(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "version": VERSION,
            "agent_id": self.agent_id,
            "runtime": "python>=3.11",
            "features": sorted(
                PYTHON_FEATURES if self.kind == "python_tools" else COMMAND_FEATURES
            ),
            "observability": "tool_dispatch_instrumented"
            if self.kind == "python_tools"
            else "process_boundary",
            "limitations": [
                "Cooperative instrumentation and process status omit uninstrumented actions.",
                "Guest code shares the verifier kernel and UID; it is not a hostile-code sandbox.",
            ],
        }


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def load_agent(path: str | Path) -> AgentBundle:
    """Snapshot explicitly selected files relative to a config; never execute on the host."""
    source = Path(path)
    try:
        directory = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise RunnerError("agent_file_unavailable") from None
    try:
        try:
            data = read_bounded_at(directory, source.name)
            raw = json.loads(data, object_pairs_hook=_unique)
            _check_tree(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise RunnerError("agent_definition_invalid_json") from None
        if (
            type(raw) is not dict
            or set(raw) - {"schema_version", "agent_id", "kind", "argv", "files", "extensions"}
            or not {"schema_version", "agent_id", "kind", "argv", "files"} <= set(raw)
            or raw["schema_version"] != "0.1.0"
            or type(raw["files"]) is not list
            or not 1 <= len(raw["files"]) <= 64
            or any(not _relative(name) for name in raw["files"])
            or type(raw["argv"]) is not list
            or ("extensions" in raw and type(raw["extensions"]) is not dict)
        ):
            raise RunnerError("agent_definition_invalid")
        # Validate shape and aggregate limits before retaining file bytes.
        AgentBundle(
            raw["agent_id"],
            raw["kind"],
            tuple(raw["argv"]),
            tuple((name, b"") for name in raw["files"]),
        )
        selected: list[tuple[str, bytes]] = []
        total = 0
        for name in raw["files"]:
            content = read_bounded_at(directory, name)
            total += len(content)
            if total > MAX_BUNDLE_BYTES:
                raise RunnerError("agent_bundle_size_limit")
            selected.append((name, content))
        return AgentBundle(raw["agent_id"], raw["kind"], tuple(raw["argv"]), tuple(selected))
    except OSError:
        raise RunnerError("agent_file_unavailable") from None
    finally:
        os.close(directory)
