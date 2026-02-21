"""
Centralized constants and text messages for the application.
All hardcoded text messages should be defined here.
"""

# API Error Messages
class ErrorMessages:
    """Error messages returned to API clients"""
    PROPERTY_NOT_FOUND = "Property not found"
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
class Defaults:
    """Default values used throughout the application"""
    UNTITLED_PROPERTY = "Untitled"
    DEFAULT_LIMIT = 50
    DEFAULT_OFFSET = 0
    MAX_SEARCH_LIMIT = 200


# Geocoding Constants
class GeocodingConstants:
    """Constants related to geocoding"""
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "MyPlans/1.0 (https://myplans.com; contact@myplans.com)"
    RATE_LIMIT_DELAY = 1.1  # Slightly more than 1 second to be safe
    TIMEOUT_CONNECT = 10
    TIMEOUT_READ = 30
    EXTRA_DELAY_AFTER_403 = 2  # seconds


# CSV Import Messages
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

