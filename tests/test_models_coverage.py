"""
Targeted tests for whoopyy.models to reach high coverage.

Covers property methods on: BodyMeasurement, StageSummary, SleepNeeded,
SleepScore, Cycle, WorkoutZoneDuration (all zone minutes), Workout,
format_duration, get_sport_name.
"""

from datetime import datetime, timezone

import pytest

from whoopyy.models import (
    BodyMeasurement,
    Cycle,
    CycleCollection,
    CycleScore,
    RecoveryCollection,
    RecoveryScore,
    Recovery,
    Sleep,
    SleepCollection,
    SleepNeeded,
    SleepScore,
    SleepStage,
    StageSummary,
    Workout,
    WorkoutCollection,
    WorkoutScore,
    WorkoutZoneDuration,
    format_duration,
    get_sport_name,
)


class TestBodyMeasurementProperties:
    """Cover height_feet and weight_pounds."""

    def test_height_feet_conversion(self) -> None:
        b = BodyMeasurement(height_meter=1.83)
        assert b.height_feet is not None
        assert abs(b.height_feet - 6.0) < 0.1

    def test_height_feet_none(self) -> None:
        b = BodyMeasurement()
        assert b.height_feet is None

    def test_weight_pounds_conversion(self) -> None:
        b = BodyMeasurement(weight_kilogram=80.0)
        assert b.weight_pounds is not None
        assert abs(b.weight_pounds - 176.4) < 1.0

    def test_weight_pounds_none(self) -> None:
        b = BodyMeasurement()
        assert b.weight_pounds is None


class TestStageSummaryProperties:
    """Cover total_sleep_time_milli, total_sleep_hours, in_bed_hours."""

    def test_total_sleep_time_milli(self) -> None:
        s = StageSummary(
            total_light_sleep_time_milli=3600000,
            total_slow_wave_sleep_time_milli=1800000,
            total_rem_sleep_time_milli=900000,
        )
        assert s.total_sleep_time_milli == 6300000

    def test_total_sleep_hours(self) -> None:
        s = StageSummary(
            total_light_sleep_time_milli=3600000,
            total_slow_wave_sleep_time_milli=3600000,
            total_rem_sleep_time_milli=3600000,
        )
        assert s.total_sleep_hours == 3.0

    def test_in_bed_hours(self) -> None:
        s = StageSummary(total_in_bed_time_milli=28800000)
        assert s.in_bed_hours == 8.0


class TestSleepNeeded:
    """Cover total_needed_milli and total_needed_hours."""

    def test_total_needed_milli(self) -> None:
        sn = SleepNeeded(
            baseline_milli=28800000,
            need_from_sleep_debt_milli=1800000,
            need_from_recent_strain_milli=900000,
            need_from_recent_nap_milli=-900000,
        )
        assert sn.total_needed_milli == 30600000

    def test_total_needed_hours(self) -> None:
        sn = SleepNeeded(baseline_milli=28800000)
        assert sn.total_needed_hours == 8.0


class TestSleepScoreProperties:
    """Cover deep_sleep_hours, rem_sleep_hours, light_sleep_hours, awake_hours, and None fallback."""

    def test_with_stage_summary(self) -> None:
        ss = StageSummary(
            total_slow_wave_sleep_time_milli=5400000,
            total_rem_sleep_time_milli=7200000,
            total_light_sleep_time_milli=14400000,
            total_awake_time_milli=1800000,
        )
        score = SleepScore(stage_summary=ss)
        assert score.deep_sleep_hours == 1.5
        assert score.rem_sleep_hours == 2.0
        assert score.light_sleep_hours == 4.0
        assert score.awake_hours == 0.5

    def test_without_stage_summary(self) -> None:
        score = SleepScore()
        assert score.deep_sleep_hours == 0.0
        assert score.rem_sleep_hours == 0.0
        assert score.light_sleep_hours == 0.0
        assert score.awake_hours == 0.0
        assert score.total_sleep_duration_hours == 0.0


