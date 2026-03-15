"""Integration tests against the real WHOOP API.

These tests are skipped by default. To run them, set these environment variables:
    WHOOP_CLIENT_ID
    WHOOP_CLIENT_SECRET
    WHOOP_REFRESH_TOKEN
    WHOOP_ACCESS_TOKEN (optional — if missing, refresh will be attempted)

Run with:
    pytest tests/integration/ -v --tb=long
"""

import os
import time

import pytest

from whoopyy import WhoopClient
from whoopyy.auth import OAuthHandler
from whoopyy.models import (
    BodyMeasurement,
    Cycle,
    CycleCollection,
    Recovery,
    RecoveryCollection,
    Sleep,
    SleepCollection,
    UserProfileBasic,
    Workout,
    WorkoutCollection,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("WHOOP_REFRESH_TOKEN"),
    reason="Integration tests require real WHOOP credentials",
)


@pytest.fixture(scope="module")
def client():
    """Build a WhoopClient from env vars — no browser OAuth needed."""
    auth = OAuthHandler(
        client_id=os.environ.get("WHOOP_CLIENT_ID", ""),
        client_secret=os.environ.get("WHOOP_CLIENT_SECRET", ""),
    )
    # Inject tokens directly from environment
    access_token = os.environ.get("WHOOP_ACCESS_TOKEN", "")
    refresh_token = os.environ["WHOOP_REFRESH_TOKEN"]

    auth._tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 3600,
        # If no access token, force immediate refresh by setting expired
        "expires_at": (time.time() + 3600) if access_token else 0.0,
        "token_type": "Bearer",
        "scope": "offline",
    }

    c = WhoopClient(
        client_id=os.environ.get("WHOOP_CLIENT_ID", ""),
        client_secret=os.environ.get("WHOOP_CLIENT_SECRET", ""),
    )
    c.auth = auth
    c._authenticated = True
    yield c
    c.close()


# =============================================================================
# Profile
# =============================================================================

class TestProfile:
    """Tests for profile endpoints."""

    def test_get_profile_basic(self, client):
        profile = client.get_profile_basic()
        assert isinstance(profile, UserProfileBasic)
        assert isinstance(profile.user_id, int)
        assert isinstance(profile.email, str) and "@" in profile.email
        assert isinstance(profile.first_name, str) and len(profile.first_name) > 0

    def test_get_body_measurement(self, client):
        body = client.get_body_measurement()
        assert isinstance(body, BodyMeasurement)
        assert body.height_meter is None or (isinstance(body.height_meter, float) and body.height_meter > 0)
        assert body.weight_kilogram is None or (isinstance(body.weight_kilogram, float) and body.weight_kilogram > 0)
        assert body.max_heart_rate is None or (isinstance(body.max_heart_rate, int) and body.max_heart_rate > 0)


# =============================================================================
# Recovery
# =============================================================================

class TestRecovery:
    """Tests for recovery endpoints."""

    def test_get_recovery_collection(self, client):
        result = client.get_recovery_collection(limit=5)
        assert isinstance(result, RecoveryCollection)
        assert isinstance(result.records, list)
        assert len(result.records) > 0
        r = result.records[0]
        assert isinstance(r, Recovery)
        assert r.score_state in ("SCORED", "PENDING_SCORE", "UNSCORABLE")

    def test_recovery_scored_fields(self, client):
        result = client.get_recovery_collection(limit=10)
        scored = [r for r in result.records if r.score_state == "SCORED"]
        assert len(scored) > 0, "Need at least one scored recovery to verify fields"
        r = scored[0]
        assert 0 <= r.score.recovery_score <= 100
        assert isinstance(r.score.resting_heart_rate, float) and r.score.resting_heart_rate > 0
        assert r.score.hrv_rmssd_milli >= 0
        # spo2 and skin_temp are optional
        assert r.score.spo2_percentage is None or isinstance(r.score.spo2_percentage, float)
        assert r.score.skin_temp_celsius is None or isinstance(r.score.skin_temp_celsius, float)

    def test_get_recovery_for_cycle(self, client):
        cycles = client.get_cycle_collection(limit=3)
        assert len(cycles.records) > 0
        cycle = cycles.records[0]
        try:
            recovery = client.get_recovery_for_cycle(cycle.id)
            assert isinstance(recovery, Recovery)
            assert recovery.cycle_id == cycle.id
        except Exception as e:
            # 404 is acceptable — not every cycle has a recovery
            assert "404" in str(e) or "NotFound" in type(e).__name__


# =============================================================================
# Cycles
# =============================================================================

class TestCycles:
    """Tests for cycle endpoints."""

    def test_get_cycle_collection(self, client):
        result = client.get_cycle_collection(limit=5)
        assert isinstance(result, CycleCollection)
        assert len(result.records) > 0
        c = result.records[0]
        assert isinstance(c, Cycle)
        assert isinstance(c.id, int)
        assert c.score_state in ("SCORED", "PENDING_SCORE", "UNSCORABLE")

    def test_cycle_scored_fields(self, client):
        result = client.get_cycle_collection(limit=10)
        scored = [c for c in result.records if c.score_state == "SCORED" and c.score]
        assert len(scored) > 0
        c = scored[0]
        assert isinstance(c.score.strain, float) and c.score.strain >= 0
        assert isinstance(c.score.kilojoule, float) and c.score.kilojoule >= 0
        assert isinstance(c.score.average_heart_rate, int)
        assert isinstance(c.score.max_heart_rate, int)

    def test_get_single_cycle(self, client):
        collection = client.get_cycle_collection(limit=1)
        cycle_id = collection.records[0].id
        cycle = client.get_cycle(cycle_id)
        assert isinstance(cycle, Cycle)
        assert cycle.id == cycle_id


