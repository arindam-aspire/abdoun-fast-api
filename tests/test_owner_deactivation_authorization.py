from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import owners


@pytest.mark.parametrize("actor_roles", [("agent",), ("admin",), ("agency",), ("agency_admin",)])
def test_deactivate_owner_rejects_agent_and_agency_roles(actor_roles):
    owner = SimpleNamespace(id=uuid4(), is_active=True)

    with (
        patch.object(owners, "_assert_owner_user", return_value=owner),
        patch.object(owners, "_assert_can_manage_owner"),
        patch.object(owners, "_hide_owner_properties") as hide_properties,
    ):
        with pytest.raises(HTTPException) as exc_info:
            owners.deactivate_owner(
                MagicMock(),
                owner_id=owner.id,
                actor_user_id=uuid4(),
                actor_roles=actor_roles,
                actor_agency_id=uuid4(),
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "FORBIDDEN",
        "message": "Insufficient permissions",
    }
    hide_properties.assert_not_called()


def test_status_deactivation_rejects_agency_even_when_owner_is_already_inactive():
    owner = SimpleNamespace(id=uuid4(), is_active=False)

    with (
        patch.object(owners, "_assert_owner_user", return_value=owner),
        patch.object(owners, "_assert_can_manage_owner"),
        patch.object(owners, "serialize_owner") as serialize_owner,
    ):
        with pytest.raises(HTTPException) as exc_info:
            owners.update_owner_status(
                MagicMock(),
                owner_id=owner.id,
                actor_user_id=uuid4(),
                actor_roles=("admin",),
                actor_agency_id=uuid4(),
                status="INACTIVE",
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "FORBIDDEN"
    serialize_owner.assert_not_called()


def test_super_admin_remains_authorized_to_deactivate_owner():
    owners._assert_can_deactivate_owner(("super_admin",))
