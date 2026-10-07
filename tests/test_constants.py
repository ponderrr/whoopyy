"""
Unit tests for whoopyy constants (WHOOP Developer API v2 endpoint paths).
"""

import pytest

from whoopyy import constants


EXPECTED_ENDPOINTS = {
    "user_profile_basic": "/developer/v2/user/profile/basic",
    "user_body_measurement": "/developer/v2/user/measurement/body",
    "user_access": "/developer/v2/user/access",
    "recovery_collection": "/developer/v2/recovery",
    "recovery_for_cycle": "/developer/v2/cycle/{cycle_id}/recovery",
    "sleep_single": "/developer/v2/activity/sleep/{sleep_id}",
    "sleep_collection": "/developer/v2/activity/sleep",
    "sleep_for_cycle": "/developer/v2/cycle/{cycle_id}/sleep",
    "cycle_single": "/developer/v2/cycle/{cycle_id}",
    "cycle_collection": "/developer/v2/cycle",
    "workout_single": "/developer/v2/activity/workout/{workout_id}",
    "workout_collection": "/developer/v2/activity/workout",
    "activity_mapping": "/developer/v1/activity-mapping/{activity_v1_id}",
}
"""The v2 endpoint contract: exactly these keys and paths."""


def test_endpoints_match_v2_contract():
    """ENDPOINTS holds exactly the 13 contract keys with their v2 paths."""
    assert constants.ENDPOINTS == EXPECTED_ENDPOINTS


def test_all_data_endpoints_use_v2():
    """Every endpoint except activity_mapping is on /developer/v2/."""
    for key, val in constants.ENDPOINTS.items():
        if key == "activity_mapping":
            continue
        assert val.startswith("/developer/v2/"), key


def test_only_activity_mapping_uses_v1():
    """activity_mapping is the only path WHOOP still documents on v1."""
    v1_keys = [k for k, v in constants.ENDPOINTS.items() if "/developer/v1/" in v]
    assert v1_keys == ["activity_mapping"]


def test_no_endpoint_uses_retired_v1_data_paths():
    """No v1 data path (recovery, sleep, cycle, workout, user) remains."""
    for val in constants.ENDPOINTS.values():
        for retired in ("/developer/v1/recovery", "/developer/v1/activity/",
                        "/developer/v1/cycle", "/developer/v1/user/"):
            assert not val.startswith(retired)


def test_max_page_limit_is_25():
    assert constants.MAX_PAGE_LIMIT == 25


def test_sleep_for_cycle_in_endpoints():
    """The v2 sleep-for-cycle endpoint is available again."""
    assert constants.ENDPOINTS["sleep_for_cycle"] == "/developer/v2/cycle/{cycle_id}/sleep"


def test_user_access_endpoint_for_revocation():
    """Revocation uses DELETE /developer/v2/user/access, not an OAuth revoke URL."""
    assert constants.ENDPOINTS["user_access"] == "/developer/v2/user/access"


def test_revoke_not_in_endpoints():
    """There is no separate OAuth revoke endpoint key."""
    assert "revoke" not in constants.ENDPOINTS
    assert not any("oauth2/revoke" in v for v in constants.ENDPOINTS.values())


@pytest.mark.parametrize(
    "key, kwargs, expected",
    [
        ("recovery_for_cycle", {"cycle_id": 93845}, "/developer/v2/cycle/93845/recovery"),
        ("sleep_for_cycle", {"cycle_id": 93845}, "/developer/v2/cycle/93845/sleep"),
        ("cycle_single", {"cycle_id": 93845}, "/developer/v2/cycle/93845"),
        (
            "sleep_single",
            {"sleep_id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8"},
            "/developer/v2/activity/sleep/ecfc6a15-4661-442f-a9a4-f160dd7afae8",
        ),
        (
            "workout_single",
            {"workout_id": "ecfc6a15-4661-442f-a9a4-f160dd7afae8"},
            "/developer/v2/activity/workout/ecfc6a15-4661-442f-a9a4-f160dd7afae8",
        ),
        ("activity_mapping", {"activity_v1_id": 12345678},
         "/developer/v1/activity-mapping/12345678"),
    ],
)
def test_endpoint_placeholders_format(key, kwargs, expected):
    """Path placeholders use the documented parameter names."""
    assert constants.ENDPOINTS[key].format(**kwargs) == expected
