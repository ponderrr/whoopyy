"""
Unit tests for WhoopPy async client.

Tests cover:
- Initialization and validation
- Async request handling (mocked)
- Async API methods (mocked)
- Async context manager
"""

import time
import uuid
from pathlib import Path

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import date, datetime, timezone

import httpx

import strapkit
from strapkit.async_client import AsyncWhoopClient
from strapkit.constants import API_BASE_URL, ENDPOINTS
from strapkit.models import (
    ActivityIdMapping,
    UserProfileBasic,
    Recovery,
    RecoveryCollection,
    Sleep,
    Cycle,
    Workout,
)
from strapkit.exceptions import (
    WhoopAPIError,
    WhoopAuthError,
    WhoopNetworkError,
    WhoopNotFoundError,
    WhoopRateLimitError,
    WhoopValidationError,
    is_retryable_error,
)
from strapkit.utils import save_tokens


@pytest.fixture(autouse=True)
def _isolate_default_token_file(tmp_path, monkeypatch):
    """
    Redirect the default token file (~/.whoop_tokens.json) to a temp path.

    Refreshes re-read the token file and lock "<file>.lock" next to it, so a
    handler built with the default token_file would otherwise read, lock or
    delete the developer's real tokens.
    """
    import os

    import strapkit.auth as auth_module
    from strapkit.constants import DEFAULT_TOKEN_FILE

    safe_path = str(tmp_path / "default_whoop_tokens.json")
    default_path = os.path.abspath(DEFAULT_TOKEN_FILE)

    def _safe(filepath):
        if os.path.abspath(os.fspath(filepath)) == default_path:
            return safe_path
        return filepath

    def _redirect_path_arg(func):
        def wrapper(filepath=DEFAULT_TOKEN_FILE, *args, **kwargs):
            return func(_safe(filepath), *args, **kwargs)
        return wrapper

    for name in (
        "load_tokens",
        "delete_tokens",
        "token_file_lock",
        "async_token_file_lock",
        "_check_token_file_writable",
        "_file_lock_held_by_current_thread",
    ):
        monkeypatch.setattr(auth_module, name, _redirect_path_arg(getattr(auth_module, name)))

    original_save = auth_module.save_tokens

    def _save(tokens, filepath=DEFAULT_TOKEN_FILE):
        return original_save(tokens, _safe(filepath))

    monkeypatch.setattr(auth_module, "save_tokens", _save)


# =============================================================================
# Fixtures
# =============================================================================

def _install_mock_transport(client, handler) -> None:
    """Route the async client's HTTP traffic through an httpx.MockTransport handler.

    The caller must ``await client._http_client.aclose()`` when done.
    """
    client._http_client = httpx.AsyncClient(
        base_url=API_BASE_URL,
        transport=httpx.MockTransport(handler),
    )


def _json_response(payload, status_code: int = 200) -> Mock:
    """Build a mock successful JSON response."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.json.return_value = payload
    mock_response.raise_for_status = Mock()
    return mock_response


@pytest.fixture
def mock_auth(tmp_path):
    """Create a mock OAuth handler."""
    auth = Mock()
    auth.token_file = str(tmp_path / ".whoop_tokens.json")
    auth.get_valid_token.return_value = "test_access_token"
    auth.async_get_valid_token = AsyncMock(return_value="test_access_token")
    auth.async_refresh_if_stale = AsyncMock(return_value="refreshed_access_token")
    auth.has_valid_tokens.return_value = True
    auth.close = Mock()

    async def _clear_tokens():
        # Mirrors OAuthHandler.async_clear_tokens(): memory and file
        auth._tokens = None
        Path(auth.token_file).unlink(missing_ok=True)

    auth.async_clear_tokens = AsyncMock(side_effect=_clear_tokens)
    return auth


@pytest.fixture
def async_client(mock_auth):
    """Create an AsyncWhoopClient with mocked auth."""
    with patch("strapkit.async_client.OAuthHandler", return_value=mock_auth):
        client = AsyncWhoopClient(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        yield client
        # Note: We don't await close() here as the event loop may not be running


@pytest.fixture
def mock_profile_response():
    """Mock profile API response."""
    return {
        "user_id": 12345,
        "email": "test@example.com",
        "first_name": "John",
        "last_name": "Doe",
    }


@pytest.fixture
def mock_recovery_collection_response():
    """Mock recovery collection API response."""
    return {
        "records": [
            {
                "cycle_id": 1,
                "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "user_id": 789,
                "created_at": "2024-01-15T08:00:00.000Z",
                "updated_at": "2024-01-15T08:30:00.000Z",
                "score_state": "SCORED",
                "score": {
                    "user_calibrating": False,
                    "recovery_score": 75.0,
                    "resting_heart_rate": 52,
                    "hrv_rmssd_milli": 65.0,
                },
            },
        ],
        "next_token": None,
    }


# =============================================================================
# Initialization Tests
# =============================================================================

class TestAsyncWhoopClientInit:
    """Tests for AsyncWhoopClient initialization."""
    
    def test_valid_initialization(self, mock_auth) -> None:
        """Test creating client with valid parameters."""
        with patch("strapkit.async_client.OAuthHandler", return_value=mock_auth):
            client = AsyncWhoopClient(
                client_id="test_id",
                client_secret="test_secret",
            )
            
            assert client.client_id == "test_id"
            assert client.client_secret == "test_secret"
            assert client._authenticated is False
            assert client._http_client.headers["User-Agent"] == f"strapkit/{strapkit.__version__}"
    
    def test_empty_client_id_rejected(self) -> None:
        """Test that empty client_id raises error."""
        with pytest.raises(ValueError, match="client_id is required"):
            AsyncWhoopClient(
                client_id="",
                client_secret="test_secret",
            )
    
    def test_empty_client_secret_rejected(self) -> None:
        """Test that empty client_secret raises error."""
        with pytest.raises(ValueError, match="client_secret is required"):
            AsyncWhoopClient(
                client_id="test_id",
                client_secret="",
            )


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAsyncAuthentication:
    """Tests for async client authentication."""
    
    def test_authenticate_success(self, async_client, mock_auth) -> None:
        """Test successful authentication."""
        mock_auth.has_valid_tokens.return_value = False
        async_client.authenticate()

        mock_auth.authorize.assert_called_once()
        assert async_client._authenticated is True
    
    def test_is_authenticated(self, async_client, mock_auth) -> None:
        """Test is_authenticated method."""
        mock_auth.has_valid_tokens.return_value = True
        
        assert async_client.is_authenticated() is True


# =============================================================================
# Async Request Tests
# =============================================================================

class TestAsyncRequest:
    """Tests for async request handling."""
    
    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self, async_client) -> None:
        """Test that async requests include auth header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        await async_client._request("GET", "/test")
        
        # Verify auth header was passed
        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert "Authorization" in call_kwargs["headers"]
        assert "Bearer test_access_token" in call_kwargs["headers"]["Authorization"]
    
    @pytest.mark.asyncio
    async def test_request_rate_limit_handling(self, async_client) -> None:
        """Test rate limit (429) handling: one wait from the headers, one retry, then raise."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        assert exc.value.retry_after == 60
        assert exc.value.status_code == 429
        # Slept exactly once, for the Retry-After value, then retried once
        mock_sleep.assert_awaited_once_with(60)
        assert async_client._http_client.request.call_count == 2
    
    @pytest.mark.asyncio
    async def test_request_auth_error_handling(self, async_client, mock_auth) -> None:
        """Test authentication error (401) triggers refresh and retry; second 401 raises WhoopAuthError."""
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        mock_response_401.text = "Unauthorized"

        async_client._http_client.request = AsyncMock(return_value=mock_response_401)

        with pytest.raises(WhoopAuthError) as exc:
            await async_client._request("GET", "/test")

        assert exc.value.status_code == 401
        # The stale-aware async refresh is awaited with the rejected token;
        # the blocking sync refresh is never used on the event loop.
        mock_auth.async_refresh_if_stale.assert_awaited_once_with("test_access_token")
        mock_auth.refresh_access_token.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_request_validation_error_handling(self, async_client) -> None:
        """Test validation error (400) handling."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameter"
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(WhoopValidationError) as exc:
            await async_client._request("GET", "/test")
        
        assert exc.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_request_204_returns_empty_dict(self, async_client) -> None:
        """Test 204 No Content returns empty dict."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        result = await async_client._request("DELETE", "/test")

        assert result == {}

    @pytest.mark.asyncio
    async def test_network_error_raises_whoop_network_error(self, async_client) -> None:
        """Test that httpx.RequestError raises WhoopNetworkError."""
        async_client._http_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(WhoopNetworkError):
            await async_client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_404_raises_whoop_not_found_error(self, async_client) -> None:
        """Test that a 404 response raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(WhoopNotFoundError) as exc:
            await async_client._request("GET", "/test/resource")

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_401_triggers_refresh_and_retry(self, async_client, mock_auth) -> None:
        """Test that a 401 triggers token refresh and a successful retry."""
        mock_401 = Mock()
        mock_401.status_code = 401
        mock_401.text = "Unauthorized"

        mock_200 = Mock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"ok": True}
        mock_200.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(side_effect=[mock_401, mock_200])

        result = await async_client._request("GET", "/test")

        assert result == {"ok": True}
        mock_auth.async_refresh_if_stale.assert_awaited_once_with("test_access_token")
        mock_auth.refresh_access_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_401_double_triggers_raises_auth_error(self, async_client, mock_auth) -> None:
        """Test that two consecutive 401s raises WhoopAuthError after one refresh."""
        mock_401 = Mock()
        mock_401.status_code = 401
        mock_401.text = "Unauthorized"

        async_client._http_client.request = AsyncMock(return_value=mock_401)

        with pytest.raises(WhoopAuthError):
            await async_client._request("GET", "/test")

        mock_auth.async_refresh_if_stale.assert_awaited_once()

    def test_is_retryable_error_true_for_network_error(self, async_client) -> None:
        """Test that is_retryable_error returns True for WhoopNetworkError."""
        error = WhoopNetworkError("timeout")
        assert is_retryable_error(error) is True


