"""
Pydantic models for Whoop API data structures.

This module defines type-safe, validated models for all Whoop API responses.
All models use Pydantic v2 with Field validators for data integrity.

Model Hierarchy:
    User Profile:
        - UserProfileBasic: Basic user info (id, email, name)
        - BodyMeasurement: Physical measurements
    
    Recovery:
        - RecoveryScore: Recovery metrics (HRV, RHR, etc.)
        - Recovery: Complete recovery record
        - RecoveryCollection: Paginated recovery list
    
    Sleep:
        - SleepStage: Individual sleep stage
        - SleepScore: Sleep quality metrics
        - Sleep: Complete sleep record
        - SleepCollection: Paginated sleep list
    
    Cycle (Daily Strain):
        - CycleScore: Daily strain metrics
        - Cycle: Complete cycle record
        - CycleCollection: Paginated cycle list
    
    Workout:
        - WorkoutZoneDuration: HR zone breakdown
        - WorkoutScore: Workout metrics
        - Workout: Complete workout record
        - WorkoutCollection: Paginated workout list

Example:
    >>> from whoopyy.models import Recovery, RecoveryScore
    >>> score = RecoveryScore(
    ...     user_calibrating=False,
    ...     recovery_score=75.5,
    ...     resting_heart_rate=52,
    ...     hrv_rmssd_milli=65.2
    ... )
    >>> print(f"Recovery: {score.recovery_score}%")
    Recovery: 75.5%
"""

from datetime import datetime
from typing import Optional, Dict, List, Literal, Iterator

from pydantic import BaseModel, Field, ConfigDict

__all__ = [
    "UserProfileBasic",
    "BodyMeasurement",
    "RecoveryScore",
    "Recovery",
    "RecoveryCollection",
    "SleepStage",
    "StageSummary",
    "SleepNeeded",
    "SleepScore",
    "Sleep",
    "SleepCollection",
    "CycleScore",
    "Cycle",
    "CycleCollection",
    "WorkoutZoneDuration",
    "WorkoutScore",
    "SPORT_NAMES",
    "Workout",
    "WorkoutCollection",
    "format_duration",
    "get_sport_name",
]

# =============================================================================
# User Profile Models
# =============================================================================

class UserProfileBasic(BaseModel):
    """
    Basic user profile information from Whoop API.
    
    Contains core identifying information for the authenticated user.
    
    Attributes:
        user_id: Unique Whoop user identifier.
        email: User's registered email address.
        first_name: User's first name.
        last_name: User's last name.
    
    Example:
        >>> profile = UserProfileBasic(
        ...     user_id=12345,
        ...     email="user@example.com",
        ...     first_name="John",
        ...     last_name="Doe"
        ... )
        >>> print(f"Hello, {profile.first_name}!")
        Hello, John!
    """
    
    model_config = ConfigDict(frozen=True)
    
    user_id: int = Field(..., description="Unique Whoop user identifier")
    email: str = Field(..., description="User's registered email address")
    first_name: str = Field(..., description="User's first name")
    last_name: str = Field(..., description="User's last name")
    
    @property
    def full_name(self) -> str:
        """Get user's full name."""
        return f"{self.first_name} {self.last_name}"


class BodyMeasurement(BaseModel):
    """
    Body measurement data from Whoop API.
    
    Contains physical measurements used for calorie calculations.
    All fields are optional as users may not have set all values.
    
    Attributes:
        height_meter: Height in meters.
        weight_kilogram: Weight in kilograms.
        max_heart_rate: Maximum heart rate in bpm.
    
    Example:
        >>> body = BodyMeasurement(
        ...     height_meter=1.83,
        ...     weight_kilogram=82.5,
        ...     max_heart_rate=195
        ... )
        >>> print(f"Height: {body.height_meter}m")
        Height: 1.83m
    """
    
    model_config = ConfigDict(frozen=True)
    
    height_meter: Optional[float] = Field(
        None, 
        gt=0,
        description="Height in meters"
    )
    weight_kilogram: Optional[float] = Field(
        None, 
        gt=0,
        description="Weight in kilograms"
    )
    max_heart_rate: Optional[int] = Field(
        None, 
        gt=0,
        description="Maximum heart rate in bpm"
    )
    
    @property
    def height_feet(self) -> Optional[float]:
        """Convert height to feet."""
        if self.height_meter is None:
            return None
        return round(self.height_meter * 3.28084, 2)
    
    @property
    def weight_pounds(self) -> Optional[float]:
        """Convert weight to pounds."""
        if self.weight_kilogram is None:
            return None
        return round(self.weight_kilogram * 2.20462, 1)


