from app.services.notification_template_service import NotificationTemplateService
from app.constants.notification_types import NotificationType


def test_build_template_with_defaults() -> None:
    svc = NotificationTemplateService()
    title, msg = svc.build(type_key=NotificationType.AGENT_APPROVED.value, data=None)
    assert title
    assert msg


def test_build_template_with_metadata_placeholders() -> None:
    svc = NotificationTemplateService()
    title, msg = svc.build(
        type_key=NotificationType.SYSTEM_ANNOUNCEMENT.value,
        data={"metadata": {"lead_name": "John Doe"}},
    )
    assert isinstance(title, str)
    assert isinstance(msg, str)

