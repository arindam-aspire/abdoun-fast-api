from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.agency import (
    AgencyInvitationAcceptRequest,
    AgencyInvitationCreateRequest,
    AgencyOfflineRegistrationRequest,
)
from app.schemas.agents import normalize_phone, validate_e164_phone
from app.services.agency_workflows import (
    ACTIVE,
    APPROVED,
    PENDING_APPROVAL,
    agency_response,
    offline_register_agency,
    resend_agency_password_setup,
)
from app.services.auth import CognitoUsernameExists, register_cognito_user


# ---------------------------------------------------------------------------
# Phone normalisation in agency schemas
# ---------------------------------------------------------------------------

class TestAgencyPhoneNormalization:
    def test_offline_registration_normalizes_phone(self):
        req = AgencyOfflineRegistrationRequest(
            agency_name="Test",
            agency_trade_name="Test",
            email="a@b.com",
            phone="+962 7 1234 5678",
        )
        assert req.phone == "+962712345678"

    def test_offline_registration_rejects_invalid_phone(self):
        with pytest.raises(Exception):
            AgencyOfflineRegistrationRequest(
                agency_name="Test",
                agency_trade_name="Test",
                email="a@b.com",
                phone="abc",
            )

    def test_invitation_accept_normalizes_phone(self):
        req = AgencyInvitationAcceptRequest(
            token="tok",
            agency_name="A",
            agency_trade_name="A",
            phone="  +962-7-999-0000  ",
        )
        assert req.phone == "+96279990000"

    def test_invitation_create_normalizes_phone(self):
        req = AgencyInvitationCreateRequest(
            email="a@b.com",
            phone=" +962 700 0000 ",
        )
        assert req.phone == "+9627000000"

    def test_invitation_create_allows_none_phone(self):
        req = AgencyInvitationCreateRequest(email="a@b.com")
        assert req.phone is None


# ---------------------------------------------------------------------------
# Password link suppression for ACTIVE agencies
# ---------------------------------------------------------------------------

