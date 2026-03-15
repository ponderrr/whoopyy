"""
Unit tests for WhoopPy export utilities.

Tests cover:
- CSV export functions
- Trend analysis functions
- Report generation
- Moving average calculation
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from whoopyy.export import (
    RecoveryTrends,
    SleepTrends,
    TrainingLoadTrends,
    analyze_recovery_trends,
    analyze_sleep_trends,
    analyze_training_load,
    calculate_moving_average,
    export_cycle_csv,
    export_recovery_csv,
    export_sleep_csv,
    export_workout_csv,
    generate_summary_report,
)
from whoopyy.models import (
    Cycle,
    CycleStrain,
    Recovery,
    RecoveryScore,
    Sleep,
    SleepScore,
    Workout,
    WorkoutScore,
    WorkoutZoneDuration,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_recovery_score():
    """Create a sample recovery score."""
    return RecoveryScore(
        user_calibrating=False,
        recovery_score=75.0,
        resting_heart_rate=52,
        hrv_rmssd_milli=65.0,
        spo2_percentage=98.0,
        skin_temp_celsius=36.5,
    )


@pytest.fixture
def sample_recoveries(sample_recovery_score):
    """Create a list of sample recovery records."""
    recoveries = []
    for i in range(14):
        # Vary the score for more realistic data
        score = RecoveryScore(
            user_calibrating=False,
            recovery_score=50 + (i * 3) % 40,  # Scores between 50-87
            resting_heart_rate=50 + i % 5,
            hrv_rmssd_milli=55 + i * 2,
        )
        recovery = Recovery(
            cycle_id=i + 1,
            sleep_id=i + 1,
            user_id=12345,
            created_at=datetime(2024, 1, 15 - i, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15 - i, 8, 30, 0, tzinfo=timezone.utc),
            score_state="SCORED",
            score=score,
        )
        recoveries.append(recovery)
    return recoveries


@pytest.fixture
def sample_sleep_score():
    """Create a sample sleep score."""
    return SleepScore(
        stage_summary={
            "total_light_sleep_time_milli": 14400000,  # 4 hours
            "total_slow_wave_sleep_time_milli": 5400000,  # 1.5 hours
            "total_rem_sleep_time_milli": 7200000,  # 2 hours
            "total_awake_time_milli": 1800000,  # 0.5 hours
        },
        sleep_needed={},
        respiratory_rate=14.5,
        sleep_performance_percentage=85.0,
        sleep_consistency_percentage=90.0,
        sleep_efficiency_percentage=92.0,
    )


@pytest.fixture
def sample_sleeps(sample_sleep_score):
    """Create a list of sample sleep records."""
    sleeps = []
    for i in range(10):
        score = SleepScore(
            stage_summary={},
            sleep_needed={},
            respiratory_rate=14.0 + i * 0.1,
            sleep_performance_percentage=80 + i % 15,
            sleep_consistency_percentage=85.0,
            sleep_efficiency_percentage=88 + i % 10,
        )
        sleep = Sleep(
            id=i + 1,
            user_id=12345,
            created_at=datetime(2024, 1, 15 - i, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15 - i, 8, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 14 - i, 22, 30, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15 - i, 6, 30, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            nap=i == 5,  # One nap in the middle
            score_state="SCORED",
            score=score,
        )
        sleeps.append(sleep)
    return sleeps


@pytest.fixture
def sample_cycles():
    """Create a list of sample cycle records."""
    cycles = []
    for i in range(10):
        score = CycleStrain(
            score=8 + (i * 2) % 10,  # Strain 8-17
            average_heart_rate=70 + i * 2,
            max_heart_rate=150 + i * 5,
            kilojoule=2000 + i * 200,
            zone_duration={
                "zone_zero_milli": 3600000,
                "zone_one_milli": 7200000,
                "zone_two_milli": 5400000,
                "zone_three_milli": 3600000,
                "zone_four_milli": 1800000,
                "zone_five_milli": 600000,
            },
        )
        cycle = Cycle(
            id=i + 1,
            user_id=12345,
            created_at=datetime(2024, 1, 15 - i, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15 - i, 20, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15 - i, 8, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 16 - i, 8, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            score_state="SCORED",
            score=score,
        )
        cycles.append(cycle)
    return cycles


@pytest.fixture
def sample_workouts():
    """Create a list of sample workout records."""
    workouts = []
    for i in range(5):
        zone_duration = WorkoutZoneDuration(
            zone_zero_milli=60000,
            zone_one_milli=300000,
            zone_two_milli=600000,
            zone_three_milli=900000,
            zone_four_milli=300000,
            zone_five_milli=60000,
        )
        score = WorkoutScore(
            strain=10 + i,
            average_heart_rate=130 + i * 5,
            max_heart_rate=170 + i * 3,
            kilojoule=500 + i * 100,
            percent_recorded=98.0,
            zone_duration=zone_duration,
            distance_meter=5000 + i * 1000,
            altitude_gain_meter=50 + i * 10,
            altitude_change_meter=10 + i * 5,
        )
        workout = Workout(
            id=i + 1,
            user_id=12345,
            created_at=datetime(2024, 1, 15 - i, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15 - i, 11, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15 - i, 10, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15 - i, 11, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            sport_id=0,  # Running
            score_state="SCORED",
            score=score,
        )
        workouts.append(workout)
    return workouts


# =============================================================================
# Recovery Analysis Tests
# =============================================================================

class TestAnalyzeRecoveryTrends:
    """Tests for analyze_recovery_trends function."""
    
    def test_basic_analysis(self, sample_recoveries) -> None:
        """Test basic recovery trend analysis."""
        trends = analyze_recovery_trends(sample_recoveries)
        
        assert isinstance(trends, RecoveryTrends)
        assert trends.record_count == 14
        assert 0 <= trends.average_score <= 100
        assert trends.min_score <= trends.average_score <= trends.max_score
    
    def test_recovery_zones(self, sample_recoveries) -> None:
        """Test recovery zone distribution."""
        trends = analyze_recovery_trends(sample_recoveries)
        
        total_days = trends.green_days + trends.yellow_days + trends.red_days
        assert total_days == trends.record_count
    
    def test_hrv_coefficient_of_variation(self, sample_recoveries) -> None:
        """Test HRV stability metric."""
        trends = analyze_recovery_trends(sample_recoveries)
        
        assert trends.hrv_coefficient_of_variation >= 0
    
    def test_empty_recoveries_raises_error(self) -> None:
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError, match="No scored recovery records"):
            analyze_recovery_trends([])
    
    def test_unscored_recoveries_raises_error(self) -> None:
        """Test that records without scores raise ValueError."""
        unscored = Recovery(
            cycle_id=1,
            sleep_id=1,
            user_id=12345,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            score_state="PENDING",
            score=None,
        )
        with pytest.raises(ValueError, match="No scored recovery records"):
            analyze_recovery_trends([unscored])


# =============================================================================
# Sleep Analysis Tests
# =============================================================================

class TestAnalyzeSleepTrends:
    """Tests for analyze_sleep_trends function."""
    
    def test_basic_analysis(self, sample_sleeps) -> None:
        """Test basic sleep trend analysis."""
        trends = analyze_sleep_trends(sample_sleeps, include_naps=False)
        
        assert isinstance(trends, SleepTrends)
        assert trends.record_count > 0
        assert 0 <= trends.average_performance <= 100
        assert 0 <= trends.consistency_score <= 100
    
    def test_nap_counting(self, sample_sleeps) -> None:
        """Test that naps are counted correctly."""
        trends = analyze_sleep_trends(sample_sleeps, include_naps=False)
        
        assert trends.nap_count == 1  # We set one nap in fixtures
    
    def test_empty_sleeps_raises_error(self) -> None:
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError, match="No scored sleep records"):
            analyze_sleep_trends([])


# =============================================================================
# Training Load Analysis Tests
# =============================================================================

class TestAnalyzeTrainingLoad:
    """Tests for analyze_training_load function."""
    
    def test_basic_analysis(self, sample_cycles) -> None:
        """Test basic training load analysis."""
        trends = analyze_training_load(sample_cycles)
        
        assert isinstance(trends, TrainingLoadTrends)
        assert trends.record_count == 10
        assert trends.total_strain > 0
        assert trends.average_daily_strain > 0
    
    def test_strain_distribution(self, sample_cycles) -> None:
        """Test strain distribution calculation."""
        trends = analyze_training_load(sample_cycles)
        
        total_days = (
            trends.low_strain_days + 
            trends.moderate_strain_days + 
            trends.high_strain_days
        )
        assert total_days == trends.record_count
    
    def test_with_workouts(self, sample_cycles, sample_workouts) -> None:
        """Test analysis with workout data included."""
        trends = analyze_training_load(sample_cycles, sample_workouts)
        
        assert trends.workout_count == 5
        assert trends.total_workout_minutes > 0
    
    def test_empty_cycles_raises_error(self) -> None:
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError, match="No scored cycle records"):
            analyze_training_load([])


# =============================================================================
# CSV Export Tests
# =============================================================================

class TestExportRecoveryCsv:
    """Tests for export_recovery_csv function."""
    
    def test_basic_export(self, sample_recoveries) -> None:
        """Test basic CSV export."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_recovery_csv(sample_recoveries, filepath)
            
            assert count == 14
            assert filepath.exists()
            
            # Verify file has content
            content = filepath.read_text()
            assert "Recovery Score" in content
            assert "HRV (ms)" in content
        finally:
            filepath.unlink(missing_ok=True)
    
    def test_empty_list_returns_zero(self) -> None:
        """Test that empty list returns 0."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_recovery_csv([], filepath)
            assert count == 0
        finally:
            filepath.unlink(missing_ok=True)


class TestExportSleepCsv:
    """Tests for export_sleep_csv function."""
    
    def test_basic_export(self, sample_sleeps) -> None:
        """Test basic CSV export."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_sleep_csv(sample_sleeps, filepath)
            
            assert count == 10
            assert filepath.exists()
        finally:
            filepath.unlink(missing_ok=True)
    
    def test_exclude_naps(self, sample_sleeps) -> None:
        """Test excluding naps from export."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_sleep_csv(sample_sleeps, filepath, include_naps=False)
            
            # Should exclude the one nap
            assert count == 9
        finally:
            filepath.unlink(missing_ok=True)


class TestExportCycleCsv:
    """Tests for export_cycle_csv function."""
    
    def test_basic_export(self, sample_cycles) -> None:
        """Test basic CSV export."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_cycle_csv(sample_cycles, filepath)
            
            assert count == 10
            assert filepath.exists()
        finally:
            filepath.unlink(missing_ok=True)