# =============================================================================
# Recovery Models
# =============================================================================

class RecoveryScore(BaseModel):
    """
    Recovery score metrics from Whoop API.
    
    Contains the key physiological metrics that contribute to recovery score.
    
    Attributes:
        user_calibrating: Whether user is in initial calibration period.
        recovery_score: Overall recovery percentage (0-100).
        resting_heart_rate: Resting heart rate in bpm.
        hrv_rmssd_milli: Heart rate variability (RMSSD) in milliseconds.
        spo2_percentage: Blood oxygen saturation percentage (0-100).
        skin_temp_celsius: Skin temperature in Celsius.
    
    Example:
        >>> score = RecoveryScore(
        ...     user_calibrating=False,
        ...     recovery_score=75.5,
        ...     resting_heart_rate=52,
        ...     hrv_rmssd_milli=65.2,
        ...     spo2_percentage=98.5
        ... )
        >>> print(f"HRV: {score.hrv_rmssd_milli}ms")
        HRV: 65.2ms
    """
    
    model_config = ConfigDict(frozen=True)
    
    user_calibrating: bool = Field(
        ..., 
        description="Whether user is in calibration period"
    )
    recovery_score: float = Field(
        ..., 
        ge=0, 
        le=100, 
        description="Recovery score 0-100"
    )
    resting_heart_rate: float = Field(
        ...,
        gt=0,
        description="Resting heart rate in bpm"
    )
    hrv_rmssd_milli: float = Field(
        ...,
        ge=0,
        description="HRV RMSSD in milliseconds"
    )
    spo2_percentage: Optional[float] = Field(
        None, 
        ge=0, 
        le=100, 
        description="SpO2 percentage"
    )
    skin_temp_celsius: Optional[float] = Field(
        None, 
        description="Skin temperature in Celsius"
    )
    
    @property
    def recovery_zone(self) -> str:
        """
        Get recovery zone color based on score.
        
        - Green (67-100): Optimal recovery, ready for high strain
        - Yellow (34-66): Moderate recovery, train with caution
        - Red (0-33): Poor recovery, prioritize rest
        
        Returns:
            Zone color string: "green", "yellow", or "red"
        """
        if self.recovery_score >= 67:
            return "green"
        elif self.recovery_score >= 34:
            return "yellow"
        else:
            return "red"


class Recovery(BaseModel):
    """
    Complete recovery record from Whoop API.
    
    Represents a single recovery measurement, typically taken each morning.
    
    Attributes:
        cycle_id: Associated physiological cycle ID.
        sleep_id: Associated sleep record ID.
        user_id: User's unique identifier.
        created_at: When the record was created.
        updated_at: When the record was last updated.
        score_state: Scoring state (SCORED, PENDING_SCORE, UNSCORABLE).
        score: Recovery score data (None if not yet scored).
    
    Example:
        >>> recovery = Recovery(
        ...     cycle_id=123,
        ...     sleep_id=456,
        ...     user_id=789,
        ...     created_at=datetime.now(),
        ...     updated_at=datetime.now(),
        ...     score_state="SCORED",
        ...     score=RecoveryScore(...)
        ... )
        >>> if recovery.score:
        ...     print(f"Recovery: {recovery.score.recovery_score}%")
    """
    
    model_config = ConfigDict(frozen=True)
    
    cycle_id: int = Field(..., description="Associated cycle ID")
    sleep_id: str = Field(..., description="Associated sleep ID (UUID)")
    user_id: int = Field(..., description="User's unique identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"] = Field(
        ...,
        description="Scoring state: SCORED, PENDING_SCORE, UNSCORABLE"
    )
    score: Optional[RecoveryScore] = Field(
        None, 
        description="Recovery score data (None if pending)"
    )
    
    @property
    def is_scored(self) -> bool:
        """Check if recovery has been scored."""
        return self.score_state == "SCORED" and self.score is not None


