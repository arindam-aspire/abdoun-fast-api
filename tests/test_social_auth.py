"""Social sign-in and sign-up for User and Owner accounts."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import RequestContext, get_request_context, require_any_role, require_authenticated_user
from app.api.v1.routes import auth as auth_routes
from app.core.config import get_settings
from app.core.tokens import create_token, verify_token
from app.models.live_schema import SocialAccount
from app.schemas.auth import SignUpRequest, SocialLoginRequest
from app.services.auth import create_auth_tokens, requires_password_set, serialize_user, verify_refresh_token
from app.services.social_auth import SocialIdentity, authenticate_social, verify_social_identity


def _settings(**updates):
    values = {
        "apple_oauth_client_ids": "apple-client",
        "apple_oauth_jwks_url": "https://jwks.example.test/apple",
        "apple_oauth_issuers": "https://appleid.apple.com",
        "social_token_leeway_seconds": 0,
        "social_provider_http_timeout_seconds": 5,
    }
    values.update(updates)
    return get_settings().model_copy(update=values)


def _user(**overrides):
    data = {
        "id": uuid4(),
        "email": "user@example.com",
        "full_name": "Test User",
        "phone_number": None,
        "is_active": True,
        "is_email_verified": True,
        "is_phone_verified": False,
        "password_hash": None,
        "deleted_at": None,
        "profile_picture_url": None,
        "created_at": None,
        "cognito_sub": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _identity(**overrides) -> SocialIdentity:
    data = {
        "provider": "google",
        "provider_user_id": "google-subject-1",
        "email": "new.user@example.com",
        "email_verified": True,
        "full_name": "New User",
    }
    data.update(overrides)
    return SocialIdentity(**data)


def _private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _id_token(private_key, **claims) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": "google-client",
        "sub": "google-subject-1",
        "exp": now + 600,
        "iat": now,
        "email": "New.User@Example.com",
        "email_verified": True,
        "name": "New User",
    }
    payload.update(claims)
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token if isinstance(token, str) else token.decode("ascii")


def _patch_signer(monkeypatch, private_key) -> None:
    monkeypatch.setattr("app.services.social_auth.get_settings", lambda: _settings())
    monkeypatch.setattr(
        "app.services.social_auth._signing_key_for_token",
        lambda jwks_url, token: SimpleNamespace(key=private_key.public_key()),
    )


def _error_code(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code"))
    return ""


def _patch_new_account(monkeypatch, identity: SocialIdentity | None = None):
    created: dict = {}
    identity = identity or _identity()

    def create_user(db, **kwargs):
        created["kwargs"] = kwargs
        user = _user(
            email=kwargs["email"],
            full_name=kwargs["full_name"],
            phone_number=kwargs["phone_number"],
            is_active=kwargs["is_active"],
            is_email_verified=False,
            is_phone_verified=True,
        )
        created["user"] = user
        return user

    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: identity)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    return created


@pytest.mark.parametrize(
    ("provider", "token_field"),
    [("google", "id_token"), ("facebook", "access_token")],
)
def test_direct_provider_tokens_are_rejected(monkeypatch, provider: str, token_field: str) -> None:
    private_key = _private_key()
    signer = MagicMock()
    monkeypatch.setattr("app.services.social_auth.get_settings", lambda: _settings())
    monkeypatch.setattr("app.services.social_auth._signing_key_for_token", signer)
    token = _id_token(private_key) if token_field == "id_token" else "facebook-user-token"

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider=provider, **{token_field: token})

    assert caught.value.status_code == 401
    assert _error_code(caught.value) == "SOCIAL_COGNITO_TOKEN_REQUIRED"
    signer.assert_not_called()
    assert token not in json.dumps(caught.value.detail)


def test_apple_accepts_string_email_verified(monkeypatch) -> None:
    private_key = _private_key()
    _patch_signer(monkeypatch, private_key)
    token = _id_token(
        private_key,
        iss="https://appleid.apple.com",
        aud="apple-client",
        sub="apple-subject-9",
        email="apple.owner@example.com",
        email_verified="true",
        name="",
        given_name="Apple",
        family_name="Owner",
    )

    identity = verify_social_identity(provider="apple", id_token=token)

    assert identity.provider == "apple"
    assert identity.provider_user_id == "apple-subject-9"
    assert identity.email_verified is True
    assert identity.full_name == "Apple Owner"


def test_new_user_social_signup_creates_registered_user(monkeypatch) -> None:
    created = _patch_new_account(monkeypatch)
    cognito = MagicMock()
    monkeypatch.setattr("app.services.auth.register_cognito_user", cognito)
    db = MagicMock()

    user, role_name = authenticate_social(db, provider="google", id_token="token", role="user")

    assert role_name == "registered_user"
    assert created["kwargs"]["role"] == "registered_user"
    assert created["kwargs"]["password"] is None
    assert created["kwargs"]["phone_number"] is None
    assert user.is_email_verified is True
    assert user.is_phone_verified is False
    assert user.phone_number is None
    cognito.assert_not_called()
    account = db.add.call_args.args[0]
    assert isinstance(account, SocialAccount)
    assert account.provider == "google"
    assert account.provider_user_id == "google-subject-1"
    assert account.user_id == user.id


def test_new_owner_social_signup(monkeypatch) -> None:
    created = _patch_new_account(monkeypatch, _identity(email="owner@example.com", full_name="Owner One"))

    user, role_name = authenticate_social(db=MagicMock(), provider="google", id_token="token", role="Owner")

    assert role_name == "owner"
    assert created["kwargs"]["role"] == "owner"
    assert user.email == "owner@example.com"
    assert user.is_phone_verified is False


def test_existing_user_social_login_reuses_account(monkeypatch) -> None:
    existing = _user(email="user@example.com")
    account = SimpleNamespace(user_id=existing.id)
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity(email=existing.email))
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )
    db = MagicMock()
    db.get.return_value = existing

    first_user, first_role = authenticate_social(db, provider="google", id_token="token", role="registered_user")
    second_user, second_role = authenticate_social(db, provider="google", id_token="token", role="user")

    assert first_user is existing
    assert second_user is existing
    assert first_role == "registered_user"
    assert second_role == "registered_user"
    create_user.assert_not_called()


def test_existing_owner_social_login_and_permissions(monkeypatch) -> None:
    existing = _user(email="owner@example.com", is_phone_verified=False)
    account = SimpleNamespace(user_id=existing.id)
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity(email=existing.email))
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="owner")],
    )
    db = MagicMock()
    db.get.return_value = existing

    user, role_name = authenticate_social(db, provider="apple", id_token="token", role="owner")

    assert user is existing
    assert role_name == "owner"
    role = SimpleNamespace(id=uuid4(), name="owner", description="Owner", created_at=None)
    monkeypatch.setattr("app.services.auth.load_user_roles", lambda db, user_id: [role])
    monkeypatch.setattr("app.services.auth.ensure_agent_can_authenticate", lambda db, account_user: None)
    monkeypatch.setattr("app.services.auth.primary_agency_id_for_context", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.auth.active_mappings", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "app.services.auth._role_permissions",
        lambda db, role_id: [
            {"id": "perm-1", "code": "owner.property.create", "description": "Create property", "created_at": None}
        ],
    )
    tokens = create_auth_tokens(db, user, role_name=role_name)
    access_payload = verify_token(tokens["access_token"], expected_type="access")
    assert access_payload is not None
    assert access_payload["roles"] == ["owner"]
    assert access_payload["role"]["role_name"] == "owner"
    assert "agent" not in access_payload["roles"]
    assert tokens["requires_password_set"] is False
    profile = serialize_user(db, user)
    assert profile["roles"][0]["name"] == "owner"
    assert profile["roles"][0]["permissions"][0]["code"] == "owner.property.create"
    assert profile["is_phone_verified"] is False
    assert profile["is_email_verified"] is True


def test_duplicate_provider_identity_returns_existing_account(monkeypatch) -> None:
    existing = _user()
    account = SimpleNamespace(user_id=existing.id)
    calls = {"count": 0}

    def find_account(db, provider, provider_user_id):
        calls["count"] += 1
        return None if calls["count"] == 1 else account

    def create_user(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("duplicate provider identity"))

    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr("app.services.social_auth._find_social_account", find_account)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )
    db = MagicMock()
    db.get.return_value = existing

    user, role_name = authenticate_social(db, provider="google", id_token="token", role="user")

    assert user is existing
    assert role_name == "registered_user"
    db.rollback.assert_called_once()


def test_logout_then_social_login_uses_same_account(monkeypatch) -> None:
    existing = _user()
    account = SimpleNamespace(user_id=existing.id)
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )
    db = MagicMock()
    db.get.return_value = existing

    logged_out = auth_routes.logout()
    user, role_name = authenticate_social(db, provider="google", id_token="token")

    assert logged_out["data"]["logged_out"] is True
    assert user.id == existing.id
    assert role_name is None


def test_existing_email_with_different_login_is_not_merged(monkeypatch) -> None:
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: _user())
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="google", id_token="token", role="owner")

    assert caught.value.status_code == 409
    assert _error_code(caught.value) == "SOCIAL_EMAIL_ALREADY_REGISTERED"
    create_user.assert_not_called()


def test_missing_verified_email_does_not_create_an_account(monkeypatch) -> None:
    create_user = MagicMock()
    looked_up = {"called": False}

    def finder(*args, **kwargs):
        looked_up["called"] = True
        return None

    monkeypatch.setattr(
        "app.services.social_auth.verify_social_identity",
        lambda **kwargs: _identity(email=None, email_verified=False),
    )
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", finder)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="apple", id_token="token", role="user")

    assert _error_code(caught.value) == "SOCIAL_PROFILE_INCOMPLETE"
    assert looked_up["called"] is False
    create_user.assert_not_called()


def test_unverified_provider_email_is_rejected(monkeypatch) -> None:
    create_user = MagicMock()
    monkeypatch.setattr(
        "app.services.social_auth.verify_social_identity",
        lambda **kwargs: _identity(email_verified=False),
    )
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="google", id_token="token", role="user")

    assert _error_code(caught.value) == "SOCIAL_EMAIL_NOT_VERIFIED"
    create_user.assert_not_called()


@pytest.mark.parametrize("role", ["agent", "admin", "agency_admin", "super_admin", "Agency Admin"])
def test_unsupported_role_cannot_be_created(monkeypatch, role: str) -> None:
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="google", id_token="token", role=role)

    assert caught.value.status_code == 403
    assert _error_code(caught.value) == "SOCIAL_ROLE_NOT_ALLOWED"
    create_user.assert_not_called()


def test_existing_user_cannot_escalate_to_owner_or_agent(monkeypatch) -> None:
    existing = _user()
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(
        "app.services.social_auth._find_social_account",
        lambda *args, **kwargs: SimpleNamespace(user_id=existing.id),
    )
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )
    db = MagicMock()
    db.get.return_value = existing

    user, role_name = authenticate_social(db, provider="google", id_token="token", role="owner")
    with pytest.raises(HTTPException) as agent_attempt:
        authenticate_social(db, provider="google", id_token="token", role="agent")

    assert user is existing
    assert role_name == "registered_user"
    assert agent_attempt.value.status_code == 403
    create_user.assert_not_called()


def test_privileged_account_cannot_use_social_sign_in(monkeypatch) -> None:
    existing = _user()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(
        "app.services.social_auth._find_social_account",
        lambda *args, **kwargs: SimpleNamespace(user_id=existing.id),
    )
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="owner"), SimpleNamespace(name="agent")],
    )
    db = MagicMock()
    db.get.return_value = existing

    with pytest.raises(HTTPException) as caught:
        authenticate_social(db, provider="google", id_token="token", role="owner")

    assert caught.value.status_code == 403
    assert _error_code(caught.value) == "SOCIAL_ROLE_NOT_ALLOWED"


def test_social_route_returns_password_login_token_shape(monkeypatch) -> None:
    user = _user()
    monkeypatch.setattr(auth_routes, "authenticate_social", lambda db, **kwargs: (user, "registered_user"))

    def fake_tokens(db, account_user, role_name=None):
        assert account_user is user
        assert role_name == "registered_user"
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "app-id-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "requires_password_set": False,
            "remember_me_cookie": False,
        }

    monkeypatch.setattr(auth_routes, "create_auth_tokens", fake_tokens)
    db = MagicMock()
    response = auth_routes.login_with_social(
        SocialLoginRequest(provider="google", id_token="provider-secret-token", role="user"),
        db,
    )

    assert response["success"] is True
    assert response["message"] == "Signed in successfully"
    assert set(response["data"]) == {
        "access_token",
        "refresh_token",
        "id_token",
        "token_type",
        "expires_in",
        "requires_password_set",
        "remember_me_cookie",
    }
    encoded = json.dumps(response)
    assert "provider-secret-token" not in encoded
    assert "otp" not in encoded.lower()
    db.commit.assert_called_once()


def test_social_refresh_uses_existing_token_flow(monkeypatch) -> None:
    user = _user(email="owner@example.com", password_hash=None)
    role = SimpleNamespace(name="owner")
    monkeypatch.setattr("app.services.auth.load_user_roles", lambda db, user_id: [role])
    monkeypatch.setattr("app.services.auth.ensure_agent_can_authenticate", lambda db, account_user: None)
    db = MagicMock()
    db.get.return_value = user

    tokens = create_auth_tokens(db, user, role_name="owner")
    refreshed = verify_refresh_token(db, tokens["refresh_token"], "owner@example.com")

    assert refreshed is user
    with pytest.raises(HTTPException) as caught:
        verify_refresh_token(db, tokens["refresh_token"], "other@example.com")
    assert caught.value.status_code == 401


def test_request_ignores_client_profile_and_still_requires_a_token() -> None:
    payload = SocialLoginRequest.model_validate(
        {
            "provider": "google",
            "id_token": "provider-token",
            "role": "admin",
            "email": "attacker@example.com",
            "email_verified": True,
            "full_name": "Attacker",
            "phone_number": "+15550001111",
        }
    )

    assert payload.provider == "google"
    assert "email" not in payload.model_dump()
    assert "phone_number" not in payload.model_dump()
    with pytest.raises(ValidationError):
        SocialLoginRequest.model_validate({"provider": "google", "role": "owner"})
    coded = SocialLoginRequest.model_validate(
        {
            "provider": "facebook",
            "role": "owner",
            "code": "auth-code",
            "code_verifier": "verifier",
            "redirect_uri": "http://localhost:3000/en/auth/social/callback",
        }
    )
    assert coded.code == "auth-code"
    assert coded.id_token is None


def test_new_social_signup_requires_a_supported_role(monkeypatch) -> None:
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth.verify_social_identity", lambda **kwargs: _identity())
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="google", id_token="token")

    assert caught.value.status_code == 400
    assert _error_code(caught.value) == "SOCIAL_ROLE_REQUIRED"
    create_user.assert_not_called()


def test_social_owner_does_not_require_a_password_but_other_passwordless_accounts_do() -> None:
    owner = _user(password_hash=None)
    owner_role = SimpleNamespace(name="owner")
    social_db = MagicMock()
    social_db.execute.return_value.first.return_value = (owner.id,)
    assert requires_password_set(social_db, owner, [owner_role]) is False

    agency_admin = _user(password_hash=None)
    admin_role = SimpleNamespace(name="admin")
    admin_db = MagicMock()
    admin_db.execute.return_value.first.return_value = None
    assert requires_password_set(admin_db, agency_admin, [admin_role]) is True


def test_password_signup_schema_still_requires_a_password() -> None:
    with pytest.raises(ValidationError):
        SignUpRequest.model_validate(
            {
                "full_name": "Password User",
                "email": "password.user@example.com",
                "role": "registered_user",
            }
        )


COGNITO_ISSUER = "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_testpool"
COGNITO_CLIENT = "cognito-app-client"
COGNITO_POOL = "us-west-2_testpool"


def _cognito_settings(**updates):
    values = {
        "cognito_region": "us-west-2",
        "cognito_user_pool_id": COGNITO_POOL,
        "cognito_app_client_id": COGNITO_CLIENT,
        "cognito_issuer": COGNITO_ISSUER,
        "cognito_jwks_url": "https://jwks.example.test/cognito",
        "cognito_google_provider_names": "Google",
        "cognito_facebook_provider_names": "Facebook",
        "cognito_apple_provider_names": "SignInWithApple,Apple",
    }
    values.update(updates)
    return _settings(**values)


def _cognito_token(
    private_key,
    *,
    provider: str,
    provider_user_id: str,
    cognito_sub: str,
    email: str,
    **claims,
) -> str:
    provider_name = {"google": "Google", "facebook": "Facebook"}[provider]
    now = int(time.time())
    payload = {
        "iss": COGNITO_ISSUER,
        "aud": COGNITO_CLIENT,
        "sub": cognito_sub,
        "exp": now + 600,
        "iat": now,
        "token_use": "id",
        "email": email,
        "email_verified": True,
        "name": "Social User",
        "cognito:username": f"{provider_name}_{provider_user_id}",
        "identities": [
            {
                "userId": provider_user_id,
                "providerName": provider_name,
                "providerType": provider_name,
                "primary": "true",
            }
        ],
        "role": "super_admin",
    }
    payload.update(claims)
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token if isinstance(token, str) else token.decode("ascii")


def _patch_cognito_signer(monkeypatch, private_key, **settings) -> None:
    monkeypatch.setattr("app.services.social_auth.get_settings", lambda: _cognito_settings(**settings))
    monkeypatch.setattr(
        "app.services.social_auth._signing_key_for_token",
        lambda jwks_url, token: SimpleNamespace(key=private_key.public_key()),
    )


def _patch_account_creation(monkeypatch):
    created: dict = {}

    def create_user(db, **kwargs):
        created["kwargs"] = kwargs
        user = _user(
            email=kwargs["email"],
            full_name=kwargs["full_name"],
            phone_number=kwargs["phone_number"],
            is_active=kwargs["is_active"],
            is_email_verified=False,
            is_phone_verified=True,
            cognito_sub=None,
        )
        created["user"] = user
        return user

    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth._find_user_by_cognito_sub", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    return created


@pytest.mark.parametrize(
    ("provider", "provider_user_id", "cognito_sub", "email", "requested_role", "stored_role"),
    [
        ("google", "google-user-1", "cognito-google-user", "Google.User@Example.com", "user", "registered_user"),
        ("google", "google-owner-1", "cognito-google-owner", "Google.Owner@Example.com", "Owner", "owner"),
        ("facebook", "fb-user-1", "cognito-facebook-user", "Facebook.User@Example.com", "registered_user", "registered_user"),
        ("facebook", "fb-owner-1", "cognito-facebook-owner", "Facebook.Owner@Example.com", "property_owner", "owner"),
    ],
)
def test_cognito_new_social_signup_creates_the_requested_role(
    monkeypatch,
    provider: str,
    provider_user_id: str,
    cognito_sub: str,
    email: str,
    requested_role: str,
    stored_role: str,
) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    created = _patch_account_creation(monkeypatch)
    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=provider_user_id,
        cognito_sub=cognito_sub,
        email=email,
    )

    db = MagicMock()
    user, role_name = authenticate_social(db, provider=provider, id_token=token, role=requested_role)

    assert role_name == stored_role
    assert created["kwargs"]["role"] == stored_role
    assert created["kwargs"]["password"] is None
    assert user.cognito_sub == cognito_sub
    assert user.email == email.lower()
    assert user.is_email_verified is True
    assert user.is_phone_verified is False
    account = db.add.call_args.args[0]
    assert isinstance(account, SocialAccount)
    assert account.provider == provider
    assert account.provider_user_id == provider_user_id
    assert account.user_id == user.id


def test_cognito_signup_persists_provider_subject_not_client_claims(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    created = _patch_account_creation(monkeypatch)
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-subject-77",
        cognito_sub="cognito-subject-77",
        email="New.Google@Example.com",
        phone_number="+15550001111",
    )
    db = MagicMock()

    user, role_name = authenticate_social(db, provider="google", id_token=token, role="user")

    assert role_name == "registered_user"
    assert created["kwargs"]["role"] == "registered_user"
    assert user.cognito_sub == "cognito-subject-77"
    account = db.add.call_args.args[0]
    assert isinstance(account, SocialAccount)
    assert account.provider == "google"
    assert account.provider_user_id == "google-subject-77"
    assert token not in json.dumps(created["kwargs"])


def test_cognito_facebook_signup_accepts_mapped_email_without_verified_claim(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    created = _patch_account_creation(monkeypatch)
    token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="fb-unverified-claim",
        cognito_sub="cognito-fb-unverified",
        email="Facebook.New@Example.com",
        email_verified=False,
    )

    user, role_name = authenticate_social(MagicMock(), provider="facebook", id_token=token, role="user")

    assert role_name == "registered_user"
    assert user.email == "facebook.new@example.com"
    assert user.is_email_verified is True
    assert created["kwargs"]["role"] == "registered_user"
    assert token not in json.dumps(created["kwargs"])


def test_cognito_google_unverified_email_does_not_create_an_account(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    created = _patch_account_creation(monkeypatch)
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-unverified",
        cognito_sub="cognito-google-unverified",
        email="unverified.google@example.com",
        email_verified=False,
    )

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="google", id_token=token, role="owner")

    assert _error_code(caught.value) == "SOCIAL_EMAIL_NOT_VERIFIED"
    assert "user" not in created
    assert token not in json.dumps(caught.value.detail)


@pytest.mark.parametrize("provider", ["google", "facebook"])
def test_cognito_existing_social_account_keeps_persisted_role(monkeypatch, provider: str) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    stored_role = "owner" if provider == "facebook" else "registered_user"
    existing = _user(email="kept@example.com", cognito_sub=None)
    account = SimpleNamespace(user_id=existing.id, updated_at=None)
    create_user = MagicMock()
    cognito_lookup = MagicMock()
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: account)
    monkeypatch.setattr("app.services.social_auth._find_user_by_cognito_sub", cognito_lookup)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name=stored_role)],
    )
    db = MagicMock()
    db.get.return_value = existing
    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=f"{provider}-subject",
        cognito_sub=f"cognito-{provider}",
        email="different@example.com",
    )

    user, role_name = authenticate_social(db, provider=provider, id_token=token, role=stored_role)

    assert user is existing
    assert user.email == "kept@example.com"
    assert user.cognito_sub == f"cognito-{provider}"
    assert role_name == stored_role
    create_user.assert_not_called()
    cognito_lookup.assert_not_called()


@pytest.mark.parametrize("provider", ["google", "facebook"])
def test_existing_cognito_user_without_application_social_row_is_reused(monkeypatch, provider: str) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    existing = _user(email="existing.owner@example.com", cognito_sub=f"cognito-{provider}-existing")
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.services.social_auth._find_user_by_cognito_sub",
        lambda db, subject: existing,
    )
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="owner")],
    )
    db = MagicMock()
    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=f"{provider}-idp-id",
        cognito_sub=existing.cognito_sub,
        email="other.email@example.com",
    )

    user, role_name = authenticate_social(db, provider=provider, id_token=token, role="owner")

    assert user is existing
    assert user.email == "existing.owner@example.com"
    assert role_name == "owner"
    create_user.assert_not_called()
    account = db.add.call_args.args[0]
    assert isinstance(account, SocialAccount)
    assert account.provider == provider
    assert account.provider_user_id == f"{provider}-idp-id"
    assert account.user_id == existing.id


@pytest.mark.parametrize("provider", ["google", "facebook"])
def test_cognito_existing_user_role_is_not_replaced(monkeypatch, provider: str) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    existing = _user(cognito_sub=f"cognito-{provider}-role")
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth._find_user_by_cognito_sub", lambda db, subject: existing)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )

    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=f"{provider}-role-id",
        cognito_sub=existing.cognito_sub,
        email=existing.email,
    )
    user, role_name = authenticate_social(MagicMock(), provider=provider, id_token=token, role="owner")

    assert user is existing
    assert role_name == "registered_user"
    create_user.assert_not_called()


def test_cognito_email_already_registered_is_not_merged(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    create_user = MagicMock()
    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth._find_user_by_cognito_sub", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: _user())
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="fb-existing-email",
        cognito_sub="cognito-new-subject",
        email="user@example.com",
    )

    with pytest.raises(HTTPException) as caught:
        authenticate_social(MagicMock(), provider="facebook", id_token=token, role="user")

    assert caught.value.status_code == 409
    assert _error_code(caught.value) == "SOCIAL_EMAIL_ALREADY_REGISTERED"
    create_user.assert_not_called()


def test_concurrent_cognito_signup_returns_the_existing_user(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    existing = _user(cognito_sub="cognito-race")
    lookups = {"count": 0}

    def find_cognito(db, subject):
        lookups["count"] += 1
        return None if lookups["count"] == 1 else existing

    def create_user(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("duplicate cognito subject"))

    monkeypatch.setattr("app.services.social_auth._find_social_account", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth._find_user_by_cognito_sub", find_cognito)
    monkeypatch.setattr("app.services.social_auth.find_user_by_username", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.social_auth.create_user", create_user)
    monkeypatch.setattr(
        "app.services.social_auth.load_user_roles",
        lambda db, user_id: [SimpleNamespace(name="registered_user")],
    )
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-race",
        cognito_sub="cognito-race",
        email="race@example.com",
    )
    db = MagicMock()

    user, role_name = authenticate_social(db, provider="google", id_token=token, role="user")

    assert user is existing
    assert role_name == "registered_user"
    db.rollback.assert_called_once()
    account = db.add.call_args.args[0]
    assert account.provider_user_id == "google-race"


@pytest.mark.parametrize("provider", ["google", "facebook"])
def test_expired_cognito_token_is_rejected(monkeypatch, provider: str) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=f"{provider}-expired",
        cognito_sub=f"cognito-{provider}-expired",
        email="expired@example.com",
        exp=int(time.time()) - 120,
    )

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider=provider, id_token=token)

    assert caught.value.status_code == 401
    assert _error_code(caught.value) == "SOCIAL_TOKEN_EXPIRED"
    assert token not in json.dumps(caught.value.detail)


@pytest.mark.parametrize("provider", ["google", "facebook"])
def test_invalid_cognito_signature_is_rejected(monkeypatch, provider: str) -> None:
    private_key = _private_key()
    other_key = _private_key()
    monkeypatch.setattr("app.services.social_auth.get_settings", lambda: _cognito_settings())
    monkeypatch.setattr(
        "app.services.social_auth._signing_key_for_token",
        lambda jwks_url, token: SimpleNamespace(key=other_key.public_key()),
    )
    token = _cognito_token(
        private_key,
        provider=provider,
        provider_user_id=f"{provider}-bad-signature",
        cognito_sub=f"cognito-{provider}-bad",
        email="bad@example.com",
    )

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider=provider, id_token=token)

    assert _error_code(caught.value) == "SOCIAL_TOKEN_INVALID"
    assert token not in json.dumps(caught.value.detail)


def test_cognito_wrong_issuer_and_audience_are_rejected(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    wrong_issuer = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-issuer",
        cognito_sub="cognito-issuer",
        email="issuer@example.com",
        iss="https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_other",
    )
    wrong_audience = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="fb-audience",
        cognito_sub="cognito-audience",
        email="audience@example.com",
        aud="some-other-client",
    )

    with pytest.raises(HTTPException) as issuer_error:
        verify_social_identity(provider="google", id_token=wrong_issuer)
    with pytest.raises(HTTPException) as audience_error:
        verify_social_identity(provider="facebook", id_token=wrong_audience)

    assert issuer_error.value.status_code == 401
    assert "issuer" in str(issuer_error.value.detail).lower()
    assert _error_code(audience_error.value) == "SOCIAL_TOKEN_INVALID"
    assert "audience" in str(audience_error.value.detail).lower()


def test_cognito_provider_must_match_the_verified_identity(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-not-facebook",
        cognito_sub="cognito-mismatch",
        email="mismatch@example.com",
    )

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider="facebook", id_token=token)

    assert _error_code(caught.value) == "SOCIAL_TOKEN_INVALID"
    assert token not in json.dumps(caught.value.detail)


def test_cognito_access_token_is_not_accepted_as_identity(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="fb-access",
        cognito_sub="cognito-access",
        email="access@example.com",
        token_use="access",
    )

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider="facebook", access_token=token)

    assert _error_code(caught.value) == "SOCIAL_TOKEN_INVALID"
    assert "identity token" in str(caught.value.detail).lower()
    assert token not in json.dumps(caught.value.detail)


def test_cognito_username_identifies_provider_when_identities_claim_is_absent(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="username-user",
        cognito_sub="cognito-username",
        email="username@example.com",
        identities=None,
    )

    identity = verify_social_identity(provider="google", id_token=token)

    assert identity.provider == "google"
    assert identity.provider_user_id == "username-user"
    assert identity.cognito_sub == "cognito-username"


def test_cognito_provider_type_matches_when_provider_name_is_custom(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="fb-custom-name",
        cognito_sub="cognito-fb-custom",
        email="custom.facebook@example.com",
        identities=[
            {
                "userId": "fb-custom-name",
                "providerName": "MLS Facebook",
                "providerType": "Facebook",
            }
        ],
    )

    identity = verify_social_identity(provider="facebook", id_token=token)

    assert identity.provider == "facebook"
    assert identity.provider_user_id == "fb-custom-name"
    assert identity.cognito_sub == "cognito-fb-custom"


def test_cognito_accepts_identities_encoded_as_json(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(monkeypatch, private_key)
    token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="json-fb-user",
        cognito_sub="cognito-json-fb",
        email="json.fb@example.com",
        identities=json.dumps(
            [{"userId": "json-fb-user", "providerName": "Facebook", "providerType": "Facebook"}]
        ),
    )

    identity = verify_social_identity(provider="facebook", id_token=token)

    assert identity.provider_user_id == "json-fb-user"
    assert identity.email == "json.fb@example.com"


def test_unconfigured_cognito_pool_rejects_a_cognito_token(monkeypatch) -> None:
    private_key = _private_key()
    _patch_cognito_signer(
        monkeypatch,
        private_key,
        cognito_issuer="",
        cognito_jwks_url="",
        cognito_region="",
        cognito_user_pool_id="",
        cognito_app_client_id="",
    )
    token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="google-unconfigured",
        cognito_sub="cognito-unconfigured",
        email="unconfigured@example.com",
    )

    with pytest.raises(HTTPException) as caught:
        verify_social_identity(provider="google", id_token=token)

    assert caught.value.status_code == 503
    assert _error_code(caught.value) == "SOCIAL_PROVIDER_NOT_CONFIGURED"


def test_cognito_issuer_and_jwks_are_derived_from_pool_settings() -> None:
    derived = _cognito_settings(cognito_issuer="", cognito_jwks_url="", cognito_region="eu-central-1", cognito_user_pool_id="eu-central-1_pool")
    explicit = _cognito_settings(
        cognito_issuer="https://issuer.example.test",
        cognito_jwks_url="",
        cognito_region="eu-central-1",
        cognito_user_pool_id="eu-central-1_pool",
    )

    assert derived.resolved_cognito_issuer() == "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_pool"
    assert derived.resolved_cognito_jwks_url() == (
        "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_pool/.well-known/jwks.json"
    )
    assert explicit.resolved_cognito_issuer() == "https://issuer.example.test"
    assert explicit.resolved_cognito_jwks_url() == "https://issuer.example.test/.well-known/jwks.json"


def test_derived_cognito_issuer_validates_google_and_facebook_tokens(monkeypatch) -> None:
    private_key = _private_key()
    issuer = "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_pool"
    _patch_cognito_signer(
        monkeypatch,
        private_key,
        cognito_issuer="",
        cognito_jwks_url="",
        cognito_region="eu-central-1",
        cognito_user_pool_id="eu-central-1_pool",
        cognito_app_client_id=COGNITO_CLIENT,
    )
    google_token = _cognito_token(
        private_key,
        provider="google",
        provider_user_id="derived-google",
        cognito_sub="cognito-derived-google",
        email="derived.google@example.com",
        iss=issuer,
    )
    facebook_token = _cognito_token(
        private_key,
        provider="facebook",
        provider_user_id="derived-facebook",
        cognito_sub="cognito-derived-facebook",
        email="derived.facebook@example.com",
        iss=issuer,
    )

    google_identity = verify_social_identity(provider="google", id_token=google_token)
    facebook_identity = verify_social_identity(provider="facebook", id_token=facebook_token)

    assert google_identity.cognito_sub == "cognito-derived-google"
    assert facebook_identity.provider_user_id == "derived-facebook"


def test_social_tokens_follow_existing_authorization_dependencies(monkeypatch) -> None:
    def issue(role_name: str) -> RequestContext:
        user = _user()
        role = SimpleNamespace(name=role_name)
        monkeypatch.setattr("app.services.auth.load_user_roles", lambda db, user_id: [role])
        monkeypatch.setattr("app.services.auth.ensure_agent_can_authenticate", lambda db, account_user: None)
        tokens = create_auth_tokens(MagicMock(), user, role_name=role_name)
        payload = verify_token(tokens["access_token"], expected_type="access")
        assert payload is not None
        assert payload["roles"] == [role_name]
        assert payload["role"]["role_name"] == role_name
        return RequestContext(locale="en", user_id=user.id, roles=tuple(payload["roles"]))

    user_context = issue("registered_user")
    owner_context = issue("owner")

    assert require_authenticated_user(user_context).user_id == user_context.user_id
    assert require_any_role("registered_user")(user_context).roles == ("registered_user",)
    assert require_any_role("owner", "registered_user")(user_context).user_id == user_context.user_id
    assert require_any_role("owner")(owner_context).roles == ("owner",)
    assert require_any_role("owner", "registered_user")(owner_context).roles == ("owner",)

    with pytest.raises(HTTPException) as user_on_owner_only:
        require_any_role("owner")(user_context)
    with pytest.raises(HTTPException) as owner_on_admin:
        require_any_role("admin", "super_admin")(owner_context)
    with pytest.raises(HTTPException) as missing_token:
        require_authenticated_user(RequestContext(locale="en"))

    assert user_on_owner_only.value.status_code == 403
    assert owner_on_admin.value.status_code == 403
    assert missing_token.value.status_code == 401

    invalid = get_request_context(MagicMock(), authorization="Bearer not-a-token", accept_language="en")
    anonymous = get_request_context(MagicMock(), authorization=None, accept_language="en")
    expired = create_token(
        subject=str(uuid4()),
        token_type="access",
        expires_in_seconds=-30,
        role_name="owner",
        roles=["owner"],
    )
    expired_context = get_request_context(MagicMock(), authorization=f"Bearer {expired}", accept_language="en")
    assert invalid.user_id is None
    assert anonymous.user_id is None
    assert expired_context.user_id is None
    assert verify_token("not-a-token", expected_type="access") is None
    assert verify_token(expired, expected_type="access") is None
