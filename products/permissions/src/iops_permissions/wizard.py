"""The first run, for a person at a terminal. Scripts keep today's exact JSON error.

A bare `iops-permissions` prints a machine-readable `invalid_arguments` error. That is the correct
answer for a script and the worst available answer for a person meeting the tool, so this module
answers the second case and only the second case. One gate decides: a bare invocation where both
stdin and stdout are terminals, outside CI. Everything else keeps the behaviour it had, byte for
byte, because these commands run inside other agents' harnesses where a prompt is a hang, and a
hang is worse than an error.

Nothing here is a new dependency. Arrow keys are `termios`/`tty` on Unix and `msvcrt` on Windows,
both standard library; colour is escape codes. This product declares three packages, all of them
schema-related, and the locked dependency set is audited to keep it that way: a terminal-UI
framework inside a tool that reasons about authorization would be an embarrassing trade.

The terminal handling down to `answered` is a hand copy of one shared implementation, verified by
driving a real pseudo-terminal. It is copied rather than imported on purpose: the two products are
separate distributions with separate lockfiles and no code in common, and a third package in the
middle to hold eighty lines of terminal handling would be the coupling they exist without.
Copying means both carry the same bugs, which is the point - one fix ports by hand to the other.
Three of those bugs are already paid for and the comments below say which, so that nobody
"simplifies" the fix back out again.

What is this product's own is everything under `the first run` further down. The wizard reads,
computes and explains. It writes only files it has named first, in the current directory, after a
question whose preselected answer is the one that writes nothing.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .export import export_scenario
from .inputs import loads_action_request, loads_fixture_descriptor, loads_policy
from .simulator import evaluate
from .validation import ContractValidationError

CYAN, GREEN, DIM, BOLD, RED, OFF = (
    "\x1b[36m",
    "\x1b[32m",
    "\x1b[2m",
    "\x1b[1m",
    "\x1b[31m",
    "\x1b[0m",
)

CANCELLED_EXIT = 130

# The hint must describe what the control ACTUALLY does. This read "Esc go back", transcribed
# from another product's frame, while Esc here cancels the wizard and exits 130. A control whose
# hint describes something it does not do is a defect, not a cosmetic difference. If a later
# wizard grows a real go-back, the control and the hint change together.
HINT = "↑/↓ choose · Enter confirm · Esc cancel"
HINT_PLAIN = "up/down choose - Enter confirm - Esc cancel"

# This product's own vocabulary. None of these words is ever printed as a pass.
UNRESOLVED = ("failed", "skipped", "unsupported", "inconclusive", "error")


def survive_narrow_consoles() -> None:
    """Replace, rather than crash on, a character the console's encoding has no byte for."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if reconfigure is not None and encoding != "utf8":
            reconfigure(errors="replace")


def wants_a_wizard(argv: Sequence[str], env: Mapping[str, str] | None = None) -> bool:
    """True only for a bare invocation by a person at a terminal.

    BOTH streams are checked. stdout alone is a TTY under `cmd < file` and stdin alone is a TTY
    under `cmd | less`, and neither of those can drive a selection control. CI is checked because
    a prompt inside a pipeline is a hang, and a hang is worse than an error.
    """
    where = os.environ if env is None else env
    try:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):  # a closed or replaced stream
        return False
    return (
        not list(argv)[1:]
        and interactive
        and not where.get("CI")
        and where.get("TERM", "") != "dumb"
        and not where.get("IOPS_NO_WIZARD")
    )


