"""The first run, for a person at a terminal. Scripts keep today's exact JSON error.

A bare `iops-crashlab` prints a machine-readable `invalid_arguments` error. That is the correct
answer for a script and the worst available answer for a person meeting the tool, so this module
answers the second case and only the second case. One gate decides: a bare invocation where both
stdin and stdout are terminals, outside CI. Everything else keeps the behaviour it had, byte for
byte, because these commands run inside other agents' harnesses where a prompt is a hang, and a
hang is worse than an error.

Nothing here is a new dependency. Arrow keys are `termios`/`tty` on Unix and `msvcrt` on Windows,
both standard library; colour is escape codes. This product declares three packages, all of them
schema-related, and the locked dependency set is audited to keep it that way: a terminal-UI
framework inside a tool that tests agents under fault would be an embarrassing trade.

The terminal handling down to `answered` is a hand copy of one shared implementation, verified by
driving a real pseudo-terminal. It is copied rather than imported on purpose: the two products are
separate distributions with separate lockfiles and no code in common, and a third package in the
middle to hold eighty lines of terminal handling would be the coupling they exist without.
Copying means both carry the same bugs, which is the point - one fix ports by hand to the other.
Three of those bugs are already paid for and the comments below say which, so that nobody
"simplifies" the fix back out again. The copy is byte-identical to the one in `iops_permissions`.

What is this product's own is everything under `the first run` further down. Two things there touch
the machine, and both are named on screen before they are offered: pulling the pinned official base
image by digest, and creating one report directory in the current directory. The preselected answer
to each does neither. An actual run reports its verdict in this product's own vocabulary and exits
with that verdict's declared code, so a skipped, unsupported or inconclusive run can never be read
here as a pass.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

from .docker import RunnerError, RunnerUnsupported, prepare_reference_image
from .runner import run_scenario
from .validation import ContractValidationError, loads_document

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
        tick = _paint("✓" if wide else "ok", GREEN)
        print(tick + " " + subject + _paint(separator + detail, DIM))
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


# Kept here rather than imported from `cli`, which imports this module: the two would be a cycle.
# This product's own tests assert both of these still agree with the command line's tables.
SCENARIOS: tuple[tuple[str, str], ...] = (
    ("protected-file-write", "an agent is told not to touch a file, then tries"),
    ("fake-api-partial-failure", "an API answers some calls and fails others"),
    ("execution-budget", "an agent is given less time than the task needs"),
    ("user-authored-postcondition", "conditions written by you, not chosen from a list"),
)
VERDICT_EXITS = {
    "passed": 0,
    "failed": 1,
    "error": 2,
    "inconclusive": 3,
    "unsupported": 4,
    "skipped": 5,
}

REPORT_DIRECTORY = "iops-crashlab-first-run"

VALUE = "Find out how an agent behaves when things break."
DESCRIPTION = (
    "Run a scenario against a reference agent in a restricted local",
    "container, inject a fault, then check the result against conditions",
    "this host declared before the run. The agent does not grade itself.",
)


def _builtin(name: str) -> dict[str, Any]:
    data = files(__package__).joinpath("_scenarios", name + ".json").read_bytes()
    return loads_document("scenario-definition", data)


def run(directory: Path | None = None) -> int:
    """The first run. Returns the process exit code."""
    survive_narrow_consoles()
    return _steps(directory if directory is not None else Path.cwd())


def _cancelled(question: str) -> int:
    answered(question, "cancelled, nothing was changed")
    return CANCELLED_EXIT


def _finish(image: tuple[str, str, str], scenario: tuple[str, str, str]) -> None:
    print()
    print(_paint("✓" if can_draw_blocks() else "ok", GREEN) + "  " + _paint("Your first run", BOLD))
    print()
    for subject, result, detail in (image, scenario):
        outcome(subject, result, detail)
    print()
    print("A verdict here is this host's check of the result, not the agent's claim.")
    print("Run the same scenario yourself, into a report directory of your own:")
    print(
        "Try: "
        + _paint('"iops-crashlab test builtin:' + SCENARIOS[0][0] + ' --output ./report"', CYAN)
    )


def _steps(here: Path) -> int:
    banner("CRASH LAB", VALUE, DESCRIPTION)

    step(1, 3, "Prepare the local image")
    print("Scenarios run inside a container built from a pinned official base")
    print("image, named by digest. Preparing it downloads that base image and")
    print("builds one local image. Nothing else on your machine changes.")
    print()
    question = "Prepare the pinned reference image?"
    options = ("Yes, download and build it", "No, finish for now")
    picked = choose(question, options, default=1)
    if picked is None:
        return _cancelled(question)
    answered(question, options[picked])
    no_image = ("Scenario run", "skipped", "no image to run it in")
    if picked == 1:
        _finish(("Reference image", "skipped", "not requested"), no_image)
        return 0
    try:
        prepared = prepare_reference_image(pull=True)
    except RunnerUnsupported as error:
        _finish(("Reference image", "unsupported", str(error)), no_image)
        return VERDICT_EXITS["unsupported"]
    except (RunnerError, OSError) as error:
        _finish(("Reference image", "error", type(error).__name__), no_image)
        return VERDICT_EXITS["error"]
    image = ("Reference image", "ok", str(prepared.get("image", "prepared")))
    outcome("Image ready", "ok", str(prepared.get("image", "prepared")))
    print()

    step(2, 3, "Choose a scenario")
    print("Each scenario declares the fault to inject and the conditions this")
    print("host will check afterwards. Choosing one reads a packaged file and")
    print("writes nothing.")
    print()
    question = "Which scenario should run?"
    wide = can_draw_blocks()
    labels = tuple(
        name + (" — " + summary if wide else " -- " + summary) for name, summary in SCENARIOS
    )
    picked = choose(question, labels, default=0)
    if picked is None:
        return _cancelled(question)
    answered(question, labels[picked])
    name = SCENARIOS[picked][0]
    print()

    step(3, 3, "Run it")
    print("The scenario runs in a disposable container with no network. Its")
    print("report is written to ./" + REPORT_DIRECTORY + ", and the container is")
    print("removed afterwards. Nothing outside that directory is written.")
    print()
    question = "Run this scenario now?"
    options = ("Yes, run it and show the verdict", "No, finish for now")
    picked = choose(question, options, default=1)
    if picked is None:
        return _cancelled(question)
    answered(question, options[picked])
    if picked == 1:
        _finish(image, ("Scenario run", "skipped", "not requested"))
        return 0
    try:
        result = run_scenario(_builtin(name), here / REPORT_DIRECTORY)
    except FileExistsError:
        already = "a directory named " + REPORT_DIRECTORY + " is already here"
        _finish(image, ("Scenario run", "skipped", already))
        return VERDICT_EXITS["skipped"]
    except RunnerUnsupported as error:
        _finish(image, ("Scenario run", "unsupported", str(error)))
        return VERDICT_EXITS["unsupported"]
    except (ContractValidationError, RunnerError, OSError) as error:
        _finish(image, ("Scenario run", "error", type(error).__name__))
        return VERDICT_EXITS["error"]
    verdict = str(result["verdict"])
    detail = name + ", report in ./" + REPORT_DIRECTORY
    if verdict == "passed":
        _finish(image, ("Scenario run", "ok", "passed, " + detail))
    elif verdict in UNRESOLVED:
        _finish(image, ("Scenario run", verdict, detail))
    else:
        # A verdict this wizard does not recognise is reported as an error rather than guessed at.
        _finish(image, ("Scenario run", "error", "unrecognised verdict " + verdict))
        return VERDICT_EXITS["error"]
    return VERDICT_EXITS[verdict]
