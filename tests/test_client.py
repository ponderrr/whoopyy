"""
Unit tests for WhoopPy main client.

Tests cover:
- Initialization and validation
- Request handling (mocked)
- API methods (mocked)
- Pagination
- Error handling
- Context manager
"""

import time
from datetime import datetime, date, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
import httpx

from whoopyy.client import WhoopClient
from whoopyy.models import (
    UserProfileBasic,
    BodyMeasurement,
    Recovery,
    RecoveryCollection,
    RecoveryScore,
    Sleep,
    SleepCollection,
    Cycle,
    CycleCollection,
    Workout,
    WorkoutCollection,
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
    auth.has_valid_tokens.return_value = True
    auth.close = Mock()
    return auth


@pytest.fixture
def client(mock_auth):
    """Create a WhoopClient with mocked auth."""
    with patch("whoopyy.client.OAuthHandler", return_value=mock_auth):
        c = WhoopClient(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        yield c
        c.close()


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
def mock_recovery_response():
    """Mock single recovery API response."""
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
            "resting_heart_rate": 52,
            "hrv_rmssd_milli": 65.2,
            "spo2_percentage": 98.5,
            "skin_temp_celsius": 36.5,
        },
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
            {
                "cycle_id": 2,
                "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567891",
                "user_id": 789,
                "created_at": "2024-01-16T08:00:00.000Z",
                "updated_at": "2024-01-16T08:30:00.000Z",
                "score_state": "SCORED",
                "score": {
                    "user_calibrating": False,
                    "recovery_score": 80.0,
                    "resting_heart_rate": 50,
                    "hrv_rmssd_milli": 70.0,
                },
            },
        ],
        "next_token": None,
    }


# =============================================================================
# Initialization Tests
# =============================================================================