class TestCycleProperties:
    """Cover is_current, duration_hours, is_scored."""

    def _make_cycle(self, end=None, score=None, score_state="PENDING_SCORE"):
        return Cycle(
            id=1,
            user_id=1,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            start=datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc),
            end=end,
            timezone_offset="-05:00",
            score_state=score_state,
            score=score,
        )

    def test_is_current_true(self) -> None:
        c = self._make_cycle(end=None)
        assert c.is_current is True

    def test_is_current_false(self) -> None:
        c = self._make_cycle(end=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc))
        assert c.is_current is False

    def test_duration_hours_none_when_ongoing(self) -> None:
        c = self._make_cycle(end=None)
        assert c.duration_hours is None

    def test_duration_hours_computed(self) -> None:
        c = self._make_cycle(end=datetime(2024, 1, 2, 8, 0, tzinfo=timezone.utc))
        assert c.duration_hours == 24.0

    def test_is_scored_true(self) -> None:
        score = CycleScore(strain=10, kilojoule=2000, average_heart_rate=70, max_heart_rate=150)
        c = self._make_cycle(
            end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            score=score,
            score_state="SCORED",
        )
        assert c.is_scored is True

    def test_is_scored_false(self) -> None:
        c = self._make_cycle()
        assert c.is_scored is False


class TestWorkoutZoneDurationMinutes:
    """Cover all zone_*_minutes and total_minutes with None fields."""

    def test_all_zones_set(self) -> None:
        z = WorkoutZoneDuration(
            zone_zero_milli=60000,
            zone_one_milli=120000,
            zone_two_milli=180000,
            zone_three_milli=240000,
            zone_four_milli=300000,
            zone_five_milli=360000,
        )
        assert z.zone_zero_minutes == 1.0
        assert z.zone_one_minutes == 2.0
        assert z.zone_two_minutes == 3.0
        assert z.zone_three_minutes == 4.0
        assert z.zone_four_minutes == 5.0
        assert z.zone_five_minutes == 6.0
        assert z.total_minutes == 21.0

    def test_all_zones_none(self) -> None:
        z = WorkoutZoneDuration()
        assert z.zone_zero_minutes == 0.0
        assert z.zone_one_minutes == 0.0
        assert z.zone_two_minutes == 0.0
        assert z.zone_three_minutes == 0.0
        assert z.zone_four_minutes == 0.0
        assert z.zone_five_minutes == 0.0
        assert z.total_minutes == 0.0


class TestWorkoutScoreProperties:
    """Cover calories, distance_km, distance_miles."""

    def test_calories(self) -> None:
        ws = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=1000, percent_recorded=100,
        )
        assert ws.calories == 239.0

    def test_distance_km(self) -> None:
        ws = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=1000, percent_recorded=100, distance_meter=5000,
        )
        assert ws.distance_km == 5.0

    def test_distance_km_none(self) -> None:
        ws = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=1000, percent_recorded=100,
        )
        assert ws.distance_km is None

    def test_distance_miles(self) -> None:
        ws = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=1000, percent_recorded=100, distance_meter=1609.34,
        )
        assert abs(ws.distance_miles - 1.0) < 0.01

    def test_distance_miles_none(self) -> None:
        ws = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=1000, percent_recorded=100,
        )
        assert ws.distance_miles is None


class TestWorkoutProperties:
    """Cover sport_display_name, duration_hours, duration_minutes, is_scored."""

    def _make_workout(self, sport_id=0, sport_name=None, score=None, score_state="PENDING_SCORE"):
        return Workout(
            id="w-uuid-1",
            user_id=1,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            start=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=sport_id,
            sport_name=sport_name,
            score_state=score_state,
            score=score,
        )

    def test_sport_display_name_from_sport_name(self) -> None:
        w = self._make_workout(sport_name="mountain_biking")
        assert w.sport_display_name == "Mountain Biking"

    def test_sport_display_name_from_id(self) -> None:
        w = self._make_workout(sport_id=44)
        assert w.sport_display_name == "Yoga"

    def test_sport_display_name_unknown(self) -> None:
        w = self._make_workout(sport_id=99999)
        assert "Unknown" in w.sport_display_name

    def test_duration_hours(self) -> None:
        w = self._make_workout()
        assert w.duration_hours == 1.0

    def test_duration_minutes(self) -> None:
        w = self._make_workout()
        assert w.duration_minutes == 60.0

    def test_is_scored(self) -> None:
        score = WorkoutScore(
            strain=10, average_heart_rate=140, max_heart_rate=170,
            kilojoule=500, percent_recorded=100,
        )
        w = self._make_workout(score=score, score_state="SCORED")
        assert w.is_scored is True


