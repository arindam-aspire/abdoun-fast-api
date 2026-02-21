"""
Centralized logging messages for the application.
All log messages should be defined here.
"""


class LogMessages:
    """Logging messages organized by category"""
    
    # Geocoding Log Messages
    class Geocoding:
        """Geocoding-related log messages"""
        RATE_LIMITING = "⏱️ Rate limiting: sleeping for {sleep_time:.2f}s"
        GEOCODING_REQUEST = "🌐 Geocoding request for: '{location}'"
        SUCCESSFULLY_GEOCODED = "✅ Successfully geocoded '{location}' to ({lon}, {lat})"
        NO_RESULTS_FOUND = "❌ No results found for location: '{location}'"
        ACCESS_FORBIDDEN = "🚫 Access forbidden (403) for '{location}'. Check User-Agent and rate limiting."
        GEOCODING_API_ERROR = "💥 Geocoding API error for '{location}': {status_code}"
        TIMEOUT_GEOCODING = "⏱️ Timeout while geocoding '{location}'"
        CONNECTION_ERROR = "🌐 Connection error while geocoding '{location}'"
        REQUEST_ERROR = "🌐 Request error while geocoding '{location}': {error}"
        DATA_PARSING_ERROR = "🔧 Data parsing error while geocoding '{location}': {error}"
        UNEXPECTED_ERROR = "💥 Unexpected error while geocoding '{location}': {error}"
        INVALID_COORDINATE_RANGE = "⚠️ Invalid coordinate range for '{location}': ({lon}, {lat})"
        INVALID_COORDINATES_RETURNED = "⚠️ Invalid coordinates returned for '{location}': lon={lon}, lat={lat}"
        FOUND_COORDINATES_CLEANED = "🎯 Found coordinates for '{location}' using cleaned name: '{cleaned_location}'"
        FOUND_COORDINATES_PART = "🎯 Found coordinates for '{location}' using part {part_num}: '{part}'"
        FOUND_COORDINATES_COMBINED = "🎯 Found coordinates for '{location}' using combined parts: '{combined}'"
        FOUND_COORDINATES_MAIN = "🎯 Found coordinates for '{location}' using main location: '{main_location}'"
        FOUND_COORDINATES_FALLBACK = "🎯 Found coordinates for '{location}' using fallback: '{suffix_location}'"
        TRYING_SIMPLIFIED_LOCATION = "🔄 Trying simplified location: '{simplified_location}'"
    
    # Azure OpenAI Log Messages
    class AzureOpenAI:
        """Azure OpenAI-related log messages"""
        TRYING_GEOCODING = "🤖 Trying Azure OpenAI geocoding for: '{location}'"
        TRYING_FALLBACK = "🤖 Trying Azure OpenAI as final fallback for: '{location}'"
        GEOCODED_SUCCESS = "✅ Azure OpenAI geocoded '{location}' to ({lat:.6f}, {lon:.6f})"
        COULD_NOT_GEOCODE = "❌ Azure OpenAI could not geocode '{location}'"
        LIBRARY_NOT_INSTALLED = "⚠️  OpenAI library not installed. Install with: pip install openai"
        FAILED_TO_PARSE_RESPONSE = "⚠️  Failed to parse Azure OpenAI response for '{location}': {error}"
        GEOCODING_ERROR = "⚠️  Azure OpenAI geocoding error for '{location}': {error}"
        NOT_CONFIGURED = "⚠️  Azure OpenAI not configured, skipping fallback for: '{location}'"
    
    # CSV Import Log Messages
    class CSVImport:
        """CSV import-related log messages"""
        GEOCODING_UNAVAILABLE = "⚠️  Warning: Geocoding service not available, skipping geocoding"
        UPDATED_PROPERTIES = "✅ Updated {count} existing properties (coordinates and/or location_name)."
        ERROR_UPDATING = "⚠️  Error updating properties: {error}"
        ALL_DUPLICATES = "ℹ️  All {count} properties were duplicates, nothing to import."
        UPDATED_AND_SKIPPED = "ℹ️  Updated {updated} properties, {skipped} were skipped (already had all data)."
        IMPORTED_UPDATED_SKIPPED = "✅ {summary}"
        BATCH_INSERT_FAILED = "⚠️  Batch insert failed due to duplicates, trying individual inserts..."
        IMPORTED_SKIPPED = "✅ Imported {imported} properties, skipped {skipped} duplicates."
    
    # Print Messages (for scripts)
    class Print:
        """Print messages for console output in scripts"""
        AZURE_OPENAI_GEOCODED = "    🤖 ✅ Azure OpenAI geocoded '{location}' to ({lat:.6f}, {lon:.6f})"
        AZURE_OPENAI_COULD_NOT_GEOCODE = "    🤖 ❌ Azure OpenAI could not geocode '{location}'"
        TRYING_AZURE_OPENAI_FALLBACK = "    🤖 Trying Azure OpenAI as final fallback for: '{location}'"


def format_log_message(template: str, **kwargs) -> str:
    """Helper function to format log messages with variables"""
    try:
        return template.format(**kwargs)
    except KeyError:
        # If a key is missing, return the template as-is
        return template

