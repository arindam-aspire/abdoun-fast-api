"""Centralized constants and text messages for the application; no hardcoded API/log messages elsewhere."""

# API Error Messages
class ErrorMessages:
    """Error messages returned to API clients"""
    PROPERTY_NOT_FOUND = "Property not found"
    RECENT_VIEWS_UPDATE_FAILED = "Failed to update recent views"
    RECENT_VIEWS_CLEAR_FAILED = "Failed to clear recent views"
    GEOCODING_SERVICE_UNAVAILABLE = "Geocoding service not available, skipping geocoding"
    ERROR_UPDATING_PROPERTIES = "Error updating properties"
    BATCH_INSERT_FAILED = "Batch insert failed due to duplicates, trying individual inserts..."
    INVALID_COORDINATE_RANGE = "Invalid coordinate range"
    INVALID_COORDINATES = "Invalid coordinates returned"
    ACCESS_FORBIDDEN = "Access forbidden (403). Check User-Agent and rate limiting."
    GEOCODING_API_ERROR = "Geocoding API error"
    TIMEOUT_GEOCODING = "Timeout while geocoding"
    CONNECTION_ERROR = "Connection error while geocoding"
    REQUEST_ERROR = "Request error while geocoding"
    DATA_PARSING_ERROR = "Data parsing error while geocoding"
    UNEXPECTED_ERROR = "Unexpected error while geocoding"
    AZURE_OPENAI_NOT_CONFIGURED = "Azure OpenAI not configured, skipping fallback"
    OPENAI_LIBRARY_NOT_INSTALLED = "OpenAI library not installed. Install with: pip install openai"
    FAILED_TO_PARSE_AZURE_RESPONSE = "Failed to parse Azure OpenAI response"
    AZURE_OPENAI_GEOCODING_ERROR = "Azure OpenAI geocoding error"
    AZURE_OPENAI_COULD_NOT_GEOCODE = "Azure OpenAI could not geocode"
    
    # Auth Errors
    USER_EXISTS = "User with this email or phone number already exists"
    INVALID_CREDENTIALS = "Invalid email/phone or password"
    INVALID_OTP = "Invalid or expired OTP"
    OTP_NOT_CONFIGURED = "OTP login is not configured. Configure Cognito custom auth Lambda triggers (Define Auth Challenge, Create Auth Challenge, Verify Auth Challenge) for this user pool, or use password login: POST /api/v1/auth/login/password"
    INVALID_TOKEN = "Invalid or expired token"
    INVALID_TOKEN_USE = "Invalid token_use: {token_use}, expected 'access'"
    USER_NOT_FOUND = "User not found"
    USER_NOT_CONFIRMED = "User is not confirmed. Please verify your account using the confirmation code."
    USER_INACTIVE = "User account is inactive"
    MISSING_PERMISSION = "Missing required permission: {permission}"
    MISSING_ROLE = "Missing required role: {role}"
    INVITE_EXPIRED = "Invitation has expired or already been used"
    INVALID_INVITE_TOKEN = "Invalid invitation token"
    INVITE_TOKEN_REQUIRED = "Invite token is required"
    REGISTRATION_FAILED = "Agent registration failed"
    COGNITO_ERROR = "Authentication service error: {error}"
    NOT_FOUND = "Not Found"
    
    # RBAC/Agent Errors
    INVITE_FAILED = "Failed to create agent invitation"
    EMAIL_MISMATCH = "Email does not match invitation"
    NOT_AN_AGENT = "User is not an agent"
    APPROVAL_FAILED = "Agent approval failed"
    ASSIGNMENT_FAILED = "Agent assignment failed"
    LOGOUT_FAILED = "Logout failed"
    INVALID_INVITE = "Invalid or expired invitation"
    MISSING_SUB = "Token payload is missing 'sub' claim"
    SOCIAL_AUTH_FAILED = "Social authentication failed"
    REVOCATION_FAILED = "Failed to revoke agent privileges"
    UNAUTHORIZED_ACCESS = "You are not authorized to perform this action"
    AGENT_REJECT_FAILED = "Failed to reject agent"
    REFRESH_USERNAME_REQUIRED = "username (sub or email) is required when Cognito app client uses a secret. Include it from your login response."
    AGENT_NOT_PENDING = "Agent is not pending approval"
    ASSIGNMENT_NOT_FOUND = "Active assignment not found"
    ROLE_NOT_FOUND = "Role not found"
    USER_ALREADY_HAS_ROLE = "User already has this role"
    USER_DOES_NOT_HAVE_ROLE = "User does not have this role"
    CANNOT_DEACTIVATE_SELF = "Cannot deactivate your own account"
    AGENT_ALREADY_EXISTS = "An agent with this email already exists"
    INVALID_EMAIL = "Please enter a valid email address"
    INVITE_NOT_FOUND = "Invitation not found or expired"
    INVITE_ALREADY_USED = "Invitation has already been used"
    INVITE_ALREADY_REVOKED = "Invitation has been revoked"
    INVITE_CANNOT_RESEND = "Cannot resend invitation: invitation is already used or revoked"
    INVITE_CANNOT_REVOKE = "Cannot revoke invitation: invitation is already used"
    ALREADY_SUBMITTED = "You have already submitted your application"
    INVALID_STATUS_TRANSITION = "Agent must be in PENDING_REVIEW status to accept"
    INVALID_AGENT_STATUS = "Invalid agent status"
    INVALID_AGENT_STATUS_TRANSITION = "Invalid agent status transition"
    REASON_REQUIRED = "A decline reason is required"
    AGENT_NOT_FOUND = "Agent not found"
    ALREADY_DELETED = "This agent has already been deleted"
    DEV_AUTH_INIT_FAILED = "Failed to initialize development auth user"
    COGNITO_SIGNUP_MISSING_USERSUB = "Cognito signup did not return UserSub"
    COGNITO_CONFIRM_FAILED_TEMP_PASSWORD = "Could not confirm user in Cognito. The agent may not be able to log in with the temporary password."
    USER_NOT_FOUND_FOR_INVITE = "User not found for this invite"
    ADMIN_CANNOT_ASSIGN_SELF_AS_AGENT = "An admin cannot assign themselves as an agent"
    ADMINS_CANNOT_BE_ASSIGNED_AS_AGENTS = "Admins cannot be assigned as agents"
    ONLY_AGENT_ROLE_CAN_BE_ASSIGNED_TO_ADMIN = "Only users with AGENT role can be assigned to an admin"
    INVALID_PREVIOUS_PASSWORD_OR_PERMISSIONS = "Invalid previous password or insufficient permissions"
    PASSWORD_DOES_NOT_MEET_REQUIREMENTS = "Password does not meet requirements"
    ONLY_ACTIVE_PROPERTIES_CAN_BE_FAVORITED = "Only active properties can be favorited"
    PROPERTY_ALREADY_FAVORITED = "Property is already in favorites"
    FAVORITE_NOT_FOUND = "Favorite not found"
    SAVED_SEARCH_NOT_FOUND = "Saved search not found"
    SAVED_SEARCH_NAME_EXISTS = "Saved search name already exists"
    INVALID_SAVED_SEARCH_NAME = "Saved search name is required"
    INVALID_SEARCH_CRITERIA = "search_criteria must be a non-empty JSON object"

    # Generic / HTTP (exception handlers, fallbacks)
    REQUEST_FAILED = "Request failed"
    VALIDATION_ERROR = "Validation error"
    INTERNAL_SERVER_ERROR = "Internal server error"
    UNEXPECTED_ERROR_OCCURRED = "An unexpected error occurred."
    INPUT_CANNOT_BE_NONE = "Input cannot be None"
    TOKEN_VERIFICATION_FAILED_INTERNAL = "Token verification failed"
    CANNOT_EXTRACT_USERNAME_FROM_ACCESS_TOKEN = "Cannot extract username from access token"
    COGNITO_USER_POOL_ID_NOT_CONFIGURED = "COGNITO_USER_POOL_ID is not configured"
    PROFILE_OTP_DELIVERY_FAILED = "Could not send verification code. Try again later or contact support."
    PROFILE_EMAIL_IN_USE = "This email is already registered to another account"
    PROFILE_PHONE_IN_USE = "This phone number is already registered to another account"
    PROFILE_NAME_INVALID = "Display name cannot be empty"
    PROFILE_COGNITO_UPDATE_FAILED = "Identity provider rejected the update. Try again or contact support."
    PROFILE_UPDATE_NO_CHANGES = "No changes to apply for the provided profile fields"
    PROFILE_VERIFY_NO_PAIRS = (
        "Provide at least one verification pair: email with email_otp and/or phone_number with phone_otp"
    )
    PROFILE_VERIFY_EMAIL_OTP_REQUIRED = "email_otp is required when email is provided"
    PROFILE_VERIFY_PHONE_OTP_REQUIRED = "phone_otp is required when phone_number is provided"
    PROFILE_VERIFY_EMAIL_REQUIRED = "email is required when email_otp is provided"
    PROFILE_VERIFY_PHONE_REQUIRED = "phone_number is required when phone_otp is provided"
    PROFILE_UPDATE_NO_FIELDS = "At least one profile field must be provided"