def colour_is_welcome(env: Mapping[str, str] | None = None) -> bool:
    where = os.environ if env is None else env
    if where.get("NO_COLOR") or where.get("TERM", "") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def can_draw_blocks(stream: object | None = None) -> bool:
    """Whether the console has a byte for the wordmark's block character.

    Probed rather than assumed from the platform: a Windows terminal set to UTF-8 renders it fine
    and a Unix console under a narrow locale does not, so the platform is the wrong question.
    """
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "█".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _read_key(fd: int) -> str:
    """One keypress, as a word: up, down, enter, cancel, or the character itself.

    Reads with `os.read`, never `sys.stdin.read`, and the reason is NOT that the latter blocks.
    Measured through a PTY on CPython 3.12 / macOS: `sys.stdin.read(1)` returns its byte promptly.
    The real fault is quieter and worse. An arrow is three bytes, `ESC [ A`, delivered together;
    `sys.stdin.read(1)` takes the ESC and the TextIOWrapper swallows the remaining `[A` into its
    own buffer, where `select()` on the file descriptor cannot see it. The peek below then reports
    nothing pending and EVERY ARROW KEY IS READ AS A BARE ESC, so the control cancels instead of
    moving. `os.read` leaves the rest on the descriptor, where the peek can find it.

    Counterfactual this one with an ARROW, never with Enter. Enter is a single byte and passes
    either way, so a reviewer who mutates this line and presses Enter concludes the fix was
    unnecessary. Corrected 2026-11-05: an earlier version of this comment said it blocked, which
    came from changing two things at once while chasing a hang that was really a test harness not
    draining the pty master.

    The caller owns raw mode. Setting it per keypress leaves the terminal cooked between keys,
    which echoes whatever is typed while the screen is being redrawn.
    """
    # `sys.platform`, not `os.name`: mypy narrows the first and not the second, so under strict
    # settings the Windows branch gets checked against POSIX stubs and fails on msvcrt. Same
    # behaviour, six fewer type errors.
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows, not here
        import msvcrt

        key: str = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        if key in ("\r", "\n"):
            return "enter"
        if key in ("\x1b", "\x03"):
            return "cancel"
        return key

    import select

    def pending(timeout: float = 0.05) -> bool:
        return bool(select.select([fd], [], [], timeout)[0])

    pressed = os.read(fd, 1).decode("utf-8", "replace")
    if pressed == "\x1b":
        # An arrow arrives as ESC [ A/B, all three bytes together; a bare Esc arrives alone. The
        # only thing that tells them apart is whether more bytes are already waiting, so this
        # peeks first. Reading unconditionally is the obvious version and it hangs forever on a
        # bare Esc - found by driving a real PTY, because no scripted-stdin unit test reproduces
        # it: a fake stream returns "" at EOF where a terminal simply never answers.
        if not pending():
            return "cancel"
        if os.read(fd, 1) != b"[":
            return "cancel"
        if not pending():
            return ""
        return {b"A": "up", b"B": "down"}.get(os.read(fd, 1), "")
    if pressed in ("\r", "\n"):
        return "enter"
    if pressed == "\x03":
        return "cancel"
    return pressed


def choose(question: str, options: Sequence[str], default: int = 0) -> int | None:
    """Arrow-key radio list. Returns the chosen index, or None if the user cancelled.

    `default` is the index preselected, and it must be the SAFE option: Enter-mashing is the most
    common way a wizard is answered and it must not change anything on disk.
    """
    colour = colour_is_welcome()
    wide = can_draw_blocks()
    hint = HINT if wide else HINT_PLAIN
    cursor_mark, filled, hollow = ("›", "●", "○") if wide else (">", "(*)", "( )")

    def paint(text: str, code: str) -> str:
        return code + text + OFF if colour else text

    at = default
    print(paint(question, BOLD))
    for _ in options:
        print()
    print(paint(hint, DIM))

    def draw(at: int) -> None:
        # Up over the hint line and the options, then rewrite. Never clear the screen: the
        # collapsed answer lines below are a transcript, and clearing destroys it.
        sys.stdout.write("\x1b[" + str(len(options) + 1) + "A")
        for index, text in enumerate(options):
            here = index == at
            cursor = paint(cursor_mark, CYAN) if here else " " * len(cursor_mark)
            mark = paint(filled, CYAN) if here else hollow
            label = paint(text, BOLD) if here else text
            sys.stdout.write("\r\x1b[K" + cursor + " " + mark + " " + label + "\n")
        sys.stdout.write("\r\x1b[K" + paint(hint, DIM) + "\n")
        sys.stdout.flush()

    def erase() -> None:
        # Take the whole block back - question, options and hint - so the caller can print one
        # collapsed line in its place. Without this the menu stays on screen under its own
        # answer, and the scrollback becomes a wall of dead menus instead of a transcript.
        sys.stdout.write("\x1b[" + str(len(options) + 2) + "A\r\x1b[J")
        sys.stdout.flush()

    fd = sys.stdin.fileno()
    saved = None
    if sys.platform != "win32":
        import termios
        import tty

        saved = termios.tcgetattr(fd)
        # Raw mode BEFORE the first frame is drawn, not after it. `tty.setraw` is
        # `tcsetattr` with TCSAFLUSH, which DISCARDS whatever is already in the input queue,
        # so a key pressed between the question appearing on screen and this line was thrown
        # away and the wizard sat there looking frozen. Probed through a real pseudo-terminal
        # by writing the key the instant the frame appeared: it was lost on three runs in
        # eight. Drawing after the switch also makes the first frame consistent with every
        # redraw, which the key loop has always done in raw mode. Every line `draw` writes
        # begins with its own carriage return, which is what makes that safe.
        tty.setraw(fd)
    try:
        draw(at)
        return _loop(len(options), at, draw, erase, fd)
    finally:
        # Always, on every path, including an exception mid-draw. A command that exits leaving
        # echo off is a worse bug than anything this wizard was built to prevent.
        if saved is not None:
            import termios

            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _loop(
    count: int,
    at: int,
    draw: Callable[[int], None],
    erase: Callable[[], None],
    fd: int,
) -> int | None:
    """The key loop. `at` is passed INTO draw rather than closed over.

    It was a closure over `choose`'s `at` while this function rebound its own local of the same
    name, so the returned index moved and the highlight on screen never did. A PTY test that only
    asserts the return value cannot see that: it has to look at what was drawn.
    """
    while True:
        key = _read_key(fd)
        if key in ("up", "k"):
            at = (at - 1) % count
        elif key in ("down", "j"):
            at = (at + 1) % count
        elif key == "enter":
            erase()
            return at
        elif key == "cancel":
            erase()
            return None
        draw(at)