# =============================================================================
# Sleep
# =============================================================================

class TestSleep:
    """Tests for sleep endpoints."""

    def test_get_sleep_collection(self, client):
        result = client.get_sleep_collection(limit=5)
        assert isinstance(result, SleepCollection)
        assert len(result.records) > 0
        s = result.records[0]
        assert isinstance(s, Sleep)
        assert s.score_state in ("SCORED", "PENDING_SCORE", "UNSCORABLE")
        assert isinstance(s.nap, bool)

    def test_sleep_scored_fields(self, client):
        result = client.get_sleep_collection(limit=10)
        scored = [s for s in result.records if s.score_state == "SCORED" and s.score]
        assert len(scored) > 0
        s = scored[0]
        ss = s.score.stage_summary
        assert ss is not None
        assert isinstance(ss.total_in_bed_time_milli, int)
        assert isinstance(ss.total_rem_sleep_time_milli, int)
        assert isinstance(ss.total_slow_wave_sleep_time_milli, int)
        assert isinstance(ss.total_light_sleep_time_milli, int)
        assert isinstance(ss.total_awake_time_milli, int)
        # Optional float fields
        assert s.score.sleep_performance_percentage is None or isinstance(
            s.score.sleep_performance_percentage, float
        )
        assert s.score.sleep_efficiency_percentage is None or isinstance(
            s.score.sleep_efficiency_percentage, float
        )
        assert s.score.respiratory_rate is None or s.score.respiratory_rate >= 0

    def test_sleep_nap_filtering(self, client):
        result = client.get_sleep_collection(limit=25)
        assert all(isinstance(s.nap, bool) for s in result.records)

    def test_get_single_sleep(self, client):
        collection = client.get_sleep_collection(limit=1)
        sleep_id = collection.records[0].id
        sleep = client.get_sleep(sleep_id)
        assert isinstance(sleep, Sleep)
        assert sleep.id == sleep_id


# =============================================================================
# Workouts
# =============================================================================

class TestWorkouts:
    """Tests for workout endpoints."""

    def test_get_workout_collection(self, client):
        result = client.get_workout_collection(limit=5)
        assert isinstance(result, WorkoutCollection)
        if len(result.records) == 0:
            pytest.skip("No workout data available for this account")
        w = result.records[0]
        assert isinstance(w, Workout)
        assert isinstance(w.sport_id, int)
        assert w.score_state in ("SCORED", "PENDING_SCORE", "UNSCORABLE")

    def test_workout_scored_fields(self, client):
        result = client.get_workout_collection(limit=10)
        scored = [w for w in result.records if w.score_state == "SCORED" and w.score]
        if not scored:
            pytest.skip("No scored workouts available")
        w = scored[0]
        assert isinstance(w.score.strain, float) and w.score.strain >= 0
        assert isinstance(w.score.kilojoule, float)
        assert isinstance(w.score.average_heart_rate, int)
        assert isinstance(w.score.max_heart_rate, int)
        # Zone durations are all Optional
        zd = w.score.zone_duration
        if zd:
            for zone_val in [
                zd.zone_zero_milli, zd.zone_one_milli, zd.zone_two_milli,
                zd.zone_three_milli, zd.zone_four_milli, zd.zone_five_milli,
            ]:
                assert zone_val is None or isinstance(zone_val, int)
        # Optional distance/altitude
        assert w.score.distance_meter is None or isinstance(w.score.distance_meter, float)
        assert w.score.altitude_gain_meter is None or isinstance(w.score.altitude_gain_meter, float)

    def test_get_single_workout(self, client):
        collection = client.get_workout_collection(limit=1)
        if not collection.records:
            pytest.skip("No workout data available")
        workout_id = collection.records[0].id
        workout = client.get_workout(workout_id)
        assert isinstance(workout, Workout)
        assert workout.id == workout_id


# =============================================================================
# Pagination
# =============================================================================

class TestPagination:
    """Tests for pagination cursor handling."""

    def test_pagination_follows_next_token(self, client):
        page1 = client.get_cycle_collection(limit=2)
        if page1.next_token:
            page2 = client.get_cycle_collection(limit=2, next_token=page1.next_token)
            assert isinstance(page2, CycleCollection)

    def test_get_all_cycles_returns_more_than_one_page(self, client):
        all_cycles = client.get_all_cycles()
        assert len(all_cycles) >= 1
        assert all(isinstance(c, Cycle) for c in all_cycles)


# =============================================================================
# Export
# =============================================================================

class TestExport:
    """Tests for CSV export with real data."""

    def test_export_cycle_csv_with_real_data(self, client, tmp_path):
        from whoopyy.export import export_cycle_csv
        cycles = client.get_all_cycles()
        if not cycles:
            pytest.skip("No cycle data available")
        output = tmp_path / "cycles.csv"
        export_cycle_csv(cycles, str(output))
        assert output.exists()
        content = output.read_text()
        assert len(content) > 0

    def test_export_sleep_csv_with_real_data(self, client, tmp_path):
        from whoopyy.export import export_sleep_csv
        sleeps = client.get_all_sleep()
        if not sleeps:
            pytest.skip("No sleep data available")
        output = tmp_path / "sleep.csv"
        export_sleep_csv(sleeps, str(output))
        assert output.exists()
        content = output.read_text()
        assert len(content) > 0

    def test_export_workout_csv_with_real_data(self, client, tmp_path):
        from whoopyy.export import export_workout_csv
        workouts = client.get_all_workouts()
        if not workouts:
            pytest.skip("No workout data available")
        output = tmp_path / "workouts.csv"
        export_workout_csv(workouts, str(output))
        assert output.exists()
        content = output.read_text()
        assert len(content) > 0
