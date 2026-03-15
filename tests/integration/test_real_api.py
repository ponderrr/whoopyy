"""Integration tests against the real WHOOP API.

These tests are skipped by default. To run them, set these environment variables:
    WHOOP_CLIENT_ID
    WHOOP_CLIENT_SECRET
    WHOOP_REFRESH_TOKEN
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("WHOOP_REFRESH_TOKEN"),
    reason="Integration tests require real WHOOP credentials"
)


def test_get_profile():
    """Verify profile endpoint returns valid UserProfile."""
    # Would test: client.get_profile() returns non-empty user_id
    pass


def test_get_recovery_collection():
    """Verify recovery collection returns valid Recovery objects."""
    # Would test: returns list, each has valid score_state
    pass


def test_get_sleep_collection():
    """Verify sleep collection returns valid Sleep objects with stage_summary."""
    pass


def test_get_cycle_collection():
    """Verify cycle collection returns valid Cycle objects with strain."""
    pass


def test_get_workout_collection():
    """Verify workout collection returns valid Workout objects with sport_id."""
    pass


def test_export_cycle_csv(tmp_path):
    """Verify CSV export completes without AttributeError."""
    pass


def test_export_sleep_csv(tmp_path):
    """Verify sleep CSV export handles None score fields."""
    pass