# Validation messages (Pydantic/schema validators — shown to API clients on validation failure)
class ValidationMessages:
    """Validation error messages used in request schemas"""
    EMAIL_REGEX_PATTERN = r"[^@]+@[^@]+\.[^@]+"
    PHONE_E164 = "Phone number must be in international format (e.g., +00 000000000)"
    PASSWORD_MIN_LENGTH = "Password must be at least 8 characters long"
    PASSWORD_UPPERCASE = "Password must have at least one uppercase letter"
    PASSWORD_LOWERCASE = "Password must have at least one lowercase letter"
    PASSWORD_NUMBER = "Password must have at least one number"
    PASSWORD_SPECIAL = "Password must have at least one special character"
    INVALID_EMAIL_FORMAT = "Invalid email format"
    USERNAME_EMAIL_OR_PHONE = "Username must be a valid email or phone number (+00 000000000)"
    USERNAME_EMAIL_OR_E164 = "Username must be a valid email or phone (e.g. +00 000000000)"
    PASSWORD_SPECIAL_CHARS = "!@#$%^&*()-_=+[]{}|;:,.<>?"


# Success Messages
class SuccessMessages:
    """Success messages for operations"""
    PROPERTY_UPDATED = "Updated {count} existing properties (coordinates and/or location_name)."
    PROPERTIES_IMPORTED = "imported {count} new properties"
    PROPERTIES_UPDATED = "updated {count} existing properties"
    PROPERTIES_SKIPPED = "skipped {count} duplicates"
    PROPERTIES_IMPORTED_SKIPPED = "Imported {imported} properties, skipped {skipped} duplicates."
    AZURE_OPENAI_GEOCODED = "Azure OpenAI geocoded '{location}' to ({lat:.6f}, {lon:.6f})"
    SUCCESSFULLY_GEOCODED = "Successfully geocoded '{location}' to ({lon}, {lat})"
    FOUND_COORDINATES_CLEANED = "Found coordinates for '{location}' using cleaned name: '{cleaned_location}'"
    FOUND_COORDINATES_PART = "Found coordinates for '{location}' using part {part_num}: '{part}'"
    FOUND_COORDINATES_COMBINED = "Found coordinates for '{location}' using combined parts: '{combined}'"
    FOUND_COORDINATES_MAIN = "Found coordinates for '{location}' using main location: '{main_location}'"
    FOUND_COORDINATES_FALLBACK = "Found coordinates for '{location}' using fallback: '{suffix_location}'"
    
    # Auth Success
    USER_REGISTERED = "User registered successfully"
    LOGIN_SUCCESSFUL = "Login successful"
    LOGOUT_SUCCESSFUL = "Logged out successfully"
    PASSWORD_RESET_SUCCESS = "Password reset successfully"
    OTP_SENT = "OTP has been sent"
    CONFIRMATION_CODE_SENT = "Confirmation code has been sent"
    ACCOUNT_CONFIRMED = "Account confirmed successfully"
    AGENT_INVITED = "Agent invitation sent successfully"
    AGENT_INVITE_SENT_TO = "Invitation sent to {email}"
    AGENT_REGISTERED = "Agent registered successfully"
    AGENT_APPROVED = "Agent approved successfully"
    AGENT_STATUS_UPDATED = "Agent status updated successfully"
    AGENT_ASSIGNED = "Agent assigned successfully"
    INVITE_VALID = "Invitation token is valid"
    REGISTRATION_PENDING = "Registration successful, pending admin approval"
    SOCIAL_LOGIN_SUCCESSFUL = "Social login successful"
    AGENT_REVOKED = "Agent privileges revoked successfully"
    ADMIN_REGISTERED = "Admin registered successfully"
    AGENT_REJECTED = "Agent application rejected"
    USER_UPDATED = "User updated successfully"
    USER_DELETED = "User deactivated successfully"
    ROLE_ASSIGNED_TO_USER = "Role assigned to user successfully"
    ROLE_REMOVED_FROM_USER = "Role removed from user successfully"
    RECENT_VIEW_UPDATED = "Recent view updated"
    RECENT_VIEWS_CLEARED = "Recent views cleared"
    RECENT_VIEW_REMOVED = "Recent view removed"
    AGENT_DELETED = "Agent has been deleted"
    AGENT_ACCEPTED = "Agent accepted. Approval email sent."
    AGENT_DECLINED = "Agent declined. Rejection email sent with the reason."
    INVITE_RESENT = "Invitation resent successfully"
    INVITE_REVOKED = "Invitation revoked successfully"
    AGENT_CREATED_WITH_TEMP_PASSWORD = "Agent created successfully with a temporary password"
    AGENT_ONBOARDING_SUBMITTED_UNDER_REVIEW = "Your application has been submitted and is under review."
    PROPERTY_FAVORITED = "Property added to favorites successfully"
    PROPERTIES_FAVORITED_BULK = "Bulk favorites processed successfully"
    PROPERTY_UNFAVORITED = "Property removed from favorites successfully"
    PROFILE_UPDATED_SUCCESS = "Profile updated successfully"
    PROFILE_VERIFICATION_REQUIRED = "Verification required for profile update"


