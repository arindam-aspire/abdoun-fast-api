from __future__ import annotations

from app.core.config import Settings
from app.services.remember_me_crypto import decrypt_refresh_token, encrypt_refresh_token


def test_encrypt_decrypt_roundtrip() -> None:
    settings = Settings()
    rt = "cognito-refresh-token-value"
    enc = encrypt_refresh_token(settings, rt)
    assert enc != rt
    assert decrypt_refresh_token(settings, enc) == rt


def test_decrypt_invalid_returns_none() -> None:
    settings = Settings()
    assert decrypt_refresh_token(settings, "not-valid-fernet") is None
