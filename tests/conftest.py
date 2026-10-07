import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, AsyncMock


# =============================================================================
# WHOOP v2 API response fixtures
#
# Shapes follow the official WHOOP v2 OpenAPI component schemas: sleeps and
# workouts are identified by UUID strings, cycles by integers. Deprecated v1
# fields (``v1_id``, ``sport_id``) are optional and may be absent.
# =============================================================================

@pytest.fixture
def sample_recovery_dict():
    """Full valid WHOOP v2 recovery response dict (sleep_id is a UUID)."""
    return {
        "cycle_id": 123,
        "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "user_id": 789,
        "created_at": "2024-01-15T08:00:00.000Z",
        "updated_at": "2024-01-15T08:30:00.000Z",
        "score_state": "SCORED",
        "score": {
            "user_calibrating": False,
            "recovery_score": 75.5,
            "resting_heart_rate": 52.0,
            "hrv_rmssd_milli": 65.2,
            "spo2_percentage": 98.5,
            "skin_temp_celsius": 36.5,
        },
    }


@pytest.fixture
def sample_sleep_dict():
    """Full valid WHOOP v2 sleep response dict (no deprecated v1_id)."""
    return {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "cycle_id": 100,
        "user_id": 456,
        "created_at": "2024-01-15T08:00:00.000Z",
        "updated_at": "2024-01-15T08:30:00.000Z",
        "start": "2024-01-14T22:30:00.000Z",
        "end": "2024-01-15T06:30:00.000Z",
        "timezone_offset": "-05:00",
        "nap": False,
        "score_state": "SCORED",
        "score": None,
    }


@pytest.fixture
def sample_cycle_dict():
    """Full valid WHOOP v2 cycle response dict. end and step_count are nullable."""
    return {
        "id": 999,
        "user_id": 456,
        "created_at": "2024-01-15T08:00:00.000Z",
        "updated_at": "2024-01-15T20:00:00.000Z",
        "start": "2024-01-15T08:00:00.000Z",
        "end": None,
        "timezone_offset": "-05:00",
        "score_state": "PENDING_SCORE",
        "score": None,
        "step_count": None,
    }


@pytest.fixture
def sample_workout_dict():
    """
    Full valid WHOOP v2 workout response dict.

    sport_name is required in v2. The deprecated sport_id (44 = Yoga) and
    v1_id are included because WHOOP may still send them during migration.
    """
    return {
        "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "v1_id": 1043,
        "user_id": 456,
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-15T11:00:00.000Z",
        "start": "2024-01-15T10:00:00.000Z",
        "end": "2024-01-15T11:00:00.000Z",
        "timezone_offset": "-05:00",
        "sport_name": "yoga",
        "sport_id": 44,
        "score_state": "SCORED",
        "score": {
            "strain": 8.2463,
            "average_heart_rate": 123,
            "max_heart_rate": 146,
            "kilojoule": 1569.34033203125,
            "percent_recorded": 100.0,
            "distance_meter": 1772.77035916,
            "altitude_gain_meter": 46.64384460449,
            "altitude_change_meter": -0.781372010707855,
            "zone_durations": {
                "zone_zero_milli": 300000,
                "zone_one_milli": 600000,
                "zone_two_milli": 900000,
                "zone_three_milli": 900000,
                "zone_four_milli": 600000,
                "zone_five_milli": 300000,
            },
        },
    }


@pytest.fixture
def sample_activity_mapping_dict():
    """WHOOP activity-mapping response: legacy v1 ID mapped to its v2 UUID."""
    return {"v2_activity_id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8"}


@pytest.fixture
def mock_auth_handler():
    mock = MagicMock()
    mock.get_valid_token.return_value = "test_access_token"
    mock.async_get_valid_token = AsyncMock(return_value="test_access_token")
    mock.has_valid_tokens.return_value = True
    mock._is_token_expired.return_value = False
    return mock