# Info Messages
class InfoMessages:
    """Informational messages"""
    ALL_DUPLICATES = "All {count} properties were duplicates, nothing to import."
    UPDATED_AND_SKIPPED = "Updated {updated} properties, {skipped} were skipped (already had all data)."
    TRYING_AZURE_OPENAI = "Trying Azure OpenAI as final fallback for: '{location}'"
    TRYING_AZURE_OPENAI_GEOCODING = "Trying Azure OpenAI geocoding for: '{location}'"
    TRYING_SIMPLIFIED_LOCATION = "Trying simplified location: '{simplified_location}'"
    RATE_LIMITING = "Rate limiting: sleeping for {sleep_time:.2f}s"
    GEOCODING_REQUEST = "Geocoding request for: '{location}'"
    NO_RESULTS_FOUND = "No results found for location: '{location}'"
    AGENT_ALREADY_SUBMITTED = "You have already submitted your application."


# Warning Messages
class WarningMessages:
    """Warning messages"""
    WARNING_GEOCODING_UNAVAILABLE = "Warning: Geocoding service not available, skipping geocoding"
    INVALID_COORDINATE_RANGE = "Invalid coordinate range for '{location}': ({lon}, {lat})"
    INVALID_COORDINATES_RETURNED = "Invalid coordinates returned for '{location}': lon={lon}, lat={lat}"
    TIMEOUT_GEOCODING = "Timeout while geocoding '{location}'"
    CONNECTION_ERROR_GEOCODING = "Connection error while geocoding '{location}'"
    OPENAI_LIBRARY_NOT_INSTALLED = "OpenAI library not installed. Install with: pip install openai"
    FAILED_TO_PARSE_AZURE_RESPONSE = "Failed to parse Azure OpenAI response for '{location}': {error}"
    AZURE_OPENAI_GEOCODING_ERROR = "Azure OpenAI geocoding error for '{location}': {error}"
    AZURE_OPENAI_NOT_CONFIGURED = "Azure OpenAI not configured, skipping fallback for: '{location}'"


