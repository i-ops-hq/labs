"""The first-run wizard, and the script path it must never reach.

Three kinds of test here, and the split is deliberate.

The gate and the encoding probe are plain unit tests. The step flow replaces `choose` and reads
what was printed, which is what proves the safe default neither writes nor reaches Docker, and
that a non-pass outcome names itself. Neither of those can see a terminal bug, so the control
itself is driven through a real pseudo-terminal at the bottom of this file, and those tests assert
on what was DRAWN rather than only on what was returned: the reference implementation once
returned a moving index while the highlight on screen never moved, and a test that reads the
return value passes that wizard.

The PTY harness drains the master from a thread. `tty.setraw` is `tcsetattr` with TCSAFLUSH, which
waits for pending output to drain, so a harness that reads only after the child exits deadlocks it
before it ever reads a key - and that looks exactly like a hang in the wizard.

Nothing in this file requires Docker. The Docker-shaped outcomes are forced by replacing the image
and runner calls, because what is under test is how an outcome is reported, not whether a daemon
is installed.
"""

import json
import os
import pty
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import warnings

import pytest
from iops_crashlab import cli, wizard
from iops_crashlab.docker import RunnerError, RunnerUnsupported

BARE_ERROR = {
    "status": "error",
    "code": "invalid_arguments",
    "message": "Invalid arguments; use --help for supported usage.",
}
COLOUR = re.compile(r"\x1b\[[0-9;]*m")


class FakeStream:
    def __init__(self, tty=True, encoding="utf-8"):
        self._tty = tty
        self.encoding = encoding

    def isatty(self):
        return self._tty

    def write(self, text):
        return len(text)

    def flush(self):
        return None


def gate(argv, env, stdin_tty, stdout_tty):
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = FakeStream(stdin_tty), FakeStream(stdout_tty)
    try:
        return wizard.wants_a_wizard(argv, env)
    finally:
        sys.stdin, sys.stdout = stdin, stdout


def answers(*picks):
    """Stand in for `choose`, returning a scripted answer each time it is asked."""
    remaining = list(picks)

    def chose(question, options, default=0):
        if not remaining:
            raise AssertionError("the wizard asked more questions than the test scripted")
        pick = remaining.pop(0)
        return default if pick == "default" else pick

    return chose


def plain(capsys):
    return COLOUR.sub("", capsys.readouterr().out)


def prepared(monkeypatch):
    monkeypatch.setattr(
        wizard, "prepare_reference_image", lambda **_kwargs: {"image": "iops-crashlab:test"}
    )


# 1. A bare invocation that is not a person keeps today's exact answer.
def test_bare_invocation_without_a_terminal_is_unchanged(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "iops_crashlab"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    # Which stream carries the error is part of the contract, not an implementation detail: a
    # script doing `cmd 2>/dev/null | jq` breaks the day it moves. This read
    # `result.stdout or result.stderr`, which passes whichever stream carries it, so the test
    # named "keeps today's exact answer" could not see the answer move.
    assert result.stdout == ""
    assert json.loads(result.stderr) == BARE_ERROR
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("argv", "env", "stdin_tty", "stdout_tty", "expected"),
    [
        (["x"], {}, True, True, True),
        (["x"], {}, False, True, False),  # stdout only: `iops-crashlab < file`
        (["x"], {}, True, False, False),  # stdin only: `iops-crashlab | less`
        (["x"], {}, False, False, False),
        (["x", "examples"], {}, True, True, False),
        (["x"], {"CI": "1"}, True, True, False),
        (["x"], {"CI": "true"}, True, True, False),
        (["x"], {"TERM": "dumb"}, True, True, False),
        (["x"], {"IOPS_NO_WIZARD": "1"}, True, True, False),
    ],
)
def test_the_gate_answers_each_case(argv, env, stdin_tty, stdout_tty, expected):
    assert gate(argv, env, stdin_tty, stdout_tty) is expected


def test_a_stream_without_isatty_is_not_a_terminal():
    import types

    stdin = sys.stdin
    sys.stdin = types.SimpleNamespace()
    try:
        assert wizard.wants_a_wizard(["x"], {}) is False
    finally:
        sys.stdin = stdin


# 5. A console with no byte for a block character must not raise.
@pytest.mark.parametrize(
    ("encoding", "expected"),
    [("utf-8", True), ("cp1252", False), ("ascii", False), ("bogus-codec", False), (None, False)],
)
def test_the_block_character_is_probed_not_assumed(encoding, expected):
    assert wizard.can_draw_blocks(FakeStream(encoding=encoding)) is expected


