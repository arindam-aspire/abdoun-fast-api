"""
End-to-end backend flow test (DB + services) for:
1) Create an agent user (with AGENT role + AgentProfile)
2) Assign agent to a given admin (writes admin_agent_assignments)
3) Verify DB row exists
4) Verify AdminDashboardService summary reflects totalAgentCount

This avoids Cognito/network calls and validates the backend + DB wiring.

Default behavior marks the created agent as deleted at the end (soft-delete) and
revokes the assignment to keep the DB tidy; use --no-cleanup to keep data.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import and_, select

# Add project root so "app" can be imported when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import AdminAgentAssignment, AgentProfile, Role, User  # noqa: E402
from app.repositories.agent_repository import AgentRepository  # noqa: E402
from app.schemas.user import AdminAgentAssignmentRequest  # noqa: E402
from app.services.admin_dashboard_service import AdminDashboardService  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from app.utils.constants import AgentStatus, UserRoles  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test agent create + assign + dashboard summary flow.")
    p.add_argument("--admin-id", required=True, help="Admin user UUID to assign to.")
    p.add_argument(
        "--can-inherit-privileges",
        default="true",
        choices=("true", "false"),
        help="Value for can_inherit_privileges on the assignment (default: true).",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not revoke assignment or soft-delete created agent at the end.",
    )
    return p.parse_args()


def _get_role(db, name: str) -> Role:
    role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if not role:
        raise RuntimeError(f"Role not found: {name!r}. Run scripts/seed_rbac.py first.")
    return role


def _get_user(db, user_id: UUID) -> User:
    u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not u:
        raise RuntimeError(f"User not found: {user_id}")
    return u


def main() -> int:
    args = _parse_args()
    admin_id = UUID(str(args.admin_id))
    cip = str(args.can_inherit_privileges).strip().lower() == "true"
    cleanup = not bool(args.no_cleanup)

    with SessionLocal() as db:
        admin_user = _get_user(db, admin_id)
        agent_role = _get_role(db, UserRoles.AGENT)

        # --- Step 1: create an agent user in DB ---
        now = datetime.now(timezone.utc)
        unique = uuid4().hex[:8]
        agent_email = f"flowtest_agent_{unique}@example.com"
        agent = User(
            id=uuid4(),
            cognito_sub=None,
            full_name=f"FlowTest Agent {unique}",
            email=agent_email,
            phone_number=f"+1999{unique[:6]}",
            is_active=True,
            is_email_verified=True,
            is_phone_verified=False,
            profile_picture_url=None,
            deleted_at=None,
            deleted_by=None,
        )
        agent.roles.append(agent_role)
        db.add(agent)
        db.flush()  # ensures PK is available

        profile = AgentProfile(
            user_id=agent.id,
            service_area="FlowTest Area",
            status=AgentStatus.APPROVED,
            approved_at=now,
            reviewed_at=now,
            form_submitted_at=now,
            password_set_at=now,
        )
        db.add(profile)
        db.commit()

        # --- Step 2: assign via real service path (writes admin_agent_assignments) ---
        repo = AgentRepository(db)
        agent_service = AgentService(repo)
        req = AdminAgentAssignmentRequest(agent_id=agent.id, can_inherit_privileges=cip)
        agent_service.assign_agent(req, admin_user)
        db.commit()

        # --- Step 3: verify DB row ---
        assignment = db.execute(
            select(AdminAgentAssignment).where(
                and_(
                    AdminAgentAssignment.admin_id == admin_id,
                    AdminAgentAssignment.agent_id == agent.id,
                )
            )
        ).scalar_one_or_none()
        if not assignment:
            raise RuntimeError("Assignment row was not created.")

        # --- Step 4: verify dashboard summary ---
        dash_service = AdminDashboardService(repo=None)  # type: ignore[arg-type]
        # AdminDashboardService needs AdminDashboardRepository; construct it directly.
        from app.repositories.admin_dashboard_repository import AdminDashboardRepository  # noqa: E402

        dash_service = AdminDashboardService(AdminDashboardRepository(db))
        summary = dash_service.get_dashboard_summary(admin_user)

        print("=== FLOW RESULT ===")
        print(f"admin_id: {admin_id}")
        print(f"created_agent_id: {agent.id}")
        print(f"created_agent_email: {agent.email}")
        print(
            "assignment:",
            {
                "id": str(assignment.id),
                "admin_id": str(assignment.admin_id),
                "agent_id": str(assignment.agent_id),
                "is_active": bool(assignment.is_active),
                "can_inherit_privileges": bool(assignment.can_inherit_privileges),
                "assigned_at": str(assignment.assigned_at),
                "revoked_at": str(assignment.revoked_at) if assignment.revoked_at else None,
            },
        )
        print("dashboard_summary_totals:", {k: summary.get(k) for k in ("totalAgentCount",)})

        # --- Optional cleanup (revoke assignment + soft-delete the created agent user) ---
        if cleanup:
            # Revoke assignment (so it stops affecting dashboards)
            agent_service.unassign_agent(req, admin_user)
            # Soft-delete created agent user
            agent.deleted_at = datetime.now(timezone.utc)
            agent.deleted_by = admin_id
            db.commit()
            print("cleanup: revoked assignment + soft-deleted created agent")
        else:
            print("cleanup: skipped (--no-cleanup)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

