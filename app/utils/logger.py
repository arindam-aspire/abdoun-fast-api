"""
Centralized logging system configuration.
All logging setup and utilities should be defined here.
"""

import logging
import sys
from typing import Callable, Tuple

# Ensure every LogRecord includes a request_id field (for correlation IDs).
from app.utils.request_context import get_request_id


_ORIGINAL_RECORD_FACTORY = logging.getLogRecordFactory()


def _record_factory(*args: object, **kwargs: object) -> logging.LogRecord:
    record = _ORIGINAL_RECORD_FACTORY(*args, **kwargs)
    rid = get_request_id()
    record.request_id = rid if rid else "-"
    return record


logging.setLogRecordFactory(_record_factory)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a given module name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def get_coordinate_update_logger() -> logging.Logger:
    """
    Get a specialized logger for coordinate update operations.
    
    Returns:
        Logger instance configured for coordinate updates
    """
    logger = logging.getLogger("coordinate_updates")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get_emoji_safe_text(text: str) -> str:
    """
    Get emoji-safe text for logging (handles encoding issues on Windows).
    
    Args:
        text: Text that may contain emojis
        
    Returns:
        Text safe for logging (may have emojis replaced on Windows)
    """
    if sys.platform == 'win32':
        try:
            # Try to encode/decode to check if it's safe
            text.encode('utf-8', errors='strict')
            return text
        except UnicodeEncodeError:
            # Replace problematic characters
            return text.encode('ascii', 'replace').decode('ascii')
    return text


def setup_windows_console_encoding():
    """
    Setup Windows console encoding for UTF-8 support.
    This should be called at the start of scripts that need emoji support.
    """
    if sys.platform == 'win32':
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def get_coord_logger() -> Tuple[logging.Logger, Callable[[str], str]]:
    """
    Get logger for coordinate updates with emoji-safe text function.
    
    Returns:
        Tuple of (logger, emoji_safe_function)
    """
    try:
        # Try to import custom logger if it exists
        from app.utils.logger import get_coordinate_update_logger, get_emoji_safe_text
        return get_coordinate_update_logger(), get_emoji_safe_text
    except ImportError:
        # Fallback to standard logger
        logger = logging.getLogger(__name__)
        return logger, lambda x: x


# Configure module-level loggers
api_logger = get_logger("app.api")
service_logger = get_logger("app.services")
db_logger = get_logger("app.db")