class RecoveryCollection(BaseModel):
    """
    Paginated collection of recovery records.
    
    Attributes:
        records: List of Recovery records.
        next_token: Token for fetching next page (None if last page).
    
    Example:
        >>> collection = client.get_recovery_collection(limit=10)
        >>> for recovery in collection.records:
        ...     if recovery.score:
        ...         print(recovery.score.recovery_score)
        >>> if collection.next_token:
        ...     next_page = client.get_recovery_collection(
        ...         next_token=collection.next_token
        ...     )
    """
    
    records: List[Recovery] = Field(
        default_factory=list, 
        description="List of recovery records"
    )
    next_token: Optional[str] = Field(
        None, 
        description="Pagination token for next page"
    )
    
    def __len__(self) -> int:
        """Return number of records in collection."""
        return len(self.records)

    def __iter__(self) -> Iterator[Recovery]:
        """Iterate over records."""
        return iter(self.records)


# =============================================================================
# Sleep Models
# =============================================================================

class SleepStage(BaseModel):
    """
    Individual sleep stage data.
    
    Attributes:
        stage_id: Stage identifier (0=awake, 1=light, 2=deep/SWS, 3=REM).
        start_millis: Stage start time in milliseconds.
        end_millis: Stage end time in milliseconds.
    
    Example:
        >>> stage = SleepStage(stage_id=2, start_millis=0, end_millis=1800000)
        >>> print(f"Deep sleep: {stage.duration_minutes}min")
        Deep sleep: 30.0min
    """
    
    model_config = ConfigDict(frozen=True)
    
    stage_id: int = Field(..., description="Stage ID: 0=awake, 1=light, 2=SWS, 3=REM")
    start_millis: int = Field(..., ge=0, description="Stage start in milliseconds")
    end_millis: int = Field(..., ge=0, description="Stage end in milliseconds")
    
    @property
    def duration_seconds(self) -> float:
        """Calculate stage duration in seconds."""
        return (self.end_millis - self.start_millis) / 1000
    
    @property
    def duration_minutes(self) -> float:
        """Calculate stage duration in minutes."""
        return round(self.duration_seconds / 60, 1)
    
    @property
    def stage_name(self) -> str:
        """Get human-readable stage name."""
        names = {0: "Awake", 1: "Light", 2: "Deep (SWS)", 3: "REM"}
        return names.get(self.stage_id, f"Unknown ({self.stage_id})")


class StageSummary(BaseModel):
    """
    Sleep stage duration breakdown from v2 API.
    
    All durations are in milliseconds.
    """
    
    model_config = ConfigDict(frozen=True)
    
    total_in_bed_time_milli: int = Field(0, description="Total time in bed")
    total_awake_time_milli: int = Field(0, description="Total time awake")
    total_no_data_time_milli: int = Field(0, description="Time with no data")
    total_light_sleep_time_milli: int = Field(0, description="Light sleep duration")
    total_slow_wave_sleep_time_milli: int = Field(0, description="Deep (SWS) sleep duration")
    total_rem_sleep_time_milli: int = Field(0, description="REM sleep duration")
    sleep_cycle_count: int = Field(0, description="Number of sleep cycles")
    disturbance_count: int = Field(0, description="Number of disturbances")
    
    @property
    def total_sleep_time_milli(self) -> int:
        """Total actual sleep time (light + deep + REM)."""
        return (
            self.total_light_sleep_time_milli +
            self.total_slow_wave_sleep_time_milli +
            self.total_rem_sleep_time_milli
        )
    
    @property
    def total_sleep_hours(self) -> float:
        """Total sleep time in hours."""
        return round(self.total_sleep_time_milli / 3600000, 2)
    
    @property
    def in_bed_hours(self) -> float:
        """Total time in bed in hours."""
        return round(self.total_in_bed_time_milli / 3600000, 2)


class SleepNeeded(BaseModel):
    """
    Sleep need breakdown from v2 API.
    
    All durations are in milliseconds.
    """
    
    model_config = ConfigDict(frozen=True)
    
    baseline_milli: int = Field(0, description="Baseline sleep need")
    need_from_sleep_debt_milli: int = Field(0, description="Additional need from sleep debt")
    need_from_recent_strain_milli: int = Field(0, description="Additional need from recent strain")
    need_from_recent_nap_milli: int = Field(0, description="Reduction from recent naps (can be negative)")
    
    @property
    def total_needed_milli(self) -> int:
        """Total sleep needed."""
        return (
            self.baseline_milli +
            self.need_from_sleep_debt_milli +
            self.need_from_recent_strain_milli +
            self.need_from_recent_nap_milli
        )
    
    @property
    def total_needed_hours(self) -> float:
        """Total sleep needed in hours."""
        return round(self.total_needed_milli / 3600000, 2)


