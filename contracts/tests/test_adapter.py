import importlib.util
import sys
from dataclasses import FrozenInstanceError

import pytest

from .conftest import ROOT

spec = importlib.util.spec_from_file_location(
    "adapter_reference", ROOT / "contracts/reference/python/agent_adapter.py"
)
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)


def descriptor(features):
    return adapter.AdapterDescriptor(
        "synthetic-inspector",
        "0.0.0",
        ("custom-python",),
        frozenset(features),
        "none",
        "declared_only",
        ("Synthetic descriptor, not an integration.",),
    )


def test_missing_features_are_typed_unsupported():
    result = adapter.negotiate(descriptor({"inspect"}), frozenset({"launch"}))
    assert isinstance(result, adapter.Unsupported)
    assert result.status == "unsupported"
    assert result.reason_code == "missing_verified_features"


def test_negotiation_success_is_not_a_run():
    result = adapter.negotiate(descriptor({"inspect"}), frozenset({"inspect"}))
    assert result.status == "ok"
    assert result.value == frozenset({"inspect"})


def test_error_is_distinct_from_unsupported_and_status_is_immutable():
    error = adapter.AdapterError("inspect", "fixture_unavailable")
    assert error.status == "error"
    assert not isinstance(error, adapter.Unsupported)
    with pytest.raises(FrozenInstanceError):
        error.status = "ok"


def test_inspector_returns_explicit_unsupported():
    class Inspector:
        def describe(self):
            return descriptor(set())

        def inspect(self, target):
            return adapter.Unsupported("inspect", "fixture_not_supported")

    instance = Inspector()
    assert instance.inspect(adapter.Target("fixture://unknown")).status == "unsupported"
    assert not hasattr(instance, "start")
