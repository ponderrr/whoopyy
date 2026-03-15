"""
Targeted tests for whoopyy.exceptions to reach high coverage.
"""

from whoopyy.exceptions import (
    WhoopAPIError,
    WhoopAuthError,
    WhoopError,
    WhoopNetworkError,
    WhoopNotFoundError,
    WhoopRateLimitError,
    WhoopTokenError,
    WhoopValidationError,
    is_retryable_error,
)


class TestWhoopErrorRepr:
    """Tests for WhoopError.__repr__."""

    def test_repr_with_status_code(self) -> None:
        err = WhoopError("bad", status_code=500)
        r = repr(err)
        assert "WhoopError" in r
        assert "500" in r
        assert "bad" in r

    def test_repr_without_status_code(self) -> None:
        err = WhoopError("oops")
        r = repr(err)
        assert "WhoopError" in r
        assert "oops" in r


class TestWhoopRateLimitErrorRepr:
    """Tests for WhoopRateLimitError.__repr__."""

    def test_repr(self) -> None:
        err = WhoopRateLimitError("limit", retry_after=30, status_code=429)
        r = repr(err)
        assert "WhoopRateLimitError" in r
        assert "30" in r
        assert "429" in r


class TestIsRetryableError:
    """Tests for is_retryable_error() utility function."""

    def test_rate_limit_error_is_retryable(self) -> None:
        err = WhoopRateLimitError("rate", retry_after=10)
        assert is_retryable_error(err) is True

    def test_network_error_is_retryable(self) -> None:
        err = WhoopNetworkError("timeout")
        assert is_retryable_error(err) is True

    def test_auth_error_not_retryable(self) -> None:
        err = WhoopAuthError("bad auth", status_code=401)
        assert is_retryable_error(err) is False

    def test_token_error_not_retryable(self) -> None:
        err = WhoopTokenError("expired")
        assert is_retryable_error(err) is False

    def test_validation_error_not_retryable(self) -> None:
        err = WhoopValidationError("invalid", status_code=400)
        assert is_retryable_error(err) is False

    def test_api_error_5xx_retryable(self) -> None:
        err = WhoopAPIError("server error", status_code=502)
        assert is_retryable_error(err) is True

    def test_api_error_4xx_not_retryable(self) -> None:
        err = WhoopAPIError("client error", status_code=400)
        assert is_retryable_error(err) is False

    def test_api_error_no_status_not_retryable(self) -> None:
        err = WhoopAPIError("unknown")
        assert is_retryable_error(err) is False

    def test_not_found_error_not_retryable(self) -> None:
        err = WhoopNotFoundError("missing", status_code=404)
        assert is_retryable_error(err) is False

    def test_base_whoop_error_not_retryable(self) -> None:
        err = WhoopError("generic")
        assert is_retryable_error(err) is False
