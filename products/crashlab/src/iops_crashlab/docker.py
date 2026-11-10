"""Bounded local Docker control. No arbitrary scenario command construction."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agents import AgentBundle


class RunnerError(RuntimeError):
    """Static reason only; daemon stderr and host paths are never reflected."""


class RunnerUnsupported(RunnerError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: bytes


def command(
    args: list[str],
    *,
    timeout: float = 10,
    limit: int = 131072,
    data: bytes | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        if data is not None:
            assert process.stdin is not None
            process.stdin.write(data)
            process.stdin.close()
        while selector.get_map() or process.poll() is None:
            if time.monotonic() >= deadline:
                raise RunnerError("docker_command_timeout")
            for key, _ in selector.select(0.05):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(chunk)
                    if len(output) > limit:
                        raise RunnerError("docker_command_output_limit")
        return CommandResult(process.wait(timeout=1), bytes(output))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        process.stdout.close()
        selector.close()


def bundle() -> dict[str, bytes]:
    root = files(__package__).joinpath("reference")
    return {
        name: root.joinpath(name).read_bytes()
        for name in (
            "agent.py",
            "driver.py",
            "verifier.py",
            "base-image.txt",
            "bootstrap.py",
            "crashlab_tools.py",
            "image_cleanup.py",
            "dockerfile-template.txt",
            "LICENSE.txt",
            "NOTICE.txt",
        )
    }


def bundle_hash() -> str:
    digest = hashlib.sha256()
    for name, content in sorted(bundle().items()):
        digest.update(name.encode() + b"\0" + content)
    return digest.hexdigest()


def image_tag(agent: AgentBundle | None = None) -> str:
    if agent is None:
        return "iops-crashlab-reference:" + bundle_hash()[:16]
    return "iops-crashlab-agent:" + image_fingerprint(agent)[:32]


def image_fingerprint(agent: AgentBundle) -> str:
    return hashlib.sha256((bundle_hash() + ":" + agent.digest()).encode()).hexdigest()


class Docker:
    def __init__(self) -> None:
        executable = shutil.which("docker")
        if executable is None:
            raise RunnerUnsupported("docker_missing")
        if any(
            os.environ.get(name)
            for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
        ):
            raise RunnerUnsupported("docker_endpoint_override_not_supported")
        self.env = dict(os.environ)
        self.env.pop("BUILDX_BUILDER", None)
        # Explicitly use the local Engine build API rather than a configured remote buildx builder.
        self.env["DOCKER_BUILDKIT"] = "0"
        try:
            context = command(
                [executable, "context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
                env=self.env,
            )
            endpoint = json.loads(context.output)
        except (OSError, ValueError, RunnerError):
            raise RunnerUnsupported("docker_context_unavailable") from None
        if (
            context.returncode
            or not isinstance(endpoint, str)
            or not endpoint.startswith("unix:///")
        ):
            raise RunnerUnsupported("remote_docker_not_supported")
        self.prefix = [executable, "--host", endpoint]
        try:
            info = self.json(["info", "--format", "{{json .}}"])
        except RunnerError:
            raise RunnerUnsupported("docker_engine_unavailable") from None
        if (
            info.get("OSType") != "linux"
            or info.get("CgroupVersion") != "2"
            or not info.get("MemoryLimit")
            or not info.get("PidsLimit")
            or not any(
                str(value).startswith("name=seccomp") for value in info.get("SecurityOptions", [])
            )
        ):
            raise RunnerUnsupported("linux_seccomp_required")
        version = re.fullmatch(
            r"([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})(?:[-+].{0,40})?",
            str(info.get("ServerVersion", "")),
        )
        self.version = version.group(1) if version else "unknown"

    def call(self, args: list[str], **kwargs: Any) -> CommandResult:
        try:
            result = command([*self.prefix, *args], env=self.env, **kwargs)
        except OSError:
            raise RunnerError("docker_command_unavailable") from None
        if result.returncode:
            raise RunnerError("docker_command_failed")
        return result

    def json(self, args: list[str]) -> Any:
        try:
            return json.loads(self.call(args).output)
        except (ValueError, UnicodeError):
            raise RunnerError("docker_response_invalid") from None

    def image(self, agent: AgentBundle | None = None) -> str:
        try:
            inspected = self.json(["image", "inspect", image_tag(agent)])[0]
        except (RunnerError, IndexError, TypeError):
            raise RunnerUnsupported("reference_image_not_prepared") from None
        identifier = inspected.get("Id", "")
        if (
            not re.fullmatch(r"sha256:[a-f0-9]{64}", identifier)
            or inspected.get("Config", {}).get("Labels", {}).get("org.iops.crashlab.bundle-sha256")
            != bundle_hash()
            or (
                agent is not None
                and inspected.get("Config", {})
                .get("Labels", {})
                .get("org.iops.crashlab.agent-sha256")
                != agent.digest()
            )
        ):
            raise RunnerUnsupported("reference_image_identity_mismatch")
        return str(identifier)


def prepare_reference_image(*, pull: bool = False) -> dict[str, str]:
    return _prepare_image(None, pull=pull)


def prepare_agent_image(agent: AgentBundle, *, pull: bool = False) -> dict[str, str]:
    """Copy selected files after trusted offline image cleanup; never run agent code at build."""
    return _prepare_image(agent, pull=pull)


def _prepare_image(agent: AgentBundle | None, *, pull: bool) -> dict[str, str]:
    docker = Docker()
    assets = bundle()
    base = assets["base-image.txt"].decode().strip()
    if not re.fullmatch(r"python@sha256:[a-f0-9]{64}", base):
        raise RunnerError("invalid_bundled_base_image")
    if pull:
        docker.call(["pull", base], timeout=120)
    else:
        try:
            docker.call(["image", "inspect", base])
        except RunnerError:
            raise RunnerUnsupported("pinned_base_image_missing_use_prepare_pull") from None
    with tempfile.TemporaryDirectory(prefix="iops-crashlab-build-") as directory:
        root = Path(directory)
        for name, content in assets.items():
            if name.endswith(".py") or name in {"LICENSE.txt", "NOTICE.txt"}:
                (root / name).write_bytes(content)
        extra = ""
        if agent is not None:
            selected = root / "selected"
            selected.mkdir()
            for name, content in agent.files:
                destination = selected / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o444)
            (root / "agent-spec.json").write_text(json.dumps(agent.configuration()))
            extra = "COPY selected/ /opt/agent/\nCOPY agent-spec.json /opt/crashlab/\n"
        (root / "Dockerfile").write_text(
            assets["dockerfile-template.txt"].decode().format(base=base, agent_copy=extra)
        )
        arguments = [
            "build",
            "--pull=false",
            "--network=none",
            "--tag",
            image_tag(agent),
            "--label",
            "org.iops.crashlab.bundle-sha256=" + bundle_hash(),
        ]
        if agent is not None:
            arguments += ["--label", "org.iops.crashlab.agent-sha256=" + agent.digest()]
        docker.call([*arguments, str(root)], timeout=120)
    return {
        "image_id": docker.image(agent) if agent is not None else docker.image(),
        "base_image": base,
        "bundle_sha256": bundle_hash(),
        "engine_version": docker.version,
        **({"agent_bundle_sha256": agent.digest()} if agent is not None else {}),
    }