def test_colour_is_refused_when_it_is_not_welcome():
    stdout = sys.stdout
    sys.stdout = FakeStream(tty=False)
    try:
        assert wizard.colour_is_welcome({}) is False
    finally:
        sys.stdout = stdout
    sys.stdout = FakeStream(tty=True)
    try:
        assert wizard.colour_is_welcome({"NO_COLOR": "1"}) is False
        assert wizard.colour_is_welcome({"TERM": "dumb"}) is False
    finally:
        sys.stdout = stdout


def test_a_narrow_console_prints_an_ascii_wordmark(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wizard, "can_draw_blocks", lambda *_args: False)
    monkeypatch.setattr(wizard, "choose", answers("default"))
    assert wizard.run(tmp_path) == 0
    text = plain(capsys)
    assert "CRASH LAB" in text
    for glyph in ("█", "✓", "●", "›"):
        assert glyph not in text
    assert text.encode("ascii")


# Colour and encoding are independent questions. This combination - colour wanted, encoding too
# narrow for the glyphs - is the ordinary Windows console, and it is unreachable under pytest's
# capture, which turns colour off and takes the other branch. Forcing both is the only way the
# tick's gate is tested at all, and it is why a colour-gated tick survived review here.
def test_a_colour_terminal_with_a_narrow_encoding_still_prints_ascii(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wizard, "colour_is_welcome", lambda *_args: True)
    monkeypatch.setattr(wizard, "can_draw_blocks", lambda *_args: False)
    monkeypatch.setattr(wizard, "choose", answers("default"))
    assert wizard.run(tmp_path) == 0
    text = capsys.readouterr().out
    offenders = sorted({f"U+{ord(ch):04X} {ch}" for ch in text if ord(ch) > 127})
    assert offenders == [], "a narrow frame emitted " + ", ".join(offenders)


def test_a_wide_console_prints_the_block_wordmark(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wizard, "choose", answers("default"))
    wizard.run(tmp_path)
    assert "█" in capsys.readouterr().out


# 6. The preselected answer is the safe one: the default neither writes nor reaches Docker.
def test_the_default_never_touches_the_machine(tmp_path, monkeypatch, capsys):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the default answer must not reach Docker")

    monkeypatch.setattr(wizard, "prepare_reference_image", refuse)
    monkeypatch.setattr(wizard, "run_scenario", refuse)
    monkeypatch.setattr(wizard, "choose", answers("default"))
    assert wizard.run(tmp_path) == 0
    assert list(tmp_path.iterdir()) == []
    text = plain(capsys)
    assert "No, finish for now" in text
    assert "skipped" in text
    assert "Your first run" in text


def test_declining_the_run_still_leaves_the_directory_empty(tmp_path, monkeypatch, capsys):
    prepared(monkeypatch)
    monkeypatch.setattr(
        wizard, "run_scenario", lambda *_a, **_k: pytest.fail("declining must not run a scenario")
    )
    monkeypatch.setattr(wizard, "choose", answers(0, "default", "default"))
    assert wizard.run(tmp_path) == 0
    assert list(tmp_path.iterdir()) == []
    assert "skipped" in plain(capsys)


def test_an_unavailable_daemon_is_unsupported_and_never_a_pass(tmp_path, monkeypatch, capsys):
    def unsupported(**_kwargs):
        raise RunnerUnsupported("docker_unavailable")

    monkeypatch.setattr(wizard, "prepare_reference_image", unsupported)
    monkeypatch.setattr(wizard, "choose", answers(0))
    assert wizard.run(tmp_path) == wizard.VERDICT_EXITS["unsupported"]
    text = plain(capsys)
    assert "unsupported" in text
    assert "docker_unavailable" in text
    assert "passed" not in text
    assert list(tmp_path.iterdir()) == []


def test_a_broken_daemon_is_an_error_not_a_failed_agent(tmp_path, monkeypatch, capsys):
    def broken(**_kwargs):
        raise RunnerError("daemon_refused")

    monkeypatch.setattr(wizard, "prepare_reference_image", broken)
    monkeypatch.setattr(wizard, "choose", answers(0))
    assert wizard.run(tmp_path) == wizard.VERDICT_EXITS["error"]
    text = plain(capsys)
    assert "error" in text
    assert "failed" not in text


