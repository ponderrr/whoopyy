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
    WhoopRateLimitError,
    WhoopValidationError,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_auth():
    """Create a mock OAuth handler."""
    auth = Mock()
    auth.get_valid_token.return_value = "test_access_token"
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
                "sleep_id": 1,
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
    async def test_request_auth_error_handling(self, async_client) -> None:
        """Test authentication error (401) handling."""
        mock_response = Mock()
        mock_response.status_code = 401
        
        async_client._http_client.request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(WhoopAuthError) as exc:
            await async_client._request("GET", "/test")
        
        assert exc.value.status_code == 401
    
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
        """Test async get_recovery method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cycle_id": 123,
            "sleep_id": 456,
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
        
        recovery = await async_client.get_recovery(123)
        
        assert isinstance(recovery, Recovery)
        assert recovery.cycle_id == 123
    
    @pytest.mark.asyncio
    async def test_get_recovery_invalid_id(self, async_client) -> None:
        """Test get_recovery with invalid ID."""
        with pytest.raises(ValueError, match="Invalid recovery_id"):
            await async_client.get_recovery(-1)
    
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
            "id": 123,
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
        
        sleep = await async_client.get_sleep(123)
        
        assert isinstance(sleep, Sleep)
        assert sleep.id == 123


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
            "id": 123,
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
        
        workout = await async_client.get_workout(123)
        
        assert isinstance(workout, Workout)
        assert workout.id == 123
        assert workout.sport_name == "Running"


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
