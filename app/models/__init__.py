from app.models.property import Base  # noqa: F401
from app.models.owner import Owner, PropertyOwner  # noqa: F401
from app.models.property_listing_submission import PropertyListingSubmission  # noqa: F401
from app.models.property_normalized import PropertyNormalized  # noqa: F401
from app.models.user_property_favorite import UserPropertyFavorite  # noqa: F401
from app.models.user_saved_search import UserSavedSearch  # noqa: F401
from app.models.recently_viewed_property import RecentlyViewedProperty  # noqa: F401
from app.models.agency import Agency  # noqa: F401

# Alias for backward compatibility during migration
Property = PropertyNormalized

__all__ = [
    "Base",
    "Owner",
    "PropertyOwner",
    "PropertyListingSubmission",
    "Property",
    "PropertyNormalized",
    "UserPropertyFavorite",
    "UserSavedSearch",
    "RecentlyViewedProperty",
    "Agency",
]