@pytest.mark.parametrize(
    ("verdict", "code"),
    [("passed", 0), ("failed", 1), ("inconclusive", 3), ("unsupported", 4), ("skipped", 5)],
)
def test_a_verdict_keeps_its_declared_exit_code(tmp_path, monkeypatch, capsys, verdict, code):
    prepared(monkeypatch)
    monkeypatch.setattr(wizard, "run_scenario", lambda *_a, **_k: {"verdict": verdict})
    monkeypatch.setattr(wizard, "choose", answers(0, "default", 0))
    assert wizard.run(tmp_path) == code
    assert verdict in plain(capsys)


def test_an_unrecognised_verdict_is_an_error_rather_than_a_guess(tmp_path, monkeypatch, capsys):
    prepared(monkeypatch)
    monkeypatch.setattr(wizard, "run_scenario", lambda *_a, **_k: {"verdict": "splendid"})
    monkeypatch.setattr(wizard, "choose", answers(0, "default", 0))
    assert wizard.run(tmp_path) == wizard.VERDICT_EXITS["error"]
    assert "unrecognised verdict splendid" in plain(capsys)


def test_an_existing_report_directory_is_skipped_rather_than_reused(tmp_path, monkeypatch, capsys):
    (tmp_path / wizard.REPORT_DIRECTORY).mkdir()
    prepared(monkeypatch)

    def already_there(*_args, **_kwargs):
        raise FileExistsError(wizard.REPORT_DIRECTORY)

    monkeypatch.setattr(wizard, "run_scenario", already_there)
    monkeypatch.setattr(wizard, "choose", answers(0, "default", 0))
    assert wizard.run(tmp_path) == wizard.VERDICT_EXITS["skipped"]
    assert "skipped" in plain(capsys)
    assert list((tmp_path / wizard.REPORT_DIRECTORY).iterdir()) == []


@pytest.mark.parametrize("at", [0, 1, 2])
def test_cancelling_any_question_exits_130_and_touches_nothing(tmp_path, monkeypatch, at):
    prepared(monkeypatch)
    monkeypatch.setattr(
        wizard, "run_scenario", lambda *_a, **_k: pytest.fail("cancelling must not run a scenario")
    )
    picks = [0, "default", "default"]
    picks[at] = None
    monkeypatch.setattr(wizard, "choose", answers(*picks[: at + 1]))
    assert wizard.run(tmp_path) == wizard.CANCELLED_EXIT
    assert list(tmp_path.iterdir()) == []


# These two tables are duplicated out of `cli` to avoid an import cycle. If they drift, the wizard
# offers a scenario the command cannot load, or reports an exit code the command does not declare.
def test_the_offered_scenarios_are_real_builtins():
    assert [name for name, _ in wizard.SCENARIOS] == list(cli.BUILTINS)


def test_the_verdict_exit_codes_match_the_command():
    assert wizard.VERDICT_EXITS == cli.EXIT_CODES


def test_every_packaged_scenario_the_wizard_offers_loads():
    for name, summary in wizard.SCENARIOS:
        assert wizard._builtin(name)["scenario_id"]
        assert summary


# Raw mode has to be on before anything a driver or a person can see is drawn. `tty.setraw` is
# `tcsetattr` with TCSAFLUSH, which DISCARDS the input queue, so a key that arrives before it is
# thrown away and the wizard looks frozen. Measured through a real pseudo-terminal: writing the
# key the instant the question text appeared lost it on three runs in eight. The pseudo-terminal
# cases below wait for drawn output before sending a key, so this ordering is what makes that
# wait sound rather than lucky. Asserted on the ORDER of the two side effects, because the
# window is microseconds wide and a timing test for it would prove nothing.
def test_raw_mode_is_entered_before_the_first_frame_is_drawn(monkeypatch):
    import termios
    import tty
    import types

    order = []

    class Recorder:
        encoding = "utf-8"

        def isatty(self):
            return False

        def write(self, text):
            # `draw` opens every frame by moving the cursor up over the block it is about to
            # rewrite. The question, the blank option lines and the hint are printed before
            # that and are allowed to precede raw mode; the frame is not.
            order.append("frame" if text.startswith("\x1b[") and text.endswith("A") else "text")

        def flush(self):
            return None

    monkeypatch.setattr(termios, "tcgetattr", lambda fd: "saved")
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, saved: order.append("restore"))
    monkeypatch.setattr(tty, "setraw", lambda fd: order.append("raw"))
    monkeypatch.setattr(wizard.sys, "stdin", types.SimpleNamespace(fileno=lambda: 0))
    monkeypatch.setattr(wizard.sys, "stdout", Recorder())
    monkeypatch.setattr(wizard, "_read_key", lambda fd: "enter")

    assert wizard.choose("Pick one", ("first", "second"), 0) == 0
    assert "raw" in order and "frame" in order, order
    assert order.index("raw") < order.index("frame"), order
    assert order[-1] == "restore", order


