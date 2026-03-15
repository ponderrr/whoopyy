"""
Unit tests for WhoopPy Pydantic models.

Tests cover:
- Model instantiation with valid data
- Field validation (boundaries, types)
- Computed properties
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from whoopyy.models import (
    # User Profile
    UserProfileBasic,
    BodyMeasurement,
    # Recovery
    RecoveryScore,
    Recovery,
    RecoveryCollection,
    # Sleep
    SleepStage,
    SleepScore,
    Sleep,
    SleepCollection,
    # Cycle
    CycleScore,
    Cycle,
    CycleCollection,
    # Workout
    WorkoutZoneDuration,
    WorkoutScore,
    Workout,
    WorkoutCollection,
    # Helpers
    format_duration,
    get_sport_name,
    SPORT_NAMES,
)


# =============================================================================
# User Profile Model Tests
# =============================================================================

class TestUserProfileBasic:
    """Tests for UserProfileBasic model."""
    
    def test_valid_profile(self) -> None:
        """Test creating a valid user profile."""
        profile = UserProfileBasic(
            user_id=12345,
            email="test@example.com",
            first_name="John",
            last_name="Doe"
        )
        
        assert profile.user_id == 12345
        assert profile.email == "test@example.com"
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"
    
    def test_full_name_property(self) -> None:
        """Test full_name computed property."""
        profile = UserProfileBasic(
            user_id=1,
            email="test@example.com",
            first_name="Jane",
            last_name="Smith"
        )
        
        assert profile.full_name == "Jane Smith"
    
    def test_model_is_frozen(self) -> None:
        """Test that model is immutable."""
        profile = UserProfileBasic(
            user_id=1,
            email="test@example.com",
            first_name="John",
            last_name="Doe"
        )
        
        with pytest.raises(ValidationError):
            profile.first_name = "Changed"


class TestBodyMeasurement:
    """Tests for BodyMeasurement model."""
    
    def test_valid_measurement(self) -> None:
        """Test creating valid body measurements."""
        body = BodyMeasurement(
            height_meter=1.83,
            weight_kilogram=82.5,
            max_heart_rate=195
        )
        
        assert body.height_meter == 1.83
        assert body.weight_kilogram == 82.5
        assert body.max_heart_rate == 195
    
    def test_optional_fields(self) -> None:
        """Test that all fields are optional."""
        body = BodyMeasurement()
        
        assert body.height_meter is None
        assert body.weight_kilogram is None
        assert body.max_heart_rate is None
    
    def test_height_feet_conversion(self) -> None:
        """Test height conversion to feet."""
        body = BodyMeasurement(height_meter=1.83)
        
        assert body.height_feet == pytest.approx(6.0, rel=0.01)
    
    def test_weight_pounds_conversion(self) -> None:
        """Test weight conversion to pounds."""
        body = BodyMeasurement(weight_kilogram=82.5)
        
        assert body.weight_pounds == pytest.approx(181.9, rel=0.01)
    
    def test_negative_height_rejected(self) -> None:
        """Test that negative height is rejected."""
        with pytest.raises(ValidationError):
            BodyMeasurement(height_meter=-1.0)
    
    def test_zero_weight_rejected(self) -> None:
        """Test that zero weight is rejected."""
        with pytest.raises(ValidationError):
            BodyMeasurement(weight_kilogram=0)


# =============================================================================
# Recovery Model Tests
# =============================================================================

class TestRecoveryScore:
    """Tests for RecoveryScore model."""
    
    def test_valid_score(self) -> None:
        """Test creating a valid recovery score."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=75.5,
            resting_heart_rate=52,
            hrv_rmssd_milli=65.2,
            spo2_percentage=98.5,
            skin_temp_celsius=36.5
        )
        
        assert score.recovery_score == 75.5
        assert score.resting_heart_rate == 52
        assert score.hrv_rmssd_milli == 65.2
    
    def test_recovery_zone_green(self) -> None:
        """Test green recovery zone (67-100)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=80.0,
            resting_heart_rate=50,
            hrv_rmssd_milli=70.0
        )
        
        assert score.recovery_zone == "green"
    
    def test_recovery_zone_yellow(self) -> None:
        """Test yellow recovery zone (34-66)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=50.0,
            resting_heart_rate=55,
            hrv_rmssd_milli=50.0
        )
        
        assert score.recovery_zone == "yellow"
    
    def test_recovery_zone_red(self) -> None:
        """Test red recovery zone (0-33)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=25.0,
            resting_heart_rate=65,
            hrv_rmssd_milli=30.0
        )
        
        assert score.recovery_zone == "red"
    
    def test_recovery_zone_boundary_67(self) -> None:
        """Test boundary at 67 (should be green)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=67.0,
            resting_heart_rate=52,
            hrv_rmssd_milli=60.0
        )
        
        assert score.recovery_zone == "green"
    
    def test_recovery_zone_boundary_34(self) -> None:
        """Test boundary at 34 (should be yellow)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=34.0,
            resting_heart_rate=58,
            hrv_rmssd_milli=45.0
        )
        
        assert score.recovery_zone == "yellow"
    
    def test_score_above_100_rejected(self) -> None:
        """Test that recovery_score > 100 is rejected."""
        with pytest.raises(ValidationError):
            RecoveryScore(
                user_calibrating=False,
                recovery_score=101.0,
                resting_heart_rate=52,
                hrv_rmssd_milli=65.0
            )
    
    def test_score_below_0_rejected(self) -> None:
        """Test that recovery_score < 0 is rejected."""
        with pytest.raises(ValidationError):
            RecoveryScore(
                user_calibrating=False,
                recovery_score=-1.0,
                resting_heart_rate=52,
                hrv_rmssd_milli=65.0
            )
    
    def test_negative_hrv_rejected(self) -> None:
        """Test that negative HRV is rejected."""
        with pytest.raises(ValidationError):
            RecoveryScore(
                user_calibrating=False,
                recovery_score=75.0,
                resting_heart_rate=52,
                hrv_rmssd_milli=-10.0
            )
    
    def test_spo2_above_100_rejected(self) -> None:
        """Test that SpO2 > 100 is rejected."""
        with pytest.raises(ValidationError):
            RecoveryScore(
                user_calibrating=False,
                recovery_score=75.0,
                resting_heart_rate=52,
                hrv_rmssd_milli=65.0,
                spo2_percentage=105.0
            )


class TestRecovery:
    """Tests for Recovery model."""
    
    @pytest.fixture
    def sample_recovery(self) -> Recovery:
        """Create a sample recovery for testing."""
        return Recovery(
            cycle_id=123,
            sleep_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id=789,
            created_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc),
            score_state="SCORED",
            score=RecoveryScore(
                user_calibrating=False,
                recovery_score=75.5,
                resting_heart_rate=52,
                hrv_rmssd_milli=65.2
            )
        )

    def test_valid_recovery(self, sample_recovery: Recovery) -> None:
        """Test creating a valid recovery record."""
        assert sample_recovery.cycle_id == 123
        assert sample_recovery.sleep_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert sample_recovery.score_state == "SCORED"
        assert sample_recovery.score is not None
    
    def test_is_scored_true(self, sample_recovery: Recovery) -> None:
        """Test is_scored when recovery is scored."""
        assert sample_recovery.is_scored is True
    
    def test_is_scored_false_pending(self) -> None:
        """Test is_scored when score is pending."""
        recovery = Recovery(
            cycle_id=123,
            sleep_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id=789,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            score_state="PENDING_SCORE",
            score=None
        )
        
        assert recovery.is_scored is False


class TestRecoveryCollection:
    """Tests for RecoveryCollection model."""
    
    def test_empty_collection(self) -> None:
        """Test creating an empty collection."""
        collection = RecoveryCollection(records=[])
        
        assert len(collection) == 0
        assert collection.next_token is None
    
    def test_collection_with_records(self) -> None:
        """Test collection with multiple records."""
        records = [
            Recovery(
                cycle_id=i + 1,
                sleep_id=f"a1b2c3d4-e5f6-7890-abcd-ef123456{i:04d}",
                user_id=1,
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
                score_state="SCORED",
                score=RecoveryScore(
                    user_calibrating=False,
                    recovery_score=70.0 + i,
                    resting_heart_rate=50,
                    hrv_rmssd_milli=60.0
                )
            )
            for i in range(5)
        ]
        
        collection = RecoveryCollection(records=records, next_token="abc123")
        
        assert len(collection) == 5
        assert collection.next_token == "abc123"
    
    def test_collection_iteration(self) -> None:
        """Test iterating over collection."""
        records = [
            Recovery(
                cycle_id=i + 1,
                sleep_id=f"a1b2c3d4-e5f6-7890-abcd-ef123456{i:04d}",
                user_id=1,
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
                score_state="SCORED",
                score=None
            )
            for i in range(3)
        ]

        collection = RecoveryCollection(records=records)

        cycle_ids = [r.cycle_id for r in collection]
        assert cycle_ids == [1, 2, 3]


# =============================================================================
# Sleep Model Tests
# =============================================================================

class TestSleepStage:
    """Tests for SleepStage model."""
    
    def test_valid_stage(self) -> None:
        """Test creating a valid sleep stage."""
        stage = SleepStage(
            stage_id=2,
            start_millis=0,
            end_millis=1800000  # 30 minutes
        )
        
        assert stage.stage_id == 2
        assert stage.duration_seconds == 1800.0
        assert stage.duration_minutes == 30.0
    
    def test_stage_names(self) -> None:
        """Test stage name property."""
        stages = [
            (0, "Awake"),
            (1, "Light"),
            (2, "Deep (SWS)"),
            (3, "REM"),
            (99, "Unknown (99)"),
        ]
        
        for stage_id, expected_name in stages:
            stage = SleepStage(stage_id=stage_id, start_millis=0, end_millis=1000)
            assert stage.stage_name == expected_name


class TestSleepScore:
    """Tests for SleepScore model."""
    
    @pytest.fixture
    def sample_sleep_score(self) -> SleepScore:
        """Create a sample sleep score."""
        return SleepScore(
            stage_summary={
                "total_light_sleep_time_milli": 14400000,      # 4 hours
                "total_slow_wave_sleep_time_milli": 5400000,   # 1.5 hours
                "total_rem_sleep_time_milli": 7200000,         # 2 hours
                "total_awake_time_milli": 1800000,             # 0.5 hours
            },
            sleep_needed={
                "baseline_milli": 28800000,
                "need_from_sleep_debt_milli": 0,
            },
            respiratory_rate=14.5,
            sleep_performance_percentage=85.0,
            sleep_efficiency_percentage=92.0
        )
    
    def test_total_sleep_duration(self, sample_sleep_score: SleepScore) -> None:
        """Test total sleep duration calculation."""
        # 4 + 1.5 + 2 = 7.5 hours
        assert sample_sleep_score.total_sleep_duration_hours == 7.5
    
    def test_deep_sleep_hours(self, sample_sleep_score: SleepScore) -> None:
        """Test deep sleep hours calculation."""
        assert sample_sleep_score.deep_sleep_hours == 1.5
    
    def test_rem_sleep_hours(self, sample_sleep_score: SleepScore) -> None:
        """Test REM sleep hours calculation."""
        assert sample_sleep_score.rem_sleep_hours == 2.0
    
    def test_light_sleep_hours(self, sample_sleep_score: SleepScore) -> None:
        """Test light sleep hours calculation."""
        assert sample_sleep_score.light_sleep_hours == 4.0
    
    def test_awake_hours(self, sample_sleep_score: SleepScore) -> None:
        """Test awake hours calculation."""
        assert sample_sleep_score.awake_hours == 0.5


class TestSleep:
    """Tests for Sleep model."""
    
    def test_valid_sleep(self) -> None:
        """Test creating a valid sleep record."""
        sleep = Sleep(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            cycle_id=100,
            user_id=456,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            start=datetime(2024, 1, 15, 22, 30, tzinfo=timezone.utc),
            end=datetime(2024, 1, 16, 6, 30, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            nap=False,
            score_state="SCORED",
            score=None
        )

        assert sleep.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert sleep.nap is False
        assert sleep.duration_hours == 8.0

    def test_nap_sleep(self) -> None:
        """Test creating a nap record."""
        sleep = Sleep(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567891",
            cycle_id=101,
            user_id=456,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            start=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            nap=True,
            score_state="SCORED",
            score=None
        )
        
        assert sleep.nap is True
        assert sleep.duration_minutes == 30.0


# =============================================================================
# Cycle Model Tests
# =============================================================================

class TestCycleScore:
    """Tests for CycleScore model."""

    def test_valid_strain(self) -> None:
        """Test creating a valid cycle strain."""
        strain = CycleScore(
            strain=14.5,
            average_heart_rate=72,
            max_heart_rate=175,
            kilojoule=2500.0,
        )

        assert strain.strain == 14.5
        assert strain.calories == 598  # 2500 * 0.239006 rounded

    def test_strain_level_light(self) -> None:
        """Test light strain level (0-9)."""
        strain = CycleScore(
            strain=5.0,
            average_heart_rate=65,
            max_heart_rate=120,
            kilojoule=1000.0,
        )

        assert strain.strain_level == "Light"

    def test_strain_level_moderate(self) -> None:
        """Test moderate strain level (10-13)."""
        strain = CycleScore(
            strain=12.0,
            average_heart_rate=72,
            max_heart_rate=155,
            kilojoule=2000.0,
        )

        assert strain.strain_level == "Moderate"

    def test_strain_level_strenuous(self) -> None:
        """Test strenuous strain level (14-17)."""
        strain = CycleScore(
            strain=15.5,
            average_heart_rate=85,
            max_heart_rate=175,
            kilojoule=3000.0,
        )

        assert strain.strain_level == "Strenuous"

    def test_strain_level_all_out(self) -> None:
        """Test all out strain level (18-21)."""
        strain = CycleScore(
            strain=19.0,
            average_heart_rate=95,
            max_heart_rate=190,
            kilojoule=4000.0,
        )

        assert strain.strain_level == "All Out"

    def test_strain_above_21_rejected(self) -> None:
        """Test that strain > 21 is rejected."""
        with pytest.raises(ValidationError):
            CycleScore(
                strain=22.0,
                average_heart_rate=72,
                max_heart_rate=175,
                kilojoule=2500.0,
            )


# =============================================================================
# Workout Model Tests
# =============================================================================

class TestWorkoutZoneDuration:
    """Tests for WorkoutZoneDuration model."""
    
    def test_valid_zones(self) -> None:
        """Test creating valid zone durations."""
        zones = WorkoutZoneDuration(
            zone_zero_milli=60000,
            zone_one_milli=300000,
            zone_two_milli=600000,
            zone_three_milli=900000,
            zone_four_milli=300000,
            zone_five_milli=60000
        )
        
        assert zones.zone_one_minutes == 5.0
        assert zones.zone_three_minutes == 15.0
        assert zones.total_minutes == 37.0


class TestWorkoutScore:
    """Tests for WorkoutScore model."""
    
    def test_valid_score(self) -> None:
        """Test creating a valid workout score."""
        score = WorkoutScore(
            strain=12.5,
            average_heart_rate=145,
            max_heart_rate=175,
            kilojoule=800.0,
            percent_recorded=98.5,
            distance_meter=5000.0
        )
        
        assert score.strain == 12.5
        assert score.calories == 191  # 800 * 0.239006 rounded
        assert score.distance_km == 5.0
        assert score.distance_miles == pytest.approx(3.11, rel=0.01)


class TestWorkout:
    """Tests for Workout model."""
    
    def test_valid_workout(self) -> None:
        """Test creating a valid workout."""
        workout = Workout(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            user_id=456,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
            start=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=0,
            score_state="SCORED",
            score=None
        )

        assert workout.sport_display_name == "Running"
        assert workout.duration_hours == 1.0
        assert workout.duration_minutes == 60.0

    def test_sport_names(self) -> None:
        """Test various sport name lookups."""
        test_cases = [
            (0, "Running"),
            (1, "Cycling"),
            (44, "Yoga"),
            (45, "Weightlifting"),
            (96, "HIIT"),
            (9999, "Unknown Sport (9999)"),
        ]

        for sport_id, expected_name in test_cases:
            workout = Workout(
                id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                user_id=1,
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
                start=datetime.now(tz=timezone.utc),
                end=datetime.now(tz=timezone.utc),
                timezone_offset="-05:00",
                sport_id=sport_id,
                score_state="SCORED"
            )
            assert workout.sport_display_name == expected_name


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestFormatDuration:
    """Tests for format_duration helper."""
    
    def test_hours_and_minutes(self) -> None:
        """Test formatting hours and minutes."""
        assert format_duration(28800000) == "8h 0m"
        assert format_duration(5400000) == "1h 30m"
    
    def test_minutes_only(self) -> None:
        """Test formatting minutes only (< 1 hour)."""
        assert format_duration(1800000) == "30m"
        assert format_duration(900000) == "15m"
    
    def test_zero_duration(self) -> None:
        """Test zero duration."""
        assert format_duration(0) == "0m"
    
    def test_negative_duration_rejected(self) -> None:
        """Test that negative duration raises error."""
        with pytest.raises(ValueError):
            format_duration(-1000)


class TestGetSportName:
    """Tests for get_sport_name helper."""
    
    def test_known_sports(self) -> None:
        """Test getting known sport names."""
        assert get_sport_name(0) == "Running"
        assert get_sport_name(44) == "Yoga"
        assert get_sport_name(96) == "HIIT"
    
    def test_unknown_sport(self) -> None:
        """Test getting unknown sport name."""
        assert get_sport_name(9999) == "Unknown Sport (9999)"


class TestSportNamesConstant:
    """Tests for SPORT_NAMES constant."""
    
    def test_sport_names_not_empty(self) -> None:
        """Test that SPORT_NAMES is populated."""
        assert len(SPORT_NAMES) > 50  # Should have many sports
    
    def test_common_sports_present(self) -> None:
        """Test that common sports are present."""
        common_sports = [0, 1, 44, 45, 52, 96]  # Running, Cycling, Yoga, etc.

        for sport_id in common_sports:
            assert sport_id in SPORT_NAMES


# =============================================================================
# New Workout / WorkoutZoneDuration Model Tests
# =============================================================================

class TestWorkoutDeserializesWithSportId:
    """Tests for Workout model using sport_id (v2 API behavior)."""

    def test_workout_deserializes_with_sport_id(self) -> None:
        """Test that a workout with sport_id (and no sport_name) parses correctly."""
        workout = Workout(
            id="abc-123",
            user_id=1,
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=0,
            score_state="SCORED",
        )
        assert workout.sport_id == 0

    def test_workout_sport_name_is_optional(self) -> None:
        """Test that sport_name defaults to None when not provided."""
        workout = Workout(
            id="abc-456",
            user_id=1,
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=1,
            score_state="SCORED",
        )
        assert workout.sport_name is None

    def test_workout_sport_name_explicit_value(self) -> None:
        """Test that sport_name is stored when explicitly provided."""
        workout = Workout(
            id="abc-789",
            user_id=1,
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=0,
            sport_name="Running",
            score_state="SCORED",
        )
        assert workout.sport_name == "Running"


class TestWorkoutZoneDurationNullable:
    """Tests for WorkoutZoneDuration with nullable zone fields."""

    def test_workout_zone_durations_nullable(self) -> None:
        """Test that all zone fields accept None."""
        zones = WorkoutZoneDuration(
            zone_zero_milli=None,
            zone_one_milli=None,
            zone_two_milli=None,
            zone_three_milli=None,
            zone_four_milli=None,
            zone_five_milli=None,
        )
        assert zones.zone_zero_milli is None
        assert zones.zone_five_milli is None

    def test_workout_zone_durations_defaults_to_none(self) -> None:
        """Test that zone fields default to None when not specified."""
        zones = WorkoutZoneDuration()
        assert zones.zone_zero_milli is None
        assert zones.zone_one_milli is None
        assert zones.zone_two_milli is None
        assert zones.zone_three_milli is None
        assert zones.zone_four_milli is None
        assert zones.zone_five_milli is None

    def test_workout_zone_durations_with_values(self) -> None:
        """Test that all zone fields accept integer values."""
        zones = WorkoutZoneDuration(
            zone_zero_milli=60000,
            zone_one_milli=300000,
            zone_two_milli=600000,
            zone_three_milli=900000,
            zone_four_milli=300000,
            zone_five_milli=60000,
        )
        assert zones.zone_zero_milli == 60000
        assert zones.zone_one_milli == 300000
        assert zones.zone_two_milli == 600000
        assert zones.zone_three_milli == 900000
        assert zones.zone_four_milli == 300000
        assert zones.zone_five_milli == 60000


# =============================================================================
# Type Correctness Tests (new)
# =============================================================================

class TestRecoveryScoreTypeCorrectness:
    """Tests for RecoveryScore field type corrections."""

    def test_recovery_score_resting_hr_accepts_float(self) -> None:
        """RecoveryScore.resting_heart_rate should accept a float value."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=75.0,
            resting_heart_rate=52.3,
            hrv_rmssd_milli=65.0,
        )
        assert score.resting_heart_rate == 52.3

    def test_recovery_score_hrv_accepts_zero(self) -> None:
        """RecoveryScore.hrv_rmssd_milli should accept 0.0 (ge=0)."""
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=75.0,
            resting_heart_rate=52,
            hrv_rmssd_milli=0.0,
        )
        assert score.hrv_rmssd_milli == 0.0