class TestExportWorkoutCsv:
    """Tests for export_workout_csv function."""
    
    def test_basic_export(self, sample_workouts) -> None:
        """Test basic CSV export."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)
        
        try:
            count = export_workout_csv(sample_workouts, filepath)
            
            assert count == 5
            assert filepath.exists()
            
            content = filepath.read_text()
            assert "Running" in content  # Sport name
            assert "Strain" in content
        finally:
            filepath.unlink(missing_ok=True)


# =============================================================================
# Report Generation Tests
# =============================================================================

class TestGenerateSummaryReport:
    """Tests for generate_summary_report function."""
    
    def test_basic_report(
        self, sample_recoveries, sample_sleeps, sample_cycles, sample_workouts
    ) -> None:
        """Test basic report generation."""
        report = generate_summary_report(
            sample_recoveries, sample_sleeps, sample_cycles, sample_workouts
        )
        
        assert isinstance(report, str)
        assert "WHOOP DATA SUMMARY REPORT" in report
        assert "RECOVERY METRICS" in report
        assert "SLEEP METRICS" in report
        assert "TRAINING LOAD" in report
        assert "RECOMMENDATIONS" in report
    
    def test_report_to_file(
        self, sample_recoveries, sample_sleeps, sample_cycles
    ) -> None:
        """Test saving report to file."""
        with tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="w"
        ) as f:
            filepath = Path(f.name)
        
        try:
            report = generate_summary_report(
                sample_recoveries, sample_sleeps, sample_cycles,
                output=filepath,
            )
            
            assert filepath.exists()
            content = filepath.read_text()
            assert content == report
        finally:
            filepath.unlink(missing_ok=True)


# =============================================================================
# Moving Average Tests
# =============================================================================

class TestCalculateMovingAverage:
    """Tests for calculate_moving_average function."""
    
    def test_basic_moving_average(self) -> None:
        """Test basic moving average calculation."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        ma = calculate_moving_average(values, window=3)
        
        assert len(ma) == 5
        assert ma[0] is None
        assert ma[1] is None
        assert ma[2] == pytest.approx(20.0)  # (10+20+30)/3
        assert ma[3] == pytest.approx(30.0)  # (20+30+40)/3
        assert ma[4] == pytest.approx(40.0)  # (30+40+50)/3
    
    def test_window_of_one(self) -> None:
        """Test with window size of 1."""
        values = [10.0, 20.0, 30.0]
        ma = calculate_moving_average(values, window=1)
        
        assert ma == [10.0, 20.0, 30.0]
    
    def test_empty_list(self) -> None:
        """Test with empty list."""
        ma = calculate_moving_average([], window=3)
        assert ma == []
    
    def test_invalid_window_raises_error(self) -> None:
        """Test that invalid window raises ValueError."""
        with pytest.raises(ValueError, match="Window must be at least 1"):
            calculate_moving_average([1.0, 2.0, 3.0], window=0)


