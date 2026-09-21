from app.services.notifications.email.exceptions import EmailConfigurationError, EmailDeliveryError
from app.services.notifications.email.purpose import EmailPurpose
from app.services.notifications.email.result import EmailSendResult
from app.services.notifications.email.service import EmailService, get_email_service, send_email

__all__ = [
    "EmailConfigurationError",
    "EmailDeliveryError",
    "EmailPurpose",
    "EmailSendResult",
    "EmailService",
    "get_email_service",
    "send_email",
]
