from __future__ import annotations

from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.permissions import PermissionChecker, RoleChecker, get_user_permissions, get_user_roles


def _role(name: str, perm_codes: list[str]) -> SimpleNamespace:
    perms = [SimpleNamespace(code=c) for c in perm_codes]
    return SimpleNamespace(name=name, permissions=perms)


def test_get_user_permissions_collects_direct_role_permissions() -> None:
    user = SimpleNamespace(id="u1", roles=[_role("agent", ["a", "b"]), _role("viewer", ["b", "c"])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    assert get_user_permissions(cast(Any, user), cast(Any, db)) == {"a", "b", "c"}


def test_get_user_permissions_includes_inherited_admin_permissions() -> None:
    admin = SimpleNamespace(roles=[_role("admin", ["x", "y"])])
    assignment = SimpleNamespace(admin_id="a1", admin=admin)

    user = SimpleNamespace(id="u1", roles=[_role("agent", ["a"])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [assignment]
    db.execute.return_value = result

    assert get_user_permissions(cast(Any, user), cast(Any, db)) == {"a", "x", "y"}


def test_get_user_roles_collects_direct_and_inherited_roles() -> None:
    admin = SimpleNamespace(roles=[_role("admin", ["p1"]), _role("manager", ["p2"])])
    assignment = SimpleNamespace(admin_id="a1", admin=admin)
    user = SimpleNamespace(id="u1", roles=[_role("agent", ["a"])])

    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [assignment]
    db.execute.return_value = result

    assert get_user_roles(cast(Any, user), cast(Any, db)) == {"agent", "admin", "manager"}


def test_role_checker_allows_when_role_present() -> None:
    user = SimpleNamespace(id="u1", roles=[_role("admin", [])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    checker = RoleChecker("admin")
    assert checker(user=cast(Any, user), db=cast(Any, db)) is user


def test_role_checker_raises_403_when_role_missing() -> None:
    user = SimpleNamespace(id="u1", roles=[_role("agent", [])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    checker = RoleChecker("admin")
    with pytest.raises(HTTPException) as exc:
        checker(user=cast(Any, user), db=cast(Any, db))
    assert exc.value.status_code == 403


def test_permission_checker_allows_when_permission_present() -> None:
    user = SimpleNamespace(id="u1", roles=[_role("agent", ["agent:invite"])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    checker = PermissionChecker("agent:invite")
    assert checker(user=cast(Any, user), db=cast(Any, db)) is user


def test_permission_checker_raises_403_when_permission_missing() -> None:
    user = SimpleNamespace(id="u1", roles=[_role("agent", ["something:else"])])
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    checker = PermissionChecker("agent:invite")
    with pytest.raises(HTTPException) as exc:
        checker(user=cast(Any, user), db=cast(Any, db))
    assert exc.value.status_code == 403