# =============================================================================
# Bug-fix Regression Tests
# =============================================================================

class TestExportCycleCsvNoAttributeError:
    """Regression tests for cycle.score.strain (was .score) bug."""

    def test_export_cycle_csv_no_attribute_error(self) -> None:
        """Calling export_cycle_csv on a scored Cycle should not raise AttributeError."""
        from whoopyy.models import CycleScore

        score = CycleScore(
            strain=12.5,
            kilojoule=2000.0,
            average_heart_rate=75,
            max_heart_rate=160,
        )
        cycle = Cycle(
            id=1,
            user_id=12345,
            created_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 16, 8, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            score_state="SCORED",
            score=score,
        )

        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)

        try:
            count = export_cycle_csv([cycle], filepath)
            assert count == 1
        finally:
            filepath.unlink(missing_ok=True)

    def test_analyze_training_load_no_attribute_error(self) -> None:
        """analyze_training_load with a scored Cycle should not raise AttributeError."""
        from whoopyy.models import CycleScore

        score = CycleScore(
            strain=10.0,
            kilojoule=1800.0,
            average_heart_rate=70,
            max_heart_rate=155,
        )
        cycle = Cycle(
            id=2,
            user_id=12345,
            created_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 16, 8, 0, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            score_state="SCORED",
            score=score,
        )

        trends = analyze_training_load([cycle])
        assert trends.total_strain == pytest.approx(10.0)


