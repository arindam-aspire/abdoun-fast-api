from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from app.utils.resilience import RetryConfig, is_retryable_http_error, retry


def test_is_retryable_http_error_true_when_not_http_error() -> None:
    assert is_retryable_http_error(requests.exceptions.Timeout()) is True


def test_is_retryable_http_error_true_when_no_response_attached() -> None:
    exc = requests.exceptions.HTTPError("boom")
    assert is_retryable_http_error(exc) is True


@pytest.mark.parametrize("status_code,expected", [(500, True), (503, True), (408, True), (404, False), (401, False)])
def test_is_retryable_http_error_filters_by_status_code(status_code: int, expected: bool) -> None:
    resp = SimpleNamespace(status_code=status_code)
    exc = requests.exceptions.HTTPError("boom")
    exc.response = resp  # type: ignore[attr-defined]
    assert is_retryable_http_error(exc) is expected


def test_retry_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    monkeypatch.setattr("app.utils.resilience.random.uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr("app.utils.resilience.time.sleep", lambda s: sleeps.append(s))

    calls = {"n": 0}

    @retry(cfg=RetryConfig(max_attempts=4, base_delay_s=0.01, max_delay_s=0.5, jitter_s=0.0))
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.Timeout()
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    assert sleeps, "Expected backoff sleeps before success"


def test_retry_stops_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.resilience.random.uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr("app.utils.resilience.time.sleep", lambda _s: None)

    calls = {"n": 0}

    @retry(cfg=RetryConfig(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0))
    def always_fails() -> str:
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("down")

    with pytest.raises(requests.exceptions.ConnectionError):
        always_fails()
    assert calls["n"] == 3


def test_retry_does_not_retry_when_is_retryable_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.resilience.time.sleep", lambda _s: None)

    calls = {"n": 0}

    @retry(
        cfg=RetryConfig(max_attempts=5, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
        retry_on=(requests.exceptions.HTTPError,),
        is_retryable=lambda _exc: False,
    )
    def fails_with_http_error() -> str:
        calls["n"] += 1
        raise requests.exceptions.HTTPError("nope")

    with pytest.raises(requests.exceptions.HTTPError):
        fails_with_http_error()
    assert calls["n"] == 1

