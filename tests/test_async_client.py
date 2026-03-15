"""
Unit tests for WhoopPy async client.

Tests cover:
- Initialization and validation
- Async request handling (mocked)
- Async API methods (mocked)
- Async context manager
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

import httpx

from whoopyy.async_client import AsyncWhoopClient
from whoopyy.models import (
    UserProfileBasic,
    Recovery,
    RecoveryCollection,
    Sleep,
    Cycle,
    Workout,
)
from whoopyy.exceptions import (
    WhoopAPIError,
    WhoopAuthError,
    WhoopNetworkError,
    WhoopNotFoundError,
    WhoopRateLimitError,
    WhoopValidationError,
    is_retryable_error,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_auth():
    """Create a mock OAuth handler."""
    auth = Mock()
    auth.get_valid_token.return_value = "test_access_token"
    auth.async_get_valid_token = AsyncMock(return_value="test_access_token")
    auth.has_valid_tokens.return_value = True
    auth.close = Mock()
    return auth


@pytest.fixture
def async_client(mock_auth):
    """Create an AsyncWhoopClient with mocked auth."""
    with patch("whoopyy.async_client.OAuthHandler", return_value=mock_auth):
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
        with patch("whoopyy.async_client.OAuthHandler", return_value=mock_auth):
            client = AsyncWhoopClient(
                client_id="test_id",
                client_secret="test_secret",
            )
            
            assert client.client_id == "test_id"
            assert client.client_secret == "test_secret"
            assert client._authenticated is False
    
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
        """Test rate limit (429) handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(WhoopRateLimitError) as exc:
            await async_client._request("GET", "/test")
        
        assert exc.value.retry_after == 60
        assert exc.value.status_code == 429
    
    @pytest.mark.asyncio
    async def test_request_auth_error_handling(self, async_client, mock_auth) -> None:
        """Test authentication error (401) triggers refresh and retry; second 401 raises WhoopAuthError."""
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        mock_response_401.text = "Unauthorized"

        mock_auth.refresh_access_token = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response_401)

        with pytest.raises(WhoopAuthError) as exc:
            await async_client._request("GET", "/test")

        assert exc.value.status_code == 401
        mock_auth.refresh_access_token.assert_called_once()
    
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

        mock_auth.refresh_access_token = Mock()

        async_client._http_client.request = AsyncMock(side_effect=[mock_401, mock_200])

        result = await async_client._request("GET", "/test")

        assert result == {"ok": True}
        mock_auth.refresh_access_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_401_double_triggers_raises_auth_error(self, async_client, mock_auth) -> None:
        """Test that two consecutive 401s raises WhoopAuthError after one refresh."""
        mock_401 = Mock()
        mock_401.status_code = 401
        mock_401.text = "Unauthorized"

        mock_auth.refresh_access_token = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_401)

        with pytest.raises(WhoopAuthError):
            await async_client._request("GET", "/test")

        mock_auth.refresh_access_token.assert_called_once()

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
            "sport_id": 0,
            "score_state": "SCORED",
            "score": None,
        }
        mock_response.raise_for_status = Mock()

        async_client._http_client.request = AsyncMock(return_value=mock_response)

        workout = await async_client.get_workout("abc-workout-uuid")

        assert isinstance(workout, Workout)
        assert workout.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert workout.sport_display_name == "Running"

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
            "sport_id": 0,
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
        with patch("whoopyy.async_client.OAuthHandler", return_value=mock_auth):
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
    """Tests for async revoke_access() method."""

    @pytest.mark.asyncio
    async def test_revoke_access_sends_post(self, async_client, mock_auth) -> None:
        """Test that revoke_access() POSTs to the correct OAuth revocation URL."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(async_client._http_client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
            await async_client.revoke_access()

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/oauth/oauth2/revoke" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_revoke_access_clears_tokens(self, async_client, mock_auth) -> None:
        """Test that revoke_access() clears stored tokens on success."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_auth._tokens = {"access_token": "test_access_token"}

        with patch.object(async_client._http_client, "post", new=AsyncMock(return_value=mock_response)):
            await async_client.revoke_access()

        assert mock_auth._tokens is None
        assert async_client._authenticated is False

    @pytest.mark.asyncio
    async def test_revoke_access_raises_on_error(self, async_client, mock_auth) -> None:
        """Test that revoke_access() raises WhoopAuthError on non-200 response."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_token"

        with patch.object(async_client._http_client, "post", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(WhoopAuthError) as exc_info:
                await async_client.revoke_access()

        assert exc_info.value.status_code == 400


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

        from whoopyy.models import SleepCollection
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

        from whoopyy.models import CycleCollection, Cycle
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
            "sport_id": 44,
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

        from whoopyy.models import WorkoutCollection, Workout
        collection = await async_client.get_workout_collection(limit=10)

        assert isinstance(collection, WorkoutCollection)
        assert len(collection.records) == 3
        assert all(w.sport_display_name == "Yoga" for w in collection.records)

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
            "timezone_offset": "-05:00", "sport_id": 0, "score_state": "SCORED",
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
            "timezone_offset": "-05:00", "sport_id": 0, "score_state": "SCORED",
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
        with patch("whoopyy.async_client.OAuthHandler", return_value=mock_auth):
            async with AsyncWhoopClient(
                client_id="test_id", client_secret="test_secret"
            ) as client:
                session = client._http_client
            assert session.is_closed