class SleepScore(BaseModel):
    """
    Sleep quality score and metrics.
    
    Attributes:
        stage_summary: Sleep stage durations.
        sleep_needed: Sleep need breakdown.
        respiratory_rate: Breathing rate during sleep.
        sleep_performance_percentage: Sleep performance score (0-100).
        sleep_consistency_percentage: Sleep consistency score (0-100).
        sleep_efficiency_percentage: Sleep efficiency score (0-100).
    """
    
    model_config = ConfigDict(frozen=True)
    
    stage_summary: Optional[StageSummary] = Field(
        None,
        description="Sleep stage breakdown"
    )
    sleep_needed: Optional[SleepNeeded] = Field(
        None,
        description="Sleep need breakdown"
    )
    respiratory_rate: Optional[float] = Field(
        None,
        ge=0,
        description="Breathing rate during sleep"
    )
    sleep_performance_percentage: Optional[float] = Field(
        None, 
        ge=0, 
        le=100,
        description="Sleep performance score 0-100"
    )
    sleep_consistency_percentage: Optional[float] = Field(
        None, 
        ge=0, 
        le=100,
        description="Sleep consistency score 0-100"
    )
    sleep_efficiency_percentage: Optional[float] = Field(
        None, 
        ge=0, 
        le=100,
        description="Sleep efficiency score 0-100"
    )
    
    @property
    def total_sleep_duration_hours(self) -> float:
        """Calculate total actual sleep time in hours."""
        if self.stage_summary:
            return self.stage_summary.total_sleep_hours
        return 0.0
    
    @property
    def deep_sleep_hours(self) -> float:
        """Get deep (slow wave) sleep duration in hours."""
        if self.stage_summary:
            return round(self.stage_summary.total_slow_wave_sleep_time_milli / 3600000, 2)
        return 0.0
    
    @property
    def rem_sleep_hours(self) -> float:
        """Get REM sleep duration in hours."""
        if self.stage_summary:
            return round(self.stage_summary.total_rem_sleep_time_milli / 3600000, 2)
        return 0.0
    
    @property
    def light_sleep_hours(self) -> float:
        """Get light sleep duration in hours."""
        if self.stage_summary:
            return round(self.stage_summary.total_light_sleep_time_milli / 3600000, 2)
        return 0.0
    
    @property
    def awake_hours(self) -> float:
        """Get time awake during sleep in hours."""
        if self.stage_summary:
            return round(self.stage_summary.total_awake_time_milli / 3600000, 2)
        return 0.0


class Sleep(BaseModel):
    """
    Complete sleep activity record.
    
    Attributes:
        id: Unique sleep record identifier.
        user_id: User's unique identifier.
        created_at: When the record was created.
        updated_at: When the record was last updated.
        start: Sleep start time.
        end: Sleep end time.
        timezone_offset: Timezone offset string.
        nap: Whether this is a nap (True) or main sleep (False).
        score_state: Scoring state (SCORED, PENDING_SCORE, UNSCORABLE).
        score: Sleep score data (None if not yet scored).
    
    Example:
        >>> sleep = Sleep(
        ...     id=123,
        ...     user_id=456,
        ...     start=datetime(2024, 1, 15, 22, 30),
        ...     end=datetime(2024, 1, 16, 6, 30),
        ...     nap=False,
        ...     score_state="SCORED",
        ...     ...
        ... )
        >>> print(f"Duration: {sleep.duration_hours}h")
        Duration: 8.0h
    """
    
    model_config = ConfigDict(frozen=True)
    
    id: str = Field(..., description="Unique sleep record ID (UUID)")
    cycle_id: int = Field(..., description="Associated cycle ID")
    user_id: int = Field(..., description="User's unique identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    start: datetime = Field(..., description="Sleep start time")
    end: datetime = Field(..., description="Sleep end time")
    timezone_offset: str = Field(..., description="Timezone offset")
    nap: bool = Field(..., description="True if nap, False if main sleep")
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"] = Field(
        ...,
        description="Scoring state: SCORED, PENDING_SCORE, UNSCORABLE"
    )
    score: Optional[SleepScore] = Field(
        None, 
        description="Sleep score data (None if pending)"
    )
    
    @property
    def duration_hours(self) -> float:
        """Calculate total time in bed in hours."""
        duration = self.end - self.start
        return round(duration.total_seconds() / 3600, 2)
    
    @property
    def duration_minutes(self) -> float:
        """Calculate total time in bed in minutes."""
        return round(self.duration_hours * 60, 1)
    
    @property
    def is_scored(self) -> bool:
        """Check if sleep has been scored."""
        return self.score_state == "SCORED" and self.score is not None


