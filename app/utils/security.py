"""
Security utilities for input validation and ReDoS prevention.
"""

# Maximum input lengths to prevent ReDoS attacks
MAX_INPUT_LENGTH = 1000  # General input limit
MAX_CURRENCY_INPUT_LENGTH = 100  # Currency/price input limit
MAX_AREA_INPUT_LENGTH = 50  # Area input limit
MAX_LOCATION_INPUT_LENGTH = 500  # Location input limit


def validate_input_length(value: str, max_length: int) -> str:
    """
    Validate and truncate input to prevent ReDoS attacks.
    
    Args:
        value: Input string to validate
        max_length: Maximum allowed length
        
    Returns:
        Truncated string if needed
        
    Raises:
        ValueError: If input is None or invalid
    """
    if value is None:
        raise ValueError("Input cannot be None")
    
    text = str(value).strip()
    if len(text) > max_length:
        return text[:max_length]
    return text