class TestWhoopClientInit:
    """Tests for WhoopClient initialization."""
    
    def test_valid_initialization(self, mock_auth) -> None:
        """Test creating client with valid parameters."""
        with patch("whoopyy.client.OAuthHandler", return_value=mock_auth):
            client = WhoopClient(
                client_id="test_id",
                client_secret="test_secret",
            )
            
            assert client.client_id == "test_id"
            assert client.client_secret == "test_secret"
            assert client._authenticated is False
            
            client.close()
    
    def test_empty_client_id_rejected(self) -> None:
        """Test that empty client_id raises error."""
        with pytest.raises(ValueError, match="client_id is required"):
            WhoopClient(
                client_id="",
                client_secret="test_secret",
            )
    
    def test_empty_client_secret_rejected(self) -> None:
        """Test that empty client_secret raises error."""
        with pytest.raises(ValueError, match="client_secret is required"):
            WhoopClient(
                client_id="test_id",
                client_secret="",
            )


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Tests for authentication functionality."""
    
    def test_authenticate_success(self, client, mock_auth) -> None:
        """Test successful authentication."""
        mock_auth.has_valid_tokens.return_value = False
        client.authenticate()

        mock_auth.authorize.assert_called_once()
        assert client._authenticated is True
    
    def test_is_authenticated_after_auth(self, client, mock_auth) -> None:
        """Test is_authenticated after authentication."""
        client.authenticate()
        
        assert client.is_authenticated() is True
    
    def test_is_authenticated_with_valid_tokens(self, client, mock_auth) -> None:
        """Test is_authenticated when tokens are valid."""
        mock_auth.has_valid_tokens.return_value = True
        
        assert client.is_authenticated() is True


# =============================================================================
# Request Tests
# =============================================================================

class TestRequest:
    """Tests for internal request handling."""
    
    def test_request_adds_auth_header(self, client, mock_auth) -> None:
        """Test that requests include auth header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ) as mock_request:
            client._request("GET", "/test")
            
            # Verify auth header was passed
            call_kwargs = mock_request.call_args.kwargs
            assert "Authorization" in call_kwargs["headers"]
            assert "Bearer test_access_token" in call_kwargs["headers"]["Authorization"]
    
    def test_request_rate_limit_handling(self, client) -> None:
        """Test rate limit (429) handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")
            
            assert exc.value.retry_after == 60
            assert exc.value.status_code == 429
    
    def test_request_auth_error_handling(self, client, mock_auth) -> None:
        """Test authentication error (401) triggers refresh and retry; second 401 raises WhoopAuthError."""
        mock_response_401 = Mock()
        mock_response_401.status_code = 401
        mock_response_401.text = "Unauthorized"

        mock_auth.refresh_access_token = Mock()

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response_401,
        ):
            with pytest.raises(WhoopAuthError) as exc:
                client._request("GET", "/test")

            assert exc.value.status_code == 401
            mock_auth.refresh_access_token.assert_called_once()
    
    def test_request_validation_error_handling(self, client) -> None:
        """Test validation error (400) handling."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid parameter"
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            with pytest.raises(WhoopValidationError) as exc:
                client._request("GET", "/test")
            
            assert exc.value.status_code == 400
    
    def test_request_204_returns_empty_dict(self, client) -> None:
        """Test 204 No Content returns empty dict."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.raise_for_status = Mock()

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            result = client._request("DELETE", "/test")

            assert result == {}

    def test_network_error_raises_whoop_network_error(self, client) -> None:
        """Test that httpx.RequestError raises WhoopNetworkError."""
        with patch.object(
            client._http_client,
            "request",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(WhoopNetworkError):
                client._request("GET", "/test")

    def test_404_raises_whoop_not_found_error(self, client) -> None:
        """Test that a 404 response raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response,
        ):
            with pytest.raises(WhoopNotFoundError) as exc:
                client._request("GET", "/test/resource")

            assert exc.value.status_code == 404

    def test_401_triggers_refresh_and_retry(self, client, mock_auth) -> None:
        """Test that a 401 triggers token refresh and a successful retry."""
        mock_401 = Mock()
        mock_401.status_code = 401
        mock_401.text = "Unauthorized"

        mock_200 = Mock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"ok": True}
        mock_200.raise_for_status = Mock()

        mock_auth.refresh_access_token = Mock()

        with patch.object(
            client._http_client,
            "request",
            side_effect=[mock_401, mock_200],
        ):
            result = client._request("GET", "/test")

        assert result == {"ok": True}
        mock_auth.refresh_access_token.assert_called_once()

    def test_401_double_triggers_raises_auth_error(self, client, mock_auth) -> None:
        """Test that two consecutive 401s raises WhoopAuthError after one refresh."""
        mock_401 = Mock()
        mock_401.status_code = 401
        mock_401.text = "Unauthorized"

        mock_auth.refresh_access_token = Mock()

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_401,
        ):
            with pytest.raises(WhoopAuthError):
                client._request("GET", "/test")

        mock_auth.refresh_access_token.assert_called_once()

    def test_is_retryable_error_true_for_network_error(self, client) -> None:
        """Test that is_retryable_error returns True for WhoopNetworkError."""
        error = WhoopNetworkError("timeout")
        assert is_retryable_error(error) is True


# =============================================================================
# Profile Methods Tests
# =============================================================================

class TestProfileMethods:
    """Tests for profile API methods."""
    
    def test_get_profile_basic(self, client, mock_profile_response) -> None:
        """Test get_profile_basic method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_profile_response
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            profile = client.get_profile_basic()
            
            assert isinstance(profile, UserProfileBasic)
            assert profile.user_id == 12345
            assert profile.email == "test@example.com"
            assert profile.first_name == "John"
    
    def test_get_body_measurement(self, client) -> None:
        """Test get_body_measurement method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "height_meter": 1.83,
            "weight_kilogram": 82.5,
            "max_heart_rate": 195,
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            body = client.get_body_measurement()
            
            assert isinstance(body, BodyMeasurement)
            assert body.height_meter == 1.83
            assert body.weight_kilogram == 82.5


# =============================================================================
# Recovery Methods Tests
# =============================================================================

