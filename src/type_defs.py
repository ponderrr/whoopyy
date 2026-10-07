"""
Type definitions for the strapkit SDK.

This module defines TypedDict structures for internal data contracts.
These are primarily used for:
- Token data storage/retrieval
- Raw API response typing before Pydantic validation
- Internal data transfer objects

The raw response types mirror the WHOOP v2 API component schemas. Keys
the API always returns are required; keys it may omit are optional.
Timestamps are ISO 8601 strings, as they arrive on the wire.

For public API models, use Pydantic models in the models module instead.

Example:
    >>> from strapkit.type_defs import TokenData
    >>> tokens: TokenData = {
    ...     "access_token": "abc123",
    ...     "refresh_token": "xyz789",
    ...     "expires_in": 3600,
    ...     "expires_at": 1704067200.0,
    ...     "token_type": "Bearer",
    ...     "scope": "offline read:profile"
    ... }
"""

from typing import TypedDict, Optional, Any, Literal

__all__ = [
    "TokenData",
    "PaginationParams",
    "PaginatedResponse",
    "UserProfileBasicResponse",
    "BodyMeasurementResponse",
    "RecoveryScoreResponse",
    "RecoveryResponse",
    "SleepStageResponse",
    "SleepNeededResponse",
    "SleepScoreResponse",
    "SleepResponse",
    "CycleScoreResponse",
    "CycleResponse",
    "ZoneDurationsResponse",
    "WorkoutScoreResponse",
    "WorkoutResponse",
    "ActivityIdMappingResponse",
]


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
        start: Start datetime for filtering (ISO 8601 date-time string).
        end: End datetime for filtering (ISO 8601 date-time string).
        limit: Maximum records to return (1-25).
        nextToken: Pagination token for next page.
    """
    
    start: str
    end: str
    limit: int
    nextToken: str


class _PaginatedResponseRequired(TypedDict):
    """Required keys of PaginatedResponse."""

    records: list[dict[str, Any]]


class PaginatedResponse(_PaginatedResponseRequired, total=False):
    """
    Standard paginated response structure from Whoop API.

    Attributes:
        records: List of data records.
        next_token: Token for fetching the next page (absent or null on
            the last page).
    """

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


class BodyMeasurementResponse(TypedDict):
    """
    Raw API response for body measurements.
    
    Attributes:
        height_meter: Height in meters.
        weight_kilogram: Weight in kilograms.
        max_heart_rate: Maximum heart rate in bpm.
    """
    
    height_meter: float
    weight_kilogram: float
    max_heart_rate: int


class _RecoveryScoreResponseRequired(TypedDict):
    """Required keys of RecoveryScoreResponse."""

    user_calibrating: bool
    recovery_score: float
    resting_heart_rate: float
    hrv_rmssd_milli: float


class RecoveryScoreResponse(_RecoveryScoreResponseRequired, total=False):
    """
    Raw API response for recovery score data.
    
    Attributes:
        user_calibrating: Whether user is in calibration period.
        recovery_score: Recovery score (0-100).
        resting_heart_rate: Resting HR in bpm.
        hrv_rmssd_milli: HRV RMSSD in milliseconds.
        spo2_percentage: Blood oxygen percentage (WHOOP 4.0+ only).
        skin_temp_celsius: Skin temperature in Celsius (WHOOP 4.0+ only).
    """
    
    spo2_percentage: float
    skin_temp_celsius: float


class _RecoveryResponseRequired(TypedDict):
    """Required keys of RecoveryResponse."""

    cycle_id: int
    sleep_id: str
    user_id: int
    created_at: str
    updated_at: str
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]


class RecoveryResponse(_RecoveryResponseRequired, total=False):
    """
    Raw API response for a recovery record.

    Attributes:
        cycle_id: Associated cycle ID.
        sleep_id: Associated sleep ID (UUID string).
        user_id: User's unique identifier.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
        score_state: SCORED, PENDING_SCORE, or UNSCORABLE.
        score: Recovery score data (only present when SCORED).
    """

    score: RecoveryScoreResponse


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


class SleepNeededResponse(TypedDict):
    """
    Raw API response for sleep need breakdown.

    All durations are in milliseconds.

    Attributes:
        baseline_milli: Baseline sleep need.
        need_from_sleep_debt_milli: Additional need from sleep debt.
        need_from_recent_strain_milli: Additional need from recent strain.
        need_from_recent_nap_milli: Reduction from recent naps (zero or negative).
    """

    baseline_milli: int
    need_from_sleep_debt_milli: int
    need_from_recent_strain_milli: int
    need_from_recent_nap_milli: int


class _SleepScoreResponseRequired(TypedDict):
    """Required keys of SleepScoreResponse."""

    stage_summary: SleepStageResponse
    sleep_needed: SleepNeededResponse


class SleepScoreResponse(_SleepScoreResponseRequired, total=False):
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
    
    respiratory_rate: float
    sleep_performance_percentage: float
    sleep_consistency_percentage: float
    sleep_efficiency_percentage: float


class _SleepResponseRequired(TypedDict):
    """Required keys of SleepResponse."""

    id: str
    cycle_id: int
    user_id: int
    created_at: str
    updated_at: str
    start: str
    end: str
    timezone_offset: str
    nap: bool
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]


class SleepResponse(_SleepResponseRequired, total=False):
    """
    Raw API response for a sleep record.

    Attributes:
        id: Unique sleep ID (UUID string).
        cycle_id: ID of the cycle this sleep belongs to.
        v1_id: Deprecated legacy v1 ID (WHOOP: will not exist past 09/01/2025).
        user_id: User's unique identifier.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
        start: Sleep start time.
        end: Sleep end time.
        timezone_offset: Timezone offset ('+hh:mm', '-hh:mm', or 'Z').
        nap: True if nap, False if main sleep.
        score_state: SCORED, PENDING_SCORE, or UNSCORABLE.
        score: Sleep score data (only present when SCORED).
    """

    v1_id: int
    score: SleepScoreResponse


class CycleScoreResponse(TypedDict):
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


class _CycleResponseRequired(TypedDict):
    """Required keys of CycleResponse."""

    id: int
    user_id: int
    created_at: str
    updated_at: str
    start: str
    timezone_offset: str
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]


class CycleResponse(_CycleResponseRequired, total=False):
    """
    Raw API response for a physiological cycle record.

    Attributes:
        id: Unique cycle ID.
        user_id: User's unique identifier.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
        start: Cycle start time.
        end: Cycle end time (absent for the current cycle).
        timezone_offset: Timezone offset ('+hh:mm', '-hh:mm', or 'Z').
        score_state: SCORED, PENDING_SCORE, or UNSCORABLE.
        score: Cycle score data (only present when SCORED).
        step_count: Total steps in the cycle (None if no step data).
    """

    end: str
    score: CycleScoreResponse
    step_count: Optional[int]


class ZoneDurationsResponse(TypedDict):
    """
    Raw API response for heart rate zone durations.

    All durations are in milliseconds.

    Attributes:
        zone_zero_milli: Time in zone 0 (very light activity).
        zone_one_milli: Time in zone 1 (light activity).
        zone_two_milli: Time in zone 2 (moderate activity).
        zone_three_milli: Time in zone 3 (hard activity).
        zone_four_milli: Time in zone 4 (very hard activity).
        zone_five_milli: Time in zone 5 (maximum effort).
    """

    zone_zero_milli: int
    zone_one_milli: int
    zone_two_milli: int
    zone_three_milli: int
    zone_four_milli: int
    zone_five_milli: int


class _WorkoutScoreResponseRequired(TypedDict):
    """Required keys of WorkoutScoreResponse."""

    strain: float
    average_heart_rate: int
    max_heart_rate: int
    kilojoule: float
    percent_recorded: float
    zone_durations: ZoneDurationsResponse


class WorkoutScoreResponse(_WorkoutScoreResponseRequired, total=False):
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
        zone_durations: Time in each HR zone.
    """
    
    distance_meter: float
    altitude_gain_meter: float
    altitude_change_meter: float