# ---------------------------------------------------------------------------------------------
# The selection control, driven through a real pseudo-terminal.
# ---------------------------------------------------------------------------------------------

DRIVER = """
import sys, termios
from iops_crashlab import wizard

wizard.survive_narrow_consoles()
fd = sys.stdin.fileno()
# On macOS tcgetattr always differs afterwards by PENDIN, a kernel status bit nobody set, so a
# straight before/after comparison fails for a reason that has nothing to do with the wizard.
PENDIN = getattr(termios, "PENDIN", 0)


def snapshot():
    attributes = termios.tcgetattr(fd)
    attributes[3] &= ~PENDIN
    return attributes


before = snapshot()
options = ["Yes, download and build it", "No, finish for now"]
at = wizard.choose("Prepare the pinned reference image?", options, default=1)
restored = snapshot() == before
wizard.answered(
    "Prepare the pinned reference image?", "cancelled" if at is None else options[at]
)
print("CHOSE=" + ("cancel" if at is None else str(at)))
print("RESTORED=" + str(restored))
"""


def environment():
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "IOPS_NO_WIZARD")}
    env["TERM"] = "xterm"
    env["NO_COLOR"] = "1"
    return env


def drive(arguments, keys, cwd, limit=25.0, env_extra=None):
    """Run a command under a real PTY, feeding it keys, and return its output and exit code."""
    child_environment = environment()
    child_environment.update(env_extra or {})
    # The working directory is set by the shell, after its own exec, rather than by the child
    # before it. See the comment on the exec below for why that distinction is not cosmetic.
    command = (
        "cd " + shlex.quote(str(cwd)) + " && exec " + shlex.join([sys.executable, "-u", *arguments])
    )
    with warnings.catch_warnings():
        # forkpty warns when the process has threads, because a child can deadlock on a lock it
        # inherited mid-acquisition. Earlier PTY cases in this file have already started reader
        # threads, so the warning is expected here. It is harmless only because of the exec below.
        warnings.simplefilter("ignore", DeprecationWarning)
        pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - this branch is the child, which only ever execs
        try:
            # exec is the FIRST and only thing the child does. That is what makes the inherited
            # thread state harmless: exec replaces the whole process image, so no inherited lock
            # is ever touched. A child that chdir'd, imported or printed first would be a real
            # intermittent deadlock, and it would surface here under pytest rather than as a
            # plain script. Exec first, always.
            os.execve("/bin/sh", ["/bin/sh", "-c", command], child_environment)
        finally:
            os._exit(127)
    drawn = bytearray()
    stop = threading.Event()

    def drain():
        while not stop.is_set():
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            drawn.extend(chunk)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    def settled(quiet=0.12, timeout=15.0):
        """Wait until the child has drawn something and then stopped writing.

        This was a fixed `time.sleep(0.35)` before each key, which is a race rather than a
        wait: the key went out whether or not the child was ready for it, and a loaded
        machine lost it to the raw-mode flush. Output going quiet after a frame means the
        child is blocked in `_read_key`, so the key cannot be discarded - and it adapts,
        waiting longer under load and less when the child is fast.
        """
        end = time.time() + timeout
        while time.time() < end:
            size = len(drawn)
            time.sleep(quiet)
            if size and len(drawn) == size:
                return True
        return False

    try:
        for key in keys:
            assert settled(), "the wizard drew nothing, or never stopped drawing, before a key"
            os.write(fd, key)
        deadline = time.time() + limit
        status = None
        while time.time() < deadline:
            done, state = os.waitpid(pid, os.WNOHANG)
            if done:
                status = state
                break
            time.sleep(0.05)
        if status is None:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            raise AssertionError(
                "the wizard did not exit: " + bytes(drawn).decode("utf-8", "replace")
            )
    finally:
        stop.set()
        reader.join(timeout=2.0)
        os.close(fd)
    code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -os.WTERMSIG(status)
    return code, bytes(drawn).decode("utf-8", "replace")


def highlighted(text, count=2):
    """Which option carried the filled marker on the LAST frame actually drawn."""
    last = text.split("\x1b[" + str(count + 1) + "A")[-1]
    marked = [
        COLOUR.sub("", line).split("●")[-1].strip() for line in last.split("\n") if "●" in line
    ]
    return marked[-1] if marked else None


@pytest.fixture
def driver(tmp_path):
    (tmp_path / "driver.py").write_text(DRIVER)
    return tmp_path


