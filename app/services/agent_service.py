"""
Agent business logic: invites, onboarding, admin CRUD, assignments.
Orchestrates AgentRepository; calls Cognito and notification where needed.
No FastAPI or Pydantic response schemas; returns domain data for routers to map.
"""

import math
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from botocore.exceptions import NoCredentialsError

from app.core.config import get_settings
from app.models.user import AdminAgentAssignment, AgentInvite, AgentProfile, User
from app.repositories.agent_repository import AgentRepository
from app.schemas.user import (
    AdminAgentAssignmentRequest,
    AdminCreateAgentRequest,
    AgentInviteRequest,
    AgentOnboardingFormRequest,
    AgentStatusUpdateRequest,
)
from app.services import cognito as cognito_module
from app.services import notification as notification_module
from app.utils.constants import (
    AgentStatus,
    ErrorMessages,
    SuccessMessages,
    UserRoles,
)
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.status_codes import HTTPStatus


def _generate_temporary_password(length: int = 16) -> str:
    """Generate a strong temporary password for Cognito."""
    import string
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special_chars = "!@#$%^&*()-_=+[]{}|;:,.<>?"
    special = secrets.choice(special_chars)
    remaining_length = max(length - 4, 4)
    alphabet = string.ascii_letters + string.digits + special_chars
    remaining = [secrets.choice(alphabet) for _ in range(remaining_length)]
    chars = [upper, lower, digit, special] + remaining
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _try_create_cognito_user_for_agent(
    user: User,
    current_user: User,
    agent_id: uuid.UUID,
) -> None:
    """Create Cognito user for agent on approval if configured; skip if already has cognito_sub."""
    if user.cognito_sub:
        return
    settings = get_settings()
    pool_id = (settings.cognito_user_pool_id or "").strip()
    client_id = (settings.cognito_client_id or "").strip()
    if not pool_id or not client_id:
        api_logger.warning(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user skipped (missing config)",
                error=f"user_id={user.id}",
            )
            + " - Set COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID to enable Cognito user creation."
        )
        return
    try:
        cognito_service = cognito_module.cognito_service
        response = cognito_service.create_agent_user(
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number or "",
        )
        if response and "User" in response:
            cognito_sub = response["User"]["Username"]
            user.cognito_sub = cognito_sub
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_APPROVED,
                    agent_id=str(agent_id),
                    approver_id=current_user.email,
                )
                + f" | Cognito user created with sub: {cognito_sub}"
            )
        else:
            api_logger.warning(
                format_log_message(
                    LogMessages.RBAC.NOTIFICATION_FAILED,
                    context="cognito create user - invalid response",
                    error=f"user_id={user.id}, email={user.email}",
                )
            )
    except NoCredentialsError:
        api_logger.warning(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user - AWS credentials not configured",
                error=f"user_id={user.id}, email={user.email}",
            )
            + " - Agent approval will proceed but Cognito user not created"
        )
    except Exception as e:
        api_logger.error(
            format_log_message(
                LogMessages.RBAC.NOTIFICATION_FAILED,
                context="cognito create user failed",
                error=f"user_id={user.id}, email={user.email}, error={str(e)}",
            )
            + " - Agent approval will proceed but Cognito user not created"
        )


