from __future__ import annotations

import logging

from app.utils.request_context import set_request_id


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_log_record_includes_request_id_field() -> None:
    logger = logging.getLogger("tests.request_id")
    handler = _Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    set_request_id("test_request_id_123456")
    try:
        logger.info("hello")
    finally:
        set_request_id(None)
        logger.removeHandler(handler)

    assert handler.records, "Expected at least one LogRecord captured"
    record = handler.records[-1]
    assert hasattr(record, "request_id")
    assert record.request_id == "test_request_id_123456"


def test_log_record_request_id_defaults_to_dash_when_missing() -> None:
    logger = logging.getLogger("tests.request_id.default")
    handler = _Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    set_request_id(None)
    try:
        logger.info("hello")
    finally:
        logger.removeHandler(handler)

    record = handler.records[-1]
    assert record.request_id == "-"

