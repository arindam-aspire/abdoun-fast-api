from __future__ import annotations

from app.services.remember_me_tokens import generate_opaque_remember_me_token, hash_remember_me_opaque_token


def test_opaque_token_unique_and_hash_stable() -> None:
    a = generate_opaque_remember_me_token()
    b = generate_opaque_remember_me_token()
    assert a != b
    h = hash_remember_me_opaque_token(a)
    assert len(h) == 64
    assert hash_remember_me_opaque_token(a) == h
