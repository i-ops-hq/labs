"""Standalone controlled-reference CLI with redacted output and explicit provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any, NoReturn

from ._version import VERSION
from .agents import load_agent
from .docker import RunnerError, RunnerUnsupported, prepare_agent_image, prepare_reference_image
from .runner import run_scenario
from .validation import MAX_DOCUMENT_BYTES, ContractValidationError, ValidationIssue, loads_document
from .wizard import run as run_wizard
from .wizard import wants_a_wizard

BUILTINS = ("protected-file-write", "fake-api-partial-failure", "execution-budget")
EXIT_CODES = {
    "passed": 0,
    "failed": 1,
    "error": 2,
    "inconclusive": 3,
    "unsupported": 4,
    "skipped": 5,
}


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "invalid_arguments",
                    "message": "Invalid arguments; use --help for supported usage.",
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)


def read_regular(path: str | Path) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_DOCUMENT_BYTES:
            raise OSError("Input must be a bounded regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read(MAX_DOCUMENT_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_scenario(source: str) -> dict[str, Any]:
    if source.startswith("builtin:"):
        name = source.removeprefix("builtin:")
        if name not in BUILTINS:
            raise ContractValidationError(
                (
                    ValidationIssue(
                        "unknown_builtin", "$", "The requested built-in scenario is not supported."
                    ),
                )
            )
        data = files(__package__).joinpath("_scenarios", name + ".json").read_bytes()
    else:
        data = read_regular(source)
    return loads_document("scenario-definition", data)


def verify_artifacts(result: dict[str, Any], directory: Path) -> bool:
    expected = {
        "events": "events.jsonl",
        "state": "state.json",
        "execution": "execution.json",
        "report": "report.md",
    }
    if not result["artifacts"]:
        return False
    for artifact in result["artifacts"]:
        filename = expected.get(artifact["artifact_id"])
        if (
            filename is None
            or artifact["locator"] != f"artifact://{result['run_id']}/{filename}"
            or "sha256" not in artifact
        ):
            return False
        try:
            data = read_regular(directory / filename)
        except OSError:
            return False
        if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            return False
    return True


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "verdict": result["verdict"],
        "provenance": result["provenance"],
        "run_id": result["run_id"],
        "scenario_id": result["scenario_id"],
        "assertions": [
            {"assertion_id": item["assertion_id"], "outcome": item["outcome"]}
            for item in result["assertions"]
        ],
        "authenticity": "not_authenticated",
        "limit": "The verdict is scoped to defined observations, not global agent safety.",
    }


def emit(report: dict[str, Any], format_name: str) -> None:
    if format_name == "json":
        print(json.dumps(report, sort_keys=True))
    else:
        if report.get("provenance") in {"mock", "reference"}:
            print("ILLUSTRATIVE / SIMULATED RESULT — NOT EXECUTED EVIDENCE")
        for key, value in report.items():
            print(key + ": " + json.dumps(value, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = SafeParser(description="Controlled local agent tests in restricted Docker containers.")
    root.add_argument("--version", action="version", version="iops-crashlab " + VERSION)
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Build the pinned local reference image")
    prepare.add_argument(
        "--pull", action="store_true", help="Download the pinned official base image"
    )
    prepare.add_argument("--agent", help="Explicit local agent bundle definition")
    describe = commands.add_parser("describe-agent", help="Describe bounded adapter visibility")
    describe.add_argument("agent")
    commands.add_parser("examples", help="List packaged standalone scenarios")
    validate = commands.add_parser("validate", help="Check shape and reference-runner requirements")
    validate.add_argument("scenario")
    validate.add_argument("--agent", help="Negotiate against an explicit agent bundle")
    test = commands.add_parser("test", help="Execute a supported disposable reference scenario")
    test.add_argument("scenario")
    test.add_argument("--agent", help="Run an explicitly prepared agent bundle inside Docker")
    test.add_argument("--output", required=True, help="New private local report directory")
    test.add_argument(
        "--reference-variant",
        choices=("respect", "violate", "timeout", "noisy", "silent"),
        default="respect",
    )
    test.add_argument("--skip", action="store_true", help="Record deliberate nonexecution")
    test.add_argument("--format", choices=("json", "text"), default="json")
    report = commands.add_parser(
        "report", help="Read a validated result without trusting its claims"
    )
    report.add_argument("result")
    report.add_argument("--verify-artifacts", action="store_true")
    report.add_argument("--format", choices=("json", "text"), default="text")
    return root


def main(argv: list[str] | None = None) -> int:
    # A bare invocation by a person at a terminal gets the wizard; everything else, including a
    # bare invocation from a script, reaches the parser below and behaves exactly as before.
    arguments = sys.argv[1:] if argv is None else argv
    if wants_a_wizard([sys.argv[0], *arguments], os.environ):
        return run_wizard()
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            agent = load_agent(args.agent) if args.agent else None
            emit(
                prepare_agent_image(agent, pull=args.pull)
                if agent
                else prepare_reference_image(pull=args.pull),
                "json",
            )
            return 0
        if args.command == "describe-agent":
            emit(load_agent(args.agent).describe(), "json")
            return 0
        if args.command == "examples":
            emit({"scenarios": ["builtin:" + name for name in BUILTINS]}, "json")
            return 0
        if args.command == "report":
            result = loads_document("evidence-result", read_regular(args.result))
            report = summarize(result)
            if args.verify_artifacts:
                good = verify_artifacts(result, Path(args.result).parent)
                report["artifact_integrity"] = "verified" if good else "not_verified"
                emit(report, args.format)
                return 0 if good else 2
            emit(report, args.format)
            return 0
        scenario = load_scenario(args.scenario)
        agent = load_agent(args.agent) if args.agent else None
        if args.command == "validate":
            from .catalog import negotiate

            negotiate(scenario, "respect", agent)
            emit(
                {
                    "schema_valid": True,
                    "adapter_requirements": "supported",
                    "runtime_status": "not_checked",
                },
                "json",
            )
            return 0
        result = run_scenario(
            scenario, args.output, variant=args.reference_variant, skip=args.skip, agent=agent
        )
        emit(summarize(result), args.format)
        return EXIT_CODES[result["verdict"]]
    except ContractValidationError as error:
        print(
            json.dumps({"status": "error", "issues": [asdict(issue) for issue in error.issues]}),
            file=sys.stderr,
        )
        return 2
    except RunnerUnsupported as error:
        print(json.dumps({"status": "unsupported", "reason_code": str(error)}))
        return 4
    except RunnerError as error:
        print(json.dumps({"status": "error", "reason_code": str(error)}), file=sys.stderr)
        return 2
    except (OSError, UnicodeError):
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "local_io_error",
                    "message": "A local input/output operation could not be completed.",
                }
            ),
            file=sys.stderr,
        )
        return 2