def answered(question: str, answer: str) -> None:
    """Collapse a question to one transcript line. States what is true, not what was clicked.

    Whether the terminal wants colour and whether its encoding has a byte for the tick are two
    different questions and need two different gates. This had one: the tick was chosen by the
    colour gate, so a colour terminal under a narrow locale printed a replacement character where
    the tick belongs. The bug could not be reached under pytest's capture, because capture turns
    colour off and takes the other branch, which is why the paired test below forces colour on.
    """
    colour = colour_is_welcome()
    tick = "✓" if can_draw_blocks() else "ok"
    tail = DIM + answer + OFF if colour else answer
    print((GREEN + tick + OFF if colour else tick) + " " + question + " " + tail)


# ---------------------------------------------------------------------------------------------
# The first run. Everything below is this product's own.
# ---------------------------------------------------------------------------------------------


def _paint(text: str, code: str) -> str:
    return code + text + OFF if colour_is_welcome() else text


def outcome(subject: str, result: str, detail: str) -> None:
    """One status line. A non-pass outcome always names itself, and never reads as a pass."""
    wide = can_draw_blocks()
    separator = " · " if wide else " - "
    if result == "ok":
        print(
            _paint("✓" if wide else "ok", GREEN) + " " + subject + _paint(separator + detail, DIM)
        )
        return
    if result not in UNRESOLVED:
        raise ValueError("unresolved outcome expected")
    failing = result in ("failed", "error")
    mark = ("×" if wide else "!!") if failing else ("·" if wide else "-")
    dash = " — " if wide else " -- "
    print(
        _paint(mark, RED if failing else DIM)
        + " "
        + subject
        + _paint(separator + result + dash + detail, DIM)
    )


def banner(wordmark: str, value: str, description: Sequence[str]) -> None:
    """The eyebrow, the wordmark, one value sentence, then at most three lines. Never more."""
    print(_paint("WELCOME TO", DIM))
    if can_draw_blocks():
        print(_paint("▐█▌", CYAN) + " " + _paint(wordmark, BOLD))
    else:
        # A mojibake wordmark is worse than no wordmark, so a narrow console gets bold caps.
        print(_paint(wordmark, BOLD))
    print()
    print(_paint(value, BOLD))
    print()
    for line in description:
        print(line)
    print()


def step(number: int, total: int, name: str) -> None:
    """The counter is always `n / total`, even when total is 1: it says how long this is."""
    print(_paint(str(number) + " / " + str(total), CYAN) + "  " + _paint(name, BOLD))
    print()