# Default Values
class LoggerDefaults:
    """Defaults for logging (e.g. request_id when absent)."""
    REQUEST_ID_EMPTY = "-"


class Defaults:
    """Default values used throughout the application"""
    UNTITLED_PROPERTY = "Untitled"
    UNTITLED_PROPERTY_FALLBACK = "Untitled Property"  # Fallback title in translation when empty
    SOCIAL_USER_DEFAULT_NAME = "Social User"  # Default name when social provider omits it
    DEFAULT_LIMIT = 50
    DEFAULT_OFFSET = 0
    MAX_SEARCH_LIMIT = 200
    LANG_QUERY_DESCRIPTION = "Language code for title/description: en, ar, esp, fr"
    AGENT_DECLINE_REASON_ADMIN = "Application rejected by admin"
    DEFAULT_PHONE_PREFIX_10_DIGIT = "+91"
    DEFAULT_SOCIAL_PROVIDER = "Google"
    ROLE_PERMISSION_PREFIX = "role:"
    PASSWORD_MIN_LENGTH = 8
    TOKEN_TYPE_BEARER = "Bearer"
    DEFAULT_COUNTRY = "Jordan"
    DEFAULT_COUNTRY_ID = 1
    DEFAULT_CURRENCY = "JOD"
    DEFAULT_CURRENCY_DISPLAY = "JD"
    MAP_EMBED_URL_TEMPLATE = "https://maps.google.com/?q={lat},{lng}"
    DEFAULT_BROKER_NAME = "Abdoun Real Estate"