class TestRecoveryMethods:
    """Tests for recovery API methods."""
    
    def test_get_recovery(self, client, mock_recovery_response) -> None:
        """Test get_recovery_for_cycle method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_recovery_response
        mock_response.raise_for_status = Mock()

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            recovery = client.get_recovery_for_cycle(123)

            assert isinstance(recovery, Recovery)
            assert recovery.cycle_id == 123
            assert recovery.score is not None
            assert recovery.score.recovery_score == 75.5

    def test_get_recovery_invalid_id(self, client) -> None:
        """Test get_recovery_for_cycle with invalid ID."""
        with pytest.raises(ValueError, match="Invalid cycle_id"):
            client.get_recovery_for_cycle(-1)
    
    def test_get_recovery_collection(
        self, client, mock_recovery_collection_response
    ) -> None:
        """Test get_recovery_collection method."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_recovery_collection_response
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            collection = client.get_recovery_collection(limit=10)
            
            assert isinstance(collection, RecoveryCollection)
            assert len(collection.records) == 2
            assert collection.next_token is None
    
    def test_get_recovery_collection_invalid_limit(self, client) -> None:
        """Test get_recovery_collection with invalid limit."""
        with pytest.raises(WhoopValidationError):
            client.get_recovery_collection(limit=100)  # Max is 50
    
    def test_get_recovery_collection_with_dates(self, client) -> None:
        """Test get_recovery_collection with date filtering."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"records": [], "next_token": None}
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ) as mock_request:
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 31, tzinfo=timezone.utc)
            
            client.get_recovery_collection(start=start, end=end)
            
            # Verify params were passed
            call_kwargs = mock_request.call_args.kwargs
            assert "start" in call_kwargs["params"]
            assert "end" in call_kwargs["params"]
    
    def test_get_all_recovery(self, client) -> None:
        """Test get_all_recovery with pagination."""
        # First page
        page1_response = {
            "records": [
                {
                    "cycle_id": 1,
                    "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "user_id": 1,
                    "created_at": "2024-01-15T08:00:00.000Z",
                    "updated_at": "2024-01-15T08:00:00.000Z",
                    "score_state": "SCORED",
                    "score": {
                        "user_calibrating": False,
                        "recovery_score": 70.0,
                        "resting_heart_rate": 50,
                        "hrv_rmssd_milli": 60.0,
                    },
                }
            ],
            "next_token": "page2",
        }

        # Second page
        page2_response = {
            "records": [
                {
                    "cycle_id": 2,
                    "sleep_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567891",
                    "user_id": 1,
                    "created_at": "2024-01-16T08:00:00.000Z",
                    "updated_at": "2024-01-16T08:00:00.000Z",
                    "score_state": "SCORED",
                    "score": {
                        "user_calibrating": False,
                        "recovery_score": 75.0,
                        "resting_heart_rate": 52,
                        "hrv_rmssd_milli": 65.0,
                    },
                }
            ],
            "next_token": None,
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = [page1_response, page2_response]
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            all_records = client.get_all_recovery()
            
            assert len(all_records) == 2
            assert all_records[0].cycle_id == 1
            assert all_records[1].cycle_id == 2
    
    def test_get_all_recovery_with_max_records(self, client) -> None:
        """Test get_all_recovery with max_records limit."""
        page_response = {
            "records": [
                {
                    "cycle_id": i + 1,
                    "sleep_id": f"a1b2c3d4-e5f6-7890-abcd-ef123456{i:04d}",
                    "user_id": 1,
                    "created_at": "2024-01-15T08:00:00.000Z",
                    "updated_at": "2024-01-15T08:00:00.000Z",
                    "score_state": "SCORED",
                    "score": {
                        "user_calibrating": False,
                        "recovery_score": 70.0,
                        "resting_heart_rate": 50,
                        "hrv_rmssd_milli": 60.0,
                    },
                }
                for i in range(10)
            ],
            "next_token": "more",
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page_response
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            records = client.get_all_recovery(max_records=5)
            
            assert len(records) == 5


# =============================================================================
# Sleep Methods Tests
# =============================================================================

class TestSleepMethods:
    """Tests for sleep API methods."""
    
    def test_get_sleep(self, client) -> None:
        """Test get_sleep method."""
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

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            sleep = client.get_sleep("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

            assert isinstance(sleep, Sleep)
            assert sleep.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            assert sleep.nap is False

    def test_get_sleep_invalid_id(self, client) -> None:
        """Test get_sleep with invalid ID."""
        with pytest.raises(ValueError, match="Invalid sleep_id"):
            client.get_sleep("")

    def test_get_sleep_accepts_uuid_string(self, client) -> None:
        """Test get_sleep accepts a UUID string and makes HTTP call."""
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

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ) as mock_request:
            sleep = client.get_sleep("abc-123")

            assert isinstance(sleep, Sleep)
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert "abc-123" in call_kwargs["url"]

    def test_get_sleep_rejects_empty_string(self, client) -> None:
        """Test get_sleep raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid sleep_id"):
            client.get_sleep("")


