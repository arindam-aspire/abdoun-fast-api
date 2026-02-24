from app.models.property import Base  # noqa: F401
from app.models.property_normalized import PropertyNormalized  # noqa: F401

# Alias for backward compatibility during migration
Property = PropertyNormalized

__all__ = [
    "Base",
    "Property",
    "PropertyNormalized",
]