class SleepCollection(BaseModel):
    """
    Paginated collection of sleep records.
    
    Attributes:
        records: List of Sleep records.
        next_token: Token for fetching next page (None if last page).
    """
    
    records: List[Sleep] = Field(
        default_factory=list,
        description="List of sleep records"
    )
    next_token: Optional[str] = Field(
        None,
        description="Pagination token for next page"
    )

    def __len__(self) -> int:
        """Return number of records in collection."""
        return len(self.records)

    def __iter__(self) -> Iterator[Sleep]:
        """Iterate over records."""
        return iter(self.records)


# =============================================================================
# Cycle (Daily Strain) Models
# =============================================================================

class CycleScore(BaseModel):
    """
    Cycle strain score and metrics from v2 API.
    
    Represents daily strain accumulated through activities.
    
    Attributes:
        strain: Strain score (0-21 scale).
        average_heart_rate: Average heart rate during cycle.
        max_heart_rate: Maximum heart rate during cycle.
        kilojoule: Total energy expenditure in kilojoules.
    """
    
    model_config = ConfigDict(frozen=True)
    
    strain: float = Field(
        ..., 
        ge=0, 
        le=21, 
        description="Strain score 0-21"
    )
    kilojoule: float = Field(
        ..., 
        ge=0,
        description="Energy expenditure in kilojoules"
    )
    average_heart_rate: int = Field(
        ..., 
        gt=0,
        description="Average heart rate during cycle"
    )
    max_heart_rate: int = Field(
        ..., 
        gt=0,
        description="Maximum heart rate during cycle"
    )
    
    @property
    def calories(self) -> float:
        """Convert kilojoules to calories."""
        return round(self.kilojoule * 0.239006, 0)
    
    @property
    def strain_level(self) -> str:
        """
        Get strain level description.
        
        - Light (0-9): Easy recovery day
        - Moderate (10-13): Normal activity
        - Strenuous (14-17): Hard training day
        - All Out (18-21): Maximum effort
        """
        if self.strain < 10:
            return "Light"
        elif self.strain < 14:
            return "Moderate"
        elif self.strain < 18:
            return "Strenuous"
        else:
            return "All Out"


class Cycle(BaseModel):
    """
    Complete physiological cycle record (typically 24 hours).
    
    A cycle represents one full day of physiological data from
    wake time to next wake time.
    
    Attributes:
        id: Unique cycle identifier.
        user_id: User's unique identifier.
        created_at: When the record was created.
        updated_at: When the record was last updated.
        start: Cycle start time.
        end: Cycle end time.
        timezone_offset: Timezone offset string.
        score_state: Scoring state (SCORED, PENDING_SCORE, UNSCORABLE).
        score: Cycle strain data (None if not yet scored).
    
    Example:
        >>> cycle = Cycle(...)
        >>> if cycle.score:
        ...     print(f"Daily strain: {cycle.score.score}")
    """
    
    model_config = ConfigDict(frozen=True)
    
    id: int = Field(..., description="Unique cycle ID")
    user_id: int = Field(..., description="User's unique identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    start: datetime = Field(..., description="Cycle start time")
    end: Optional[datetime] = Field(None, description="Cycle end time (None if current cycle)")
    timezone_offset: str = Field(..., description="Timezone offset")
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"] = Field(
        ...,
        description="Scoring state: SCORED, PENDING_SCORE, UNSCORABLE"
    )
    score: Optional[CycleScore] = Field(
        None, 
        description="Cycle strain data (None if pending)"
    )
    
    @property
    def is_current(self) -> bool:
        """Check if this is the current (ongoing) cycle."""
        return self.end is None
    
    @property
    def duration_hours(self) -> Optional[float]:
        """Calculate cycle duration in hours (None if cycle is ongoing)."""
        if self.end is None:
            return None
        duration = self.end - self.start
        return round(duration.total_seconds() / 3600, 2)
    
    @property
    def is_scored(self) -> bool:
        """Check if cycle has been scored."""
        return self.score_state == "SCORED" and self.score is not None