class RateLimits:
    """Rate limit policy strings used by the limiter decorators."""

    SIGNUP = "10/minute"
    SIGNUP_ADMIN = "5/minute"
    LOGIN_PASSWORD = SIGNUP_ADMIN
    LOGIN_OTP_REQUEST = "3/minute"
    LOGIN_OTP_VERIFY = SIGNUP_ADMIN
    FORGOT_PASSWORD_REQUEST = LOGIN_OTP_REQUEST
    FORGOT_PASSWORD_CONFIRM = LOGIN_OTP_REQUEST
    PROFILE_OTP_REQUEST = LOGIN_OTP_REQUEST
    PROFILE_OTP_VERIFY = LOGIN_OTP_VERIFY
    PROFILE_UPDATE_REQUEST = "10/minute"


class ApiDocs:
    """OpenAPI documentation strings (Query/Path descriptions)."""

    AGENT_ID_DESC = "Agent ID"
    FILTER_BY_STATUS = "Filter by status"
    SEARCH_BY_NAME_OR_EMAIL = "Search by name or email"
    PAGE_NUMBER = "Page number"
    ITEMS_PER_PAGE = "Items per page"
    SORT_FIELD = "Sort field"
    SORT_ORDER = "Sort order (asc/desc)"
    FILTER_BY_IS_USED = "Filter by is_used: true/false"
    FILTER_BY_AGENT_ID = "Filter by agent ID"
    FILTER_BY_ADMIN_ID_DEFAULTS_CURRENT_USER = (
        "Filter by admin ID (defaults to current user)"
    )
    INVITE_TOKEN = "Invite token"
    FILTER_AREAS_BY_CITY_NAME = "Filter areas by city name (case-insensitive)"

    # Properties search
    LISTING_TYPE_BUY_RENT = "Listing type: buy or rent"
    PROPERTY_CATEGORY = (
        "One of: residential, commercial, land. On Hero, 'Land' is sent as lands."
    )
    PROPERTY_TYPE_SLUG = (
        "Slugified property type (e.g., apartments, villas, residential-lands)"
    )
    CITY_NAME_LOWERCASE = "City name, lowercase"
    LOCATIONS_CSV_LOWERCASE = "Comma-separated area/neighborhood names, lowercase"
    BUDGET_MIN_JD_NUMERIC_STRING = "Minimum price in JD (numeric string)"
    BUDGET_MAX_JD_NUMERIC_STRING = "Maximum price in JD (numeric string)"
    MIN_PRICE_ALIAS = "Alias for budgetMin (for hero search compatibility)"
    MAX_PRICE_ALIAS = "Alias for budgetMax (for hero search compatibility)"
    EXCLUSIVE_FILTER = (
        "Filter by exclusive status (true/1 for exclusive only, false/0 for non-exclusive only)"
    )
    PAGE_NUMBER_1_BASED = "Page number, 1-based"
    ITEMS_PER_PAGE = "Items per page"
    MAX_SIMILAR_PROPERTIES = "Maximum number of similar properties to return"
    GEOCODE_MISSING_QUERY = "If True, geocode locations that don't have coordinates (slower, rate-limited)"

    # Users
    FILTER_BY_ROLE = "Filter by role (admin, agent, registered_user)"
    SEARCH_USERS = "Search by email, phone number, or full_name"


