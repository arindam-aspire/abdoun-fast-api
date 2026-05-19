"""Background watermarking after presigned S3 PUT (original preserved, watermarked copy)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.s3_service import S3Service
from app.services.watermark_service import WatermarkService

logger = logging.getLogger(__name__)

_in_flight: set[str] = set()
_in_flight_lock = threading.Lock()


class PropertyImageWatermarkProcessor:
    """Poll for original upload, then write a watermarked copy (does not modify the original)."""

    def __init__(
        self,
        s3_service: S3Service | None = None,
        watermark_service: WatermarkService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._s3 = s3_service or S3Service()
        self._watermark = watermark_service or WatermarkService()
        self._settings = settings or get_settings()

    def schedule_after_presigned_upload(
        self,
        *,
        original_key: str,
        watermarked_key: str,
        file_extension: str,
    ) -> None:
        """Run watermark processing in a daemon thread (non-blocking for the presign response)."""
        thread = threading.Thread(
            target=self._run_safe,
            kwargs={
                "original_key": original_key,
                "watermarked_key": watermarked_key,
                "file_extension": file_extension,
            },
            name=f"watermark-{original_key[-48:]}",
            daemon=True,
        )
        thread.start()
        logger.info(
            "[watermark] scheduled async job original_key=%s watermarked_key=%s",
            original_key,
            watermarked_key,
        )

    def process_now(
        self,
        *,
        original_key: str,
        watermarked_key: str,
        file_extension: str,
        wait_for_original: bool = True,
    ) -> bool:
        """Process immediately (multipart upload or manual finalize retry). Returns True on success."""
        return self._run_safe(
            original_key=original_key,
            watermarked_key=watermarked_key,
            file_extension=file_extension,
            wait_for_original=wait_for_original,
        )

    def _run_safe(
        self,
        *,
        original_key: str,
        watermarked_key: str,
        file_extension: str,
        wait_for_original: bool = True,
    ) -> bool:
        if not self._acquire(original_key):
            logger.info("[watermark] skip duplicate job original_key=%s", original_key)
            return False
        try:
            return self._process(
                original_key=original_key,
                watermarked_key=watermarked_key,
                file_extension=file_extension,
                wait_for_original=wait_for_original,
            )
        except Exception:
            logger.exception(
                "[watermark] job failed original_key=%s watermarked_key=%s",
                original_key,
                watermarked_key,
            )
            return False
        finally:
            self._release(original_key)

    def _process(
        self,
        *,
        original_key: str,
        watermarked_key: str,
        file_extension: str,
        wait_for_original: bool,
    ) -> bool:
        if wait_for_original and not self._wait_for_object(original_key):
            logger.error(
                "[watermark] timed out waiting for original upload original_key=%s",
                original_key,
            )
            return False

        if not self._s3.object_exists(key=original_key):
            logger.error("[watermark] original object missing original_key=%s", original_key)
            return False

        raw_bytes, _ = self._s3.get_object(key=original_key)
        ext = file_extension if file_extension.startswith(".") else f".{file_extension}"
        processed_bytes, content_type = self._watermark.process_image_bytes(
            image_bytes=raw_bytes,
            original_ext=ext,
        )
        self._s3.put_object(key=watermarked_key, body=processed_bytes, content_type=content_type)
        logger.info(
            "[watermark] wrote watermarked copy watermarked_key=%s bytes=%s (original_key=%s)",
            watermarked_key,
            len(processed_bytes),
            original_key,
        )
        return True

    def _wait_for_object(self, key: str) -> bool:
        interval = max(0.5, float(self._settings.watermark_poll_interval_seconds))
        timeout = max(interval, float(self._settings.watermark_poll_timeout_seconds))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._s3.object_exists(key=key):
                logger.info("[watermark] original object detected key=%s", key)
                return True
            time.sleep(interval)
        return False

    @staticmethod
    def _acquire(original_key: str) -> bool:
        with _in_flight_lock:
            if original_key in _in_flight:
                return False
            _in_flight.add(original_key)
            return True

    @staticmethod
    def _release(original_key: str) -> None:
        with _in_flight_lock:
            _in_flight.discard(original_key)


def file_extension_from_filename(filename: str) -> str:
    """Return dotted extension for watermark encoding."""
    ext = Path(filename).suffix.lower()
    return ext or ".jpg"
