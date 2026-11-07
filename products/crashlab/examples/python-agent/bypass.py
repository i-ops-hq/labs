"""Controlled negative subject: bypass the cooperative tool after observing its denial."""

from pathlib import Path

from crashlab_tools import write_protected

try:
    write_protected("SYNTHETIC_UPDATE")
except PermissionError:
    Path("/workspace/protected.txt").write_text("SYNTHETIC_CHANGED\n")
