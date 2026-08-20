class EmailConfigurationError(Exception):
    """Raised when email provider configuration is invalid or incomplete."""


class EmailDeliveryError(Exception):
    """Raised when an email could not be delivered."""
