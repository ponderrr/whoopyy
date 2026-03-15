"""
Targeted tests for whoopyy.utils to reach high coverage.

Covers: delete_tokens, calculate_expiry, milliseconds_to_hours,
        milliseconds_to_minutes, and error branches in save_tokens.
"""

import os
import time

import pytest

from whoopyy.utils import (
    calculate_expiry,
    delete_tokens,
    milliseconds_to_hours,
    milliseconds_to_minutes,
    save_tokens,
)


class TestDeleteTokens:
    """Tests for delete_tokens()."""

    def test_delete_existing_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "tokens.json")
        with open(filepath, "w") as f:
            f.write("{}")
        assert delete_tokens(filepath) is True
        assert not os.path.exists(filepath)

    def test_delete_nonexistent_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "nope.json")
        assert delete_tokens(filepath) is False

    def test_delete_permission_denied(self, tmp_path) -> None:
        """delete_tokens returns False when file cannot be deleted."""
        filepath = str(tmp_path / "readonly.json")
        with open(filepath, "w") as f:
            f.write("{}")
        # Make parent read-only so unlink fails
        os.chmod(str(tmp_path), 0o555)
        try:
            result = delete_tokens(filepath)
            assert result is False
        finally:
            os.chmod(str(tmp_path), 0o755)


class TestSaveTokensErrors:
    """Edge-case tests for save_tokens error handling."""

    def test_save_to_nonexistent_directory_raises(self) -> None:
        with pytest.raises(OSError):
            save_tokens({"access_token": "x"}, "/nonexistent/dir/tokens.json")


class TestCalculateExpiry:
    """Tests for calculate_expiry()."""

    def test_returns_future_timestamp(self) -> None:
        now = time.time()
        result = calculate_expiry(3600)
        assert result > now
        assert result <= now + 3601  # Allow 1s tolerance


class TestMillisecondsToHours:
    """Tests for milliseconds_to_hours()."""

    def test_eight_hours(self) -> None:
        assert milliseconds_to_hours(28800000) == 8.0

    def test_zero(self) -> None:
        assert milliseconds_to_hours(0) == 0.0

    def test_fractional(self) -> None:
        assert milliseconds_to_hours(27000000) == 7.5


class TestMillisecondsToMinutes:
    """Tests for milliseconds_to_minutes()."""

    def test_sixty_minutes(self) -> None:
        assert milliseconds_to_minutes(3600000) == 60.0

    def test_zero(self) -> None:
        assert milliseconds_to_minutes(0) == 0.0

    def test_ninety_seconds(self) -> None:
        assert milliseconds_to_minutes(90000) == 1.5