# =============================================================================
# Async Profile Methods Tests
# =============================================================================

class TestAsyncProfileMethods:
    """Tests for async profile API methods."""
    
    @pytest.mark.asyncio
    async def test_get_profile_basic(
        self, async_client, mock_profile_response
    ) -> None:
        """Test async get_profile_basic method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_profile_response
        mock_response.raise_for_status = Mock()
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        profile = await async_client.get_profile_basic()
        
        assert isinstance(profile, UserProfileBasic)
        assert profile.user_id == 12345
        assert profile.first_name == "John"


# =============================================================================
# Async Recovery Methods Tests
# =============================================================================

class TestAsyncRecoveryMethods:
    """Tests for async recovery API methods."""
    
    @pytest.mark.asyncio
    async def test_get_recovery(self, async_client) -> None:
        """Test async get_recovery_for_cycle method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cycle_id": 123,
            "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "user_id": 789,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:30:00.000Z",
            "score_state": "SCORED",
            "score": {
                "user_calibrating": False,
                "recovery_score": 75.5,
                "resting_heart_rate": 52,
                "hrv_rmssd_milli": 65.2,
            },
        }
        mock_response.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        recovery = await async_client.get_recovery_for_cycle(123)

        assert isinstance(recovery, Recovery)
        assert recovery.cycle_id == 123

    @pytest.mark.asyncio
    async def test_get_recovery_invalid_id(self, async_client) -> None:
        """Test get_recovery_for_cycle with invalid ID."""
        with pytest.raises(ValueError, match="Invalid cycle_id"):
            await async_client.get_recovery_for_cycle(-1)
    
    @pytest.mark.asyncio
    async def test_get_recovery_collection(
        self, async_client, mock_recovery_collection_response
    ) -> None:
        """Test async get_recovery_collection method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_recovery_collection_response
        mock_response.raise_for_status = Mock()
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        collection = await async_client.get_recovery_collection(limit=10)
        
        assert isinstance(collection, RecoveryCollection)
        assert len(collection.records) == 1
    
    @pytest.mark.asyncio
    async def test_get_recovery_collection_invalid_limit(
        self, async_client
    ) -> None:
        """Test get_recovery_collection with invalid limit."""
        with pytest.raises(WhoopValidationError):
            await async_client.get_recovery_collection(limit=100)


# =============================================================================
# Async Sleep Methods Tests
# =============================================================================

class TestAsyncSleepMethods:
    """Tests for async sleep API methods."""
    
    @pytest.mark.asyncio
    async def test_get_sleep(self, async_client) -> None:
        """Test async get_sleep method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "cycle_id": 100,
            "user_id": 456,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-14T22:30:00.000Z",
            "end": "2024-01-15T06:30:00.000Z",
            "timezone_offset": "-05:00",
            "nap": False,
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        sleep = await async_client.get_sleep("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert isinstance(sleep, Sleep)
        assert sleep.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    @pytest.mark.asyncio
    async def test_get_sleep_accepts_uuid_string(self, async_client) -> None:
        """Test async get_sleep accepts a UUID string and makes HTTP call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc-123",
            "cycle_id": 100,
            "user_id": 456,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-14T22:30:00.000Z",
            "end": "2024-01-15T06:30:00.000Z",
            "timezone_offset": "-05:00",
            "nap": False,
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()

        mock_request = AsyncMock(return_value=mock_response)
        async_client._http_client.request = mock_request

        sleep = await async_client.get_sleep("abc-123")

        assert isinstance(sleep, Sleep)
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert "abc-123" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_get_sleep_rejects_empty_string(self, async_client) -> None:
        """Test async get_sleep raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid sleep_id"):
            await async_client.get_sleep("")


# =============================================================================
# Async Cycle Methods Tests
# =============================================================================

class TestAsyncCycleMethods:
    """Tests for async cycle API methods."""
    
    @pytest.mark.asyncio
    async def test_get_cycle(self, async_client) -> None:
        """Test async get_cycle method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "user_id": 456,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-15T08:00:00.000Z",
            "end": "2024-01-16T08:00:00.000Z",
            "timezone_offset": "-05:00",
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        cycle = await async_client.get_cycle(123)
        
        assert isinstance(cycle, Cycle)
        assert cycle.id == 123


# =============================================================================
# Async Workout Methods Tests
# =============================================================================

class TestAsyncWorkoutMethods:
    """Tests for async workout API methods."""
    
    @pytest.mark.asyncio
    async def test_get_workout(self, async_client) -> None:
        """Test async get_workout method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "user_id": 456,
            "created_at": "2024-01-15T10:00:00.000Z",
            "updated_at": "2024-01-15T11:00:00.000Z",
            "start": "2024-01-15T10:00:00.000Z",
            "end": "2024-01-15T11:00:00.000Z",
            "timezone_offset": "-05:00",
            "sport_name": "running",
            "sport_id": 0,
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        workout = await async_client.get_workout("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        assert isinstance(workout, Workout)
        assert workout.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert workout.sport_name == "running"
        assert workout.sport_id == 0
        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == (
            "/developer/v2/activity/workout/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )

    @pytest.mark.asyncio
    async def test_get_workout_accepts_uuid_string(self, async_client) -> None:
        """Test async get_workout accepts a UUID string and makes HTTP call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc-123",
            "user_id": 456,
            "created_at": "2024-01-15T10:00:00.000Z",
            "updated_at": "2024-01-15T11:00:00.000Z",
            "start": "2024-01-15T10:00:00.000Z",
            "end": "2024-01-15T11:00:00.000Z",
            "timezone_offset": "-05:00",
            "sport_name": "running",
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()

        mock_request = AsyncMock(return_value=mock_response)
        async_client._http_client.request = mock_request

        workout = await async_client.get_workout("abc-123")

        assert isinstance(workout, Workout)
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert "abc-123" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_get_workout_rejects_empty_string(self, async_client) -> None:
        """Test async get_workout raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid workout_id"):
            await async_client.get_workout("")


# =============================================================================
# Async Context Manager Tests
# =============================================================================

class TestAsyncContextManager:
    """Tests for async context manager functionality."""
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_auth) -> None:
        """Test async context manager."""
        with patch("strapkit.async_client.OAuthHandler", return_value=mock_auth):
            async with AsyncWhoopClient(
                client_id="test_id",
                client_secret="test_secret",
            ) as client:
                assert client is not None
                assert isinstance(client, AsyncWhoopClient)
            
            # Auth should be closed after context
            mock_auth.close.assert_called_once()


# =============================================================================
# Repr Tests
# =============================================================================

class TestAsyncRepr:
    """Tests for string representation."""
    
    def test_repr(self, async_client) -> None:
        """Test __repr__ output."""
        repr_str = repr(async_client)
        
        assert "AsyncWhoopClient" in repr_str
        assert "test_cli" in repr_str
        assert "authenticated=False" in repr_str


# =============================================================================
# Async Revoke Access Tests
# =============================================================================

class TestAsyncRevokeAccess:
    """Tests for async revoke_access() (DELETE /developer/v2/user/access)."""

    @staticmethod
    def _response(status_code: int, text: str = "") -> httpx.Response:
        """Build a real httpx response for the revoke request."""
        return httpx.Response(
            status_code,
            text=text,
            request=httpx.Request("DELETE", f"{API_BASE_URL}{ENDPOINTS['user_access']}"),
        )

    @pytest.mark.asyncio
    async def test_revoke_access_sends_delete_to_user_access(self, async_client, mock_auth) -> None:
        """revoke_access() sends DELETE /developer/v2/user/access with the Bearer token."""
        async_client._http_client.request = AsyncMock(return_value=self._response(204))

        await async_client.revoke_access()

        async_client._http_client.request.assert_awaited_once()
        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["method"] == "DELETE"
        assert call_kwargs["url"] == "/developer/v2/user/access"
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_access_token"
        assert call_kwargs["json"] is None

    @pytest.mark.asyncio
    async def test_revoke_access_does_not_post_to_oauth_revoke(self, async_client, mock_auth) -> None:
        """The retired POST /oauth/oauth2/revoke call is no longer made."""
        async_client._http_client.request = AsyncMock(return_value=self._response(204))
        async_client._http_client.post = AsyncMock()

        await async_client.revoke_access()

        async_client._http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_access_204_returns_none(self, async_client, mock_auth) -> None:
        """A 204 No Content response is success; revoke_access() returns None."""
        async_client._http_client.request = AsyncMock(return_value=self._response(204))

        assert await async_client.revoke_access() is None

    @pytest.mark.asyncio
    async def test_revoke_access_clears_tokens(self, async_client, mock_auth) -> None:
        """revoke_access() clears in-memory tokens and marks the client unauthenticated."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        async_client._authenticated = True
        async_client._http_client.request = AsyncMock(return_value=self._response(204))

        await async_client.revoke_access()

        assert mock_auth._tokens is None
        assert async_client._authenticated is False

    @pytest.mark.asyncio
    async def test_revoke_access_400_raises_validation_error(self, async_client, mock_auth) -> None:
        """A 400 surfaces as WhoopValidationError and leaves tokens untouched."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        async_client._authenticated = True
        async_client._http_client.request = AsyncMock(
            return_value=self._response(400, "bad request")
        )

        with pytest.raises(WhoopValidationError) as exc_info:
            await async_client.revoke_access()

        assert exc_info.value.status_code == 400
        assert mock_auth._tokens == {"access_token": "test_access_token"}
        assert async_client._authenticated is True

    @pytest.mark.asyncio
    async def test_revoke_access_500_raises_api_error(self, async_client, mock_auth) -> None:
        """A 500 surfaces as WhoopAPIError and leaves tokens untouched."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        async_client._http_client.request = AsyncMock(
            return_value=self._response(500, "server error")
        )

        with pytest.raises(WhoopAPIError) as exc_info:
            await async_client.revoke_access()

        assert exc_info.value.status_code == 500
        assert not isinstance(exc_info.value, WhoopAuthError)
        assert mock_auth._tokens == {"access_token": "test_access_token"}

    @pytest.mark.asyncio
    async def test_revoke_access_repeated_401_raises_auth_error(self, async_client, mock_auth) -> None:
        """Two 401s (before and after refresh) raise WhoopAuthError; tokens are kept."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        async_client._http_client.request = AsyncMock(
            return_value=self._response(401, "unauthorized")
        )

        with pytest.raises(WhoopAuthError) as exc_info:
            await async_client.revoke_access()

        assert exc_info.value.status_code == 401
        mock_auth.async_refresh_if_stale.assert_awaited_once_with("test_access_token")
        assert async_client._http_client.request.call_count == 2
        assert mock_auth._tokens == {"access_token": "test_access_token"}

    @pytest.mark.asyncio
    async def test_revoke_access_401_then_204_succeeds(self, async_client, mock_auth) -> None:
        """A 401 triggers one token refresh; a 204 on retry completes the revoke."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        async_client._http_client.request = AsyncMock(
            side_effect=[self._response(401, "unauthorized"), self._response(204)]
        )

        await async_client.revoke_access()

        mock_auth.async_refresh_if_stale.assert_awaited_once_with("test_access_token")
        assert mock_auth._tokens is None
        assert async_client._authenticated is False

    @pytest.mark.asyncio
    async def test_revoke_access_over_http_transport(self, async_client, mock_auth) -> None:
        """End to end through httpx: full URL, method and Authorization header."""
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(204)

        _install_mock_transport(async_client, handler)
        try:
            await async_client.revoke_access()
        finally:
            await async_client._http_client.aclose()

        assert len(seen) == 1
        assert seen[0].method == "DELETE"
        assert str(seen[0].url) == "https://api.prod.whoop.com/developer/v2/user/access"
        assert seen[0].headers["Authorization"] == "Bearer test_access_token"
        assert async_client._authenticated is False

    @pytest.mark.asyncio
    async def test_revoke_access_deletes_token_file_and_clears_cache(
        self, async_client, mock_auth
    ) -> None:
        """A successful revoke removes the token file and the response cache."""
        token_path = Path(mock_auth.token_file)
        token_path.write_text("{}")
        async_client._cache_set("profile_basic", object(), ttl=300)
        async_client._http_client.request = AsyncMock(return_value=self._response(204))

        await async_client.revoke_access()

        assert not token_path.exists()
        assert async_client._cache == {}

    @pytest.mark.asyncio
    async def test_revoke_access_failure_keeps_token_file_and_cache(
        self, async_client, mock_auth
    ) -> None:
        """A failed revoke leaves the token file and the cache in place."""
        token_path = Path(mock_auth.token_file)
        token_path.write_text("{}")
        async_client._cache_set("profile_basic", object(), ttl=300)
        async_client._http_client.request = AsyncMock(
            return_value=self._response(500, "server error")
        )

        with pytest.raises(WhoopAPIError):
            await async_client.revoke_access()

        assert token_path.exists()
        assert "profile_basic" in async_client._cache

    @pytest.mark.asyncio
    async def test_revoke_access_signs_out_with_real_token_file(self, tmp_path) -> None:
        """After a revoke the client is unauthenticated and does not reuse the old token."""
        token_file = str(tmp_path / ".whoop_tokens.json")
        save_tokens(
            {
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "expires_at": time.time() + 3600,
                "token_type": "Bearer",
                "scope": "read:profile",
            },
            token_file,
        )
        profile = {
            "user_id": 1,
            "email": "a@example.com",
            "first_name": "A",
            "last_name": "B",
        }
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path, request.headers["Authorization"]))
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, json=profile)

        client = AsyncWhoopClient(
            client_id="test_client_id",
            client_secret="test_client_secret",
            token_file=token_file,
        )
        try:
            await client._http_client.aclose()
            _install_mock_transport(client, handler)
            await client.get_profile_basic()
            assert client.is_authenticated() is True

            await client.revoke_access()

            assert client.is_authenticated() is False
            assert not Path(token_file).exists()
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate(auto_open_browser=False)
            mock_authorize.assert_called_once_with(auto_open_browser=False)
        finally:
            await client.close()

        assert seen == [
            ("GET", "/developer/v2/user/profile/basic", "Bearer AT"),
            ("DELETE", "/developer/v2/user/access", "Bearer AT"),
        ]


# =============================================================================
# Auth Headers Coroutine Test
# =============================================================================

class TestGetAuthHeadersIsCoroutine:
    """Test that _get_auth_headers is an async coroutine function."""

    def test_get_auth_headers_is_coroutine(self, async_client) -> None:
        """_get_auth_headers must be a coroutine function (async def)."""
        import asyncio
        assert asyncio.iscoroutinefunction(async_client._get_auth_headers) is True


# =============================================================================
# Async Sleep Pagination Tests
# =============================================================================

class TestAsyncSleepPagination:
    """Tests for async sleep collection pagination."""

    def _make_sleep_record(self, idx: int) -> dict:
        return {
            "id": f"async-sleep-{idx:04d}",
            "cycle_id": idx,
            "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:30:00.000Z",
            "start": "2024-01-14T22:30:00.000Z",
            "end": "2024-01-15T06:30:00.000Z",
            "timezone_offset": "-05:00",
            "nap": False,
            "score_state": "SCORED",
            "score": None,
        }

    @pytest.mark.asyncio
    async def test_get_sleep_collection_single_page(self, async_client):
        """Async single-page sleep collection returns all items with one HTTP call."""
        page = {
            "records": [self._make_sleep_record(i) for i in range(3)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        from strapkit.models import SleepCollection
        collection = await async_client.get_sleep_collection(limit=10)

        assert isinstance(collection, SleepCollection)
        assert len(collection.records) == 3
        assert collection.next_token is None
        async_client._http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sleep_collection_two_pages(self, async_client):
        """Async two-page sleep collection yields records from both pages."""
        page1 = {
            "records": [self._make_sleep_record(i) for i in range(2)],
            "next_token": "tok1",
        }
        page2 = {
            "records": [self._make_sleep_record(i) for i in range(2, 4)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = [page1, page2]

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        all_sleeps = await async_client.get_all_sleep()

        assert len(all_sleeps) == 4
        assert async_client._http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_get_all_sleep_follows_pagination(self, async_client):
        """Async get_all_sleep aggregates across three pages."""
        pages = [
            {"records": [self._make_sleep_record(i) for i in range(5)], "next_token": "p2"},
            {"records": [self._make_sleep_record(i) for i in range(5, 10)], "next_token": "p3"},
            {"records": [self._make_sleep_record(i) for i in range(10, 12)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        all_sleeps = await async_client.get_all_sleep()

        assert len(all_sleeps) == 12
        assert async_client._http_client.request.call_count == 3


# =============================================================================
# Async Cycle Pagination Tests
# =============================================================================

class TestAsyncCyclePagination:
    """Tests for async cycle collection pagination."""

    def _make_cycle_record(self, idx: int) -> dict:
        return {
            "id": idx,
            "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-15T08:00:00.000Z",
            "end": "2024-01-16T08:00:00.000Z",
            "timezone_offset": "-05:00",
            "score_state": "SCORED",
            "score": None,
        }

    @pytest.mark.asyncio
    async def test_get_cycle_collection_basic(self, async_client):
        """Async single-page cycle collection deserializes to Cycle objects."""
        page = {
            "records": [self._make_cycle_record(i) for i in range(1, 4)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        from strapkit.models import CycleCollection, Cycle
        collection = await async_client.get_cycle_collection(limit=10)

        assert isinstance(collection, CycleCollection)
        assert len(collection.records) == 3
        assert all(isinstance(c, Cycle) for c in collection.records)

    @pytest.mark.asyncio
    async def test_get_all_cycles_multi_page(self, async_client):
        """Async get_all_cycles fetches two pages and combines results."""
        pages = [
            {"records": [self._make_cycle_record(i) for i in range(1, 4)], "next_token": "next"},
            {"records": [self._make_cycle_record(i) for i in range(4, 7)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        cycles = await async_client.get_all_cycles()

        assert len(cycles) == 6
        assert async_client._http_client.request.call_count == 2


# =============================================================================
# Async Workout Pagination Tests
# =============================================================================

class TestAsyncWorkoutPagination:
    """Tests for async workout collection pagination."""

    def _make_workout_record(self, idx: int) -> dict:
        return {
            "id": f"async-workout-{idx:04d}",
            "user_id": 1,
            "created_at": "2024-01-15T10:00:00.000Z",
            "updated_at": "2024-01-15T11:00:00.000Z",
            "start": "2024-01-15T10:00:00.000Z",
            "end": "2024-01-15T11:00:00.000Z",
            "timezone_offset": "-05:00",
            "sport_name": "yoga",
            "score_state": "SCORED",
            "score": None,
        }

    @pytest.mark.asyncio
    async def test_get_workout_collection_basic(self, async_client):
        """Async single-page workout collection deserializes to Workout objects."""
        page = {
            "records": [self._make_workout_record(i) for i in range(3)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        from strapkit.models import WorkoutCollection, Workout
        collection = await async_client.get_workout_collection(limit=10)

        assert isinstance(collection, WorkoutCollection)
        assert len(collection.records) == 3
        # v2 identifies the sport by name; the deprecated sport_id is absent
        assert all(w.sport_name == "yoga" for w in collection.records)
        assert all(w.sport_id is None for w in collection.records)

    @pytest.mark.asyncio
    async def test_get_all_workouts_multi_page(self, async_client):
        """Async get_all_workouts fetches two pages and combines results."""
        pages = [
            {"records": [self._make_workout_record(i) for i in range(4)], "next_token": "wt2"},
            {"records": [self._make_workout_record(i) for i in range(4, 8)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        workouts = await async_client.get_all_workouts()

        assert len(workouts) == 8
        assert async_client._http_client.request.call_count == 2


# =============================================================================
# Async Concurrent Fetching Tests
# =============================================================================

class TestAsyncConcurrentFetching:
    """Tests for fetch_all() and fetch_dashboard() concurrent methods."""

    def _mock_collection_response(self, records_key, records):
        """Helper to create a mock response returning a collection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "records": records,
            "next_token": None,
        }
        return mock_response

    @pytest.mark.asyncio
    async def test_fetch_all_runs_concurrently(self, async_client):
        """fetch_all() returns all 4 data types when all succeed."""
        recovery_data = {"records": [{"cycle_id": 1, "sleep_id": "s1", "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "score_state": "SCORED", "score": None}], "next_token": None}
        sleep_data = {"records": [{"id": "s1", "cycle_id": 1, "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-14T22:30:00.000Z", "end": "2024-01-15T06:30:00.000Z",
            "timezone_offset": "-05:00", "nap": False, "score_state": "SCORED",
            "score": None}], "next_token": None}
        cycle_data = {"records": [{"id": 1, "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-15T08:00:00.000Z", "end": "2024-01-16T08:00:00.000Z",
            "timezone_offset": "-05:00", "score_state": "SCORED",
            "score": None}], "next_token": None}
        workout_data = {"records": [{"id": "w1", "user_id": 1,
            "created_at": "2024-01-15T10:00:00.000Z", "updated_at": "2024-01-15T11:00:00.000Z",
            "start": "2024-01-15T10:00:00.000Z", "end": "2024-01-15T11:00:00.000Z",
            "timezone_offset": "-05:00", "sport_name": "running", "score_state": "SCORED",
            "score": None}], "next_token": None}

        responses = [recovery_data, sleep_data, cycle_data, workout_data]
        call_count = 0

        def make_response(data):
            mock = Mock()
            mock.status_code = 200
            mock.raise_for_status = Mock()
            mock.json.return_value = data
            return mock

        async def mock_request(**kwargs):
            nonlocal call_count
            url = kwargs.get("url", "")
            if "recovery" in url:
                return make_response(recovery_data)
            elif "sleep" in url:
                return make_response(sleep_data)
            elif "cycle" in url:
                return make_response(cycle_data)
            elif "workout" in url:
                return make_response(workout_data)
            return make_response(recovery_data)

        async_client._http_client.request = AsyncMock(side_effect=mock_request)

        data = await async_client.fetch_all(limit=5)

        assert "recovery" in data
        assert "sleep" in data
        assert "cycles" in data
        assert "workouts" in data
        assert all(v is not None for v in data.values())

    @pytest.mark.asyncio
    async def test_fetch_all_handles_partial_failure(self, async_client):
        """fetch_all() sets failed endpoints to None, others still populated."""
        cycle_data = {"records": [{"id": 1, "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-15T08:00:00.000Z", "end": "2024-01-16T08:00:00.000Z",
            "timezone_offset": "-05:00", "score_state": "SCORED",
            "score": None}], "next_token": None}

        async def mock_request(**kwargs):
            url = kwargs.get("url", "")
            if "recovery" in url:
                raise WhoopAPIError("API error", status_code=500)
            mock = Mock()
            mock.status_code = 200
            mock.raise_for_status = Mock()
            mock.json.return_value = cycle_data
            return mock

        async_client._http_client.request = AsyncMock(side_effect=mock_request)

        data = await async_client.fetch_all(limit=5)

        assert data["recovery"] is None
        # Other keys should still be populated (not None)
        assert data["cycles"] is not None

    @pytest.mark.asyncio
    async def test_fetch_dashboard_returns_single_records(self, async_client):
        """fetch_dashboard() returns single model instances, not collections."""
        profile_data = {"user_id": 12345, "email": "test@example.com",
            "first_name": "John", "last_name": "Doe"}
        recovery_data = {"records": [{"cycle_id": 1, "sleep_id": "s1", "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "score_state": "SCORED", "score": None}], "next_token": None}
        sleep_data = {"records": [{"id": "s1", "cycle_id": 1, "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-14T22:30:00.000Z", "end": "2024-01-15T06:30:00.000Z",
            "timezone_offset": "-05:00", "nap": False, "score_state": "SCORED",
            "score": None}], "next_token": None}
        cycle_data = {"records": [{"id": 1, "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "start": "2024-01-15T08:00:00.000Z", "end": "2024-01-16T08:00:00.000Z",
            "timezone_offset": "-05:00", "score_state": "SCORED",
            "score": None}], "next_token": None}
        workout_data = {"records": [{"id": "w1", "user_id": 1,
            "created_at": "2024-01-15T10:00:00.000Z", "updated_at": "2024-01-15T11:00:00.000Z",
            "start": "2024-01-15T10:00:00.000Z", "end": "2024-01-15T11:00:00.000Z",
            "timezone_offset": "-05:00", "sport_name": "running", "score_state": "SCORED",
            "score": None}], "next_token": None}

        async def mock_request(**kwargs):
            url = kwargs.get("url", "")
            mock = Mock()
            mock.status_code = 200
            mock.raise_for_status = Mock()
            if "profile/basic" in url:
                mock.json.return_value = profile_data
            elif "recovery" in url:
                mock.json.return_value = recovery_data
            elif "sleep" in url:
                mock.json.return_value = sleep_data
            elif "cycle" in url:
                mock.json.return_value = cycle_data
            elif "workout" in url:
                mock.json.return_value = workout_data
            else:
                mock.json.return_value = profile_data
            return mock

        async_client._http_client.request = AsyncMock(side_effect=mock_request)

        dash = await async_client.fetch_dashboard()

        assert "profile" in dash
        assert "recovery" in dash
        assert "sleep" in dash
        assert "cycle" in dash
        assert "workout" in dash
        # Profile should be a model, not a collection
        assert isinstance(dash["profile"], UserProfileBasic)
        # Others should be single records (Recovery, Sleep, Cycle, Workout), not collections
        assert isinstance(dash["recovery"], Recovery)
        assert isinstance(dash["sleep"], Sleep)
        assert isinstance(dash["cycle"], Cycle)
        assert isinstance(dash["workout"], Workout)

    @pytest.mark.asyncio
    async def test_fetch_all_selective(self, async_client):
        """fetch_all() with selective flags only fetches requested types."""
        recovery_data = {"records": [{"cycle_id": 1, "sleep_id": "s1", "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z", "updated_at": "2024-01-15T08:00:00.000Z",
            "score_state": "SCORED", "score": None}], "next_token": None}

        async def mock_request(**kwargs):
            mock = Mock()
            mock.status_code = 200
            mock.raise_for_status = Mock()
            mock.json.return_value = recovery_data
            return mock

        async_client._http_client.request = AsyncMock(side_effect=mock_request)

        data = await async_client.fetch_all(
            recovery=True, sleep=False, cycles=False, workouts=False
        )

        assert "recovery" in data
        assert "sleep" not in data
        assert "cycles" not in data
        assert "workouts" not in data


# =============================================================================
# Async HTTP Connection Pooling Tests
# =============================================================================

class TestAsyncHTTPConnectionPooling:
    """Tests for async HTTP connection pooling and session management."""

    def test_async_client_reuses_session(self, async_client):
        """The same httpx.AsyncClient instance is reused."""
        session = async_client._http_client
        assert session is async_client._http_client

    def test_async_client_session_has_timeout_config(self, async_client):
        """Async session should have the configured read timeout of 30s."""
        assert async_client._http_client.timeout.read == 30.0
        assert async_client._http_client.timeout.connect == 5.0

    @pytest.mark.asyncio
    async def test_async_client_closes_session_on_exit(self, mock_auth):
        """Async session should be closed after context manager exit."""
        with patch("strapkit.async_client.OAuthHandler", return_value=mock_auth):
            async with AsyncWhoopClient(
                client_id="test_id", client_secret="test_secret"
            ) as client:
                session = client._http_client
            assert session.is_closed


# =============================================================================
# Async Rate Limit Header Tests (WHOOP v2: X-RateLimit-Reset)
# =============================================================================

class TestAsyncRateLimitHeaders:
    """Async 429 handling waits for the time given by WHOOP's rate limit headers."""

    @staticmethod
    def _rate_limited(headers) -> Mock:
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = headers
        mock_response.text = "Too Many Requests"
        return mock_response

    @pytest.mark.asyncio
    async def test_waits_for_x_ratelimit_reset_then_retries(self, async_client) -> None:
        """A 429 with X-RateLimit-Reset sleeps that long and retries once."""
        async_client._http_client.request = AsyncMock(side_effect=[
            self._rate_limited({"X-RateLimit-Reset": "7"}),
            _json_response({"ok": True}),
        ])
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await async_client._request("GET", "/test")

        assert result == {"ok": True}
        mock_sleep.assert_awaited_once_with(7)
        assert async_client._http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_x_ratelimit_reset_preferred_over_retry_after(self, async_client) -> None:
        """X-RateLimit-Reset wins over Retry-After, for the wait and the error."""
        async_client._http_client.request = AsyncMock(
            return_value=self._rate_limited({"Retry-After": "30", "X-RateLimit-Reset": "7"})
        )
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        mock_sleep.assert_awaited_once_with(7)
        assert exc.value.retry_after == 7

    @pytest.mark.asyncio
    async def test_lowercase_dict_headers(self, async_client) -> None:
        """Lowercase header names in a plain dict are still honoured."""
        async_client._http_client.request = AsyncMock(
            return_value=self._rate_limited({"x-ratelimit-reset": "9"})
        )
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        mock_sleep.assert_awaited_once_with(9)
        assert exc.value.retry_after == 9

    @pytest.mark.asyncio
    async def test_wait_is_capped_at_120_seconds(self, async_client) -> None:
        """Long resets are capped at 2 minutes; the error reports the real value."""
        async_client._http_client.request = AsyncMock(
            return_value=self._rate_limited({"X-RateLimit-Reset": "500"})
        )
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        mock_sleep.assert_awaited_once_with(120)
        assert exc.value.retry_after == 500
        assert async_client._http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_defaults_to_60_without_headers(self, async_client) -> None:
        """Without rate limit headers the wait defaults to 60 seconds."""
        async_client._http_client.request = AsyncMock(return_value=self._rate_limited({}))
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        mock_sleep.assert_awaited_once_with(60)
        assert exc.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_invalid_reset_falls_back_to_retry_after(self, async_client) -> None:
        """A negative X-RateLimit-Reset is ignored in favour of Retry-After."""
        async_client._http_client.request = AsyncMock(
            return_value=self._rate_limited({"X-RateLimit-Reset": "-3", "Retry-After": "4"})
        )
        with patch(
            "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                await async_client._request("GET", "/test")

        mock_sleep.assert_awaited_once_with(4)
        assert exc.value.retry_after == 4

    @pytest.mark.asyncio
    async def test_real_httpx_headers_over_transport(self, async_client) -> None:
        """End to end through httpx: real (case-insensitive) response headers are used."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(
                    429, headers={"x-ratelimit-reset": "5", "retry-after": "30"}
                )
            return httpx.Response(200, json={"user_id": 1, "email": "a@b.com",
                                             "first_name": "A", "last_name": "B"})

        _install_mock_transport(async_client, handler)
        try:
            with patch(
                "strapkit.async_client.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep:
                profile = await async_client.get_profile_basic()
        finally:
            await async_client._http_client.aclose()

        assert isinstance(profile, UserProfileBasic)
        mock_sleep.assert_awaited_once_with(5)
        assert len(calls) == 2
        assert str(calls[0].url) == "https://api.prod.whoop.com/developer/v2/user/profile/basic"


# =============================================================================
# Async Sleep For Cycle Tests (GET /developer/v2/cycle/{cycle_id}/sleep)
# =============================================================================

class TestAsyncSleepForCycle:
    """Tests for async get_sleep_for_cycle()."""

    @pytest.mark.asyncio
    async def test_get_sleep_for_cycle_path_and_parsing(self, async_client, sample_sleep_dict) -> None:
        """Requests the cycle's sleep and parses it into a Sleep model."""
        payload = dict(sample_sleep_dict, v1_id=93845)
        async_client._http_client.request = AsyncMock(return_value=_json_response(payload))

        sleep = await async_client.get_sleep_for_cycle(100)

        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "/developer/v2/cycle/100/sleep"
        assert isinstance(sleep, Sleep)
        assert sleep.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert sleep.cycle_id == 100
        assert sleep.v1_id == 93845

    @pytest.mark.asyncio
    async def test_get_sleep_for_cycle_without_v1_id(self, async_client, sample_sleep_dict) -> None:
        """The deprecated v1_id is optional in the response."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_sleep_dict)
        )

        sleep = await async_client.get_sleep_for_cycle(100)

        assert sleep.v1_id is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cycle_id", [0, -1])
    async def test_get_sleep_for_cycle_invalid_id(self, async_client, cycle_id) -> None:
        """Non-positive cycle IDs are rejected before any HTTP call."""
        async_client._http_client.request = AsyncMock()

        with pytest.raises(ValueError, match="Invalid cycle_id"):
            await async_client.get_sleep_for_cycle(cycle_id)

        async_client._http_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_sleep_for_cycle_not_found(self, async_client) -> None:
        """A 404 (no sleep for the cycle) raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.text = "Not Found"
        async_client._http_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(WhoopNotFoundError):
            await async_client.get_sleep_for_cycle(100)


# =============================================================================
# Async Activity ID Mapping Tests (GET /developer/v1/activity-mapping/{id})
# =============================================================================

class TestAsyncActivityMapping:
    """Tests for async get_activity_mapping()."""

    @pytest.mark.asyncio
    async def test_get_activity_mapping_path_and_parsing(
        self, async_client, sample_activity_mapping_dict
    ) -> None:
        """Requests the v1 mapping path and parses an ActivityIdMapping."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_activity_mapping_dict)
        )

        mapping = await async_client.get_activity_mapping(12345678)

        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "/developer/v1/activity-mapping/12345678"
        assert isinstance(mapping, ActivityIdMapping)
        assert mapping.v2_activity_id == "ecfc6a15-4661-442f-a9a4-f160dd7afae8"

    @pytest.mark.asyncio
    async def test_mapping_result_feeds_get_workout(
        self, async_client, sample_activity_mapping_dict, sample_workout_dict
    ) -> None:
        """The mapped v2 UUID is accepted by get_workout()."""
        async_client._http_client.request = AsyncMock(side_effect=[
            _json_response(sample_activity_mapping_dict),
            _json_response(sample_workout_dict),
        ])

        mapping = await async_client.get_activity_mapping(1043)
        await async_client.get_workout(mapping.v2_activity_id)

        assert async_client._http_client.request.call_args.kwargs["url"] == (
            "/developer/v2/activity/workout/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("activity_v1_id", [0, -5])
    async def test_get_activity_mapping_invalid_id(self, async_client, activity_v1_id) -> None:
        """Non-positive v1 IDs are rejected before any HTTP call."""
        async_client._http_client.request = AsyncMock()

        with pytest.raises(ValueError, match="Invalid activity_v1_id"):
            await async_client.get_activity_mapping(activity_v1_id)

        async_client._http_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_activity_mapping_not_found(self, async_client) -> None:
        """An unknown v1 ID (404) raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.text = "Activity mapping not found"
        async_client._http_client.request = AsyncMock(return_value=mock_response)

        with pytest.raises(WhoopNotFoundError):
            await async_client.get_activity_mapping(1)


# =============================================================================
# Async Date Parameter Formatting Tests
# =============================================================================

class TestAsyncDateParamFormatting:
    """Tests for async client _format_date_param() and collection start/end params."""

    def test_date_only_string_expanded_to_midnight_utc(self, async_client) -> None:
        """WHOOP v2 rejects date-only strings, so YYYY-MM-DD becomes a date-time."""
        assert async_client._format_date_param("2024-01-15") == "2024-01-15T00:00:00.000Z"

    @pytest.mark.parametrize(
        "value",
        [
            "2024-01-15T10:30:00.000Z",
            "2024-01-15T10:30:00+00:00",
            "2024-01-15T00:00:00Z",
            "2024-1-5",
            "20240115",
            "2024-01-15 ",
            "not-a-date",
        ],
    )
    def test_other_strings_pass_through_unchanged(self, async_client, value) -> None:
        """Any string that is not exactly YYYY-MM-DD is passed through as-is."""
        assert async_client._format_date_param(value) == value

    def test_none_returns_none(self, async_client) -> None:
        assert async_client._format_date_param(None) is None

    def test_aware_datetime_unchanged_behaviour(self, async_client) -> None:
        dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert async_client._format_date_param(dt) == "2024-01-15T10:30:00+00:00"

    def test_naive_datetime_treated_as_utc(self, async_client) -> None:
        assert async_client._format_date_param(datetime(2024, 1, 15, 10, 30)) == (
            "2024-01-15T10:30:00+00:00"
        )

    def test_date_object_unchanged_behaviour(self, async_client) -> None:
        assert async_client._format_date_param(date(2024, 1, 15)) == (
            "2024-01-15T00:00:00+00:00"
        )

    @pytest.mark.asyncio
    async def test_collection_request_sends_normalized_dates(self, async_client) -> None:
        """Date-only start/end strings reach the API as full date-times."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response({"records": [], "next_token": None})
        )

        await async_client.get_cycle_collection(start="2024-01-01", end="2024-01-31", limit=5)

        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["params"]["start"] == "2024-01-01T00:00:00.000Z"
        assert call_kwargs["params"]["end"] == "2024-01-31T00:00:00.000Z"
        assert call_kwargs["params"]["limit"] == 5
        assert call_kwargs["url"] == "/developer/v2/cycle"


# =============================================================================
# Async Legacy v1 ID Rejection Tests
# =============================================================================

class TestAsyncLegacyIdRejection:
    """Async get_sleep / get_workout reject legacy v1 integer IDs locally."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_id", [123, "12345678", " 42 "])
    async def test_get_sleep_rejects_v1_ids(self, async_client, bad_id) -> None:
        async_client._http_client.request = AsyncMock()

        with pytest.raises(ValueError, match="Invalid sleep_id") as exc:
            await async_client.get_sleep(bad_id)

        assert "get_activity_mapping" in str(exc.value)
        async_client._http_client.request.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_id", [123, "12345678", " 42 "])
    async def test_get_workout_rejects_v1_ids(self, async_client, bad_id) -> None:
        async_client._http_client.request = AsyncMock()

        with pytest.raises(ValueError, match="Invalid workout_id") as exc:
            await async_client.get_workout(bad_id)

        assert "get_activity_mapping" in str(exc.value)
        async_client._http_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_sleep_rejects_whitespace(self, async_client) -> None:
        with pytest.raises(ValueError, match="Invalid sleep_id"):
            await async_client.get_sleep("   ")

    @pytest.mark.asyncio
    async def test_get_workout_rejects_whitespace(self, async_client) -> None:
        with pytest.raises(ValueError, match="Invalid workout_id"):
            await async_client.get_workout("   ")

    @pytest.mark.asyncio
    async def test_get_sleep_accepts_uuid_object(self, async_client, sample_sleep_dict) -> None:
        """A uuid.UUID is used as its string form in the path."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_sleep_dict)
        )
        await async_client.get_sleep(uuid.UUID("ecfc6a15-4661-442f-a9a4-f160dd7afae8"))
        assert async_client._http_client.request.call_args.kwargs["url"] == (
            "/developer/v2/activity/sleep/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    @pytest.mark.asyncio
    async def test_get_workout_accepts_uuid_object(
        self, async_client, sample_workout_dict
    ) -> None:
        """A uuid.UUID is used as its string form in the path."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_workout_dict)
        )
        await async_client.get_workout(uuid.UUID("ecfc6a15-4661-442f-a9a4-f160dd7afae8"))
        assert async_client._http_client.request.call_args.kwargs["url"] == (
            "/developer/v2/activity/workout/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_id", [None, 1.5, b"abc"])
    async def test_non_string_ids_get_no_legacy_hint(self, async_client, bad_id) -> None:
        """Only int / all-digit IDs mention get_activity_mapping()."""
        async_client._http_client.request = AsyncMock()
        with pytest.raises(ValueError, match="Invalid sleep_id") as sleep_exc:
            await async_client.get_sleep(bad_id)
        with pytest.raises(ValueError, match="Invalid workout_id") as workout_exc:
            await async_client.get_workout(bad_id)
        assert "get_activity_mapping" not in str(sleep_exc.value)
        assert "get_activity_mapping" not in str(workout_exc.value)
        async_client._http_client.request.assert_not_called()


# =============================================================================
# Async v2 Model Parsing Through The Client
# =============================================================================

class TestAsyncV2ResponseParsing:
    """v2-only fields parse correctly through the async client methods."""

    @pytest.mark.asyncio
    async def test_get_cycle_parses_step_count(self, async_client, sample_cycle_dict) -> None:
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(dict(sample_cycle_dict, step_count=8234))
        )

        cycle = await async_client.get_cycle(999)

        assert async_client._http_client.request.call_args.kwargs["url"] == "/developer/v2/cycle/999"
        assert cycle.step_count == 8234

    @pytest.mark.asyncio
    async def test_get_cycle_null_step_count(self, async_client, sample_cycle_dict) -> None:
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_cycle_dict)
        )

        cycle = await async_client.get_cycle(999)

        assert cycle.step_count is None

    @pytest.mark.asyncio
    async def test_get_workout_full_v2_payload(self, async_client, sample_workout_dict) -> None:
        """A full v2 workout (sport_name, zone_durations, v1_id) parses."""
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_workout_dict)
        )

        workout = await async_client.get_workout(sample_workout_dict["id"])

        assert workout.sport_name == "yoga"
        assert workout.v1_id == 1043
        assert workout.score is not None
        assert workout.score.zone_durations is not None
        assert workout.score.zone_durations.zone_two_milli == 900000

    @pytest.mark.asyncio
    async def test_get_workout_without_sport_id(self, async_client, sample_workout_dict) -> None:
        """WHOOP drops the deprecated sport_id and v1_id; the workout still parses."""
        payload = dict(sample_workout_dict)
        del payload["sport_id"]
        del payload["v1_id"]
        async_client._http_client.request = AsyncMock(return_value=_json_response(payload))

        workout = await async_client.get_workout(payload["id"])

        assert workout.sport_id is None
        assert workout.v1_id is None
        assert workout.sport_name == "yoga"

    @pytest.mark.asyncio
    async def test_get_recovery_for_cycle_path(self, async_client, sample_recovery_dict) -> None:
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(sample_recovery_dict)
        )

        await async_client.get_recovery_for_cycle(123)

        assert async_client._http_client.request.call_args.kwargs["url"] == (
            "/developer/v2/cycle/123/recovery"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method_name, expected_url",
        [
            ("get_recovery_collection", "/developer/v2/recovery"),
            ("get_sleep_collection", "/developer/v2/activity/sleep"),
            ("get_cycle_collection", "/developer/v2/cycle"),
            ("get_workout_collection", "/developer/v2/activity/workout"),
        ],
    )
    async def test_collection_paths_are_v2(self, async_client, method_name, expected_url) -> None:
        async_client._http_client.request = AsyncMock(
            return_value=_json_response({"records": [], "next_token": None})
        )

        await getattr(async_client, method_name)(limit=3, next_token="tok")

        call_kwargs = async_client._http_client.request.call_args.kwargs
        assert call_kwargs["url"] == expected_url
        assert call_kwargs["params"] == {"limit": 3, "nextToken": "tok"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method_name, expected_url",
        [
            ("get_profile_basic", "/developer/v2/user/profile/basic"),
            ("get_body_measurement", "/developer/v2/user/measurement/body"),
        ],
    )
    async def test_user_paths_are_v2(self, async_client, method_name, expected_url) -> None:
        payloads = {
            "get_profile_basic": {"user_id": 1, "email": "a@b.com",
                                  "first_name": "A", "last_name": "B"},
            "get_body_measurement": {"height_meter": 1.8, "weight_kilogram": 80.0,
                                     "max_heart_rate": 190},
        }
        async_client._http_client.request = AsyncMock(
            return_value=_json_response(payloads[method_name])
        )

        await getattr(async_client, method_name)()

        assert async_client._http_client.request.call_args.kwargs["url"] == expected_url


# =============================================================================
# Sync / Async API Parity
# =============================================================================

class TestSyncAsyncParity:
    """The new v2 methods exist on both clients with matching signatures."""

    @pytest.mark.parametrize(
        "name", ["get_sleep_for_cycle", "get_activity_mapping", "revoke_access"]
    )
    def test_v2_methods_match(self, name) -> None:
        import inspect

        from strapkit.client import WhoopClient

        sync_method = getattr(WhoopClient, name)
        async_method = getattr(AsyncWhoopClient, name)
        assert inspect.iscoroutinefunction(async_method)
        assert not inspect.iscoroutinefunction(sync_method)
        assert inspect.signature(sync_method) == inspect.signature(async_method)