@pytest.mark.parametrize(
    ("keys", "chose", "drawn"),
    [
        ([b"\r"], "1", "No, finish for now"),
        ([b"\x1b[A", b"\r"], "0", "Yes, download and build it"),
        ([b"\x1b[B", b"\x1b[B", b"\r"], "1", "No, finish for now"),
        ([b"k", b"\r"], "0", "Yes, download and build it"),
        ([b"j", b"\r"], "0", "Yes, download and build it"),
    ],
)
def test_the_control_moves_the_highlight_it_returns(driver, keys, chose, drawn):
    code, text = drive(["driver.py"], keys, driver)
    assert code == 0
    assert "CHOSE=" + chose in text
    assert highlighted(text) == drawn
    assert "RESTORED=True" in text


@pytest.mark.parametrize("key", [b"\x1b", b"\x03"])
def test_esc_and_ctrl_c_cancel_and_restore_the_terminal(driver, key):
    code, text = drive(["driver.py"], [key], driver)
    assert code == 0
    assert "CHOSE=cancel" in text
    assert "RESTORED=True" in text


# The hint and the control have to agree. They drifted once: the frame was transcribed from
# another product whose Esc goes back a step, while this control cancels the whole wizard. This
# asserts the pair together, so changing one without the other fails rather than shipping a
# control that promises something it does not do.
def test_the_hint_describes_what_esc_actually_does(driver):
    assert "cancel" in wizard.HINT and "go back" not in wizard.HINT
    assert "cancel" in wizard.HINT_PLAIN and "go back" not in wizard.HINT_PLAIN
    code, text = drive(["driver.py"], [b"\x1b"], driver)
    assert code == 0
    assert "CHOSE=cancel" in text
    assert "Esc cancel" in COLOUR.sub("", text)


# The same case through the real control, with the encoding forced on the child rather than a
# monkeypatch. An ASCII-only assertion is necessary but NOT sufficient here:
# survive_narrow_consoles sets errors="replace", so a glyph with no byte becomes "?", which is
# itself ASCII. The load-bearing assertion is that the tick reads "ok" - under the colour-gated
# bug it is a replacement character inside the escape codes.
def test_a_narrow_colour_terminal_draws_an_ascii_frame(driver):
    code, text = drive(
        ["driver.py"],
        [b"\r"],
        driver,
        env_extra={"PYTHONIOENCODING": "ascii", "NO_COLOR": ""},
    )
    assert code == 0, text
    plain_text = COLOUR.sub("", text)
    assert "ok Prepare the pinned reference image? No, finish for now" in plain_text, plain_text
    assert "(*)" in plain_text and "( )" in plain_text
    assert "up/down choose - Enter confirm - Esc cancel" in plain_text
    offenders = sorted({f"U+{ord(ch):04X}" for ch in text if ord(ch) > 127})
    assert offenders == [], offenders


def test_answering_collapses_the_menu_to_one_line(driver):
    _, text = drive(["driver.py"], [b"\r"], driver)
    assert "\x1b[4A\r\x1b[J" in text
    assert "✓ Prepare the pinned reference image? No, finish for now" in COLOUR.sub("", text)


def test_the_whole_wizard_runs_on_a_real_terminal_and_touches_nothing(tmp_path):
    code, text = drive(["-m", "iops_crashlab"], [b"\r"], tmp_path)
    assert code == 0
    plain_text = COLOUR.sub("", text)
    assert "CRASH LAB" in plain_text
    assert "Your first run" in plain_text
    assert "skipped" in plain_text
    assert list(tmp_path.iterdir()) == []


def test_cancelling_the_real_wizard_exits_130(tmp_path):
    code, text = drive(["-m", "iops_crashlab"], [b"\x1b"], tmp_path)
    assert code == wizard.CANCELLED_EXIT
    assert "cancelled" in COLOUR.sub("", text)
    assert list(tmp_path.iterdir()) == []


# 2. CI is a pair of real terminals that must not be asked a question. A unit test on the gate
# cannot show this: the failure mode of getting it wrong is a pipeline that hangs, so the command
# has to actually be run with both streams on a terminal and nothing typed at it.
def test_ci_on_a_real_terminal_does_not_prompt(tmp_path):
    code, text = drive(["-m", "iops_crashlab"], [], tmp_path, limit=20.0, env_extra={"CI": "1"})
    assert code == 2
    assert "CRASH LAB" not in text
    assert json.loads(text.strip().splitlines()[-1]) == BARE_ERROR
    assert list(tmp_path.iterdir()) == []
