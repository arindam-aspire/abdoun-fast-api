"""Centralized log message templates (LogMessages.*) and format_log_message helper."""


class LogMessages:
    """Logging messages organized by category"""
    
    # Geocoding Log Messages
    class Geocoding:
        """Geocoding-related log messages"""
        RATE_LIMITING = "Rate limiting: sleeping for {sleep_time:.2f}s"
        GEOCODING_REQUEST = "Geocoding request for: '{location}'"
        SUCCESSFULLY_GEOCODED = "Successfully geocoded '{location}' to ({lon}, {lat})"
        NO_RESULTS_FOUND = "No results found for location: '{location}'"
        ACCESS_FORBIDDEN = "Access forbidden (403) for '{location}'. Check User-Agent and rate limiting."
        GEOCODING_API_ERROR = "Geocoding API error for '{location}': {status_code}"
        TIMEOUT_GEOCODING = "Timeout while geocoding '{location}'"
        CONNECTION_ERROR = "Connection error while geocoding '{location}'"
        REQUEST_ERROR = "Request error while geocoding '{location}': {error}"
        DATA_PARSING_ERROR = "Data parsing error while geocoding '{location}': {error}"
        UNEXPECTED_ERROR = "Unexpected error while geocoding '{location}': {error}"
        INVALID_COORDINATE_RANGE = "Invalid coordinate range for '{location}': ({lon}, {lat})"
        INVALID_COORDINATES_RETURNED = "Invalid coordinates returned for '{location}': lon={lon}, lat={lat}"
        FOUND_COORDINATES_CLEANED = "Found coordinates for '{location}' using cleaned name: '{cleaned_location}'"
        FOUND_COORDINATES_PART = "Found coordinates for '{location}' using part {part_num}: '{part}'"
        FOUND_COORDINATES_COMBINED = "Found coordinates for '{location}' using combined parts: '{combined}'"
        FOUND_COORDINATES_MAIN = "Found coordinates for '{location}' using main location: '{main_location}'"
        FOUND_COORDINATES_FALLBACK = "Found coordinates for '{location}' using fallback: '{suffix_location}'"
        TRYING_SIMPLIFIED_LOCATION = "Trying simplified location: '{simplified_location}'"
    
    # Azure OpenAI Log Messages
    class AzureOpenAI:
        """Azure OpenAI-related log messages"""
        TRYING_GEOCODING = "Trying Azure OpenAI geocoding for: '{location}'"
        TRYING_FALLBACK = "Trying Azure OpenAI as final fallback for: '{location}'"
        GEOCODED_SUCCESS = "Azure OpenAI geocoded '{location}' to ({lat:.6f}, {lon:.6f})"
        COULD_NOT_GEOCODE = "Azure OpenAI could not geocode '{location}'"
        LIBRARY_NOT_INSTALLED = "OpenAI library not installed. Install with: pip install openai"
        FAILED_TO_PARSE_RESPONSE = "Failed to parse Azure OpenAI response for '{location}': {error}"
        GEOCODING_ERROR = "Azure OpenAI geocoding error for '{location}': {error}"
        NOT_CONFIGURED = "Azure OpenAI not configured, skipping fallback for: '{location}'"
    
    # CSV Import Log Messages
    class CSVImport:
        """CSV import-related log messages"""
        GEOCODING_UNAVAILABLE = "Warning: Geocoding service not available, skipping geocoding"
        UPDATED_PROPERTIES = "Updated {count} existing properties (coordinates and/or location_name)."
        ERROR_UPDATING = "Error updating properties: {error}"
        ALL_DUPLICATES = "All {count} properties were duplicates, nothing to import."
        UPDATED_AND_SKIPPED = "Updated {updated} properties, {skipped} were skipped (already had all data)."
        IMPORTED_UPDATED_SKIPPED = "{summary}"
        BATCH_INSERT_FAILED = "Batch insert failed due to duplicates, trying individual inserts..."
        IMPORTED_SKIPPED = "Imported {imported} properties, skipped {skipped} duplicates."
    
    # Print Messages (for scripts)
    class Print:
        """Print messages for console output in scripts"""
        AZURE_OPENAI_GEOCODED = "Azure OpenAI geocoded '{location}' to ({lat:.6f}, {lon:.6f})"
        AZURE_OPENAI_COULD_NOT_GEOCODE = "Azure OpenAI could not geocode '{location}'"
        TRYING_AZURE_OPENAI_FALLBACK = "Trying Azure OpenAI as final fallback for: '{location}'"

    # Authentication Log Messages
    class Auth:
        """Authentication-related log messages"""
        SIGNUP_SUCCESS = "User signup successful: {email}"
        SIGNUP_FAILED = "User signup failed for {email}: {error}"
        LOGIN_SUCCESS = "User login successful: {email}"
        LOGIN_FAILED = "User login failed for {email}: {error}"
        LOGOUT_SUCCESS = "User logout successful: {email}"
        LOGOUT_SUCCESS_GENERIC = "User logout successful"
        LOGOUT_FAILED = "User logout failed: {error}"
        ADMIN_CONFIRM_FAILED = "Failed to confirm user {email}: {error}"
        TOKEN_REFRESH_SUCCESS = "Token refresh successful"
        TOKEN_REFRESH_FAILED = "Token refresh failed: {error}"
        OTP_REQUEST_SUCCESS = "OTP request successful for: {username}"
        OTP_REQUEST_FAILED = "OTP request failed for {username}: {error}"
        PASSWORD_RESET_REQUEST = "Password reset requested for: {email}"
        PASSWORD_RESET_SUCCESS = "Password reset successful for: {email}"
        PASSWORD_RESET_FAILED = "Password reset failed for {email}: {error}"
        PASSWORD_SET_AT_UPDATE_FAILED = "Failed to update password_set_at: {error}"
        TOKEN_VERIFICATION_FAILED = "Token verification failed: {error}"
        JWKS_FETCH_FAILED = "Failed to fetch JWKS from Cognito: {error}"
        JWKS_KEY_NOT_FOUND = "Public key {kid} not found in JWKS."
        SIGNUP_ATTEMPT_EXISTING = "Signup attempt with existing email/phone: {email}"
        TOKEN_PAYLOAD_MISSING_SUB = "Token payload missing 'sub' claim"
        TOKEN_VERIFICATION_FAILED_DEP = "Token verification failed in security dependency"
        USER_NOT_FOUND_SUB = "User not found for sub: {sub}"
        INACTIVE_USER_ATTEMPT = "Inactive user attempt: {email}"
        SOCIAL_LOGIN_SUCCESS = "Social login successful: {email}"
        SOCIAL_AUTH_FAILED_LOG = "Social authentication failed for {email}: {error}"
        UNKNOWN_EMAIL = "Unknown"  # Placeholder when email is not available in error context
        FAILED_EXTRACT_USERNAME_FROM_TOKEN = "Failed to extract username from token: {error}"
        AWS_CREDENTIALS_NOT_CONFIGURED = "AWS credentials not configured: {error}"
        AGENT_APPROVAL_WILL_PROCEED_NO_COGNITO_USER = (
            "Agent approval will proceed but Cognito user not created. "
            "Note: admin_create_user requires AWS credentials, unlike sign_up() which is a public API."
        )
        USER_ALREADY_EXISTS_IN_COGNITO = "User already exists in Cognito: {error}"
        USER_ALREADY_EXISTS_EXPECTED_PROCEED = (
            "This is expected if user was created via signup. Agent approval will proceed."
        )
        ADMIN_UPDATE_USER_ATTRIBUTES = "Cognito admin_update_user_attributes: username={username} attrs={attr_keys}"
        ADMIN_UPDATE_USER_ATTRIBUTES_FAILED = "Cognito admin_update_user_attributes failed: username={username} error={error}"
    # RBAC Log Messages
    class RBAC:
        """RBAC-related log messages"""
        PERMISSION_DENIED = "Permission denied for user {user_id}: missing {permission}"
        ROLE_ASSIGNED = "Role '{role}' assigned to user {user_id} by {assigned_by}"
        AGENT_INVITED = "Agent invited: {email} by {invited_by}"
        AGENT_APPROVED = "Agent approved: {agent_id} by {approver_id}"
        AGENT_ASSIGNED = "Agent {agent_id} assigned to admin {admin_id}"
        INHERITANCE_TRIGGERED = "User {user_id} inheriting permissions from admin {admin_id}"
        INVITE_ATTEMPT_EXISTING = "Invite attempt for existing user: {email}"
        INVALID_INVITE_TOKEN_USED = "Invalid or expired invite token used: {token}"
        INVALID_REGISTRATION_TOKEN = "Invalid or expired agent registration token used"
        REGISTRATION_PENDING = "Agent registration pending approval: {email}"
        INVITE_FAILED_LOG = "Failed to create agent invite: {error}"
        REGISTRATION_FAILED_LOG = "Agent registration failed: {error}"
        APPROVAL_FAILED_LOG = "Failed to approve agent {agent_id}: {error}"
        ASSIGNMENT_FAILED_LOG = "Failed to assign agent: {error}"
        AGENT_REVOKED = "Agent {agent_id} privileges revoked by admin {admin_id}"
        REVOCATION_FAILED_LOG = "Failed to revoke agent privileges: {error}"
        AGENT_REJECTED = "Agent {agent_id} rejected by {rejector_id}"
        AGENT_REJECT_FAILED_LOG = "Failed to reject agent {agent_id}: {error}"
        AGENT_STATUS_UPDATE_FAILED = "Failed to update agent status {agent_id}: {error}"
        AGENT_INVITE_RESENT = "Agent invitation resent: {email} by {invited_by}"
        AGENT_INVITE_REVOKED = "Agent invitation revoked: {email} by {revoked_by}"
        NOTIFICATION_FAILED = "Notification ({context}) failed: {error}"
        USER_UPDATED_LOG = "User {user_id} updated by {admin_email}"
        USER_DELETED_LOG = "User {user_id} deactivated by {admin_email}"
        USER_DELETE_FAILED_LOG = "Failed to deactivate user: {error}"
        ROLE_ASSIGNED_LOG = "Role {role_name} assigned to user {user_id} by {admin_email}"
        ROLE_REMOVED_LOG = "Role {role_name} removed from user {user_id} by {admin_email}"
        ROLE_ASSIGN_FAILED_LOG = "Failed to assign role: {error}"
        ROLE_REMOVED_FAILED_LOG = "Failed to remove role from user: {error}"
        COGNITO_CREATE_USER_SKIPPED_MISSING_CONFIG = (
            "Cognito create user skipped (missing config) - user_id={user_id}. "
            "Set COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID to enable Cognito user creation."
        )
        COGNITO_USER_CREATED = "Cognito user created for agent approval - agent_id={agent_id} sub={cognito_sub}"
        COGNITO_CREATE_USER_CREDS_NOT_CONFIGURED = (
            "Cognito create user skipped (AWS credentials not configured) - user_id={user_id} email={email}. "
            "Agent approval will proceed but Cognito user not created."
        )
        COGNITO_CREATE_USER_FAILED = (
            "Cognito create user failed - user_id={user_id} email={email} error={error}. "
            "Agent approval will proceed but Cognito user not created."
        )
        COGNITO_REQUIRES_PASSWORD_SET_ATTR_FAILED = (
            "Could not set Cognito requires_password_set attribute for direct-created agent: {error}"
        )
        DIRECT_CREATE_AGENT_TEMP_PASSWORD_ISSUED = "Direct-create agent with temporary password issued."

    # Slow query logging (observability)
    class SlowQuery:
        """Slow SQL query log messages"""
        SLOW_QUERY = (
            "slow_query duration_ms={duration_ms:.2f} threshold_ms={threshold_ms} "
            "request_id={request_id} statement={statement}"
        )
        UNPRINTABLE_STATEMENT = "<unprintable>"

    # Database / SQLAlchemy initialization (engine, instrumentation)
    class Database:
        """Database initialization and instrumentation logs."""

        SLOW_QUERY_LOGGING_INSTALL_FAILED = (
            "Slow query logging install failed (non-fatal): {error}"
        )
        OTEL_INSTRUMENTATION_FAILED = (
            "OpenTelemetry SQLAlchemy instrumentation failed (non-fatal): {error}"
        )

    class Middleware:
        """Middleware-related logs (should not change request behavior)."""

        REQUEST_ID_OTEL_ATTRIBUTE_FAILED = (
            "Request-ID OTEL attribute set failed (non-fatal): {error}"
        )

    class Observability:
        """Observability initialization logs (must not break startup)."""

        SENTRY_INIT_SKIPPED = "Sentry init skipped (non-fatal): {error}"
        OTEL_TRACING_INIT_SKIPPED = "OpenTelemetry tracing init skipped (non-fatal): {error}"

    # Exception handlers (main.py)
    class AppException:
        HTTP_EXCEPTION = "HTTPException: {status_code} {detail} path={path}"
        VALIDATION_ERROR = "Validation error: {errors} path={path}"
        UNHANDLED_EXCEPTION = "Unhandled exception: {exc} path={path}"

    # Notification service (agent approved/rejected/invite)
    class Notification:
        AGENT_APPROVED = "Notification: agent approved — email={email} name={name} (wire to SES/email in production)"
        AGENT_REJECTED = "Notification: agent rejected — email={email} name={name} (wire to SES/email in production)"
        INVITE_SENT = "Notification: agent invite sent — to={to_email} link={link} by={by_email} (wire to SES/email in production)"
        DECLINE_REASON = "Decline reason: {decline_reason}"

    # Property route (lookup by hash, etc.)
    class Property:
        LOOKUP_HASH = "Looking up property with hash: {target_hash}"
        FOUND_N_PROPERTIES = "Found {count} properties in database"
        NO_PROPERTIES_FOR_HASH = "No properties found in database when searching for hash {target_hash}"
        FOUND_MATCHING = "Found matching property! UUID: {uuid}, hash: {prop_hash}"
        LOADED_PROPERTY = "Successfully loaded property {uuid} with relationships"
        PARSE_PROPERTY_ID_ERROR = "Could not parse property_id '{property_id}' as UUID or int: {error}"
        LOOKUP_ERROR = "Error in property lookup for hash {target_hash}: {error}"
        HASH_NOT_FOUND_AFTER_CHECK = "Property with hash {target_hash} not found after checking {checked} properties. Sample hashes: {sample_hashes}"
        IMPORT_PROPERTY_ERROR = "Error importing property {url}: {error}"
        IMPORTED_SKIPPED = "Imported {imported_count} properties, skipped {skipped_duplicates} duplicates"

    # API routes (edge/compat/deprecated paths)
    class ApiRoutes:
        """API route logs for deprecated or compat branches (avoid PII)."""

        AUTH_DEPRECATED_ADMIN_SIGNUP = (
            "Deprecated auth endpoint called: signup_admin"
        )
        AGENTS_ONBOARDING_COMPAT_MISSING_TOKEN = (
            "Agents onboarding compat missing token (query/body)."
        )
        AGENTS_ONBOARDING_COMPAT_VALIDATION_FAILED = (
            "Agents onboarding compat validation failed: {error_count} errors"
        )

    class DashboardSummaryScheduler:
        """Dashboard summary scheduler logs."""

        INVALID_SCHEDULE_TIME = (
            "Invalid DASHBOARD_SUMMARY_SCHEDULE_TIME={schedule_time}; fallback to 00:10"
        )
        REFRESH_SUCCESS = "dashboard_summary refreshed successfully rows={rows}"
        REFRESH_FAILED = "Failed to refresh dashboard_summary"
        SCHEDULER_SLEEP = (
            "dashboard_summary scheduler sleeping {wait_seconds:.0f}s until next run at {schedule_time}"
        )


def format_log_message(template: str, **kwargs) -> str:
    """Format a template with kwargs; on KeyError return template as-is. Returns: formatted string."""
    try:
        return template.format(**kwargs)
    except KeyError:
        # If a key is missing, return the template as-is
        return template

