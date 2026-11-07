"""Local permission analysis CLI. No agents or fixture references are executed."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, NoReturn

from . import __version__
from .export import export_scenario
from .inputs import loads_action_request, loads_fixture_descriptor, loads_policy
from .simulator import evaluate, inspect_manifest
from .validation import MAX_DOCUMENT_BYTES, ContractValidationError, loads_document
from .wizard import run as run_wizard
from .wizard import wants_a_wizard

EXIT_DECISIONS = {"allowed": 0, "denied": 3, "requires_approval": 4, "unknown": 5}


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default diagnostic reflects submitted argument values.
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


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="Simulate declared permissions locally; no execution.")
    parser.add_argument("--version", action="version", version="iops-permissions " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect an explicit capability manifest")
    inspect.add_argument("manifest")
    for name in ("evaluate", "export"):
        command = commands.add_parser(
            name,
            help="Evaluate declared policy"
            if name == "evaluate"
            else "Export a portable test scenario",
        )
        command.add_argument("--policy", required=True)
        command.add_argument("--action", required=True)
        command.add_argument("--manifest")
        if name == "export":
            command.add_argument("--fixture", help="Explicit isolated-test fixture descriptor")
            command.add_argument("--output", required=True)
        command.add_argument("--format", choices=("json", "text"), default="json")
    inspect.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _read(path: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
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


def _write_scenario(path: str, scenario: dict[str, Any]) -> None:
    destination = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".iops-permissions-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(scenario, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Linking provides atomic creation without overwriting an existing file or symlink.
        os.link(temporary, destination, follow_symlinks=False)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _emit(report: dict[str, Any], format_name: str) -> None:
    if format_name == "json":
        print(json.dumps(report, sort_keys=True))
    elif "decision" in report:
        print("Decision: " + report["decision"])
        print("Policy decision: " + report["policy_decision"])
        print("Matched rules: " + json.dumps(report["matched_rule_ids"]))
        for explanation in report["explanations"]:
            print("Reason: " + explanation)
        for limitation in report["limitations"]:
            print("Limit: " + limitation)
    elif "findings" in report:
        print("Manifest: " + json.dumps(report["manifest_id"]))
        print("Declared capabilities: " + str(report["capability_count"]))
        for finding in report["findings"]:
            print("Review: " + finding["description"])
            print("Limit: " + finding["limitation"])
        print("Coverage: incomplete effective permissions; no action executed.")
    else:
        for key, value in report.items():
            print(key + ": " + str(value))


def main(argv: list[str] | None = None) -> int:
    # A bare invocation by a person at a terminal gets the wizard; everything else, including a
    # bare invocation from a script, reaches the parser below and behaves exactly as before.
    arguments = sys.argv[1:] if argv is None else argv
    if wants_a_wizard([sys.argv[0], *arguments], os.environ):
        return run_wizard()
    args = _parser().parse_args(argv)
    manifest: dict[str, Any] | None
    try:
        if args.command == "inspect":
            manifest = loads_document("capability-manifest", _read(args.manifest))
            _emit(inspect_manifest(manifest), args.format)
            return 0
        policy = loads_policy(_read(args.policy))
        request = loads_action_request(_read(args.action))
        manifest = (
            loads_document("capability-manifest", _read(args.manifest)) if args.manifest else None
        )
        if args.command == "evaluate":
            result = evaluate(policy, request, manifest)
            _emit(result.to_dict(), args.format)
            return EXIT_DECISIONS[result.decision]
        fixture = loads_fixture_descriptor(_read(args.fixture)) if args.fixture else None
        exported = export_scenario(policy, request, manifest, fixture)
        report: dict[str, Any] = {
            "status": exported.status,
            "reason_code": exported.reason_code,
            "execution_status": exported.execution_status,
        }
        if exported.scenario is None:
            _emit(report, args.format)
            return 6
        _write_scenario(args.output, exported.scenario)
        report.update(scenario_id=exported.scenario["scenario_id"], mode=exported.scenario["mode"])
        _emit(report, args.format)
        return 0
    except ContractValidationError as error:
        print(
            json.dumps({"status": "error", "issues": [asdict(issue) for issue in error.issues]}),
            file=sys.stderr,
        )
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
