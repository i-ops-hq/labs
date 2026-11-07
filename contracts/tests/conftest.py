"""Source-tree contract matrix; wheel isolation is checked separately."""

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for product in ("permissions", "crashlab"):
    sys.path.insert(0, str(ROOT / "products" / product / "src"))

INDEX = json.loads((ROOT / "contracts/examples/index.json").read_text())


@pytest.fixture(params=["iops_permissions", "iops_crashlab"])
def api(request):
    return importlib.import_module(request.param)


@pytest.fixture
def result_payload():
    return json.loads((ROOT / "contracts/examples/valid/reference-result-passed.json").read_text())