class TestSleepScoreTypeCorrectness:
    """Tests for SleepScore field type corrections."""

    def test_sleep_score_respiratory_rate_accepts_zero(self) -> None:
        """SleepScore.respiratory_rate should accept 0.0 (ge=0)."""
        score = SleepScore(respiratory_rate=0.0)
        assert score.respiratory_rate == 0.0


def _make_cycle(**kwargs) -> Cycle:
    defaults = dict(
        id=1,
        user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 15, tzinfo=timezone.utc),
        timezone_offset="-05:00",
        score_state="SCORED",
    )
    defaults.update(kwargs)
    return Cycle(**defaults)


def _make_recovery(**kwargs) -> Recovery:
    defaults = dict(
        cycle_id=1,
        sleep_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        score_state="SCORED",
    )
    defaults.update(kwargs)
    return Recovery(**defaults)


def _make_sleep(**kwargs) -> Sleep:
    defaults = dict(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        cycle_id=1,
        user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 15, 22, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 16, 6, 0, tzinfo=timezone.utc),
        timezone_offset="-05:00",
        nap=False,
        score_state="SCORED",
    )
    defaults.update(kwargs)
    return Sleep(**defaults)


def _make_workout(**kwargs) -> Workout:
    defaults = dict(
        id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
        timezone_offset="-05:00",
        sport_id=0,
        score_state="SCORED",
    )
    defaults.update(kwargs)
    return Workout(**defaults)


class TestScoreStateLiteral:
    """Tests for score_state Literal type on all four models."""

    def test_score_state_literal_valid(self) -> None:
        """All three valid score_state values pass validation on all four models."""
        for state in ("SCORED", "PENDING_SCORE", "UNSCORABLE"):
            cycle = _make_cycle(score_state=state)
            assert cycle.score_state == state

            recovery = _make_recovery(score_state=state)
            assert recovery.score_state == state

            sleep = _make_sleep(score_state=state)
            assert sleep.score_state == state

            workout = _make_workout(score_state=state)
            assert workout.score_state == state

    def test_score_state_literal_invalid(self) -> None:
        """Invalid score_state value raises ValidationError on all four models."""
        with pytest.raises(ValidationError):
            _make_cycle(score_state="INVALID_STATE")

        with pytest.raises(ValidationError):
            _make_recovery(score_state="INVALID_STATE")

        with pytest.raises(ValidationError):
            _make_sleep(score_state="INVALID_STATE")

        with pytest.raises(ValidationError):
            _make_workout(score_state="INVALID_STATE")
