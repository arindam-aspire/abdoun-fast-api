"""Watermark path resolution."""

from pathlib import Path

from app.services.watermark_service import _PROJECT_ROOT, resolve_watermark_path


def test_resolve_watermark_falls_back_to_app_assets() -> None:
    """Default .env path may point at repo assets/; logo may live under app/assets/."""
    configured = "assets/watermark/abdoun_water_mark_logo.png"
    resolved = resolve_watermark_path(configured)
    expected = _PROJECT_ROOT / "app" / "assets" / "watermark" / "abdoun_water_mark_logo.png"
    if expected.is_file():
        assert resolved == expected.resolve()