# The demonstration documents are embedded rather than read from `examples/`, which is not part of
# the wheel: an installed command has no example files on disk. Each one is copied verbatim from a
# reviewed example, and this product's own tests assert the decision each still produces.
POLICY: dict[str, Any] = {
    "schema_version": "0.1.0",
    "policy_id": "operations-demo",
    "agent_ids": ["python-ops-fixture", "coding-fixture"],
    "default_decision": "unknown",
    "rules": [
        {
            "rule_id": "workspace",
            "effect": "allowed",
            "action_kinds": ["filesystem"],
            "operations": ["read", "write", "delete"],
            "resource_types": ["file"],
            "resource_patterns": ["fixture://protected-workspace/*"],
        },
        {
            "rule_id": "protect-file",
            "effect": "denied",
            "action_kinds": ["filesystem"],
            "operations": ["write", "delete"],
            "resource_types": ["file"],
            "resource_patterns": ["fixture://protected-workspace/protected.txt"],
        },
        {
            "rule_id": "approve-delete",
            "effect": "requires_approval",
            "action_kinds": ["filesystem"],
            "operations": ["delete"],
            "resource_types": ["file"],
            "resource_patterns": ["fixture://protected-workspace/*"],
        },
    ],
}

FIXTURE: dict[str, Any] = {
    "schema_version": "0.1.0",
    "template": "protected-file-write",
    "fixture_id": "fixture://protected-workspace",
    "agent_id": "python-ops-fixture",
    "adapter_id": "reference-python-fixture",
    "protected_resource": "fixture://protected-workspace/protected.txt",
    "runtime": "python>=3.11",
}

# Order matters: the first entry is preselected. Every option here is a pure computation that
# writes nothing, so the most instructive one leads.
ACTIONS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "Write to a protected file",
        "denied",
        {
            "schema_version": "0.1.0",
            "request_id": "denied-request",
            "agent_id": "python-ops-fixture",
            "action": {
                "kind": "filesystem",
                "operation": "write",
                "resource": {
                    "type": "file",
                    "identifier": "fixture://protected-workspace/protected.txt",
                },
            },
        },
    ),
    (
        "Read a workspace file",
        "allowed",
        {
            "schema_version": "0.1.0",
            "request_id": "allowed-request",
            "agent_id": "python-ops-fixture",
            "action": {
                "kind": "filesystem",
                "operation": "read",
                "resource": {
                    "type": "file",
                    "identifier": "fixture://protected-workspace/readme.txt",
                },
            },
        },
    ),
    (
        "Delete a workspace file",
        "requires_approval",
        {
            "schema_version": "0.1.0",
            "request_id": "approval-request",
            "agent_id": "python-ops-fixture",
            "action": {
                "kind": "filesystem",
                "operation": "delete",
                "resource": {
                    "type": "file",
                    "identifier": "fixture://protected-workspace/scratch.txt",
                },
            },
        },
    ),
)

POLICY_FILE = "iops-permissions-policy.json"
ACTION_FILE = "iops-permissions-action.json"
SCENARIO_FILE = "iops-permissions-scenario.json"

VALUE = "Know what an agent may do before it runs."
DESCRIPTION = (
    "Read a declared policy, evaluate one action against it, and export",
    "the result as a scenario another tool can execute. The decision is",
    "computed locally by code. Nothing is executed and nothing is sent.",
)


