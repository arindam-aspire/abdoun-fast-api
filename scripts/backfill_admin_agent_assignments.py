"""
Backfill `admin_agent_assignments` for an admin.

This script assigns *all* existing agent-role users to a specified admin by creating
missing rows in `admin_agent_assignments`. It does NOT remove or revoke anything.

Semantics:
- Agent scope: users with the `agent` role (`roles.name = UserRoles.AGENT`)
- Deleted users are excluded (`users.deleted_at IS NULL`)
- Existing assignments are left as-is (no duplication)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, select

# Add project root so "app" can be imported when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import AdminAgentAssignment, Role, User, user_roles  # noqa: E402
from app.utils.constants import UserRoles  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill admin_agent_assignments for an admin.")
    p.add_argument("--admin-id", required=True, help="Admin user UUID.")
    p.add_argument(
        "--can-inherit-privileges",
        default="true",
        choices=("true", "false"),
        help="Value for can_inherit_privileges on created assignments (default: true).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute changes but do not write anything.",
    )
    return p.parse_args()


def backfill(*, admin_id: UUID, can_inherit_privileges: bool, dry_run: bool) -> tuple[int, int]:
    """Return (agents_found, assignments_created)."""
    with SessionLocal() as db:
        agent_ids = [
            row[0]
            for row in db.execute(
                select(User.id)
                .select_from(User)
                .join(user_roles, user_roles.c.user_id == User.id)
                .join(Role, Role.id == user_roles.c.role_id)
                .where(
                    and_(
                        Role.name == UserRoles.AGENT,
                        User.deleted_at.is_(None),
                    )
                )
                .distinct()
                .order_by(User.id)
            ).all()
        ]

        created = 0
        for agent_id in agent_ids:
            existing = db.execute(
                select(AdminAgentAssignment.id).where(
                    and_(
                        AdminAgentAssignment.admin_id == admin_id,
                        AdminAgentAssignment.agent_id == agent_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            db.add(
                AdminAgentAssignment(
                    admin_id=admin_id,
                    agent_id=agent_id,
                    is_active=True,
                    can_inherit_privileges=can_inherit_privileges,
                )
            )
            created += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()

        return len(agent_ids), created


if __name__ == "__main__":
    args = _parse_args()
    admin_id = UUID(str(args.admin_id))
    cip = str(args.can_inherit_privileges).strip().lower() == "true"
    agents_found, created = backfill(
        admin_id=admin_id,
        can_inherit_privileges=cip,
        dry_run=bool(args.dry_run),
    )
    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] admin_id={admin_id} agents_found={agents_found} assignments_created={created}")