class CycleCollection(BaseModel):
    """
    Paginated collection of cycle records.
    
    Attributes:
        records: List of Cycle records.
        next_token: Token for fetching next page (None if last page).
    """
    
    records: List[Cycle] = Field(
        default_factory=list,
        description="List of cycle records"
    )
    next_token: Optional[str] = Field(
        None,
        description="Pagination token for next page"
    )

    def __len__(self) -> int:
        """Return number of records in collection."""
        return len(self.records)

    def __iter__(self) -> Iterator[Cycle]:
        """Iterate over records."""
        return iter(self.records)


# =============================================================================
# Workout Models
# =============================================================================

class WorkoutZoneDuration(BaseModel):
    """
    Heart rate zone duration breakdown.
    
    Each zone represents time spent in a specific HR intensity range.
    All durations are in milliseconds.
    
    Attributes:
        zone_zero_milli: Time below zone 1 (very low intensity).
        zone_one_milli: Time in zone 1 (light activity).
        zone_two_milli: Time in zone 2 (moderate activity).
        zone_three_milli: Time in zone 3 (hard activity).
        zone_four_milli: Time in zone 4 (very hard activity).
        zone_five_milli: Time in zone 5 (max effort).
    
    Example:
        >>> zones = WorkoutZoneDuration(
        ...     zone_zero_milli=60000,
        ...     zone_one_milli=300000,
        ...     zone_two_milli=600000,
        ...     zone_three_milli=900000,
        ...     zone_four_milli=300000,
        ...     zone_five_milli=60000
        ... )
        >>> print(f"Zone 3: {zones.zone_three_minutes}min")
        Zone 3: 15.0min
    """
    
    model_config = ConfigDict(frozen=True)
    
    zone_zero_milli: Optional[int] = None
    zone_one_milli: Optional[int] = None
    zone_two_milli: Optional[int] = None
    zone_three_milli: Optional[int] = None
    zone_four_milli: Optional[int] = None
    zone_five_milli: Optional[int] = None
    
    @property
    def zone_zero_minutes(self) -> float:
        """Zone 0 duration in minutes."""
        return round(self.zone_zero_milli / 60000, 1)
    
    @property
    def zone_one_minutes(self) -> float:
        """Zone 1 duration in minutes."""
        return round(self.zone_one_milli / 60000, 1)
    
    @property
    def zone_two_minutes(self) -> float:
        """Zone 2 duration in minutes."""
        return round(self.zone_two_milli / 60000, 1)
    
    @property
    def zone_three_minutes(self) -> float:
        """Zone 3 duration in minutes."""
        return round(self.zone_three_milli / 60000, 1)
    
    @property
    def zone_four_minutes(self) -> float:
        """Zone 4 duration in minutes."""
        return round(self.zone_four_milli / 60000, 1)
    
    @property
    def zone_five_minutes(self) -> float:
        """Zone 5 duration in minutes."""
        return round(self.zone_five_milli / 60000, 1)
    
    @property
    def total_minutes(self) -> float:
        """Total time across all zones in minutes."""
        total_ms = (
            self.zone_zero_milli + self.zone_one_milli + self.zone_two_milli +
            self.zone_three_milli + self.zone_four_milli + self.zone_five_milli
        )
        return round(total_ms / 60000, 1)