class TestExportSleepCsvAttributeAccess:
    """Regression tests for StageSummary dict vs. attribute access bug."""

    def test_export_sleep_csv_stage_summary_access(self) -> None:
        """export_sleep_csv with a non-None StageSummary should not raise AttributeError."""
        from whoopyy.models import StageSummary, SleepNeeded

        stage_summary = StageSummary(
            total_in_bed_time_milli=28800000,
            total_awake_time_milli=1800000,
            total_no_data_time_milli=0,
            total_light_sleep_time_milli=14400000,
            total_slow_wave_sleep_time_milli=5400000,
            total_rem_sleep_time_milli=7200000,
            sleep_cycle_count=4,
            disturbance_count=2,
        )
        score = SleepScore(
            stage_summary=stage_summary,
            sleep_needed=SleepNeeded(),
            respiratory_rate=14.5,
            sleep_performance_percentage=85.0,
            sleep_consistency_percentage=90.0,
            sleep_efficiency_percentage=92.0,
        )
        sleep = Sleep(
            id="sleep-uuid-001",
            cycle_id=1,
            user_id=12345,
            created_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 14, 22, 30, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 6, 30, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            nap=False,
            score_state="SCORED",
            score=score,
        )

        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)

        try:
            count = export_sleep_csv([sleep], filepath)
            assert count == 1
        finally:
            filepath.unlink(missing_ok=True)

    def test_export_sleep_csv_none_score_fields(self) -> None:
        """export_sleep_csv with None optional score fields should not raise TypeError."""
        score = SleepScore(
            stage_summary=None,
            sleep_needed=None,
            respiratory_rate=None,
            sleep_performance_percentage=None,
            sleep_consistency_percentage=None,
            sleep_efficiency_percentage=None,
        )
        sleep = Sleep(
            id="sleep-uuid-002",
            cycle_id=2,
            user_id=12345,
            created_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
            start=datetime(2024, 1, 14, 22, 30, 0, tzinfo=timezone.utc),
            end=datetime(2024, 1, 15, 6, 30, 0, tzinfo=timezone.utc),
            timezone_offset="-05:00",
            nap=False,
            score_state="SCORED",
            score=score,
        )

        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = Path(f.name)

        try:
            count = export_sleep_csv([sleep], filepath)
            assert count == 1
        finally:
            filepath.unlink(missing_ok=True)