# Development Auth Defaults
class DevAuthDefaults:
    """Defaults for local development auth bypass."""
    USER_ID = "00000000-0000-0000-0000-000000000001"
    FULL_NAME = "Dev Agent Admin"
    EMAIL = "dev-agent-admin@local.test"
    PHONE_NUMBER = "+10000000001"


# Geocoding Constants
class GeocodingConstants:
    """Constants related to geocoding"""
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "MyPlans/1.0 (https://myplans.com; contact@myplans.com)"
    RATE_LIMIT_DELAY = 1.1  # Slightly more than 1 second to be safe
    TIMEOUT_CONNECT = 10
    TIMEOUT_READ = 30
    EXTRA_DELAY_AFTER_403 = 2  # seconds
    # Azure OpenAI geocoding prompts (use {location} in user prompt)
    AZURE_GEOCODE_SYSTEM = (
        "You are a geocoding assistant. Return only valid JSON with latitude and longitude as decimal numbers, or null if not found."
    )
    AZURE_GEOCODE_USER_TEMPLATE = (
        "Find the exact geographic coordinates (latitude and longitude) for this location: '{location}'. "
        "This location is likely in Jordan, specifically in or near Amman. "
        "Return ONLY a valid JSON object with 'latitude' and 'longitude' as decimal numbers. "
        "If you cannot find the exact location, return null for both values. "
        "Example format: {{\"latitude\": 31.9539, \"longitude\": 35.9106}} or {{\"latitude\": null, \"longitude\": null}}"
    )


# CSV Import Messages
# Defaults for property import (normalized_importer / CSV)
class ImportDefaults:
    """Default values when CSV fields are missing or invalid."""
    CATEGORY_OTHER = "Other"
    TYPE_OTHER = "Other"
    LOCATION_UNKNOWN = "Unknown"
    DEFAULT_CITY = "Amman"
    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_OK_LOWER = "ok"  # CSV value that maps to verified


