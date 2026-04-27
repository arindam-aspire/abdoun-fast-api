"""
Route coverage tests: hit all route handlers with dependency overrides
so that handler code is executed (for 100% coverage).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
from app.db.session import get_db
from app.utils.responses import StandardResponse, create_success_response
from app.api.v1.deps.agents import get_agent_service
from app.api.v1.deps.agent_dashboard import get_agent_dashboard_service
from app.api.v1.deps.admin_dashboard import get_admin_dashboard_service
from app.api.v1.deps.auth import get_auth_service
from app.api.v1.deps.profile_picture_upload import get_profile_picture_upload_service
from app.api.v1.deps.users import get_user_service
from app.api.v1.deps.properties import get_property_search_service
from app.api.v1.deps.search import get_geo_search_service, get_property_import_service
from app.utils.constants import UserRoles, UserPermissions


def _make_fake_admin_user():
    u = MagicMock()
    u.id = uuid.uuid4()
    perms = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]
    perms[0].code = UserPermissions.USER_CREATE
    perms[1].code = UserPermissions.USER_DELETE
    perms[2].code = UserPermissions.ROLE_ASSIGN
    perms[3].code = UserPermissions.PROPERTY_CREATE
    role = MagicMock()
    role.name = UserRoles.ADMIN
    role.permissions = perms
    u.roles = [role]
    return u


def _fake_admin_user_sync():
    """Sync override so TestClient resolves the dependency without async."""
    return _make_fake_admin_user()


def _make_fake_agent_user():
    """User with only the agent role (for agent-only routes)."""
    u = MagicMock()
    u.id = uuid.uuid4()
    perms = [MagicMock(), MagicMock()]
    perms[0].code = UserPermissions.PROPERTY_CREATE
    perms[1].code = UserPermissions.PROPERTY_UPDATE
    role = MagicMock()
    role.name = UserRoles.AGENT
    role.permissions = perms
    u.roles = [role]
    return u


def _fake_agent_user_sync():
    return _make_fake_agent_user()


def _fake_agent_service():
    from app.schemas.user import (
        AgentStatusEnum,
        AgentInviteResponse,
        AdminCreateAgentResponse,
        AgentDetailResponse,
        AgentAcceptResponse,
        AgentDeclineResponse,
        AgentStatusUpdateResponse,
        AgentDeleteResponse,
        AgentValidateInviteResponse,
        AgentOnboardingFormResponse,
    )

    now = datetime.now(timezone.utc)
    aid = uuid.uuid4()
    invite_data = AgentInviteResponse(
        id=aid,
        email="new@b.com",
        status=AgentStatusEnum.PENDING_REVIEW,
        inviteLink="https://example.com/invite",
        invitedAt=now,
        invitedBy=None,
    )
    create_data = AdminCreateAgentResponse(
        id=aid,
        email="d@b.com",
        fullName="D",
        phone="+911234567890",
        serviceArea="X",
        status=AgentStatusEnum.APPROVED,
        temporaryPassword="x",
    )
    detail_data = AgentDetailResponse(
        id=aid,
        email="a@b.com",
        fullName="A",
        phone="+911234567890",
        serviceArea="X",
        status=AgentStatusEnum.APPROVED,
        invitedAt=now,
        invitedBy=None,
        formSubmittedAt=None,
        reviewedAt=None,
        reviewedBy=None,
        declineReason=None,
        passwordSetAt=None,
    )
    accept_data = AgentAcceptResponse(id=aid, status=AgentStatusEnum.APPROVED, reviewedAt=now, reviewedBy=aid)
    decline_data = AgentDeclineResponse(
        id=aid,
        status=AgentStatusEnum.DECLINED,
        declineReason="No",
        reviewedAt=now,
        reviewedBy=aid,
    )
    status_data = AgentStatusUpdateResponse(id=aid, status=AgentStatusEnum.APPROVED, statusReason=None)
    delete_data = AgentDeleteResponse(id=aid, status=AgentStatusEnum.DECLINED, deletedAt=now, deletedBy=aid)
    validate_data = ("e@b.com", AgentStatusEnum.PENDING_REVIEW, False, "OK")
    onboarding_data = AgentOnboardingFormResponse(
        email="e@b.com",
        status=AgentStatusEnum.PENDING_REVIEW,
        formSubmittedAt=now,
    )

    s = MagicMock()
    s.list_agents.return_value = ([], 0)
    s.list_invites.return_value = []
    s.get_assignments.return_value = []
    s.get_agent_details.return_value = detail_data.model_dump()
    s.invite_agent.return_value = invite_data.model_dump()
    s.create_agent_direct.return_value = create_data.model_dump()
    s.accept_agent.return_value = accept_data.model_dump()
    s.decline_agent.return_value = decline_data.model_dump()
    s.update_agent_status.return_value = status_data.model_dump()
    s.delete_agent.return_value = delete_data.model_dump()
    s.resend_invite.return_value = invite_data.model_dump()
    s.revoke_invite.return_value = {"revoked": True}
    s.validate_invite_token.return_value = validate_data
    s.submit_onboarding_form.return_value = onboarding_data.model_dump()
    s.assign_agent.return_value = None
    s.unassign_agent.return_value = None
    s.get_agents_summary.return_value = {
        "totalAgents": 0,
        "activeAgents": 0,
        "pendingInvites": 0,
        "pendingReview": 0,
        "declined": 0,
        "lastFiveAgents": [],
    }
    s.get_top_agents_leaderboard.return_value = {
        "firstDate": datetime(2026, 3, 27, tzinfo=timezone.utc),
        "lastDate": datetime(2026, 4, 27, tzinfo=timezone.utc),
        "agents": [],
    }
    return s


def _fake_admin_dashboard_service():
    """Minimal AdminDashboardService mock for admin dashboard route coverage."""
    s = MagicMock()
    s.get_kpis.return_value = {
        "month": "2026-01",
        "usersThisMonth": 0,
        "usersMoMDelta": 0.0,
        "agentsThisMonth": 0,
        "agentsMoMDelta": 0.0,
        "pendingApprovals": 0,
        "pendingApprovalsToday": 0,
        "listingsThisMonth": 0,
        "listingsMoMDelta": 0.0,
        "leadsThisMonth": 0,
        "leadsMoMDelta": 0.0,
        "closedDealsThisMonth": 0,
    }
    s.get_trends.return_value = {
        "months": 12,
        "monthLabels": ["Jan"] * 12,
        "userGrowthSeries": [0] * 12,
        "listingGrowthSeries": [0] * 12,
        "leadGrowthSeries": [0] * 12,
    }
    s.get_property_performance.return_value = {"items": [], "page": 1, "limit": 5, "totalItems": 0}
    s.get_dashboard_summary.return_value = {
        "month": "2026-01",
        "usersThisMonth": 0,
        "usersMoMDelta": 0.0,
        "agentsThisMonth": 0,
        "agentsMoMDelta": 0.0,
        "pendingApprovals": 0,
        "pendingApprovalsToday": 0,
        "listingsThisMonth": 0,
        "listingsMoMDelta": 0.0,
        "leadsThisMonth": 0,
        "leadsMoMDelta": 0.0,
        "closedDealsThisMonth": 0,
        "monthLabels": ["Jan"] * 12,
        "userGrowthSeries": [0] * 12,
        "listingGrowthSeries": [0] * 12,
        "leadGrowthSeries": [0] * 12,
        "leadSourceLabels": [],
        "leadSourceValues": [],
        "propertyPerformanceSeries": [],
    }
    return s


def _fake_agent_dashboard_service():
    """Minimal AgentDashboardService mock for dashboard route coverage."""
    s = MagicMock()
    s.get_dashboard_summary.return_value = {
        "totalProperties": 0,
        "leadsThisMonth": 0,
        "dealCloseCount": 0,
        "conversionRate": 0,
        "totalPropertyViews": 0,
        "activeProperties": 0,
        "draftProperties": 0,
        "inquiryVolumeAllTime": 0,
        "inquiryVolumeLast7Days": 0,
        "inquiryTrendLast30Days": [0] * 30,
        "listingsChangePercent": 0.0,
        "leadsChangePercent": 0.0,
        "dealsClosedChangePercent": 0.0,
        "propertyViewsChangePercent": 0.0,
        "recentActivity": [],
    }
    return s


def _fake_auth_service():
    from app.schemas.user import UserResponse, TokenResponse, PermissionsResponse

    uid = uuid.uuid4()
    user_data = {
        "id": uid,
        "email": "u@b.com",
        "full_name": "U",
        "phone_number": "+12025551234",
        "is_active": True,
        "is_email_verified": True,
        "is_phone_verified": False,
        "profile_picture_url": None,
        "roles": [],
        "created_at": datetime.now(timezone.utc),
        "requires_password_set": False,
    }
    token_data = {"access_token": "t", "expires_in": 3600, "token_type": "Bearer"}
    s = MagicMock()
    s.signup.return_value = create_success_response(data=UserResponse(**user_data))
    s.confirm_signup.return_value = create_success_response(data=True)
    s.resend_confirmation.return_value = create_success_response(data=True)
    s.login_password.return_value = create_success_response(data=TokenResponse(**token_data))
    s.login_otp_request.return_value = create_success_response(data={})
    s.login_otp_verify.return_value = create_success_response(data=TokenResponse(**token_data))
    s.refresh_token.return_value = create_success_response(data=TokenResponse(**token_data))
    s.forgot_password_request.return_value = create_success_response(data=True)
    s.forgot_password_confirm.return_value = create_success_response(data=True)
    s.set_password.return_value = create_success_response(data=True)
    s.get_current_user_profile.return_value = create_success_response(data=UserResponse(**user_data))
    s.get_current_user_permissions.return_value = create_success_response(
        data=PermissionsResponse(permissions=[])
    )
    s.logout.return_value = create_success_response(data=True)
    s.social_login.return_value = create_success_response(data={"url": "https://example.com"})
    s.social_callback.return_value = create_success_response(data=TokenResponse(**token_data))
    return s


def _fake_user_service():
    from app.schemas.user import UserResponse

    uid = uuid.uuid4()
    user_attrs = {
        "id": uid,
        "email": "u@b.com",
        "full_name": "U",
        "phone_number": "+12025551234",
        "is_active": True,
        "is_email_verified": True,
        "is_phone_verified": False,
        "profile_picture_url": None,
        "roles": [],
        "created_at": datetime.now(timezone.utc),
        "requires_password_set": False,
    }
    user_resp = UserResponse(**user_attrs)
    s = MagicMock()
    s.list_users.return_value = ([], 0)
    s.list_roles.return_value = []
    s.list_permissions.return_value = []
    s.get_user.return_value = user_resp
    s.update_user.return_value = user_resp
    s.delete_user.return_value = True
    s.assign_role.return_value = True
    s.remove_role.return_value = True
    return s


def _fake_property_search_service():
    s = MagicMock()
    s.search.return_value = MagicMock(data=[], total=0, page=1, pageSize=20)
    s.get_similar.return_value = MagicMock(data=[], total=0, page=1, pageSize=0)
    s.get_detail.return_value = MagicMock(id=str(uuid.uuid4()), title="P")
    return s


def _fake_geo_search_service():
    s = MagicMock()
    s.search.return_value = MagicMock(items=[], total=0)
    return s


async def _fake_import_csv(*args, **kwargs):
    return 0


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_db():
    m = MagicMock()
    m.execute.return_value.scalars.return_value.all.return_value = []
    return m


def _fake_get_db(mock_db):
    def _gen():
        yield mock_db
    return _gen


def test_agent_routes_list_agents(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_get_agents_summary(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents/summary", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("success") is True
        assert body.get("data") is not None
        assert body["data"].get("totalAgents") == 0
        assert body["data"].get("pendingInvites") == 0
        assert body["data"].get("lastFiveAgents") == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_leaderboard(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents/leaderboard", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("success") is True
        assert body.get("data") is not None
        assert body["data"].get("agents") == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_invite(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/invite",
            json={"email": "agent@example.com"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_manual_onboard(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/manual-onboard",
            json={"email": "a@b.com", "fullName": "A", "phone": "+911234567890", "serviceArea": "X"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_invites(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents/invites", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_assignments(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents/assignments", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_dashboard_summary(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_agent_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_dashboard_service] = _fake_agent_dashboard_service
    try:
        r = client.get("/api/v1/agents/dashboard/summary", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_dashboard_service, None)


def test_admin_routes_dashboard_summary(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_admin_dashboard_service] = _fake_admin_dashboard_service
    try:
        r = client.get("/api/v1/admin/dashboard/summary", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_admin_dashboard_service, None)


def test_admin_routes_dashboard_kpis(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_admin_dashboard_service] = _fake_admin_dashboard_service
    try:
        r = client.get(
            "/api/v1/admin/dashboard/kpis?month=2026-01",
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_admin_dashboard_service, None)


def test_admin_routes_dashboard_trends(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_admin_dashboard_service] = _fake_admin_dashboard_service
    try:
        r = client.get(
            "/api/v1/admin/dashboard/trends?months=6",
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_admin_dashboard_service, None)


def test_admin_routes_property_performance(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_admin_dashboard_service] = _fake_admin_dashboard_service
    try:
        r = client.get(
            "/api/v1/admin/dashboard/property-performance?pageSize=3",
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_admin_dashboard_service, None)


def test_agent_routes_get_details(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get(f"/api/v1/agents/{aid}", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_accept(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.patch(f"/api/v1/agents/{aid}/accept", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_decline(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.patch(f"/api/v1/agents/{aid}/decline", json={"reason": "No"}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_update_status(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.patch(
            f"/api/v1/agents/{aid}/status",
            json={"status": "INACTIVE"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_delete(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.delete(f"/api/v1/agents/{aid}", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_resend_invite(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(f"/api/v1/agents/{aid}/resend-invite", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_revoke_invite(client, mock_db):
    aid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.patch(f"/api/v1/agents/{aid}/revoke-invite", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_validate_invite(client):
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.get("/api/v1/agents/invite/validate?token=abc")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_onboarding(client):
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/onboarding",
            json={"token": "t", "fullName": "A", "phone": "+911234567890", "serviceArea": "X"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_onboarding_with_phone_number_key(client):
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/onboarding",
            json={"token": "t", "fullName": "A", "phone_number": "1234567890", "service_area": "Y"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_onboarding_validation_error(client):
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post("/api/v1/agents/onboarding", json={"token": "t"})  # missing required fields
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_onboarding_missing_token(client):
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/onboarding",
            json={"fullName": "A", "phone": "+911234567890", "serviceArea": "X"},
        )
        assert r.status_code in (400, 422)
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_assign_agent(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/assign-agent",
            json={"agent_id": str(uuid.uuid4()), "can_inherit_privileges": True},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agent_routes_unassign_agent(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/unassign-agent",
            json={"agent_id": str(uuid.uuid4()), "can_inherit_privileges": False},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_agent_service, None)


def test_agents_sanitize_validation_errors_base_exception(client):
    """Covers _sanitize_validation_errors when ctx value is BaseException."""
    app.dependency_overrides[get_agent_service] = _fake_agent_service
    try:
        r = client.post(
            "/api/v1/agents/onboarding",
            json={"token": "t", "fullName": "A", "phone": "bad", "serviceArea": "X"},
        )
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_auth_signup(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/signup",
            json={"email": "u@b.com", "password": "Passw0rd!", "full_name": "U", "phone_number": "+12025551234"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_signup_admin(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/signup/admin",
            json={"email": "a@b.com", "password": "Passw0rd!", "full_name": "A", "phone_number": "+12025551234"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 404  # Route raises 404 Not Found
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_confirm_signup(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/confirm-signup", json={"email": "u@b.com", "code": "123456"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_resend_confirmation(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/resend-confirmation", json={"email": "u@b.com"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_login_password(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/login/password", json={"username": "u@b.com", "password": "x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_login_otp_request(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/login/otp/request", json={"username": "u@b.com"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_login_otp_verify(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/login/otp/verify",
            json={"username": "u@b.com", "code": "123456", "session": "sess123"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_refresh(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": "x", "username": "u@b.com"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_forgot_password_request(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/forgot-password/request", json={"email": "u@b.com"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_forgot_password_confirm(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/forgot-password/confirm",
            json={"email": "u@b.com", "code": "123456", "new_password": "NewPass1!"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_set_password(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/set-password",
            json={"password": "NewPass1!"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_change_password(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post(
            "/api/v1/auth/change-password",
            json={"password": "NewPass1!", "previous_password": "OldPass1!"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_me(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def _fake_profile_picture_upload_service():
    from app.schemas.user import ProfilePictureUploadData

    s = MagicMock()
    s.initiate_upload.return_value = ProfilePictureUploadData(
        profile_picture_url="https://example.com/p.png",
        upload_url="https://presigned",
        expires_in=900,
    )
    return s


def test_auth_me_profile_picture(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_profile_picture_upload_service] = _fake_profile_picture_upload_service
    try:
        r = client.post(
            "/api/v1/auth/me/profile-picture",
            json={"file_name": "pic.png", "content_type": "image/png", "file_size": 1024},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("success") is True
        assert body.get("data", {}).get("profile_picture_url") == "https://example.com/p.png"
        assert body.get("data", {}).get("upload_url") == "https://presigned"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_profile_picture_upload_service, None)


def test_auth_logout(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_me_permissions(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.get("/api/v1/auth/me/permissions", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_social_login(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.get("/api/v1/auth/social-login?provider=Google")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_auth_callback(client):
    app.dependency_overrides[get_auth_service] = _fake_auth_service
    try:
        r = client.get("/api/v1/auth/callback?code=abc")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_service, None)


def test_users_list(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.get("/api/v1/users", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_get(client, mock_db):
    uid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.get(f"/api/v1/users/{uid}", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_update(client, mock_db):
    uid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.patch(
            f"/api/v1/users/{uid}",
            json={"fullName": "U2"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_delete(client, mock_db):
    uid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.delete(f"/api/v1/users/{uid}", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_list_roles(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.get("/api/v1/users/roles/list", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_list_permissions(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.get("/api/v1/users/permissions/list", headers={"Authorization": "Bearer x"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_assign_role(client, mock_db):
    uid = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.post(
            f"/api/v1/users/{uid}/roles",
            json={"role_id": str(uuid.uuid4())},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_users_remove_role(client, mock_db):
    uid = uuid.uuid4()
    role_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_user_service] = _fake_user_service
    try:
        r = client.delete(
            f"/api/v1/users/{uid}/roles/{role_id}",
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_user_service, None)


def test_properties_similar(client, mock_db):
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_property_search_service] = _fake_property_search_service
    try:
        r = client.get("/api/v1/properties/some-id/similar?limit=5")
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_property_search_service, None)


def test_search_geo_search(client, mock_db):
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_geo_search_service] = _fake_geo_search_service
    try:
        r = client.post(
            "/api/v1/properties/geo-search",
            json={"mode": "bounds", "bounds": {"min_lng": 0, "min_lat": 0, "max_lng": 1, "max_lat": 1}, "limit": 10},
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_geo_search_service, None)


def test_search_import_csv(client, mock_db):
    app.dependency_overrides[get_current_user] = _fake_admin_user_sync
    app.dependency_overrides[get_db] = _fake_get_db(mock_db)
    app.dependency_overrides[get_property_import_service] = lambda: MagicMock(import_from_csv=AsyncMock(return_value=0))
    try:
        r = client.post(
            "/api/v1/properties/import-csv",
            files={"file": ("props.csv", BytesIO(b"a,b,c\n1,2,3"), "text/csv")},
            data={"geocode_missing": "false"},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code in (200, 201)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_property_import_service, None)
