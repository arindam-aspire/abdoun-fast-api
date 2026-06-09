"""Unit tests for Cognito social login URL generation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.cognito import CognitoService


def test_get_social_login_url_encodes_scope_and_redirect_uri() -> None:
    service = CognitoService()
    fake_settings = SimpleNamespace(
        cognito_domain="prefix.auth.us-west-2.amazoncognito.com",
        social_redirect_uri="https://dev-api.example.com/api/v1/auth/callback",
    )
    service.client_id = "test-client-id"

    with patch("app.services.cognito.settings", fake_settings):
        url = service.get_social_login_url("Google")

    assert url.startswith("https://prefix.auth.us-west-2.amazoncognito.com/oauth2/authorize?")
    assert "scope=openid+email+profile" in url or "scope=openid%20email%20profile" in url
    assert "redirect_uri=https%3A%2F%2Fdev-api.example.com%2Fapi%2Fv1%2Fauth%2Fcallback" in url
    assert "identity_provider=Google" in url
    assert " " not in url.split("?", 1)[1]