class CSVImportMessages:
    """Messages related to CSV import operations"""
    UPDATED_PROPERTIES = "Updated {count} existing properties (coordinates and/or location_name)."
    ERROR_UPDATING = "Error updating properties: {error}"
    ALL_DUPLICATES = "All {count} properties were duplicates, nothing to import."
    UPDATED_AND_SKIPPED = "Updated {updated} properties, {skipped} were skipped (already had all data)."
    IMPORTED_UPDATED_SKIPPED = "imported {imported} new properties; updated {updated} existing properties; skipped {skipped} duplicates"
    BATCH_INSERT_FAILED = "Batch insert failed due to duplicates, trying individual inserts..."
    IMPORTED_SKIPPED = "Imported {imported} properties, skipped {skipped} duplicates."


# System Messages
class SystemMessages:
    """System-level messages"""
    APP_NAME = "Real Estate Map API"
    API_V1_PREFIX = "/api/v1"
    HEALTHY = "healthy"
    SERVICE_NAME = "realestate-api"


class ApiRoutes:
    """API route prefixes and tags."""

    AUTH_PREFIX = "/auth"
    AGENTS_PREFIX = "/agents"
    USERS_PREFIX = "/users"
    OWNERS_PREFIX = "/owners"
    PROPERTIES_PREFIX = "/properties"
    FAVORITES_PREFIX = "/favorites"
    SAVED_SEARCHES_PREFIX = "/saved-searches"
    PROPERTY_SUBMISSIONS_PREFIX = "/property-submissions"
    ADMIN_PROPERTY_SUBMISSIONS_PREFIX = "/admin/property-submissions"
    UPLOADS_PREFIX = "/uploads"
    AGENT_PROPERTIES_PREFIX = "/agent-properties"

    AUTH_TAG = "auth"
    AGENTS_TAG = "agents"
    USERS_TAG = "users"
    OWNERS_TAG = "owners"
    PROPERTIES_TAG = "properties"
    FAVORITES_TAG = "favorites"
    SAVED_SEARCHES_TAG = "saved-searches"
    PROPERTY_SUBMISSIONS_TAG = "property-submissions"
    ADMIN_PROPERTY_SUBMISSIONS_TAG = "admin-property-submissions"
    UPLOADS_TAG = "uploads"
    AGENT_PROPERTIES_TAG = "agent-properties"
    SEARCH_TAG = "search"
    LOCATIONS_TAG = "locations"


class ConfigDefaults:
    """Default configuration values used by `app/core/config.py` when env vars are absent."""

    ENVIRONMENT = "local"
    DEBUG = "false"

    # DB: dev-only fallback. Prefer setting DATABASE_URL explicitly.
    # No password in fallback URL (local dev). Prefer setting DATABASE_URL explicitly.
    DATABASE_URL = "postgresql+psycopg2://localhost:5432/realestate"

    # CORS
    CORS_ORIGINS = "http://localhost:3000"
    CORS_ALLOW_CREDENTIALS = "true"
    CORS_ALLOW_METHODS = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS = "Authorization,Content-Type,Accept,Origin,X-Requested-With"
    CORS_MAX_AGE_SECONDS = 600

    # Cognito / social
    SOCIAL_REDIRECT_URI = "http://localhost:8000/api/v1/auth/callback"
    APP_BASE_URL = "http://localhost:3000"

    # Profile change OTP (hashing). Override in every deployed environment.
    PROFILE_OTP_PEPPER_DEFAULT = "dev-only-change-profile-otp-pepper"

    # Observability
    METRICS_PATH = "/metrics"
    SLOW_QUERY_THRESHOLD_MS = "500"


class ConfigErrorMessages:
    """Configuration validation error messages."""

    INVALID_CORS_PROD_STAGING_WITH_CREDENTIALS = (
        "Invalid CORS configuration: in production/staging with credentials enabled, "
        "CORS_ORIGINS must be a non-empty explicit list and cannot include '*'."
    )
    INVALID_CORS_WITH_CREDENTIALS = (
        "Invalid CORS configuration: when CORS_ALLOW_CREDENTIALS=true, "
        "CORS_ORIGINS cannot include '*'."
    )


class DbConstants:
    """Database layer constants (URL schemes, driver names)."""

    SQLITE_URL_PREFIX = "sqlite"


