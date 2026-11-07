import json
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def example():
    def load(name):
        return json.loads((EXAMPLES / (name + ".json")).read_text())

    return load


@pytest.fixture
def policy(example):
    return example("policy")


@pytest.fixture
def action_request(example):
    return example("action-allowed")


@pytest.fixture
def capabilities(example):
    return example("operations-manifest")