class WorkoutScore(BaseModel):
    """
    Workout scoring metrics.
    
    Attributes:
        strain: Workout strain score (0-21 scale).
        average_heart_rate: Average HR during workout.
        max_heart_rate: Maximum HR during workout.
        kilojoule: Energy expenditure in kilojoules.
        percent_recorded: Percentage of workout with HR data.
        distance_meter: Distance covered in meters (if applicable).
        altitude_gain_meter: Total elevation gain in meters.
        altitude_change_meter: Net elevation change in meters.
        zone_duration: Time in each HR zone.
    
    Example:
        >>> score = WorkoutScore(
        ...     strain=12.5,
        ...     average_heart_rate=145,
        ...     max_heart_rate=175,
        ...     kilojoule=800.0,
        ...     percent_recorded=98.5
        ... )
        >>> print(f"Workout strain: {score.strain}")
    """
    
    model_config = ConfigDict(frozen=True)
    
    strain: float = Field(
        ..., 
        ge=0, 
        le=21, 
        description="Workout strain 0-21"
    )
    average_heart_rate: int = Field(
        ..., 
        gt=0,
        description="Average HR during workout"
    )
    max_heart_rate: int = Field(
        ..., 
        gt=0,
        description="Maximum HR during workout"
    )
    kilojoule: float = Field(
        ..., 
        ge=0,
        description="Energy expenditure in kilojoules"
    )
    percent_recorded: float = Field(
        ..., 
        ge=0, 
        le=100,
        description="Percentage of workout recorded"
    )
    distance_meter: Optional[float] = Field(
        None, 
        ge=0,
        description="Distance in meters"
    )
    altitude_gain_meter: Optional[float] = Field(
        None, 
        ge=0,
        description="Elevation gain in meters"
    )
    altitude_change_meter: Optional[float] = Field(
        None, 
        description="Net elevation change in meters"
    )
    zone_duration: Optional[WorkoutZoneDuration] = Field(
        None, 
        description="Time in each HR zone"
    )
    
    @property
    def calories(self) -> float:
        """Convert kilojoules to calories."""
        return round(self.kilojoule * 0.239006, 0)
    
    @property
    def distance_km(self) -> Optional[float]:
        """Convert distance to kilometers."""
        if self.distance_meter is None:
            return None
        return round(self.distance_meter / 1000, 2)
    
    @property
    def distance_miles(self) -> Optional[float]:
        """Convert distance to miles."""
        if self.distance_meter is None:
            return None
        return round(self.distance_meter * 0.000621371, 2)


# Sport ID to name mapping - defined as module constant for efficiency
SPORT_NAMES: Dict[int, str] = {
    -1: "Activity",
    0: "Running",
    1: "Cycling",
    16: "Baseball",
    17: "Basketball",
    18: "Rowing",
    19: "Fencing",
    20: "Field Hockey",
    21: "Football",
    22: "Golf",
    24: "Ice Hockey",
    25: "Lacrosse",
    27: "Rugby",
    28: "Sailing",
    29: "Skiing",
    30: "Soccer",
    31: "Softball",
    32: "Squash",
    33: "Swimming",
    34: "Tennis",
    35: "Track & Field",
    36: "Volleyball",
    37: "Water Polo",
    38: "Wrestling",
    39: "Boxing",
    42: "Dance",
    43: "Pilates",
    44: "Yoga",
    45: "Weightlifting",
    47: "Cross Country Skiing",
    48: "Functional Fitness",
    49: "Duathlon",
    51: "Gymnastics",
    52: "Hiking/Rucking",
    53: "Horseback Riding",
    55: "Kayaking",
    56: "Martial Arts",
    57: "Mountain Biking",
    59: "Powerlifting",
    60: "Rock Climbing",
    61: "Paddleboarding",
    62: "Triathlon",
    63: "Walking",
    64: "Surfing",
    65: "Elliptical",
    66: "Stairmaster",
    70: "Meditation",
    71: "Other",
    73: "Diving",
    74: "Operations - Tactical",
    75: "Operations - Medical",
    76: "Operations - Flying",
    77: "Operations - Water",
    82: "Ultimate",
    83: "Climber",
    84: "Jumping Rope",
    85: "Australian Football",
    86: "Skateboarding",
    87: "Coaching",
    88: "Ice Bath",
    89: "Commuting",
    90: "Gaming",
    91: "Snowboarding",
    92: "Motocross",
    93: "Caddying",
    94: "Obstacle Course Racing",
    95: "Motor Racing",
    96: "HIIT",
    97: "Spin",
    98: "Jiu Jitsu",
    99: "Manual Labor",
    100: "Cricket",
    101: "Pickleball",
    102: "Inline Skating",
    103: "Box Fitness",
    104: "Spikeball",
    105: "Wheelchair Pushing",
    106: "Paddle Tennis",
    107: "Barre",
    108: "Stage Performance",
    109: "High Stress Work",
    110: "Parkour",
    111: "Gaelic Football",
    112: "Hurling/Camogie",
    113: "Circus Arts",
    121: "Massage Therapy",
    125: "Watching Sports",
    126: "Assault Bike",
    127: "Kickboxing",
    128: "Stretching",
    230: "Table Tennis",
    231: "Badminton",
    232: "Netball",
    233: "Sauna",
    234: "Disc Golf",
    235: "Yard Work",
    236: "Air Compression",
    237: "Percussive Massage",
    238: "Paintball",
    239: "Ice Skating",
    240: "Handball",
}