class _WorkoutResponseRequired(TypedDict):
    """Required keys of WorkoutResponse."""

    id: str
    user_id: int
    created_at: str
    updated_at: str
    start: str
    end: str
    timezone_offset: str
    sport_name: str
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]


class WorkoutResponse(_WorkoutResponseRequired, total=False):
    """
    Raw API response for a workout record (v2 WorkoutV2 schema).

    Attributes:
        id: Unique workout ID (UUID string).
        v1_id: Deprecated legacy v1 ID (WHOOP: will not exist past 09/01/2025).
        user_id: User's unique identifier.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
        start: Workout start time.
        end: Workout end time.
        timezone_offset: Timezone offset ('+hh:mm', '-hh:mm', or 'Z').
        sport_name: Name of the WHOOP sport performed (e.g. "running").
        sport_id: Deprecated sport ID (WHOOP: will not exist past 09/01/2025).
        score_state: SCORED, PENDING_SCORE, or UNSCORABLE.
        score: Workout score data (only present when SCORED).
    """

    v1_id: int
    sport_id: int
    score: WorkoutScoreResponse


class ActivityIdMappingResponse(TypedDict):
    """
    Raw API response for a v1-to-v2 activity ID mapping.

    Attributes:
        v2_activity_id: The activity's v2 identifier (UUID string).
    """

    v2_activity_id: str
