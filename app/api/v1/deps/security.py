"""
Backward compatibility module - re-exports from app.core.auth and app.core.permissions.

This module maintains backward compatibility for existing imports while
the new implementation lives in app.core.auth and app.core.permissions.
"""
# Re-export from new modules for backward compatibility
from app.core.auth import get_current_user, security
from app.core.permissions import get_user_permissions, require_permission, require_role

__all__ = ["get_current_user", "get_user_permissions", "require_permission", "require_role", "security"]
