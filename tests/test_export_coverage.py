"""
Targeted tests for whoopyy.export to boost branch coverage.

Covers: empty/unscored record paths, report with empty data, file output.
"""

import tempfile
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest

from whoopyy.export import (
    export_cycle_csv,
    export_recovery_csv,
    export_sleep_csv,
    export_workout_csv,
    generate_summary_report,
)
from whoopyy.models import (
    Cycle,
    CycleScore,
    Recovery,
    RecoveryScore,
    Sleep,
    SleepScore,
    Workout,
    WorkoutScore,
)


def _make_recovery(scored=True, score_val=75.0):
    score = RecoveryScore(
        user_calibrating=False, recovery_score=score_val,
        resting_heart_rate=52, hrv_rmssd_milli=60,
    ) if scored else None
    return Recovery(
        cycle_id=1, sleep_id="uuid-1", user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        score_state="SCORED" if scored else "PENDING_SCORE",
        score=score,
    )


def _make_cycle(scored=True):
    score = CycleScore(
        strain=12, kilojoule=2000, average_heart_rate=70, max_heart_rate=150,
    ) if scored else None
    return Cycle(
        id=1, user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 16, 8, 0, tzinfo=timezone.utc),
        timezone_offset="-05:00",
        score_state="SCORED" if scored else "PENDING_SCORE",
        score=score,
    )


def _make_sleep(scored=True, nap=False):
    score = SleepScore(
        sleep_performance_percentage=85.0,
        sleep_efficiency_percentage=90.0,
        respiratory_rate=14.0,
    ) if scored else None
    return Sleep(
        id="s-1", cycle_id=1, user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 14, 22, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 15, 6, 0, tzinfo=timezone.utc),
        timezone_offset="-05:00", nap=nap,
        score_state="SCORED" if scored else "PENDING_SCORE",
        score=score,
    )


def _make_workout(scored=True):
    score = WorkoutScore(
        strain=10, average_heart_rate=140, max_heart_rate=170,
        kilojoule=500, percent_recorded=100,
    ) if scored else None
    return Workout(
        id="w-1", user_id=1,
        created_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        start=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        end=datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
        timezone_offset="-05:00", sport_id=0,
        score_state="SCORED" if scored else "PENDING_SCORE",
        score=score,
    )


class TestExportEmptyLists:
    """Cover empty-list and no-scored-records branches."""

    def test_recovery_csv_empty(self, tmp_path) -> None:
        assert export_recovery_csv([], str(tmp_path / "r.csv")) == 0

    def test_recovery_csv_all_unscored(self, tmp_path) -> None:
        r = _make_recovery(scored=False)
        assert export_recovery_csv([r], str(tmp_path / "r.csv")) == 0

    def test_cycle_csv_empty(self, tmp_path) -> None:
        assert export_cycle_csv([], str(tmp_path / "c.csv")) == 0

    def test_cycle_csv_all_unscored(self, tmp_path) -> None:
        c = _make_cycle(scored=False)
        assert export_cycle_csv([c], str(tmp_path / "c.csv")) == 0

    def test_sleep_csv_empty(self, tmp_path) -> None:
        assert export_sleep_csv([], str(tmp_path / "s.csv")) == 0

    def test_sleep_csv_all_unscored(self, tmp_path) -> None:
        s = _make_sleep(scored=False)
        assert export_sleep_csv([s], str(tmp_path / "s.csv")) == 0

    def test_workout_csv_empty(self, tmp_path) -> None:
        assert export_workout_csv([], str(tmp_path / "w.csv")) == 0

    def test_workout_csv_all_unscored(self, tmp_path) -> None:
        w = _make_workout(scored=False)
        assert export_workout_csv([w], str(tmp_path / "w.csv")) == 0


class TestExportIncludeUnscored:
    """Cover include_unscored paths that emit blank rows."""

    def test_recovery_csv_include_unscored(self, tmp_path) -> None:
        r = _make_recovery(scored=False)
        fp = str(tmp_path / "r.csv")
        count = export_recovery_csv([r], fp, include_unscored=True)
        assert count == 1
        content = Path(fp).read_text()
        assert "PENDING_SCORE" in content

    def test_cycle_csv_include_unscored(self, tmp_path) -> None:
        c = _make_cycle(scored=False)
        fp = str(tmp_path / "c.csv")
        count = export_cycle_csv([c], fp, include_unscored=True)
        assert count == 1

    def test_sleep_csv_include_unscored(self, tmp_path) -> None:
        s = _make_sleep(scored=False)
        fp = str(tmp_path / "s.csv")
        count = export_sleep_csv([s], fp, include_unscored=True)
        assert count == 1

    def test_workout_csv_include_unscored(self, tmp_path) -> None:
        w = _make_workout(scored=False)
        fp = str(tmp_path / "w.csv")
        count = export_workout_csv([w], fp, include_unscored=True)
        assert count == 1


class TestSleepCsvNapFiltering:
    """Cover the sleep CSV nap-filter + empty-after-filter branch."""

    def test_exclude_naps_all_naps(self, tmp_path) -> None:
        s = _make_sleep(scored=True, nap=True)
        fp = str(tmp_path / "s.csv")
        count = export_sleep_csv([s], fp, include_naps=False)
        assert count == 0


class TestReportOutputToStream:
    """Cover writing report to file-like object (TextIO)."""

    def test_report_to_stringio(self) -> None:
        r = _make_recovery()
        s = _make_sleep()
        c = _make_cycle()
        buf = StringIO()
        report = generate_summary_report([r], [s], [c], output=buf)
        buf.seek(0)
        assert buf.read() == report


class TestReportRedZone:
    """Cover the 'red zone' recommendation branch."""

    def test_red_zone_recommendation(self) -> None:
        r = _make_recovery(scored=True, score_val=20.0)
        s = _make_sleep()
        c = _make_cycle()
        report = generate_summary_report([r], [s], [c])
        assert "RED" in report


class TestReportYellowZone:
    """Cover the 'yellow zone' recommendation branch."""

    def test_yellow_zone_recommendation(self) -> None:
        r = _make_recovery(scored=True, score_val=50.0)
        s = _make_sleep()
        c = _make_cycle()
        report = generate_summary_report([r], [s], [c])
        assert "YELLOW" in report