# =============================================================================
# Cycle Methods Tests
# =============================================================================

class TestCycleMethods:
    """Tests for cycle API methods."""
    
    def test_get_cycle(self, client) -> None:
        """Test get_cycle method."""
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
        
        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            cycle = client.get_cycle(123)
            
            assert isinstance(cycle, Cycle)
            assert cycle.id == 123


# =============================================================================
# Workout Methods Tests
# =============================================================================

class TestWorkoutMethods:
    """Tests for workout API methods."""
    
    def test_get_workout(self, client) -> None:
        """Test get_workout method."""
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

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ):
            workout = client.get_workout("abc-workout-uuid")

            assert isinstance(workout, Workout)
            assert workout.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            assert workout.sport_display_name == "Running"

    def test_get_workout_accepts_uuid_string(self, client) -> None:
        """Test get_workout accepts a UUID string and makes HTTP call."""
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

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ) as mock_request:
            workout = client.get_workout("abc-123")

            assert isinstance(workout, Workout)
            mock_request.assert_called_once()
            call_kwargs = mock_request.call_args.kwargs
            assert "abc-123" in call_kwargs["url"]

    def test_get_workout_rejects_empty_string(self, client) -> None:
        """Test get_workout raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid workout_id"):
            client.get_workout("")


# =============================================================================
# Context Manager Tests
# =============================================================================

class TestContextManager:
    """Tests for context manager functionality."""
    
    def test_context_manager_closes_resources(self, mock_auth) -> None:
        """Test that context manager closes all resources."""
        with patch("whoopyy.client.OAuthHandler", return_value=mock_auth):
            with WhoopClient(
                client_id="test_id",
                client_secret="test_secret",
            ) as client:
                pass
            
            # Verify auth was closed
            mock_auth.close.assert_called_once()
            
            # Verify HTTP client was closed
            assert client._http_client.is_closed


# =============================================================================
# Repr Tests
# =============================================================================

class TestRepr:
    """Tests for string representation."""
    
    def test_repr(self, client) -> None:
        """Test __repr__ output."""
        repr_str = repr(client)
        
        assert "WhoopClient" in repr_str
        assert "test_cli" in repr_str  # First 8 chars of client_id
        assert "authenticated=False" in repr_str


# =============================================================================
# Revoke Access Tests
# =============================================================================

class TestRevokeAccess:
    """Tests for revoke_access() method."""

    def test_revoke_access_sends_post(self, client, mock_auth) -> None:
        """Test that revoke_access() POSTs to the correct OAuth revocation URL."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(client._http_client, "post", return_value=mock_response) as mock_post:
            client.revoke_access()

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", call_args[0][0])
        # First positional argument is the URL
        assert "/oauth/oauth2/revoke" in call_args[0][0]

    def test_revoke_access_clears_tokens(self, client, mock_auth) -> None:
        """Test that revoke_access() clears stored tokens on success."""
        mock_response = Mock()
        mock_response.status_code = 200

        # Give auth handler some tokens to be cleared
        mock_auth._tokens = {"access_token": "test_access_token"}

        with patch.object(client._http_client, "post", return_value=mock_response):
            client.revoke_access()

        assert mock_auth._tokens is None
        assert client._authenticated is False

    def test_revoke_access_raises_on_error(self, client, mock_auth) -> None:
        """Test that revoke_access() raises WhoopAuthError on non-200 response."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_token"

        with patch.object(client._http_client, "post", return_value=mock_response):
            with pytest.raises(WhoopAuthError) as exc_info:
                client.revoke_access()

        assert exc_info.value.status_code == 400
