"""Synthetic custom agent. Run only through Crash Lab's isolated integration."""

from crashlab_tools import write_protected

try:
    write_protected("SYNTHETIC_UPDATE")
except PermissionError:
    pass  # A denied write is an expected, handled tool failure.
