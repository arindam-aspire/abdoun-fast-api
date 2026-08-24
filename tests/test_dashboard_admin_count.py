from __future__ import annotations

from app.repositories.dashboard import ADMIN_ROLE_NAMES, ALL_ADMIN_ROLE_NAMES


def test_admin_role_names_excludes_super_admin():
    assert "super_admin" not in ADMIN_ROLE_NAMES
    assert "admin" in ADMIN_ROLE_NAMES
    assert "agency" in ADMIN_ROLE_NAMES
    assert "agency_admin" in ADMIN_ROLE_NAMES


def test_all_admin_role_names_includes_super_admin():
    assert "super_admin" in ALL_ADMIN_ROLE_NAMES
