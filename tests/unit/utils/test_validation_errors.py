"""Tests for validation error sanitization."""

from app.utils.validation_errors import sanitize_validation_errors


def test_sanitize_replaces_bytes_in_input() -> None:
    pdf_fragment = b"%PDF-1.4\xff"
    errors = [
        {
            "type": "model_attributes_type",
            "loc": ("body",),
            "msg": "Input should be a valid dictionary",
            "input": pdf_fragment,
        }
    ]
    out = sanitize_validation_errors(errors)
    assert out[0]["input"] == f"<binary data, {len(pdf_fragment)} bytes>"