def _write_new(directory: Path, name: str, document: Mapping[str, Any]) -> bool:
    """Write a named file, refusing to replace one that is already there."""
    try:
        with open(directory / name, "x", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        return False
    return True


def run(directory: Path | None = None) -> int:
    """The first run. Returns the process exit code."""
    survive_narrow_consoles()
    return _steps(directory if directory is not None else Path.cwd())


def _cancelled(question: str) -> int:
    answered(question, "cancelled, nothing was changed")
    return CANCELLED_EXIT


def _steps(here: Path) -> int:
    banner("PERMISSION SIMULATOR", VALUE, DESCRIPTION)

    step(1, 3, "Choose a policy")
    print("A demonstration policy with three rules is built into this command.")
    print("Writing a starter policy creates " + POLICY_FILE + " and")
    print(ACTION_FILE + " here, and changes nothing else on your machine.")
    print()
    question = "Which policy should this run use?"
    options = ("Write a starter policy here, then use it", "Use the built-in demonstration policy")
    picked = choose(question, options, default=1)
    if picked is None:
        return _cancelled(question)
    answered(question, options[picked])
    scaffolded: list[str] = []
    if picked == 0:
        for name, document in ((POLICY_FILE, POLICY), (ACTION_FILE, ACTIONS[0][2])):
            if _write_new(here, name, document):
                scaffolded.append(name)
            else:
                outcome(name, "skipped", "a file of that name is already here")
        if scaffolded:
            outcome("Starter files written", "ok", ", ".join(scaffolded))
    print()

    step(2, 3, "Evaluate one action")
    print("Each action is checked against the policy's rules by code, with no")
    print("model and no network involved. Nothing is executed and no file is")
    print("touched: the answer is what the declared policy says, and why.")
    print()
    question = "Which action should be evaluated?"
    labels = tuple(label for label, _, _ in ACTIONS)
    picked = choose(question, labels, default=0)
    if picked is None:
        return _cancelled(question)
    answered(question, labels[picked])
    label, _, request = ACTIONS[picked]
    try:
        policy = loads_policy(json.dumps(POLICY).encode())
        action = loads_action_request(json.dumps(request).encode())
        result = evaluate(policy, action, None)
    except ContractValidationError:
        outcome("Evaluation", "error", "the built-in documents did not validate")
        return 2
    decision = result.decision
    matched = ", ".join(result.matched_rule_ids) if result.matched_rule_ids else "no rule matched"
    outcome("Decision", "ok", decision)
    for explanation in result.to_dict()["explanations"]:
        print("  " + _paint(str(explanation), DIM))
    for limitation in result.limitations:
        print("  " + _paint(limitation, DIM))
    print()

    step(3, 3, "Export a scenario")
    exported = ""
    unresolved = ("skipped", "not reached")
    if decision != "denied":
        print("A scenario export pairs the decision with an isolated-test fixture.")
        print("This product ships one fixture, for the protected-file write, so")
        print("exporting the action you chose is unsupported rather than wrong.")
        print()
        unresolved = (
            "unsupported",
            "an export needs a fixture, and one ships only for the protected write",
        )
    else:
        print("An export writes a versioned scenario-definition file that Crash")
        print("Lab can run. It creates " + SCENARIO_FILE + " here and")
        print("changes nothing else. No network endpoint is reached.")
        print()
        question = "Export this as a Crash Lab scenario?"
        options = ("Yes, write the scenario file", "No, finish for now")
        picked = choose(question, options, default=1)
        if picked is None:
            return _cancelled(question)
        answered(question, options[picked])
        if picked == 1:
            unresolved = ("skipped", "not requested")
        else:
            fixture = loads_fixture_descriptor(json.dumps(FIXTURE).encode())
            export = export_scenario(policy, action, None, fixture)
            if export.scenario is None:
                status = export.status if export.status in UNRESOLVED else "error"
                unresolved = (status, export.reason_code)
            elif _write_new(here, SCENARIO_FILE, export.scenario):
                exported = SCENARIO_FILE
            else:
                unresolved = ("skipped", "a file named " + SCENARIO_FILE + " is already here")

    print()
    print(_paint("✓" if can_draw_blocks() else "ok", GREEN) + "  " + _paint("Your first run", BOLD))
    print()
    outcome("Policy", "ok", "written here" if scaffolded else "built-in demonstration, 3 rules")
    outcome("Action", "ok", label)
    outcome("Decision", "ok", decision + ", by " + matched)
    if exported:
        outcome("Scenario", "ok", exported)
    else:
        outcome("Scenario", unresolved[0], unresolved[1])
    print()
    print("Every decision above was computed from the declared policy alone.")
    # The one suggested command has to work. Naming the starter files when this run did not write
    # them - the default path, which writes nothing - would hand the user a command that fails on
    # a missing file, so those names appear only when both files are actually on disk.
    on_disk = (here / POLICY_FILE).is_file() and (here / ACTION_FILE).is_file()
    policy_name = POLICY_FILE if on_disk else "your-policy.json"
    action_name = ACTION_FILE if on_disk else "your-action.json"
    print("Point the command at your own policy and action to see the same answer:")
    print(
        "Try: "
        + _paint(
            '"iops-permissions evaluate --policy ' + policy_name + " --action " + action_name + '"',
            CYAN,
        )
    )
    return 0
