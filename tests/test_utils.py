"""
Unit tests for strapkit utility functions.

Tests cover:
- save_tokens: file creation, content correctness, file permissions
- load_tokens: happy path, missing file, corrupted JSON
- is_token_expired: expired/valid token detection
- format_datetime / parse_datetime: ISO8601 round-trip
- parse_rate_limit_reset: 429 wait time from WHOOP rate limit headers
"""

import json
import os
import time
from datetime import datetime, timezone

import httpx
import pytest

from strapkit import utils


# =============================================================================
# save_tokens Tests
# =============================================================================

class TestSaveTokens:
    """Tests for utils.save_tokens()."""

    def test_save_tokens_creates_file(self, tmp_path):
        """save_tokens should create the file at the given path."""
        filepath = str(tmp_path / "tokens.json")
        data = {"access_token": "abc", "refresh_token": "xyz"}
        utils.save_tokens(data, filepath)
        assert os.path.exists(filepath)

    def test_save_tokens_content_is_correct(self, tmp_path):
        """save_tokens should write the exact dict as JSON."""
        filepath = str(tmp_path / "tokens.json")
        data = {"access_token": "abc", "refresh_token": "xyz", "expires_in": 3600}
        utils.save_tokens(data, filepath)
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_save_tokens_sets_permissions_600(self, tmp_path):
        """save_tokens should restrict file to owner read/write only (0o600)."""
        filepath = str(tmp_path / "tokens.json")
        utils.save_tokens({"access_token": "abc"}, filepath)
        mode = oct(os.stat(filepath).st_mode & 0o777)
        assert mode == "0o600"

    def test_save_tokens_overwrites_existing_file(self, tmp_path):
        """save_tokens should overwrite existing content."""
        filepath = str(tmp_path / "tokens.json")
        utils.save_tokens({"access_token": "first"}, filepath)
        utils.save_tokens({"access_token": "second"}, filepath)
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded["access_token"] == "second"

    def test_save_tokens_handles_complex_dict(self, tmp_path):
        """save_tokens should handle all standard token fields."""
        filepath = str(tmp_path / "tokens.json")
        data = {
            "access_token": "acc123",
            "refresh_token": "ref456",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline read:profile",
        }
        utils.save_tokens(data, filepath)
        with open(filepath) as f:
            loaded = json.load(f)
        assert loaded["access_token"] == "acc123"
        assert loaded["token_type"] == "Bearer"


# =============================================================================
# load_tokens Tests
# =============================================================================

class TestLoadTokens:
    """Tests for utils.load_tokens()."""

    def test_load_tokens_reads_file(self, tmp_path):
        """load_tokens should return the dict written to the file."""
        filepath = str(tmp_path / "tokens.json")
        data = {"access_token": "test", "expires_in": 3600}
        with open(filepath, "w") as f:
            json.dump(data, f)
        result = utils.load_tokens(filepath)
        assert result == data

    def test_load_tokens_missing_file_returns_none(self, tmp_path):
        """load_tokens returns None when the file does not exist."""
        filepath = str(tmp_path / "nonexistent.json")
        result = utils.load_tokens(filepath)
        assert result is None

    def test_load_tokens_corrupted_json_returns_none(self, tmp_path):
        """load_tokens returns None when JSON is malformed."""
        filepath = str(tmp_path / "corrupt.json")
        with open(filepath, "w") as f:
            f.write("{invalid json}")
        result = utils.load_tokens(filepath)
        assert result is None

    def test_load_tokens_empty_file_returns_none(self, tmp_path):
        """load_tokens returns None for an empty file (invalid JSON)."""
        filepath = str(tmp_path / "empty.json")
        with open(filepath, "w") as f:
            f.write("")
        result = utils.load_tokens(filepath)
        assert result is None

    def test_load_tokens_round_trip_with_save(self, tmp_path):
        """load_tokens should recover exactly what save_tokens wrote."""
        filepath = str(tmp_path / "tokens.json")
        original = {
            "access_token": "round_trip_token",
            "refresh_token": "rr_refresh",
            "expires_in": 1800,
        }
        utils.save_tokens(original, filepath)
        loaded = utils.load_tokens(filepath)
        assert loaded == original


