import sys
from pathlib import Path

# Add project root so "app" can be imported when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import Role, Permission, role_permissions

from app.utils.constants import UserRoles, UserPermissions

def seed_rbac():
    with SessionLocal() as session:
        # Define permissions
        permissions_data = [
            {"code": UserPermissions.USER_CREATE, "description": "Can create users"},
            {"code": UserPermissions.USER_DELETE, "description": "Can delete users"},
            {"code": UserPermissions.AGENT_APPROVE, "description": "Can approve agents"},
            {"code": UserPermissions.AGENT_ASSIGN, "description": "Can assign agents to admins"},
            {"code": UserPermissions.ROLE_ASSIGN, "description": "Can assign roles to users"},
            {"code": UserPermissions.PROPERTY_CREATE, "description": "Can create properties"},
            {"code": UserPermissions.PROPERTY_UPDATE, "description": "Can update properties"},
            {"code": UserPermissions.PROPERTY_DELETE, "description": "Can delete properties"},
        ]

        # Define roles and their permission codes
        roles_data = [
            {
                "name": UserRoles.ADMIN,
                "description": "Administrator with full access",
                "permissions": [
                    UserPermissions.USER_CREATE,
                    UserPermissions.USER_DELETE,
                    UserPermissions.AGENT_APPROVE,
                    UserPermissions.AGENT_ASSIGN,
                    UserPermissions.ROLE_ASSIGN,
                    UserPermissions.PROPERTY_CREATE,
                    UserPermissions.PROPERTY_UPDATE,
                    UserPermissions.PROPERTY_DELETE
                ]
            },
            {
                "name": UserRoles.AGENT,
                "description": "Real estate agent",
                "permissions": [UserPermissions.PROPERTY_CREATE, UserPermissions.PROPERTY_UPDATE]
            },
            {
                "name": UserRoles.REGISTERED_USER,
                "description": "Standard registered user",
                "permissions": []
            }
        ]

        print("Seeding permissions...")
        db_permissions = {}
        for p_data in permissions_data:
            stmt = select(Permission).where(Permission.code == p_data["code"])
            result = session.execute(stmt)
            permission = result.scalar_one_or_none()
            
            if not permission:
                permission = Permission(
                    id=uuid.uuid4(),
                    code=p_data["code"],
                    description=p_data["description"]
                )
                session.add(permission)
                print(f"Created permission: {p_data['code']}")
            
            db_permissions[p_data["code"]] = permission
        
        session.commit()

        print("Seeding roles...")
        for r_data in roles_data:
            stmt = select(Role).where(Role.name == r_data["name"])
            result = session.execute(stmt)
            role = result.scalar_one_or_none()
            
            if not role:
                role = Role(
                    id=uuid.uuid4(),
                    name=r_data["name"],
                    description=r_data["description"]
                )
                session.add(role)
                print(f"Created role: {r_data['name']}")
            
            session.flush()
            
            # Sync permissions
            target_permissions = [db_permissions[code] for code in r_data["permissions"]]
            
            for p in target_permissions:
                assoc_stmt = select(role_permissions).where(
                    role_permissions.c.role_id == role.id,
                    role_permissions.c.permission_id == p.id
                )
                assoc_result = session.execute(assoc_stmt)
                if not assoc_result.first():
                    session.execute(
                        role_permissions.insert().values(
                            role_id=role.id,
                            permission_id=p.id
                        )
                    )
                    print(f"Assigned {p.code} to {role.name}")

        session.commit()
        print("RBAC seeding completed.")


if __name__ == "__main__":
    seed_rbac()
