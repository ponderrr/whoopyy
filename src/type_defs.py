"""
Type definitions for WhoopYY SDK.

This module defines TypedDict structures for internal data contracts.
These are primarily used for:
- Token data storage/retrieval
- Raw API response typing before Pydantic validation
- Internal data transfer objects

For public API models, use Pydantic models in the models module instead.

Example:
    >>> from whoopyy.types import TokenData
    >>> tokens: TokenData = {
    ...     "access_token": "abc123",
    ...     "refresh_token": "xyz789",
    ...     "expires_in": 3600,
    ...     "expires_at": 1704067200.0,
    ...     "token_type": "Bearer",
    ...     "scope": "offline read:profile"
    ... }
"""

from typing import TypedDict, Optional, List, Dict, Any


class TokenData(TypedDict):
    """
    OAuth token data structure for storage and retrieval.
    
    This structure matches the OAuth 2.0 token response format
    with an additional computed `expires_at` field.
    
    Attributes:
        access_token: The access token for API requests.
        refresh_token: Token for refreshing access (may be None).
        expires_in: Seconds until token expiry (from OAuth response).
        expires_at: Unix timestamp when token expires (computed).
        token_type: Token type, typically "Bearer".
        scope: Space-separated list of granted scopes.
    """
    
    access_token: str
    refresh_token: Optional[str]
    expires_in: int
    expires_at: float
    token_type: str
    scope: str


class PaginationParams(TypedDict, total=False):
    """
    Pagination parameters for collection requests.
    
    All fields are optional - the API uses defaults if not specified.
    
    Attributes:
        start: Start datetime for filtering (ISO 8601 string).
        end: End datetime for filtering (ISO 8601 string).
        limit: Maximum records to return (1-50).
        nextToken: Pagination token for next page.
    """
    
    start: str
    end: str
    limit: int
    nextToken: str


class PaginatedResponse(TypedDict):
    """
    Standard paginated response structure from Whoop API.
    
    Attributes:
        records: List of data records.
        next_token: Token for fetching next page (None if last page).
    """
    
    records: List[Dict[str, Any]]
    next_token: Optional[str]


class UserProfileBasicResponse(TypedDict):
    """
    Raw API response for basic user profile.
    
    Attributes:
        user_id: Unique user identifier.
        email: User's email address.
        first_name: User's first name.
        last_name: User's last name.
    """
    
    user_id: int
    email: str
    first_name: str
    last_name: str


class BodyMeasurementResponse(TypedDict, total=False):
    """
    Raw API response for body measurements.
    
    All fields except user_id are optional as they may not be set.
    
    Attributes:
        height_meter: Height in meters.
        weight_kilogram: Weight in kilograms.
        max_heart_rate: Maximum heart rate in bpm.
    """
    
    height_meter: float
    weight_kilogram: float
    max_heart_rate: int


class RecoveryScoreResponse(TypedDict, total=False):
    """
    Raw API response for recovery score data.
    
    Attributes:
        user_calibrating: Whether user is in calibration period.
        recovery_score: Recovery score (0-100).
        resting_heart_rate: Resting HR in bpm.
        hrv_rmssd_milli: HRV RMSSD in milliseconds.
        spo2_percentage: Blood oxygen percentage.
        skin_temp_celsius: Skin temperature in Celsius.
    """
    
    user_calibrating: bool
    recovery_score: float
    resting_heart_rate: float
    hrv_rmssd_milli: float
    spo2_percentage: float
    skin_temp_celsius: float


class SleepStageResponse(TypedDict):
    """
    Raw API response for sleep stage durations.
    
    All durations are in milliseconds.
    
    Attributes:
        total_in_bed_time_milli: Total time in bed.
        total_awake_time_milli: Time spent awake.
        total_no_data_time_milli: Time with no data.
        total_light_sleep_time_milli: Light sleep duration.
        total_slow_wave_sleep_time_milli: Deep sleep duration.
        total_rem_sleep_time_milli: REM sleep duration.
        sleep_cycle_count: Number of sleep cycles.
        disturbance_count: Number of disturbances.
    """
    
    total_in_bed_time_milli: int
    total_awake_time_milli: int
    total_no_data_time_milli: int
    total_light_sleep_time_milli: int
    total_slow_wave_sleep_time_milli: int
    total_rem_sleep_time_milli: int
    sleep_cycle_count: int
    disturbance_count: int


class SleepScoreResponse(TypedDict, total=False):
    """
    Raw API response for sleep score data.
    
    Attributes:
        stage_summary: Sleep stage breakdown.
        sleep_needed: Sleep needed data.
        respiratory_rate: Breathing rate.
        sleep_performance_percentage: Sleep performance score.
        sleep_consistency_percentage: Sleep consistency score.
        sleep_efficiency_percentage: Sleep efficiency score.
    """
    
    stage_summary: SleepStageResponse
    sleep_needed: Dict[str, Any]
    respiratory_rate: float
    sleep_performance_percentage: float
    sleep_consistency_percentage: float
    sleep_efficiency_percentage: float


class CycleScoreResponse(TypedDict, total=False):
    """
    Raw API response for cycle (strain) score data.
    
    Attributes:
        strain: Daily strain score (0-21).
        kilojoule: Energy expenditure in kilojoules.
        average_heart_rate: Average HR during cycle.
        max_heart_rate: Maximum HR during cycle.
    """
    
    strain: float
    kilojoule: float
    average_heart_rate: int
    max_heart_rate: int


class WorkoutScoreResponse(TypedDict, total=False):
    """
    Raw API response for workout score data.
    
    Attributes:
        strain: Workout strain (0-21).
        average_heart_rate: Average HR during workout.
        max_heart_rate: Max HR during workout.
        kilojoule: Energy expenditure.
        percent_recorded: Percentage of workout recorded.
        distance_meter: Distance in meters (if applicable).
        altitude_gain_meter: Elevation gain (if applicable).
        altitude_change_meter: Net elevation change (if applicable).
        zone_duration: Time in each HR zone.
    """
    
    strain: float
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: float
    percent_recorded: float
    distance_meter: float
    altitude_gain_meter: float
    altitude_change_meter: float
    zone_duration: Dict[str, int]
