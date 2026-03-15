import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def sample_recovery_dict():
    """Full valid WHOOP API recovery response dict."""
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
    """Full valid WHOOP API sleep response dict."""
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
    """Full valid WHOOP API cycle response dict. end is nullable for ongoing cycles."""
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
    }


@pytest.fixture
def sample_workout_dict():
    """Full valid WHOOP API workout response dict with sport_id=44 (Yoga)."""
    return {
        "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "user_id": 456,
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-01-15T11:00:00.000Z",
        "start": "2024-01-15T10:00:00.000Z",
        "end": "2024-01-15T11:00:00.000Z",
        "timezone_offset": "-05:00",
        "sport_id": 44,
        "score_state": "SCORED",
        "score": None,
    }


@pytest.fixture
def mock_auth_handler():
    mock = MagicMock()
    mock.get_valid_token.return_value = "test_access_token"
    mock.async_get_valid_token = AsyncMock(return_value="test_access_token")
    mock.has_valid_tokens.return_value = True
    mock._is_token_expired.return_value = False
    return mock
