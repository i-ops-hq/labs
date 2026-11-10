"""Read-only guest supervisor; wraps bounded untrusted agent output."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate telemetry key")
        result[key] = value
    return result


def decode_event(line: bytes | bytearray) -> dict[str, Any] | None:
    try:
        result = json.loads(line, object_pairs_hook=unique_keys)
        # Re-serialization must also reject NaN/Infinity and pathological nesting.
        json.dumps(result, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError):
        return None
    return result if isinstance(result, dict) else None


def main() -> None:
    config: dict[str, Any] = json.loads(sys.stdin.buffer.readline(65537))
    Path("/workspace/protected.txt").write_text("SYNTHETIC_PROTECTED\n")
    Path("/workspace/service.json").write_text('{"calls":[],"mutations":[],"faults":[]}')
    # The fixture now exists and no agent code has run. This is the only moment at which a
    # baseline can be taken that the agent could not have influenced, so the host takes it
    # here, with its own verifier process, while this driver waits. The baseline is never
    # sent back into the container: this driver does not read the reply's contents, and the
    # agent process started below never sees it at all.
    print(json.dumps({"channel": "prepared"}), flush=True)
    if sys.stdin.buffer.readline(64).strip() != b'{"channel":"start"}':
        return
    spec_file = Path("/opt/crashlab/agent-spec.json")
    spec: dict[str, Any] = (
        json.loads(spec_file.read_bytes()) if spec_file.exists() else {"kind": "reference"}
    )
    arguments = [sys.executable, "-I", "/opt/crashlab/agent.py"]
    if spec["kind"] == "python_tools":
        arguments = [sys.executable, "-I", "/opt/crashlab/bootstrap.py"]
    elif spec["kind"] == "command":
        arguments = spec["argv"]
    process = subprocess.Popen(
        arguments,
        stdin=subprocess.PIPE if spec["kind"] != "command" else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1", "HOME": "/tmp"},
    )
    assert process.stdout is not None
    if process.stdin is not None:
        try:
            process.stdin.write(json.dumps(config).encode() + b"\n")
            process.stdin.close()
        except BrokenPipeError:
            # A child can close stdin or exit early. Observe its exit/output, not a harness crash.
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = bytearray()
    total = 0
    deadline = time.monotonic() + config["timeout"]
    timed_out = output_limited = invalid_output = False
    try:
        while selector.get_map() or process.poll() is None:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            for key, _ in selector.select(0.05):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > config["output_limit"]:
                    output_limited = True
                    break
                if spec["kind"] == "command":
                    # Process output is opaque, even when it resembles trusted events.
                    continue
                buffer.extend(chunk)
                while b"\n" in buffer:
                    line, _, remainder = buffer.partition(b"\n")
                    buffer[:] = remainder
                    data = decode_event(line)
                    if data is not None:
                        print(json.dumps({"channel": "agent_event", "data": data}), flush=True)
                    else:
                        invalid_output = True
            if output_limited:
                break
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
        process.stdout.close()
        selector.close()
    if buffer and spec["kind"] != "command":
        invalid_output = True
    print(
        json.dumps(
            {
                "channel": "ready",
                "exit_code": process.returncode,
                "timed_out": timed_out,
                "output_limited": output_limited,
                "invalid_output": invalid_output,
                "captured_bytes": total,
            }
        ),
        flush=True,
    )
    # Bounded lease leaves the state available for an independent verifier exec.
    time.sleep(15)


if __name__ == "__main__":
    main()