class AgentService:
    """Service for agent invites, onboarding, admin CRUD, and admin-agent assignments."""

    def __init__(self, repo: AgentRepository) -> None:
        self._repo = repo

    # ---------- Invite ----------

    def invite_agent(
        self,
        invite_in: AgentInviteRequest,
        current_user: User,
    ) -> Dict[str, Any]:
        """
        Create invite, send email, create User + AgentProfile with INVITED status.
        Returns dict with id, email, status, inviteLink, invitedAt, invitedBy for AgentInviteResponse.
        """
        existing_user = self._repo.get_user_by_email(invite_in.email)
        if existing_user:
            if existing_user.profile:
                api_logger.warning(
                    format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email)
                )
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.AGENT_ALREADY_EXISTS,
                )
            api_logger.warning(
                format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=invite_in.email)
            )
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_EXISTS,
            )
        existing_invite = self._repo.find_unused_invite_by_email(invite_in.email)
        if existing_invite:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.AGENT_ALREADY_EXISTS,
            )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=7)
        invited_at = datetime.now()
        db_invite = self._repo.add_invite(
            email=invite_in.email,
            invited_by=current_user.id,
            token=token,
            expires_at=expires_at,
            invited_at=invited_at,
        )
        try:
            self._repo.commit()
            self._repo.refresh(db_invite)
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INVITE_FAILED,
            )
        settings = get_settings()
        invite_link = f"{settings.app_base_url.rstrip('/')}/en/agent-invite?token={token}"
        api_logger.info(
            format_log_message(
                LogMessages.RBAC.AGENT_INVITED,
                email=invite_in.email,
                invited_by=current_user.email,
            )
        )
        try:
            notification_module.notify_agent_invite_sent(
                invite_in.email, invite_link, current_user.email
            )
        except Exception as n:
            api_logger.warning(
                format_log_message(
                    LogMessages.RBAC.NOTIFICATION_FAILED,
                    context="agent invite",
                    error=str(n),
                )
            )
        db_user = User(
            email=invite_in.email,
            full_name="",
            phone_number=None,
            is_active=False,
        )
        self._repo.add_user(db_user)
        role = self._repo.get_role_by_name(UserRoles.AGENT)
        if role:
            self._repo.assign_role_to_user(db_user, role)
        profile = AgentProfile(user_id=db_user.id, status=AgentStatus.INVITED)
        self._repo.add_agent_profile(profile)
        try:
            self._repo.commit()
            self._repo.refresh(db_user)
            self._repo.refresh(profile)
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INVITE_FAILED,
            )
        invited_at_ts = db_invite.invited_at or db_invite.created_at
        return {
            "id": db_user.id,
            "email": db_invite.email,
            "status": AgentStatus.INVITED,
            "inviteLink": invite_link,
            "invitedAt": invited_at_ts,
            "invitedBy": current_user.full_name,
        }

    def create_agent_direct(
        self,
        body: AdminCreateAgentRequest,
        current_user: User,
    ) -> Dict[str, Any]:
        """
        Admin directly create agent with temp password (Cognito + local User + AgentProfile).
        Returns dict for AdminCreateAgentResponse (id, email, fullName, phone, serviceArea, status, temporaryPassword).
        """
        existing_user = self._repo.get_user_by_email(body.email)
        if existing_user:
            if existing_user.profile:
                api_logger.warning(
                    format_log_message(LogMessages.RBAC.INVITE_ATTEMPT_EXISTING, email=body.email)
                )
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ErrorMessages.AGENT_ALREADY_EXISTS,
                )
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.USER_EXISTS,
            )
        temp_password = _generate_temporary_password()
        cognito_service = cognito_module.cognito_service
        try:
            response = cognito_service.signup(
                email=body.email,
                password=temp_password,
                full_name=body.fullName,
                phone_number=body.phone,
            )
            cognito_sub = response.get("UserSub")
            if not cognito_sub:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Cognito signup did not return UserSub",
                )
            try:
                cognito_service.admin_confirm_sign_up(cognito_sub)
            except Exception as confirm_err:
                api_logger.warning(
                    format_log_message(
                        LogMessages.Auth.ADMIN_CONFIRM_FAILED,
                        email=body.email,
                        error=str(confirm_err),
                    )
                )
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Could not confirm user in Cognito. The agent may not be able to log in with the temporary password.",
                ) from confirm_err
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=format_log_message(ErrorMessages.COGNITO_ERROR, error=str(e)),
            )
        db_user = User(
            email=body.email,
            full_name=body.fullName,
            phone_number=body.phone,
            is_active=True,
            cognito_sub=cognito_sub,
        )
        self._repo.add_user(db_user)
        role = self._repo.get_role_by_name(UserRoles.AGENT)
        if role:
            self._repo.assign_role_to_user(db_user, role)
        profile = AgentProfile(
            user_id=db_user.id,
            service_area=body.serviceArea,
            status=AgentStatus.ACTIVE,
            approved_by=current_user.id,
            reviewed_by=current_user.id,
            approved_at=datetime.now(),
            reviewed_at=datetime.now(),
        )
        self._repo.add_agent_profile(profile)
        try:
            self._repo.commit()
            self._repo.refresh(db_user)
            self._repo.refresh(profile)
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INTERNAL_SERVER_ERROR,
            )
        try:
            if db_user.cognito_sub:
                getattr(
                    cognito_service,
                    "set_requires_password_set",
                    lambda _sub, _val: None,
                )(db_user.cognito_sub, True)
        except Exception as attr_err:
            api_logger.debug(
                "Could not set Cognito requires_password_set attribute for direct-created agent: %s",
                attr_err,
            )
        api_logger.info(
            format_log_message(
                LogMessages.RBAC.AGENT_INVITED,
                email=db_user.email,
                invited_by=current_user.email,
            )
            + " | Direct-create agent with temporary password issued."
        )
        return {
            "id": db_user.id,
            "email": db_user.email,
            "fullName": db_user.full_name,
            "phone": db_user.phone_number,
            "serviceArea": profile.service_area,
            "status": profile.status,
            "temporaryPassword": temp_password,
        }

    # ---------- List / Detail ----------

    def list_agents(
        self,
        *,
        status: Optional[str],
        search: Optional[str],
        page: int,
        limit: int,
        sort_by: str,
        sort_order: str,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Returns (list of agent list items as dicts, total_count).
        Each dict has keys for AgentListResponse: id, email, fullName, phone, serviceArea, status,
        invitedAt, invitedBy, formSubmittedAt, reviewedAt, declineReason.
        """
        rows, total = self._repo.list_agents_paginated(
            status=status,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            limit=limit,
        )
        agents = []
        for user, profile in rows:
            invite_info = self._repo.get_latest_invite_for_email(user.email)
            invite, inviter_name = invite_info or (None, None)
            agents.append({
                "id": user.id,
                "email": user.email,
                "fullName": user.full_name if user.full_name else None,
                "phone": user.phone_number if user.phone_number else None,
                "serviceArea": profile.service_area,
                "status": profile.status,
                "invitedAt": invite.created_at if invite else None,
                "invitedBy": inviter_name,
                "formSubmittedAt": profile.form_submitted_at,
                "reviewedAt": profile.reviewed_at,
                "declineReason": profile.decline_reason,
            })
        return agents, total

    def list_invites(
        self,
        current_user: User,
        used: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Returns list of invite dicts with id, email, expires_at, is_used, created_at, status."""
        invites = self._repo.list_invites_by_inviter(current_user.id, used=used)
        emails = [inv.email for inv in invites if inv.email]
        status_by_email = self._repo.get_status_by_emails(emails) if emails else {}
        return [
            {
                "id": str(inv.id),
                "email": inv.email,
                "expires_at": inv.expires_at,
                "is_used": inv.is_used,
                "created_at": inv.created_at,
                "status": status_by_email.get(inv.email, AgentStatus.INVITED),
            }
            for inv in invites
        ]

    def get_assignments(
        self,
        *,
        agent_id: Optional[uuid.UUID],
        admin_id: Optional[uuid.UUID],
        current_user: User,
    ) -> List[Dict[str, Any]]:
        """Returns list of assignment dicts for AdminAgentAssignmentResponse."""
        if admin_id is None:
            admin_id = current_user.id
        assignments = self._repo.list_assignments(
            agent_id=agent_id,
            admin_id=admin_id,
        )
        result = []
        for a in assignments:
            admin_user = a.admin
            agent_user = a.agent
            status = "ACTIVE" if (a.is_active and a.revoked_at is None) else "INACTIVE/REVOKED"
            result.append({
                "id": a.id,
                "admin_id": a.admin_id,
                "admin_email": admin_user.email,
                "admin_name": admin_user.full_name,
                "agent_id": a.agent_id,
                "agent_email": agent_user.email,
                "agent_name": agent_user.full_name,
                "is_active": a.is_active,
                "can_inherit_privileges": a.can_inherit_privileges,
                "assigned_at": a.assigned_at,
                "revoked_at": a.revoked_at,
                "status": status,
            })
        return result

    def get_agent_details(self, agent_id: uuid.UUID) -> Dict[str, Any]:
        """Returns dict for AgentDetailResponse."""
        pair = self._repo.get_agent_with_profile(agent_id)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        invite_info = self._repo.get_latest_invite_for_email(user.email)
        invite, inviter_name = invite_info or (None, None)
        return {
            "id": user.id,
            "email": user.email,
            "fullName": user.full_name if user.full_name else None,
            "phone": user.phone_number if user.phone_number else None,
            "serviceArea": profile.service_area,
            "status": profile.status,
            "invitedAt": invite.created_at if invite else None,
            "invitedBy": inviter_name,
            "formSubmittedAt": profile.form_submitted_at,
            "reviewedAt": profile.reviewed_at,
            "reviewedBy": profile.reviewed_by,
            "declineReason": profile.decline_reason,
            "passwordSetAt": profile.password_set_at,
        }

    # ---------- Accept / Decline / Status / Delete ----------

    def accept_agent(self, agent_id: uuid.UUID, current_user: User) -> Dict[str, Any]:
        """Approve agent (PENDING_REVIEW -> ACTIVE). Returns dict for AgentAcceptResponse."""
        pair = self._repo.get_agent_with_profile(agent_id)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        if profile.status != AgentStatus.PENDING_REVIEW:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_STATUS_TRANSITION,
            )
        try:
            _try_create_cognito_user_for_agent(user, current_user, agent_id)
            profile.status = AgentStatus.ACTIVE
            profile.reviewed_at = datetime.now()
            profile.reviewed_by = current_user.id
            profile.approved_by = current_user.id
            profile.approved_at = datetime.now()
            user.is_active = True
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_APPROVED,
                    agent_id=str(agent_id),
                    approver_id=current_user.email,
                )
            )
            try:
                notification_module.notify_agent_approved(user.email, user.full_name)
            except Exception as n:
                api_logger.warning(
                    format_log_message(
                        LogMessages.RBAC.NOTIFICATION_FAILED,
                        context="agent approved",
                        error=str(n),
                    )
                )
            return {
                "id": user.id,
                "status": profile.status,
                "reviewedAt": profile.reviewed_at,
                "reviewedBy": profile.reviewed_by,
            }
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.APPROVAL_FAILED_LOG,
                    agent_id=str(agent_id),
                    error=str(e),
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.APPROVAL_FAILED,
            )

    def decline_agent(
        self,
        agent_id: uuid.UUID,
        reason: str,
        current_user: User,
    ) -> Dict[str, Any]:
        """Decline agent (PENDING_REVIEW -> DECLINED). Returns dict for AgentDeclineResponse."""
        pair = self._repo.get_agent_with_profile(agent_id)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        if profile.status != AgentStatus.PENDING_REVIEW:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_STATUS_TRANSITION,
            )
        reason = reason or "Application rejected by admin"
        try:
            profile.status = AgentStatus.DECLINED
            profile.decline_reason = reason
            profile.reviewed_at = datetime.now()
            profile.reviewed_by = current_user.id
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_REJECTED,
                    agent_id=str(agent_id),
                    rejector_id=current_user.email,
                )
            )
            try:
                notification_module.notify_agent_rejected(
                    user.email, user.full_name, profile.decline_reason
                )
            except Exception as n:
                api_logger.warning(
                    format_log_message(
                        LogMessages.RBAC.NOTIFICATION_FAILED,
                        context="agent rejected",
                        error=str(n),
                    )
                )
            return {
                "id": user.id,
                "status": profile.status,
                "declineReason": profile.decline_reason,
                "reviewedAt": profile.reviewed_at,
                "reviewedBy": profile.reviewed_by,
            }
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.AGENT_REJECT_FAILED_LOG,
                    agent_id=str(agent_id),
                    error=str(e),
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.AGENT_REJECT_FAILED,
            )

    def update_agent_status(
        self,
        agent_id: uuid.UUID,
        payload: AgentStatusUpdateRequest,
        _current_user: User,  # kept for API consistency and future audit
    ) -> Dict[str, Any]:
        """Update agent status (ACTIVE/INACTIVE). Returns dict for AgentStatusUpdateResponse."""
        allowed = {AgentStatus.ACTIVE, AgentStatus.INACTIVE}
        if payload.status not in allowed:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_AGENT_STATUS,
            )
        pair = self._repo.get_agent_with_profile(agent_id, include_deleted=True)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        if profile.deleted_at is not None or profile.status == AgentStatus.DELETED:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.ALREADY_DELETED,
            )
        if profile.status == AgentStatus.PENDING_REVIEW:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVALID_AGENT_STATUS_TRANSITION,
            )
        try:
            if payload.status == AgentStatus.INACTIVE:
                profile.status = AgentStatus.INACTIVE
                profile.status_reason = payload.reason
                user.is_active = False
            else:
                profile.status = AgentStatus.ACTIVE
                profile.status_reason = payload.reason
                user.is_active = True
            self._repo.commit()
            self._repo.refresh(user)
            self._repo.refresh(profile)
            return {
                "id": user.id,
                "status": profile.status,
                "statusReason": profile.status_reason,
            }
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(
                    LogMessages.RBAC.AGENT_STATUS_UPDATE_FAILED,
                    agent_id=str(agent_id),
                    error=str(e),
                )
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INTERNAL_SERVER_ERROR,
            )

    def delete_agent(self, agent_id: uuid.UUID, current_user: User) -> Dict[str, Any]:
        """Soft-delete agent. Returns dict for AgentDeleteResponse."""
        pair = self._repo.get_agent_with_profile(agent_id, include_deleted=True)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        if profile.deleted_at is not None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.ALREADY_DELETED,
            )
        try:
            profile.deleted_at = datetime.now()
            profile.deleted_by = current_user.id
            profile.status = AgentStatus.DELETED
            user.is_active = False
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.USER_DELETED_LOG,
                    user_id=str(agent_id),
                    admin_email=current_user.email,
                )
            )
            return {
                "id": user.id,
                "status": profile.status,
                "deletedAt": profile.deleted_at,
                "deletedBy": profile.deleted_by,
            }
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.USER_DELETE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INTERNAL_SERVER_ERROR,
            )

    # ---------- Resend / Revoke invite ----------

    def resend_invite(self, agent_id: uuid.UUID, current_user: User) -> Dict[str, Any]:
        """Resend invite email. Returns dict for AgentInviteResponse."""
        pair = self._repo.get_agent_with_profile(agent_id)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, profile = pair
        invite = self._repo.get_latest_invite_by_email_only(user.email)
        if not invite:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.INVITE_NOT_FOUND,
            )
        if invite.is_used:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVITE_ALREADY_USED,
            )
        new_token = secrets.token_urlsafe(32)
        new_expires = datetime.now() + timedelta(days=7)
        invite.token = new_token
        invite.expires_at = new_expires
        invite.invited_at = datetime.now()
        invite.revoked_at = None
        invite.revoked_by = None
        try:
            self._repo.commit()
            self._repo.refresh(invite)
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INVITE_FAILED,
            )
        settings = get_settings()
        invite_link = f"{settings.app_base_url.rstrip('/')}/en/agent-invite?token={new_token}"
        api_logger.info(
            format_log_message(
                LogMessages.RBAC.AGENT_INVITE_RESENT,
                email=user.email,
                invited_by=current_user.email,
            )
        )
        try:
            notification_module.notify_agent_invite_sent(
                user.email, invite_link, current_user.email
            )
        except Exception as n:
            api_logger.warning(
                format_log_message(
                    LogMessages.RBAC.NOTIFICATION_FAILED,
                    context="agent invite resend",
                    error=str(n),
                )
            )
        invited_at_ts = invite.invited_at or invite.created_at
        return {
            "id": user.id,
            "email": invite.email,
            "status": profile.status,
            "inviteLink": invite_link,
            "invitedAt": invited_at_ts,
            "invitedBy": current_user.full_name,
        }

    def revoke_invite(self, agent_id: uuid.UUID, current_user: User) -> Dict[str, Any]:
        """Revoke invite. Returns dict with revoked, revokedAt."""
        pair = self._repo.get_agent_with_profile(agent_id)
        if not pair:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.AGENT_NOT_FOUND,
            )
        user, _ = pair
        invite = self._repo.get_latest_invite_by_email_only(user.email)
        if not invite:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.INVITE_NOT_FOUND,
            )
        if invite.is_used:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVITE_ALREADY_USED,
            )
        if invite.revoked_at is not None:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVITE_ALREADY_REVOKED,
            )
        try:
            invite.revoked_at = datetime.now()
            invite.revoked_by = current_user.id
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_INVITE_REVOKED,
                    email=user.email,
                    revoked_by=current_user.email,
                )
            )
            return {"revoked": True, "revokedAt": invite.revoked_at}
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.INVITE_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.INTERNAL_SERVER_ERROR,
            )

    # ---------- Public: validate token / submit onboarding ----------

    def validate_invite_token(
        self, token: str
    ) -> Tuple[str, str, bool, Optional[str]]:
        """
        Returns (email, status, already_submitted, message).
        Raises HTTPException if token invalid or invite not found/used.
        """
        invite = self._repo.find_invite_by_token_valid(token)
        if not invite:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.INVITE_NOT_FOUND,
            )
        if invite.is_used:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVITE_ALREADY_USED,
            )
        user = self._repo.get_user_by_email_with_profile(invite.email)
        already_submitted = False
        status = AgentStatus.INVITED
        message = None
        if user and user.profile:
            status = user.profile.status
            already_submitted = user.profile.form_submitted_at is not None
        from app.utils.constants import InfoMessages
        if already_submitted:
            message = InfoMessages.AGENT_ALREADY_SUBMITTED
        return (invite.email, status, already_submitted, message)

    def submit_onboarding_form(
        self, token: str, form_data: AgentOnboardingFormRequest
    ) -> Dict[str, Any]:
        """
        Submit onboarding form (token auth). Returns dict for AgentOnboardingFormResponse.
        """
        invite = self._repo.find_invite_by_token_valid(token)
        if not invite:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.INVITE_NOT_FOUND,
            )
        if invite.is_used:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.INVITE_ALREADY_USED,
            )
        user = self._repo.get_user_by_email_with_profile(invite.email)
        if not user:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="User not found for this invite",
            )
        if user.profile and user.profile.form_submitted_at:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail=ErrorMessages.ALREADY_SUBMITTED,
            )
        try:
            user.full_name = form_data.fullName
            user.phone_number = form_data.phone
            if not user.profile:
                profile = AgentProfile(
                    user_id=user.id,
                    service_area=form_data.serviceArea,
                    status=AgentStatus.PENDING_REVIEW,
                    form_submitted_at=datetime.now(),
                )
                self._repo.add_agent_profile(profile)
            else:
                user.profile.service_area = form_data.serviceArea
                user.profile.status = AgentStatus.PENDING_REVIEW
                user.profile.form_submitted_at = datetime.now()
            invite.is_used = True
            self._repo.commit()
            self._repo.refresh(user)
            if user.profile:
                self._repo.refresh(user.profile)
            api_logger.info(
                format_log_message(LogMessages.RBAC.REGISTRATION_PENDING, email=user.email)
            )
            return {
                "email": user.email,
                "status": user.profile.status if user.profile else AgentStatus.PENDING_REVIEW,
                "formSubmittedAt": user.profile.form_submitted_at if user.profile else datetime.now(),
            }
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.REGISTRATION_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=ErrorMessages.REGISTRATION_FAILED,
            )

    # ---------- Assign / Unassign ----------

    def assign_agent(
        self,
        assign_in: AdminAgentAssignmentRequest,
        current_user: User,
    ) -> bool:
        """Assign agent to current admin. Returns True on success."""
        admin_id = current_user.id
        agent = self._repo.get_user_with_profile_and_roles(assign_in.agent_id)
        if not agent:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.USER_NOT_FOUND,
            )
        if admin_id == assign_in.agent_id:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="An admin cannot assign themselves as an agent",
            )
        role_names = {r.name for r in agent.roles}
        if UserRoles.ADMIN in role_names:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Admins cannot be assigned as agents",
            )
        if UserRoles.AGENT not in role_names:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Only users with AGENT role can be assigned to an admin",
            )
        existing = self._repo.find_assignment(admin_id, assign_in.agent_id)
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.revoked_at = None
            existing.can_inherit_privileges = assign_in.can_inherit_privileges
        else:
            self._repo.add_assignment(
                admin_id=admin_id,
                agent_id=assign_in.agent_id,
                is_active=True,
                can_inherit_privileges=assign_in.can_inherit_privileges,
            )
        try:
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_ASSIGNED,
                    agent_id=str(assign_in.agent_id),
                    admin_id=str(admin_id),
                )
            )
            return True
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.ASSIGNMENT_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.ASSIGNMENT_FAILED,
            )

    def unassign_agent(
        self,
        unassign_in: AdminAgentAssignmentRequest,
        current_user: User,
    ) -> bool:
        """Revoke agent assignment. Returns True on success."""
        admin_id = current_user.id
        assignment = self._repo.find_assignment(admin_id, unassign_in.agent_id)
        if not assignment or not assignment.is_active:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail=ErrorMessages.ASSIGNMENT_NOT_FOUND,
            )
        assignment.is_active = False
        assignment.revoked_at = datetime.now()
        try:
            self._repo.commit()
            api_logger.info(
                format_log_message(
                    LogMessages.RBAC.AGENT_REVOKED,
                    agent_id=str(unassign_in.agent_id),
                    admin_id=str(admin_id),
                )
            )
            return True
        except Exception as e:
            self._repo.rollback()
            api_logger.error(
                format_log_message(LogMessages.RBAC.REVOCATION_FAILED_LOG, error=str(e))
            )
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=ErrorMessages.REVOCATION_FAILED,
            )