class TestSleepStageProperties:
    """Cover stage_name."""

    def test_stage_name_known(self) -> None:
        for sid, name in [(0, "Awake"), (1, "Light"), (2, "Deep (SWS)"), (3, "REM")]:
            s = SleepStage(stage_id=sid, start_millis=0, end_millis=60000)
            assert s.stage_name == name

    def test_stage_name_unknown(self) -> None:
        s = SleepStage(stage_id=99, start_millis=0, end_millis=60000)
        assert "Unknown" in s.stage_name


class TestSleepProperties:
    """Cover is_scored, duration_minutes."""

    def test_is_scored_true(self) -> None:
        score = SleepScore(sleep_performance_percentage=80.0)
        s = Sleep(
            id="s-1", cycle_id=1, user_id=1,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            start=datetime(2024, 1, 1, 22, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 2, 6, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00", nap=False,
            score_state="SCORED", score=score,
        )
        assert s.is_scored is True
        assert s.duration_minutes == 480.0


class TestRecoveryScoreZones:
    """Cover all three recovery zones."""

    def test_green_zone(self) -> None:
        s = RecoveryScore(
            user_calibrating=False, recovery_score=80, resting_heart_rate=50, hrv_rmssd_milli=60
        )
        assert s.recovery_zone == "green"

    def test_yellow_zone(self) -> None:
        s = RecoveryScore(
            user_calibrating=False, recovery_score=50, resting_heart_rate=50, hrv_rmssd_milli=40
        )
        assert s.recovery_zone == "yellow"

    def test_red_zone(self) -> None:
        s = RecoveryScore(
            user_calibrating=False, recovery_score=20, resting_heart_rate=60, hrv_rmssd_milli=20
        )
        assert s.recovery_zone == "red"


class TestCycleScoreProperties:
    """Cover calories and strain_level."""

    def test_calories(self) -> None:
        cs = CycleScore(strain=10, kilojoule=2000, average_heart_rate=70, max_heart_rate=150)
        assert cs.calories > 0

    def test_strain_level_light(self) -> None:
        cs = CycleScore(strain=5, kilojoule=1000, average_heart_rate=60, max_heart_rate=120)
        assert cs.strain_level == "Light"

    def test_strain_level_moderate(self) -> None:
        cs = CycleScore(strain=12, kilojoule=2000, average_heart_rate=70, max_heart_rate=150)
        assert cs.strain_level == "Moderate"

    def test_strain_level_strenuous(self) -> None:
        cs = CycleScore(strain=16, kilojoule=3000, average_heart_rate=80, max_heart_rate=170)
        assert cs.strain_level == "Strenuous"

    def test_strain_level_all_out(self) -> None:
        cs = CycleScore(strain=19, kilojoule=4000, average_heart_rate=90, max_heart_rate=190)
        assert cs.strain_level == "All Out"


class TestFormatDuration:
    """Cover format_duration edge cases."""

    def test_hours_and_minutes(self) -> None:
        assert format_duration(5400000) == "1h 30m"

    def test_minutes_only(self) -> None:
        assert format_duration(300000) == "5m"

    def test_zero(self) -> None:
        assert format_duration(0) == "0m"

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            format_duration(-1)


class TestGetSportName:
    """Cover get_sport_name."""

    def test_known_sport(self) -> None:
        assert get_sport_name(0) == "Running"
        assert get_sport_name(44) == "Yoga"

    def test_unknown_sport(self) -> None:
        result = get_sport_name(99999)
        assert "Unknown" in result


class TestCollectionLen:
    """Cover __len__ on all Collection classes."""

    def test_recovery_collection_len(self) -> None:
        c = RecoveryCollection(records=[])
        assert len(c) == 0

    def test_sleep_collection_len(self) -> None:
        c = SleepCollection(records=[])
        assert len(c) == 0

    def test_cycle_collection_len(self) -> None:
        c = CycleCollection(records=[])
        assert len(c) == 0

    def test_workout_collection_len(self) -> None:
        c = WorkoutCollection(records=[])
        assert len(c) == 0
