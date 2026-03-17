"""Unit tests for app.api.v1.routes.agents helpers."""
from app.api.v1.routes import agents as agents_module


def test_sanitize_validation_errors_base_exception():
    err = Exception("bad")
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"err": err}}])
    assert out == [{"type": "x", "ctx": {"err": "bad"}}]


def test_sanitize_validation_errors_type_error():
    # Value that json.dumps() cannot serialize (e.g. set) triggers TypeError branch
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"key": {1, 2, 3}}}])
    assert out[0]["ctx"]["key"] == "{1, 2, 3}"


def test_sanitize_validation_errors_json_serializable():
    out = agents_module._sanitize_validation_errors([{"type": "x", "ctx": {"n": 42}}])
    assert out == [{"type": "x", "ctx": {"n": 42}}]


def test_sanitize_validation_errors_no_ctx():
    out = agents_module._sanitize_validation_errors([{"type": "y", "loc": ("a",)}])
    assert out == [{"type": "y", "loc": ("a",)}]
