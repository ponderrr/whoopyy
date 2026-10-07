"""
Unit tests for whoopyy.type_defs raw response types.

The required/optional keys of each TypedDict must match the WHOOP v2 API
component schemas (required keys in the spec are required here).
"""

import pytest

from whoopyy import type_defs


@pytest.mark.parametrize(
    "name, required, optional",
    [
        (
            "WorkoutResponse",
            {"id", "user_id", "created_at", "updated_at", "start", "end",
             "timezone_offset", "sport_name", "score_state"},
            {"score", "sport_id", "v1_id"},
        ),
        (
            "CycleResponse",
            {"id", "user_id", "created_at", "updated_at", "start",
             "timezone_offset", "score_state"},
            {"end", "score", "step_count"},
        ),
        (
            "SleepResponse",
            {"id", "cycle_id", "user_id", "created_at", "updated_at", "start",
             "end", "timezone_offset", "nap", "score_state"},
            {"score", "v1_id"},
        ),
        (
            "RecoveryResponse",
            {"cycle_id", "sleep_id", "user_id", "created_at", "updated_at",
             "score_state"},
            {"score"},
        ),
        ("ActivityIdMappingResponse", {"v2_activity_id"}, set()),
        (
            "WorkoutScoreResponse",
            {"strain", "average_heart_rate", "max_heart_rate", "kilojoule",
             "percent_recorded", "zone_durations"},
            {"distance_meter", "altitude_gain_meter", "altitude_change_meter"},
        ),
        (
            "ZoneDurationsResponse",
            {"zone_zero_milli", "zone_one_milli", "zone_two_milli",
             "zone_three_milli", "zone_four_milli", "zone_five_milli"},
            set(),
        ),
        (
            "CycleScoreResponse",
            {"strain", "kilojoule", "average_heart_rate", "max_heart_rate"},
            set(),
        ),
        (
            "RecoveryScoreResponse",
            {"user_calibrating", "recovery_score", "resting_heart_rate",
             "hrv_rmssd_milli"},
            {"spo2_percentage", "skin_temp_celsius"},
        ),
        # next_token is absent on the last page of every v2 collection
        ("PaginatedResponse", {"records"}, {"next_token"}),
    ],
)
def test_response_keys_match_v2_spec(name, required, optional):
    """Required and optional keys follow the v2 OpenAPI schema."""
    td = getattr(type_defs, name)
    assert set(td.__required_keys__) == required
    assert set(td.__optional_keys__) == optional


def test_workout_score_uses_zone_durations_key():
    """The v2 key is zone_durations; the legacy zone_duration key is gone."""
    keys = type_defs.WorkoutScoreResponse.__annotations__
    assert "zone_durations" in keys
    assert "zone_duration" not in keys


@pytest.mark.parametrize(
    "name",
    [
        "RecoveryResponse",
        "SleepResponse",
        "CycleResponse",
        "WorkoutResponse",
        "SleepNeededResponse",
        "ZoneDurationsResponse",
        "ActivityIdMappingResponse",
    ],
)
def test_new_response_types_exported(name):
    assert name in type_defs.__all__
    assert hasattr(type_defs, name)