class TestPasswordLinkSuppression:
    @staticmethod
    def _mock_agency(status: str):
        agency = SimpleNamespace(
            id=uuid4(),
            agency_name="Agency",
            agency_trade_name="Agency",
            legal_document_s3_link="s3://doc",
            email="a@b.com",
            phone="+962700000000",
            logo_url=None,
            website=None,
            address=None,
            city=None,
            state=None,
            country=None,
            zip_code=None,
            is_active=status == ACTIVE,
            is_verified=status in {APPROVED, ACTIVE},
            status=status,
            currency="JOD",
            measurement_unit="sqm",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return agency

    @patch("app.services.agency_workflows.serialize_agency", return_value={"id": "test"})
    def test_password_link_suppressed_for_active(self, _mock_serialize):
        agency = self._mock_agency(ACTIVE)
        result = agency_response(agency, password_setup_token="secret-token")
        assert result["password_setup_token"] is None
        assert result["password_setup_link"] is None

    @patch("app.services.agency_workflows.serialize_agency", return_value={"id": "test"})
    def test_password_link_exposed_for_approved(self, _mock_serialize):
        agency = self._mock_agency(APPROVED)
        result = agency_response(agency, password_setup_token="secret-token")
        assert result["password_setup_token"] == "secret-token"
        assert result["password_setup_link"] is not None
        assert "secret-token" in result["password_setup_link"]

    @patch("app.services.agency_workflows.serialize_agency", return_value={"id": "test"})
    def test_password_link_none_when_no_token(self, _mock_serialize):
        agency = self._mock_agency(APPROVED)
        result = agency_response(agency)
        assert result["password_setup_token"] is None
        assert result["password_setup_link"] is None

    def test_resend_blocked_for_active_agency(self):
        agency = self._mock_agency(ACTIVE)
        with pytest.raises(HTTPException) as exc_info:
            resend_agency_password_setup(MagicMock(), agency=agency, actor_id=uuid4())
        assert exc_info.value.status_code == 400
        assert "already active" in str(exc_info.value.detail).lower()

    def test_resend_blocked_for_pending_agency(self):
        agency = self._mock_agency(PENDING_APPROVAL)
        with pytest.raises(HTTPException) as exc_info:
            resend_agency_password_setup(MagicMock(), agency=agency, actor_id=uuid4())
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Invitation link format
# ---------------------------------------------------------------------------

class TestInvitationLinkFormat:
    @patch("app.services.agency_workflows.get_settings")
    def test_agency_invitation_link_includes_base_url(self, mock_settings):
        mock_settings.return_value.frontend_base_url = "https://app.example.com"
        from app.services.agency_workflows import _agency_invitation_link

        link = _agency_invitation_link("tok123")
        assert link == "https://app.example.com/agency-invitation?token=tok123"

    @patch("app.services.agency_workflows.get_settings")
    def test_agency_activation_link_includes_base_url(self, mock_settings):
        mock_settings.return_value.frontend_base_url = "https://app.example.com"
        from app.services.agency_workflows import _agency_activation_link

        link = _agency_activation_link("tok456")
        assert link == "https://app.example.com/agency-password-setup?token=tok456"

    @patch("app.services.agents.get_settings")
    def test_agent_invite_link_includes_base_url(self, mock_settings):
        mock_settings.return_value.frontend_base_url = "https://app.example.com"
        from app.services.agents import _invite_link

        link = _invite_link("tok789")
        assert link == "https://app.example.com/agent-invite?token=tok789"

    @patch("app.services.agents.get_settings")
    def test_agent_password_setup_link_includes_base_url(self, mock_settings):
        mock_settings.return_value.frontend_base_url = "https://app.example.com"
        from app.services.agents import _password_setup_link

        link = _password_setup_link("tokABC")
        assert link == "https://app.example.com/agent-password-setup?token=tokABC"


# ---------------------------------------------------------------------------
# Offline registration Cognito signup
# ---------------------------------------------------------------------------

class TestOfflineRegistrationCognito:
    @staticmethod
    def _payload() -> AgencyOfflineRegistrationRequest:
        return AgencyOfflineRegistrationRequest(
            agency_name="Offline Agency",
            agency_trade_name="Offline Trade",
            email="offline.agency@example.com",
            phone="+962712345678",
        )

    @staticmethod
    def _agency():
        return SimpleNamespace(
            id=uuid4(),
            agency_name="Offline Agency",
            agency_trade_name="Offline Trade",
            email="offline.agency@example.com",
            phone="+962712345678",
            status=PENDING_APPROVAL,
        )

    @staticmethod
    def _user():
        return SimpleNamespace(
            email="offline.agency@example.com",
            full_name="Offline Trade",
            phone_number="+962712345678",
            is_active=True,
            cognito_sub=None,
        )

    @patch("app.services.agency_workflows.record_activity")
    @patch("app.services.agency_workflows.register_cognito_user", return_value="cognito-sub-123")
    @patch("app.services.agency_workflows.create_agency_admin_user")
    @patch("app.services.agency_workflows.create_agency_record")
    def test_stores_cognito_sub_and_keeps_pending_inactive_user(
        self,
        mock_create_agency,
        mock_create_user,
        mock_cognito,
        _mock_activity,
    ):
        agency = self._agency()
        user = self._user()
        mock_create_agency.return_value = agency
        mock_create_user.return_value = user

        result_agency, token = offline_register_agency(
            MagicMock(),
            payload=self._payload(),
            actor_id=uuid4(),
        )

        mock_cognito.assert_called_once_with(
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
            on_existing="reuse",
            resolve_sub=True,
        )
        assert user.cognito_sub == "cognito-sub-123"
        assert user.is_active is False
        assert token is None
        assert result_agency is agency
        assert result_agency.status == PENDING_APPROVAL

    @patch("app.services.agency_workflows.record_activity")
    @patch("app.services.agency_workflows.register_cognito_user", return_value="existing-sub")
    @patch("app.services.agency_workflows.create_agency_admin_user")
    @patch("app.services.agency_workflows.create_agency_record")
    def test_reuses_existing_cognito_sub_without_duplicate(
        self,
        mock_create_agency,
        mock_create_user,
        mock_cognito,
        _mock_activity,
    ):
        user = self._user()
        mock_create_agency.return_value = self._agency()
        mock_create_user.return_value = user

        offline_register_agency(MagicMock(), payload=self._payload(), actor_id=uuid4())

        assert mock_cognito.call_count == 1
        assert user.cognito_sub == "existing-sub"

    @patch("app.services.auth.cognito_service")
    def test_register_cognito_user_reuses_existing_instead_of_signup_duplicate(self, mock_cognito):
        mock_cognito.enabled = True
        mock_cognito.signup.side_effect = CognitoUsernameExists()
        mock_cognito.get_user_status.return_value = "UNCONFIRMED"
        mock_cognito.get_user_sub.return_value = "existing-sub-456"

        sub = register_cognito_user(
            email="offline.agency@example.com",
            full_name="Offline Trade",
            phone_number="+962712345678",
            on_existing="reuse",
            resolve_sub=True,
        )

        assert sub == "existing-sub-456"
        mock_cognito.signup.assert_called_once()
        mock_cognito.resend_confirmation_code.assert_not_called()
        mock_cognito.get_user_sub.assert_called_once_with(email="offline.agency@example.com")

    @patch("app.services.auth.cognito_service")
    def test_register_cognito_user_propagates_cognito_errors(self, mock_cognito):
        mock_cognito.enabled = True
        mock_cognito.signup.side_effect = HTTPException(status_code=400, detail="Unable to register account")

        with pytest.raises(HTTPException) as exc_info:
            register_cognito_user(
                email="offline.agency@example.com",
                full_name="Offline Trade",
                phone_number="+962712345678",
            )

        assert exc_info.value.status_code == 400
        assert "Unable to register account" in str(exc_info.value.detail)