# =============================================================================
# is_token_expired Tests
# =============================================================================

class TestIsTokenExpired:
    """Tests for utils.is_token_expired()."""

    def test_expired_token_returns_true(self):
        """Token with past expires_at should be considered expired."""
        tokens = {"access_token": "abc", "expires_at": time.time() - 3600}
        assert utils.is_token_expired(tokens) is True

    def test_valid_token_returns_false(self):
        """Token with future expires_at (well beyond buffer) should be valid."""
        tokens = {"access_token": "abc", "expires_at": time.time() + 7200}
        assert utils.is_token_expired(tokens) is False

    def test_token_expiring_soon_treated_as_expired(self):
        """Token expiring within buffer window should be treated as expired."""
        # Default buffer is TOKEN_REFRESH_BUFFER_SECONDS (60s)
        tokens = {"access_token": "abc", "expires_at": time.time() + 30}
        assert utils.is_token_expired(tokens) is True

    def test_missing_expires_at_treated_as_expired(self):
        """Token without expires_at (defaults to 0) should be expired."""
        tokens = {"access_token": "abc"}
        assert utils.is_token_expired(tokens) is True

    def test_custom_buffer_seconds(self):
        """Custom buffer_seconds parameter should be respected."""
        # Token expires in 500s; with buffer=600, should appear expired
        tokens = {"access_token": "abc", "expires_at": time.time() + 500}
        assert utils.is_token_expired(tokens, buffer_seconds=600) is True
        # With buffer=0, it should appear valid
        assert utils.is_token_expired(tokens, buffer_seconds=0) is False


# =============================================================================
# format_datetime / parse_datetime Tests
# =============================================================================

class TestFormatDatetime:
    """Tests for utils.format_datetime()."""

    def test_aware_datetime_formatted_correctly(self):
        """UTC-aware datetime should produce ISO 8601 string."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = utils.format_datetime(dt)
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_naive_datetime_assumes_utc(self):
        """Naive datetime should be treated as UTC."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = utils.format_datetime(dt)
        assert "2024-01-15" in result
        # Should contain UTC offset indicator
        assert "+00:00" in result or "Z" in result or "UTC" in result


class TestParseDatetime:
    """Tests for utils.parse_datetime()."""

    def test_parse_z_suffix(self):
        """parse_datetime should handle 'Z' (Zulu/UTC) suffix."""
        result = utils.parse_datetime("2024-01-15T08:30:00.000Z")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_offset_notation(self):
        """parse_datetime should handle explicit UTC offset."""
        result = utils.parse_datetime("2024-01-15T08:30:00+00:00")
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_parse_returns_datetime_with_tzinfo(self):
        """Parsed datetime should carry timezone information."""
        result = utils.parse_datetime("2024-06-20T12:00:00.000Z")
        assert result.tzinfo is not None

    def test_parse_invalid_raises_value_error(self):
        """parse_datetime should raise ValueError for unparsable strings."""
        with pytest.raises((ValueError, Exception)):
            utils.parse_datetime("not-a-date")


# =============================================================================
# parse_rate_limit_reset Tests
# =============================================================================

