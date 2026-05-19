"""Server-side image watermarking with Pillow (property listing photos)."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.exceptions.property_image_upload import PropertyImageUploadError
from app.utils.status_codes import HTTPStatus

logger = logging.getLogger(__name__)

# Repo root (parent of ``app/``) — stable base for relative WATERMARK_IMAGE_PATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_watermark_path(configured: str) -> Path:
    """Resolve watermark file path (absolute, cwd-relative, or repo-root-relative)."""
    raw = (configured or "").strip()
    if not raw:
        raise PropertyImageUploadError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Watermark configuration error",
            detail="WATERMARK_IMAGE_PATH is empty",
        )

    candidate = Path(raw)
    tried: list[str] = []

    def _try(path: Path) -> Path | None:
        tried.append(str(path))
        return path.resolve() if path.is_file() else None

    hit = _try(candidate)
    if hit is not None:
        logger.info("[watermark] resolved path=%s (configured=%s)", hit, raw)
        return hit

    if not candidate.is_absolute():
        for path in (
            Path.cwd() / candidate,
            _PROJECT_ROOT / candidate,
            _PROJECT_ROOT / "app" / "assets" / "watermark" / candidate.name,
        ):
            hit = _try(path)
            if hit is not None:
                logger.info(
                    "[watermark] resolved path=%s (configured=%s tried=%s)",
                    hit,
                    raw,
                    tried,
                )
                return hit

    unresolved = candidate.resolve()
    logger.error(
        "[watermark] file not found configured=%s cwd=%s project_root=%s tried=%s",
        raw,
        Path.cwd(),
        _PROJECT_ROOT,
        tried,
    )
    return unresolved


class WatermarkService:
    """Apply a cached watermark logo to property images using alpha compositing."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._watermark_master: Image.Image | None = None

    def process_image_bytes(self, *, image_bytes: bytes, original_ext: str) -> tuple[bytes, str]:
        """Watermark raw image bytes and return encoded bytes + output content type."""
        logger.info(
            "[watermark] process start input_bytes=%s ext=%s config path=%s scale=%s opacity=%s position=%s",
            len(image_bytes),
            original_ext,
            self._settings.watermark_image_path,
            self._settings.watermark_scale,
            self._settings.watermark_opacity,
            self._settings.watermark_position,
        )
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                base = img.convert("RGBA")
        except UnidentifiedImageError as exc:
            logger.warning("[watermark] invalid image bytes ext=%s", original_ext)
            raise PropertyImageUploadError(
                status_code=HTTPStatus.BAD_REQUEST,
                message="Invalid image file",
                detail="The uploaded file is not a valid image",
            ) from exc

        logger.info("[watermark] base image size=%dx%d mode=RGBA", base.width, base.height)

        watermark_master = self._get_watermark_master()
        sized = self._resize_watermark(watermark_master, base.width, base.height)
        logger.info("[watermark] resized watermark size=%dx%d", sized.width, sized.height)

        transparent = self._apply_opacity(sized, self._settings.watermark_opacity)
        self._log_alpha_stats(transparent, label="after_opacity")

        result = self._paste_watermark(base, transparent)

        output_bytes, content_type = self._encode_image(result, original_ext)
        logger.info(
            "[watermark] process done output_bytes=%s content_type=%s (input_bytes=%s)",
            len(output_bytes),
            content_type,
            len(image_bytes),
        )
        return output_bytes, content_type

    def _get_watermark_master(self) -> Image.Image:
        if self._watermark_master is not None:
            return self._watermark_master

        path = resolve_watermark_path(self._settings.watermark_image_path)
        if not path.is_file():
            logger.error("Watermark image not found: %s (configured=%s)", path, self._settings.watermark_image_path)
            raise PropertyImageUploadError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message="Watermark configuration error",
                detail=f"Watermark image not found: {path}",
            )

        watermark = Image.open(path).convert("RGBA")
        logger.info(
            "[watermark] loaded file=%s size=%dx%d",
            path,
            watermark.width,
            watermark.height,
        )
        self._log_alpha_stats(watermark, label="master")
        self._watermark_master = watermark
        return watermark

    @staticmethod
    def _log_alpha_stats(image: Image.Image, *, label: str) -> None:
        """Log alpha channel range — helps detect invisible (fully transparent) watermarks."""
        if image.mode != "RGBA":
            return
        alpha = image.getchannel("A")
        extrema = alpha.getextrema()
        logger.info("[watermark] alpha %s min=%s max=%s", label, extrema[0], extrema[1])
        if extrema[1] == 0:
            logger.warning("[watermark] alpha %s is fully transparent — logo will not be visible", label)

    def _resize_watermark(
        self,
        watermark: Image.Image,
        target_image_width: int,
        target_image_height: int,
    ) -> Image.Image:
        """Resize watermark to fit within a box scaled to the target image."""
        scale_factor = self._settings.watermark_scale
        max_width = max(1, int(target_image_width * scale_factor))
        max_height = max(1, int(target_image_height * scale_factor))
        width_ratio = max_width / watermark.width
        height_ratio = max_height / watermark.height
        scale = min(width_ratio, height_ratio)
        new_width = max(1, int(watermark.width * scale))
        new_height = max(1, int(watermark.height * scale))
        return watermark.resize((new_width, new_height), Image.Resampling.LANCZOS)

    @staticmethod
    def _apply_opacity(watermark: Image.Image, opacity: int) -> Image.Image:
        """Blend watermark opacity (0–255) while preserving existing alpha."""
        opacity = max(0, min(255, opacity))
        if opacity == 255:
            return watermark

        result = watermark.copy()
        alpha = result.getchannel("A")
        alpha = alpha.point(lambda p: int(p * opacity / 255))
        result.putalpha(alpha)
        return result

    def _watermark_position(
        self,
        base_width: int,
        base_height: int,
        wm_width: int,
        wm_height: int,
    ) -> tuple[int, int]:
        """Return (x, y) for center-aligned watermark placement on every image."""
        return (base_width - wm_width) // 2, (base_height - wm_height) // 2

    def _paste_watermark(self, base: Image.Image, watermark: Image.Image) -> Image.Image:
        """Composite watermark onto the base image at the configured position."""
        if base.mode != "RGBA":
            base = base.convert("RGBA")

        x, y = self._watermark_position(base.width, base.height, watermark.width, watermark.height)
        x = max(0, x)
        y = max(0, y)

        logger.info(
            "[watermark] composite position=(%s,%s) base=%dx%d watermark=%dx%d",
            x,
            y,
            base.width,
            base.height,
            watermark.width,
            watermark.height,
        )
        composed = base.copy()
        composed.alpha_composite(watermark, dest=(x, y))
        return composed

    def _encode_image(self, image: Image.Image, original_ext: str) -> tuple[bytes, str]:
        """Encode composited image with format-appropriate settings."""
        ext = original_ext.lower()
        buffer = io.BytesIO()
        jpeg_quality = self._settings.watermark_jpeg_quality

        if ext in (".jpg", ".jpeg"):
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.save(buffer, format="JPEG", quality=jpeg_quality, subsampling=0)
            return buffer.getvalue(), "image/jpeg"

        if ext == ".png":
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            image.save(buffer, format="PNG", compress_level=3)
            return buffer.getvalue(), "image/png"

        if ext == ".webp":
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            image.save(buffer, format="WEBP", quality=jpeg_quality, method=6)
            return buffer.getvalue(), "image/webp"

        raise PropertyImageUploadError(
            status_code=HTTPStatus.BAD_REQUEST,
            message="Invalid file extension",
            detail=f"Unsupported output extension: {ext}",
        )
