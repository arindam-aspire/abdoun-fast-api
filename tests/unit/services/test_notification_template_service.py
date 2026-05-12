from app.constants.notification_types import NotificationType
from app.services.notification_template_service import NotificationTemplateService


def test_build_template_with_defaults() -> None:
    svc = NotificationTemplateService()
    title, msg = svc.build(type_key=NotificationType.AGENT_APPROVED.value, data=None)
    assert title
    assert msg


def test_build_template_with_metadata_placeholders() -> None:
    svc = NotificationTemplateService()
    title, msg = svc.build(
        type_key=NotificationType.LEAD_CREATED.value,
        data={
            "lead_name": "John Doe",
            "lead_id": "L-1",
            "creator_name": "Admin",
            "metadata": {"extra": "z"},
        },
    )
    assert isinstance(title, str)
    assert isinstance(msg, str)
    assert "John Doe" in msg