class Workout(BaseModel):
    """
    Complete workout activity record.
    
    Attributes:
        id: Unique workout identifier.
        user_id: User's unique identifier.
        created_at: When the record was created.
        updated_at: When the record was last updated.
        start: Workout start time.
        end: Workout end time.
        timezone_offset: Timezone offset string.
        sport_id: Sport type identifier.
        score_state: Scoring state (SCORED, PENDING_SCORE, UNSCORABLE).
        score: Workout score data (None if not yet scored).
    
    Example:
        >>> workout = Workout(...)
        >>> print(f"Activity: {workout.sport_name}")
        >>> print(f"Duration: {workout.duration_minutes}min")
        >>> if workout.score:
        ...     print(f"Strain: {workout.score.strain}")
    """
    
    model_config = ConfigDict(frozen=True)
    
    id: str = Field(..., description="Unique workout ID (UUID)")
    user_id: int = Field(..., description="User's unique identifier")
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    start: datetime = Field(..., description="Workout start time")
    end: datetime = Field(..., description="Workout end time")
    timezone_offset: str = Field(..., description="Timezone offset")
    sport_id: int = Field(..., description="Sport identifier returned by the WHOOP API.")
    sport_name: Optional[str] = Field(None, description="Not returned by WHOOP API. Use sport_id with constants.SPORT_NAMES for lookup.")
    score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"] = Field(
        ...,
        description="Scoring state: SCORED, PENDING_SCORE, UNSCORABLE"
    )
    score: Optional[WorkoutScore] = Field(
        None, 
        description="Workout score data (None if pending)"
    )
    
    @property
    def sport_display_name(self) -> str:
        """Get human-readable sport name (uses sport_name field or falls back to sport_id lookup)."""
        if self.sport_name:
            return self.sport_name.replace("_", " ").title()
        if self.sport_id is not None:
            return SPORT_NAMES.get(self.sport_id, f"Unknown Sport ({self.sport_id})")
        return "Unknown Sport"
    
    @property
    def duration_hours(self) -> float:
        """Calculate workout duration in hours."""
        duration = self.end - self.start
        return round(duration.total_seconds() / 3600, 2)
    
    @property
    def duration_minutes(self) -> float:
        """Calculate workout duration in minutes."""
        return round(self.duration_hours * 60, 1)
    
    @property
    def is_scored(self) -> bool:
        """Check if workout has been scored."""
        return self.score_state == "SCORED" and self.score is not None


class WorkoutCollection(BaseModel):
    """
    Paginated collection of workout records.
    
    Attributes:
        records: List of Workout records.
        next_token: Token for fetching next page (None if last page).
    """
    
    records: List[Workout] = Field(
        default_factory=list,
        description="List of workout records"
    )
    next_token: Optional[str] = Field(
        None,
        description="Pagination token for next page"
    )

    def __len__(self) -> int:
        """Return number of records in collection."""
        return len(self.records)

    def __iter__(self) -> Iterator[Workout]:
        """Iterate over records."""
        return iter(self.records)


# =============================================================================
# Helper Functions
# =============================================================================

def format_duration(milliseconds: int) -> str:
    """
    Format duration from milliseconds to human-readable string.
    
    Args:
        milliseconds: Duration in milliseconds.
    
    Returns:
        Formatted duration string (e.g., "7h 45m").
    
    Example:
        >>> format_duration(28800000)  # 8 hours
        '8h 0m'
        >>> format_duration(5400000)   # 1.5 hours
        '1h 30m'
    """
    if milliseconds < 0:
        raise ValueError(f"Duration cannot be negative: {milliseconds}")
    
    seconds = milliseconds / 1000
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def get_sport_name(sport_id: int) -> str:
    """
    Get human-readable sport name from sport ID.
    
    Args:
        sport_id: Whoop sport identifier.
    
    Returns:
        Human-readable sport name.
    
    Example:
        >>> get_sport_name(0)
        'Running'
        >>> get_sport_name(44)
        'Yoga'
    """
    return SPORT_NAMES.get(sport_id, f"Unknown Sport ({sport_id})")