class RequestIdConstants:
    """Request-ID middleware: HTTP header, OTEL attribute, Sentry tag, and placeholder when absent."""

    HEADER_NAME = "X-Request-ID"
    OTEL_ATTRIBUTE_REQUEST_ID = "request.id"
    SENTRY_TAG_REQUEST_ID = "request_id"
    EMPTY_PLACEHOLDER = "-"


class SecurityHeadersConstants:
    """Security headers middleware: header names and values (no hardcoded strings in middleware)."""

    # Header names
    X_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options"
    X_FRAME_OPTIONS = "X-Frame-Options"
    X_XSS_PROTECTION = "X-XSS-Protection"
    REFERRER_POLICY = "Referrer-Policy"
    PERMISSIONS_POLICY = "Permissions-Policy"
    CONTENT_SECURITY_POLICY = "Content-Security-Policy"
    STRICT_TRANSPORT_SECURITY = "Strict-Transport-Security"

    # Header values
    NOSNIFF = "nosniff"
    DENY = "DENY"
    XSS_BLOCK = "1; mode=block"
    REFERRER_STRICT_ORIGIN = "strict-origin-when-cross-origin"
    PERMISSIONS_RESTRICTIVE = "geolocation=(), microphone=(), camera=()"
    CSP_API_BASELINE = "default-src 'none'; frame-ancestors 'none';"
    HSTS_MAX_AGE = "max-age=31536000; includeSubDomains"


class EnvironmentNames:
    """Environment identifier strings; use with settings.environment."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    STAGING = "staging"


# Environments where HSTS and other production-only security headers are typically skipped
DEV_ENVIRONMENTS = frozenset((EnvironmentNames.LOCAL, EnvironmentNames.DEVELOPMENT))


# Cognito API response/error keys (no hardcoded AWS strings in services)
class CognitoConstants:
    """Cognito API response keys and error-message substrings."""
    USER_SUB = "UserSub"
    OTP_ERROR_SUBSTRING = "Custom auth lambda trigger"


# Repository / API sort and filter values (no hardcoded strings in repositories)
class AgentSortField:
    """Agent list sort field names (API contract)."""
    INVITED_AT = "invitedAt"
    EMAIL = "email"
    FULL_NAME = "fullName"
    CREATED_AT = "createdAt"


class SortOrder:
    """Sort direction (asc/desc)."""
    ASC = "asc"
    DESC = "desc"


class ListingStatus:
    """Property listing type for search filters."""
    BUY = "buy"
    RENT = "rent"


class PropertyListingType:
    """Listing type values in property schema/API (sale, rent, sale_rent)."""
    SALE = "sale"
    RENT = "rent"
    SALE_RENT = "sale_rent"


class PropertyExclusiveFilter:
    """Values that mean 'exclusive only' in query params."""
    TRUE_VALUES = ("true", "1", "yes")


# RBAC Roles
class UserRoles:
    ADMIN = "admin"
    AGENT = "agent"
    REGISTERED_USER = "registered_user"


# Agent Statuses
class AgentStatus:
    INVITED = "INVITED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DELETED = "DELETED"
    # Legacy statuses for backward compatibility
    PENDING = "pending"
    REJECTED = "rejected"


class AgentAssignmentStatus:
    """Human-readable assignment status labels returned to API clients."""

    ACTIVE = "ACTIVE"
    INACTIVE_REVOKED = "INACTIVE/REVOKED"


# RBAC Permissions
class UserPermissions:
    # User management
    USER_CREATE = "user:create"
    USER_DELETE = "user:delete"
    
    # Agent management
    AGENT_APPROVE = "agent:approve"
    AGENT_ASSIGN = "agent:assign"
    
    # Role management
    ROLE_ASSIGN = "role:assign"
    
    # Property management
    PROPERTY_CREATE = "property:create"
    PROPERTY_UPDATE = "property:update"
    PROPERTY_DELETE = "property:delete"
