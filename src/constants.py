"""
API constants and configuration for WhoopYY.

This module contains all static configuration values used throughout the SDK.
No magic numbers - all values are named constants with clear documentation.
"""

import os
from typing import Final

__all__ = [
    "API_BASE_URL",
    "AUTH_BASE_URL",
    "OAUTH_AUTHORIZE_URL",
    "OAUTH_TOKEN_URL",
    "ENDPOINTS",
    "SCOPES",
    "DEFAULT_RATE_LIMIT_REQUESTS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "MAX_DAILY_REQUESTS",
    "TOKEN_EXPIRY_SECONDS",
    "TOKEN_REFRESH_BUFFER_SECONDS",
    "DEFAULT_TOKEN_FILE",
    "TOKEN_FILE_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_RETRIES",
    "RETRY_BACKOFF_BASE_SECONDS",
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "RECOVERY_GREEN_THRESHOLD",
    "RECOVERY_YELLOW_THRESHOLD",
]

# =============================================================================
# Base URLs
# =============================================================================

API_BASE_URL: Final[str] = "https://api.prod.whoop.com"
"""Base URL for all Whoop API requests."""

AUTH_BASE_URL: Final[str] = "https://api.prod.whoop.com/oauth"
"""Base URL for OAuth authentication endpoints."""

# =============================================================================
# OAuth Endpoints
# =============================================================================

OAUTH_AUTHORIZE_URL: Final[str] = f"{AUTH_BASE_URL}/oauth2/auth"
"""URL for OAuth authorization redirect."""

OAUTH_TOKEN_URL: Final[str] = f"{AUTH_BASE_URL}/oauth2/token"
"""URL for OAuth token exchange and refresh."""

# =============================================================================
# API Endpoints
# =============================================================================

ENDPOINTS: Final[dict[str, str]] = {
    # User Profile
    "user_profile_basic": "/developer/v1/user/profile/basic",
    "user_body_measurement": "/developer/v1/user/measurement/body",

    # Recovery
    "recovery_collection": "/developer/v1/recovery",
    "recovery_for_cycle": "/developer/v1/cycle/{cycle_id}/recovery",

    # Sleep
    "sleep_single": "/developer/v1/activity/sleep/{sleep_id}",
    "sleep_collection": "/developer/v1/activity/sleep",

    # Cycle (Daily Strain)
    "cycle_single": "/developer/v1/cycle/{cycle_id}",
    "cycle_collection": "/developer/v1/cycle",

    # Workout
    "workout_single": "/developer/v1/activity/workout/{workout_id}",
    "workout_collection": "/developer/v1/activity/workout",
}
"""
API endpoint paths mapped by resource type.

Note: Endpoints with {id} placeholders require string formatting before use.
"""

# =============================================================================
# OAuth Scopes
# =============================================================================

SCOPES: Final[list[str]] = [
    "offline",                  # Refresh token access
    "read:profile",             # User profile data
    "read:body_measurement",    # Body measurements
    "read:recovery",            # Recovery data
    "read:sleep",               # Sleep data
    "read:cycles",              # Cycle/strain data
    "read:workout",             # Workout data
]
"""
Available OAuth scopes for Whoop API access.

- offline: Required for refresh token support
- read:profile: Access to basic user profile
- read:body_measurement: Access to body measurements (height, weight, etc.)
- read:recovery: Access to daily recovery scores and metrics
- read:sleep: Access to sleep data and stages
- read:cycles: Access to physiological cycle data (strain)
- read:workout: Access to workout data
"""

# =============================================================================
# Rate Limiting
# =============================================================================

DEFAULT_RATE_LIMIT_REQUESTS: Final[int] = 100
"""Default rate limit: requests per minute."""

RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
"""Rate limit window duration in seconds (1 minute)."""

MAX_DAILY_REQUESTS: Final[int] = 10_000
"""Maximum number of API requests allowed per day."""

# =============================================================================
# Token Configuration
# =============================================================================

TOKEN_EXPIRY_SECONDS: Final[int] = 3600
"""Default token expiry duration in seconds (1 hour)."""

TOKEN_REFRESH_BUFFER_SECONDS: Final[int] = 60
"""
Seconds before expiry to trigger proactive token refresh.

This buffer ensures tokens are refreshed before they actually expire,
preventing failed requests due to race conditions.
"""

DEFAULT_TOKEN_FILE: Final[str] = os.path.join(os.path.expanduser("~"), ".whoop_tokens.json")
"""Default filename for storing OAuth tokens locally (absolute path in user home)."""

TOKEN_FILE_PATH: Final[str] = DEFAULT_TOKEN_FILE
"""Absolute path to the OAuth token file in the user's home directory."""

# =============================================================================
# HTTP Configuration
# =============================================================================

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
"""Default HTTP request timeout in seconds."""

MAX_RETRIES: Final[int] = 3
"""Maximum number of retry attempts for retryable errors."""

RETRY_BACKOFF_BASE_SECONDS: Final[float] = 1.0
"""Base duration for exponential backoff between retries."""

# =============================================================================
# Pagination
# =============================================================================

DEFAULT_PAGE_LIMIT: Final[int] = 25
"""Default number of records per page for collection requests."""

MAX_PAGE_LIMIT: Final[int] = 25
"""Maximum allowed records per page (API constraint)."""

# =============================================================================
# Recovery Score Thresholds (Whoop's color zones)
# =============================================================================

RECOVERY_GREEN_THRESHOLD: Final[int] = 67
"""Recovery score >= 67 is green (optimal recovery)."""

RECOVERY_YELLOW_THRESHOLD: Final[int] = 34
"""Recovery score >= 34 and < 67 is yellow (moderate recovery)."""

# Scores < 34 are red (poor recovery)
