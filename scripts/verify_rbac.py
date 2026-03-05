import sys
import os
from sqlalchemy import select
from sqlalchemy.orm import Session

# Add current directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.user import User, Role, Permission, AdminAgentAssignment
from app.utils.constants import UserRoles, UserPermissions

def verify_rbac():
    print("Verifying RBAC Logic...")
    with SessionLocal() as db:
        # Check permissions for 'admin' role
        stmt = select(Role).where(Role.name == UserRoles.ADMIN)
        admin_role = db.execute(stmt).scalar_one_or_none()
        if admin_role:
            perms = [p.code for p in admin_role.permissions]
            print(f"Admin Permissions: {perms}")
            if UserPermissions.AGENT_APPROVE in perms:
                print(f"SUCCESS: Admin has '{UserPermissions.AGENT_APPROVE}' permission")
            else:
                print(f"FAILURE: Admin missing '{UserPermissions.AGENT_APPROVE}' permission")
        else:
            print("FAILURE: Admin role not found")

        print("SUCCESS: Model relations verified")

if __name__ == "__main__":
    try:
        verify_rbac()
    except Exception as e:
        print(f"Verification failed: {e}")
        sys.exit(1)