class TestParseRateLimitReset:
    """Tests for utils.parse_rate_limit_reset()."""

    def test_exported_in_all(self):
        """parse_rate_limit_reset is part of the public utils API."""
        assert "parse_rate_limit_reset" in utils.__all__

    def test_uses_x_ratelimit_reset(self):
        """X-RateLimit-Reset (WHOOP's documented header) is used when present."""
        assert utils.parse_rate_limit_reset({"X-RateLimit-Reset": "17"}) == 17

    def test_x_ratelimit_reset_preferred_over_retry_after(self):
        """X-RateLimit-Reset wins when both headers are present."""
        headers = {"Retry-After": "30", "X-RateLimit-Reset": "7"}
        assert utils.parse_rate_limit_reset(headers) == 7

    def test_falls_back_to_retry_after(self):
        """Retry-After is used when X-RateLimit-Reset is absent."""
        assert utils.parse_rate_limit_reset({"Retry-After": "45"}) == 45

    def test_falls_back_to_retry_after_when_reset_invalid(self):
        """An invalid X-RateLimit-Reset falls through to a valid Retry-After."""
        headers = {"X-RateLimit-Reset": "soon", "Retry-After": "12"}
        assert utils.parse_rate_limit_reset(headers) == 12

    def test_default_when_no_headers(self):
        """With neither header, the default (60) is returned."""
        assert utils.parse_rate_limit_reset({}) == 60

    def test_custom_default(self):
        """A caller-supplied default is returned when no header is usable."""
        assert utils.parse_rate_limit_reset({}, default=5) == 5
        assert utils.parse_rate_limit_reset({"Retry-After": "x"}, default=9) == 9

    def test_zero_is_valid(self):
        """Zero seconds is a valid non-negative wait."""
        assert utils.parse_rate_limit_reset({"X-RateLimit-Reset": "0"}) == 0

    def test_surrounding_whitespace_is_ignored(self):
        """Header values with surrounding whitespace still parse."""
        assert utils.parse_rate_limit_reset({"X-RateLimit-Reset": " 8 "}) == 8

    @pytest.mark.parametrize(
        "value",
        ["-1", "-30", "1.5", "abc", "", "Wed, 21 Oct 2015 07:28:00 GMT", "1e3", "+5"],
    )
    def test_invalid_values_fall_back_to_default(self, value):
        """Negative, decimal, empty and HTTP-date values are ignored."""
        assert utils.parse_rate_limit_reset({"X-RateLimit-Reset": value}) == 60
        assert utils.parse_rate_limit_reset({"Retry-After": value}) == 60

    def test_invalid_values_in_both_headers_return_default(self):
        """When both headers are invalid, the default is returned."""
        headers = {"X-RateLimit-Reset": "-1", "Retry-After": "2.5"}
        assert utils.parse_rate_limit_reset(headers, default=42) == 42

    @pytest.mark.parametrize(
        "name", ["x-ratelimit-reset", "X-RATELIMIT-RESET", "x-RateLimit-reset"]
    )
    def test_plain_dict_is_case_insensitive_for_reset(self, name):
        """A plain dict with a differently cased X-RateLimit-Reset key is found."""
        assert utils.parse_rate_limit_reset({name: "11"}) == 11

    @pytest.mark.parametrize("name", ["retry-after", "RETRY-AFTER", "rEtRy-AfTeR"])
    def test_plain_dict_is_case_insensitive_for_retry_after(self, name):
        """A plain dict with a differently cased Retry-After key is found."""
        assert utils.parse_rate_limit_reset({name: "22"}) == 22

    def test_plain_dict_lowercase_reset_preferred_over_retry_after(self):
        """Precedence holds even when the dict keys are lowercase."""
        headers = {"retry-after": "30", "x-ratelimit-reset": "3"}
        assert utils.parse_rate_limit_reset(headers) == 3

    def test_httpx_headers(self):
        """httpx.Headers (as on a real response) are supported."""
        headers = httpx.Headers({"x-ratelimit-reset": "13", "retry-after": "40"})
        assert utils.parse_rate_limit_reset(headers) == 13

    def test_httpx_headers_retry_after_only(self):
        """httpx.Headers with only Retry-After use it."""
        headers = httpx.Headers({"Retry-After": "25"})
        assert utils.parse_rate_limit_reset(headers) == 25

    def test_httpx_response_headers(self):
        """Headers taken from an httpx.Response are parsed case-insensitively."""
        response = httpx.Response(429, headers={"X-RATELIMIT-RESET": "4"})
        assert utils.parse_rate_limit_reset(response.headers) == 4

    def test_returns_int(self):
        """The result is always an int."""
        result = utils.parse_rate_limit_reset({"X-RateLimit-Reset": "007"})
        assert result == 7
        assert isinstance(result, int)
