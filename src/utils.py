"""
Utility functions for WhoopYY SDK.

This module provides helper functions for:
- Token storage and retrieval
- Token expiry checking
- Datetime formatting/parsing for API compatibility

Example:
    >>> from whoopyy.utils import save_tokens, load_tokens, is_token_expired
    >>> save_tokens(token_data, ".whoop_tokens.json")
    >>> tokens = load_tokens(".whoop_tokens.json")
    >>> if is_token_expired(tokens):
    ...     # Refresh token
    ...     pass
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .constants import DEFAULT_TOKEN_FILE, TOKEN_REFRESH_BUFFER_SECONDS
from .logger import get_logger
from .type_defs import TokenData

logger = get_logger(__name__)


def save_tokens(
    tokens: TokenData,
    filepath: str = DEFAULT_TOKEN_FILE
) -> None:
    """
    Save OAuth tokens to a JSON file.
    
    Tokens are stored in plaintext JSON. For production use, consider
    using the keyring module for secure storage.
    
    Args:
        tokens: Token data dictionary to save.
        filepath: Path to save tokens to. Defaults to .whoop_tokens.json.
    
    Raises:
        OSError: If file cannot be written.
        TypeError: If tokens contain non-serializable data.
    
    Example:
        >>> tokens: TokenData = {
        ...     "access_token": "abc123",
        ...     "refresh_token": "xyz789",
        ...     "expires_in": 3600,
        ...     "expires_at": time.time() + 3600,
        ...     "token_type": "Bearer",
        ...     "scope": "offline read:profile"
        ... }
        >>> save_tokens(tokens)
        >>> # Tokens saved to .whoop_tokens.json
    """
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2)
        
        logger.info(
            "Tokens saved successfully",
            extra={"filepath": filepath}
        )
    except (OSError, TypeError) as e:
        logger.error(
            "Failed to save tokens",
            extra={"filepath": filepath, "error": str(e)}
        )
        raise


def load_tokens(
    filepath: str = DEFAULT_TOKEN_FILE
) -> Optional[TokenData]:
    """
    Load OAuth tokens from a JSON file.
    
    Args:
        filepath: Path to load tokens from. Defaults to .whoop_tokens.json.
    
    Returns:
        Token data dictionary if file exists and is valid, None otherwise.
    
    Example:
        >>> tokens = load_tokens()
        >>> if tokens:
        ...     print(f"Loaded token expiring at {tokens['expires_at']}")
        ... else:
        ...     print("No saved tokens found")
    """
    path = Path(filepath)
    
    if not path.exists():
        logger.debug(
            "No token file found",
            extra={"filepath": filepath}
        )
        return None
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tokens: TokenData = json.load(f)
        
        logger.info(
            "Tokens loaded successfully",
            extra={"filepath": filepath}
        )
        return tokens
    
    except (OSError, json.JSONDecodeError) as e:
        logger.error(
            "Failed to load tokens",
            extra={"filepath": filepath, "error": str(e)}
        )
        return None


def delete_tokens(filepath: str = DEFAULT_TOKEN_FILE) -> bool:
    """
    Delete saved tokens file.
    
    Useful for logout/cleanup operations.
    
    Args:
        filepath: Path to token file. Defaults to .whoop_tokens.json.
    
    Returns:
        True if file was deleted, False if it didn't exist.
    
    Example:
        >>> delete_tokens()
        True
    """
    path = Path(filepath)
    
    if not path.exists():
        logger.debug(
            "No token file to delete",
            extra={"filepath": filepath}
        )
        return False
    
    try:
        path.unlink()
        logger.info(
            "Tokens deleted",
            extra={"filepath": filepath}
        )
        return True
    
    except OSError as e:
        logger.error(
            "Failed to delete tokens",
            extra={"filepath": filepath, "error": str(e)}
        )
        return False


def is_token_expired(
    tokens: TokenData,
    buffer_seconds: int = TOKEN_REFRESH_BUFFER_SECONDS
) -> bool:
    """
    Check if access token is expired or about to expire.
    
    Uses a buffer to proactively refresh tokens before actual expiry,
    preventing failed requests due to race conditions.
    
    Args:
        tokens: Token data to check.
        buffer_seconds: Seconds before expiry to consider expired.
                       Defaults to TOKEN_REFRESH_BUFFER_SECONDS (60s).
    
    Returns:
        True if token is expired or will expire within buffer period.
    
    Example:
        >>> tokens = load_tokens()
        >>> if is_token_expired(tokens):
        ...     # Token expired or expiring soon - refresh it
        ...     tokens = refresh_token(tokens)
        >>> else:
        ...     # Token is still valid
        ...     pass
    """
    expires_at = tokens.get("expires_at", 0)
    current_time = time.time()
    
    # Token is "expired" if current time + buffer >= expiry time
    is_expired = current_time >= (expires_at - buffer_seconds)
    
    if is_expired:
        logger.debug(
            "Token expired or expiring soon",
            extra={
                "expires_at": expires_at,
                "current_time": current_time,
                "buffer_seconds": buffer_seconds
            }
        )
    
    return is_expired


def calculate_expiry(expires_in: int) -> float:
    """
    Calculate token expiry timestamp from expires_in value.
    
    Args:
        expires_in: Seconds until token expires (from OAuth response).
    
    Returns:
        Unix timestamp when token will expire.
    
    Example:
        >>> expires_at = calculate_expiry(3600)  # 1 hour
        >>> print(f"Token expires at {datetime.fromtimestamp(expires_at)}")
    """
    return time.time() + expires_in


def format_datetime(dt: datetime) -> str:
    """
    Format datetime for Whoop API requests.
    
    Converts datetime to ISO 8601 format. If datetime is naive (no timezone),
    assumes UTC.
    
    Args:
        dt: Datetime to format.
    
    Returns:
        ISO 8601 formatted string (e.g., "2024-01-15T10:30:00+00:00").
    
    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15, 10, 30, 0)
        >>> format_datetime(dt)
        '2024-01-15T10:30:00+00:00'
    """
    # If naive datetime, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.isoformat()


def parse_datetime(dt_str: str) -> datetime:
    """
    Parse datetime from Whoop API response.
    
    Handles ISO 8601 format with various timezone representations.
    
    Args:
        dt_str: ISO 8601 datetime string from API.
    
    Returns:
        Parsed datetime object with timezone info.
    
    Raises:
        ValueError: If string cannot be parsed.
    
    Example:
        >>> dt = parse_datetime("2024-01-15T10:30:00.000Z")
        >>> print(dt.year, dt.month, dt.day)
        2024 1 15
    """
    # Handle 'Z' suffix (Zulu time = UTC)
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    
    return datetime.fromisoformat(dt_str)


def milliseconds_to_hours(milliseconds: int) -> float:
    """
    Convert milliseconds to hours.
    
    Useful for converting sleep/activity durations from API responses.
    
    Args:
        milliseconds: Duration in milliseconds.
    
    Returns:
        Duration in hours (rounded to 2 decimal places).
    
    Example:
        >>> milliseconds_to_hours(28800000)  # 8 hours
        8.0
        >>> milliseconds_to_hours(27000000)  # 7.5 hours
        7.5
    """
    hours = milliseconds / (1000 * 60 * 60)
    return round(hours, 2)


def milliseconds_to_minutes(milliseconds: int) -> float:
    """
    Convert milliseconds to minutes.
    
    Args:
        milliseconds: Duration in milliseconds.
    
    Returns:
        Duration in minutes (rounded to 1 decimal place).
    
    Example:
        >>> milliseconds_to_minutes(3600000)  # 60 minutes
        60.0
    """
    minutes = milliseconds / (1000 * 60)
    return round(minutes, 1)
