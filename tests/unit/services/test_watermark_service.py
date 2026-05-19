"""Unit tests for WatermarkService."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.exceptions.property_image_upload import PropertyImageUploadError
from app.services.watermark_service import WatermarkService


def _rgba_png_bytes(size: tuple[int, int] = (400, 300), color: tuple[int, int, int, int] = (10, 120, 200, 255)) -> bytes:
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def watermark_png(tmp_path: Path) -> Path:
    logo = Image.new("RGBA", (200, 80), (255, 0, 0, 200))
    path = tmp_path / "logo.png"
    logo.save(path, format="PNG")
    return path


def _settings(watermark_path: Path, position: str = "center") -> SimpleNamespace:
    return SimpleNamespace(
        watermark_image_path=str(watermark_path),
        watermark_scale=0.50,
        watermark_opacity=128,
        watermark_position=position,
        watermark_position_padding=20,
        watermark_jpeg_quality=95,
    )


def test_process_image_bytes_applies_watermark(watermark_png: Path) -> None:
    service = WatermarkService(settings=_settings(watermark_png))
    out_bytes, content_type = service.process_image_bytes(
        image_bytes=_rgba_png_bytes(),
        original_ext=".png",
    )
    assert content_type == "image/png"
    with Image.open(io.BytesIO(out_bytes)) as result:
        assert result.size == (400, 300)
        assert result.mode == "RGBA"


def test_process_image_bytes_jpeg_output_is_rgb(watermark_png: Path) -> None:
    service = WatermarkService(settings=_settings(watermark_png))
    out_bytes, content_type = service.process_image_bytes(
        image_bytes=_rgba_png_bytes(),
        original_ext=".jpg",
    )
    assert content_type == "image/jpeg"
    with Image.open(io.BytesIO(out_bytes)) as result:
        assert result.mode == "RGB"


def test_watermark_always_centered(watermark_png: Path) -> None:
    """Position is always center regardless of WATERMARK_POSITION env."""
    service = WatermarkService(settings=_settings(watermark_png, position="bottom-right"))
    base = Image.new("RGBA", (400, 300), (10, 120, 200, 255))
    wm = Image.new("RGBA", (100, 50), (255, 0, 0, 200))
    x, y = service._watermark_position(base.width, base.height, wm.width, wm.height)
    assert x == (400 - 100) // 2
    assert y == (300 - 50) // 2


def test_missing_watermark_raises(watermark_png: Path) -> None:
    service = WatermarkService(
        settings=SimpleNamespace(
            watermark_image_path=str(watermark_png.parent / "missing.png"),
            watermark_scale=0.5,
            watermark_opacity=128,
            watermark_position="center",
            watermark_position_padding=20,
            watermark_jpeg_quality=95,
        )
    )
    with pytest.raises(PropertyImageUploadError) as exc_info:
        service.process_image_bytes(image_bytes=_rgba_png_bytes(), original_ext=".png")
    assert exc_info.value.status_code == 500
