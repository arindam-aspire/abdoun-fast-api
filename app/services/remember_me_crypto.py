"""Encrypt/decrypt Cognito refresh tokens at rest for Remember Me sessions."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.utils.constants import RememberMeConstants


def remember_me_fernet(settings: Settings) -> Fernet:
    """Build a Fernet instance from configured master secret or profile OTP pepper."""
    material = (settings.remember_me_master_secret or settings.profile_otp_pepper or "").encode(
        "utf-8"
    )
    digest = hashlib.sha256(
        material + RememberMeConstants.FERNET_KEY_DERIVE_LABEL.encode("utf-8")
    ).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_refresh_token(settings: Settings, refresh_token: str) -> str:
    return remember_me_fernet(settings).encrypt(refresh_token.encode("utf-8")).decode("utf-8")


def decrypt_refresh_token(settings: Settings, ciphertext: str) -> str | None:
    try:
        return remember_me_fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
