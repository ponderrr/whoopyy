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
import uuid
from datetime import datetime, date, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import httpx

from whoopyy.client import WhoopClient
from whoopyy.constants import API_BASE_URL, ENDPOINTS
from whoopyy.models import (
    ActivityIdMapping,
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
from whoopyy.utils import save_tokens


# =============================================================================
# Fixtures
# =============================================================================

def _install_mock_transport(client, handler) -> None:
    """Route the client's HTTP traffic through an httpx.MockTransport handler."""
    client._http_client.close()
    client._http_client = httpx.Client(
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
        """Test rate limit (429) handling: one wait from the headers, one retry, then raise."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}

        with patch.object(
            client._http_client,
            "request",
            return_value=mock_response
        ) as mock_request, patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

            assert exc.value.retry_after == 60
            assert exc.value.status_code == 429
            # Slept exactly once, for the Retry-After value, then retried once
            mock_sleep.assert_called_once_with(60)
            assert mock_request.call_count == 2
    
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
            client.get_recovery_collection(limit=100)  # Max is 25
    
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
            "sport_name": "running",
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
            workout = client.get_workout("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

            assert isinstance(workout, Workout)
            assert workout.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            assert workout.sport_name == "running"
            assert workout.sport_id == 0
            assert mock_request.call_args.kwargs["method"] == "GET"
            assert mock_request.call_args.kwargs["url"] == (
                "/developer/v2/activity/workout/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            )

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
            "sport_name": "running",
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
    """Tests for revoke_access() (DELETE /developer/v2/user/access)."""

    @staticmethod
    def _response(status_code: int, text: str = "") -> httpx.Response:
        """Build a real httpx response for the revoke request."""
        return httpx.Response(
            status_code,
            text=text,
            request=httpx.Request("DELETE", f"{API_BASE_URL}{ENDPOINTS['user_access']}"),
        )

    def test_revoke_access_sends_delete_to_user_access(self, client, mock_auth) -> None:
        """revoke_access() sends DELETE /developer/v2/user/access with the Bearer token."""
        with patch.object(
            client._http_client, "request", return_value=self._response(204)
        ) as mock_request:
            client.revoke_access()

        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["method"] == "DELETE"
        assert call_kwargs["url"] == "/developer/v2/user/access"
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_access_token"
        assert call_kwargs["json"] is None

    def test_revoke_access_does_not_post_to_oauth_revoke(self, client, mock_auth) -> None:
        """The retired POST /oauth/oauth2/revoke call is no longer made."""
        with patch.object(
            client._http_client, "request", return_value=self._response(204)
        ), patch.object(client._http_client, "post") as mock_post:
            client.revoke_access()

        mock_post.assert_not_called()

    def test_revoke_access_204_returns_none(self, client, mock_auth) -> None:
        """A 204 No Content response is success; revoke_access() returns None."""
        with patch.object(client._http_client, "request", return_value=self._response(204)):
            assert client.revoke_access() is None

    def test_revoke_access_clears_tokens(self, client, mock_auth) -> None:
        """revoke_access() clears in-memory tokens and marks the client unauthenticated."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        client._authenticated = True

        with patch.object(client._http_client, "request", return_value=self._response(204)):
            client.revoke_access()

        assert mock_auth._tokens is None
        assert client._authenticated is False

    def test_revoke_access_400_raises_validation_error(self, client, mock_auth) -> None:
        """A 400 surfaces as WhoopValidationError and leaves tokens untouched."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        client._authenticated = True

        with patch.object(
            client._http_client, "request", return_value=self._response(400, "bad request")
        ):
            with pytest.raises(WhoopValidationError) as exc_info:
                client.revoke_access()

        assert exc_info.value.status_code == 400
        assert mock_auth._tokens == {"access_token": "test_access_token"}
        assert client._authenticated is True

    def test_revoke_access_500_raises_api_error(self, client, mock_auth) -> None:
        """A 500 surfaces as WhoopAPIError and leaves tokens untouched."""
        mock_auth._tokens = {"access_token": "test_access_token"}

        with patch.object(
            client._http_client, "request", return_value=self._response(500, "server error")
        ):
            with pytest.raises(WhoopAPIError) as exc_info:
                client.revoke_access()

        assert exc_info.value.status_code == 500
        assert not isinstance(exc_info.value, WhoopAuthError)
        assert mock_auth._tokens == {"access_token": "test_access_token"}

    def test_revoke_access_repeated_401_raises_auth_error(self, client, mock_auth) -> None:
        """Two 401s (before and after refresh) raise WhoopAuthError; tokens are kept."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        mock_auth.refresh_access_token = Mock()

        with patch.object(
            client._http_client, "request", return_value=self._response(401, "unauthorized")
        ) as mock_request:
            with pytest.raises(WhoopAuthError) as exc_info:
                client.revoke_access()

        assert exc_info.value.status_code == 401
        mock_auth.refresh_access_token.assert_called_once()
        assert mock_request.call_count == 2
        assert mock_auth._tokens == {"access_token": "test_access_token"}

    def test_revoke_access_401_then_204_succeeds(self, client, mock_auth) -> None:
        """A 401 triggers one token refresh; a 204 on retry completes the revoke."""
        mock_auth._tokens = {"access_token": "test_access_token"}
        mock_auth.refresh_access_token = Mock()

        with patch.object(
            client._http_client,
            "request",
            side_effect=[self._response(401, "unauthorized"), self._response(204)],
        ):
            client.revoke_access()

        mock_auth.refresh_access_token.assert_called_once()
        assert mock_auth._tokens is None
        assert client._authenticated is False

    def test_revoke_access_over_http_transport(self, client, mock_auth) -> None:
        """End to end through httpx: full URL, method and Authorization header."""
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(204)

        _install_mock_transport(client, handler)
        client.revoke_access()

        assert len(seen) == 1
        assert seen[0].method == "DELETE"
        assert str(seen[0].url) == "https://api.prod.whoop.com/developer/v2/user/access"
        assert seen[0].headers["Authorization"] == "Bearer test_access_token"
        assert client._authenticated is False

    def test_revoke_access_deletes_token_file_and_clears_cache(self, client, mock_auth) -> None:
        """A successful revoke removes the token file and the response cache."""
        token_path = Path(mock_auth.token_file)
        token_path.write_text("{}")
        client._cache_set("profile_basic", object(), ttl=300)

        with patch.object(client._http_client, "request", return_value=self._response(204)):
            client.revoke_access()

        assert not token_path.exists()
        assert client._cache == {}

    def test_revoke_access_failure_keeps_token_file_and_cache(self, client, mock_auth) -> None:
        """A failed revoke leaves the token file and the cache in place."""
        token_path = Path(mock_auth.token_file)
        token_path.write_text("{}")
        client._cache_set("profile_basic", object(), ttl=300)

        with patch.object(
            client._http_client, "request", return_value=self._response(500, "server error")
        ):
            with pytest.raises(WhoopAPIError):
                client.revoke_access()

        assert token_path.exists()
        assert "profile_basic" in client._cache

    def test_revoke_access_signs_out_with_real_token_file(self, tmp_path) -> None:
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

        client = WhoopClient(
            client_id="test_client_id",
            client_secret="test_client_secret",
            token_file=token_file,
        )
        try:
            _install_mock_transport(client, handler)
            client.get_profile_basic()
            assert client.is_authenticated() is True

            client.revoke_access()

            assert client.is_authenticated() is False
            assert not Path(token_file).exists()
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate(auto_open_browser=False)
            mock_authorize.assert_called_once_with(auto_open_browser=False)
        finally:
            client.close()

        assert seen == [
            ("GET", "/developer/v2/user/profile/basic", "Bearer AT"),
            ("DELETE", "/developer/v2/user/access", "Bearer AT"),
        ]


# =============================================================================
# Sleep Pagination Tests
# =============================================================================

class TestSleepPagination:
    """Tests for sleep collection pagination."""

    def _make_sleep_record(self, idx: int) -> dict:
        return {
            "id": f"sleep-uuid-{idx:04d}",
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

    def test_get_sleep_collection_single_page(self, client):
        """Single page with no next_token returns all items in one HTTP call."""
        page = {
            "records": [self._make_sleep_record(i) for i in range(3)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(
            client._http_client, "request", return_value=mock_response
        ) as mock_req:
            collection = client.get_sleep_collection(limit=10)

        assert isinstance(collection, SleepCollection)
        assert len(collection.records) == 3
        assert collection.next_token is None
        mock_req.assert_called_once()

    def test_get_sleep_collection_two_pages(self, client):
        """Two-page response yields records from both pages."""
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

        with patch.object(
            client._http_client, "request", return_value=mock_response
        ) as mock_req:
            all_sleeps = client.get_all_sleep()

        assert len(all_sleeps) == 4
        assert mock_req.call_count == 2

    def test_get_all_sleep_follows_pagination(self, client):
        """get_all_sleep aggregates records across three pages."""
        pages = [
            {"records": [self._make_sleep_record(i) for i in range(5)], "next_token": "p2"},
            {"records": [self._make_sleep_record(i) for i in range(5, 10)], "next_token": "p3"},
            {"records": [self._make_sleep_record(i) for i in range(10, 13)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        with patch.object(
            client._http_client, "request", return_value=mock_response
        ) as mock_req:
            all_sleeps = client.get_all_sleep()

        assert len(all_sleeps) == 13
        assert mock_req.call_count == 3
        assert all(isinstance(s, Sleep) for s in all_sleeps)


# =============================================================================
# Cycle Pagination Tests
# =============================================================================

class TestCyclePagination:
    """Tests for cycle collection pagination."""

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

    def test_get_cycle_collection_basic(self, client):
        """Single-page cycle collection is deserialized to Cycle objects."""
        page = {
            "records": [self._make_cycle_record(i) for i in range(1, 4)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            collection = client.get_cycle_collection(limit=10)

        assert isinstance(collection, CycleCollection)
        assert len(collection.records) == 3
        assert all(isinstance(c, Cycle) for c in collection.records)

    def test_get_all_cycles_multi_page(self, client):
        """get_all_cycles fetches two pages and returns combined list."""
        pages = [
            {"records": [self._make_cycle_record(i) for i in range(1, 4)], "next_token": "next"},
            {"records": [self._make_cycle_record(i) for i in range(4, 7)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        with patch.object(
            client._http_client, "request", return_value=mock_response
        ) as mock_req:
            cycles = client.get_all_cycles()

        assert len(cycles) == 6
        assert mock_req.call_count == 2


# =============================================================================
# Workout Pagination Tests
# =============================================================================

class TestWorkoutPagination:
    """Tests for workout collection pagination."""

    def _make_workout_record(self, idx: int) -> dict:
        return {
            "id": f"workout-uuid-{idx:04d}",
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

    def test_get_workout_collection_basic(self, client):
        """Single-page workout collection is deserialized to Workout objects."""
        page = {
            "records": [self._make_workout_record(i) for i in range(3)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            collection = client.get_workout_collection(limit=10)

        assert isinstance(collection, WorkoutCollection)
        assert len(collection.records) == 3
        # v2 identifies the sport by name; the deprecated sport_id is absent
        assert all(w.sport_name == "yoga" for w in collection.records)
        assert all(w.sport_id is None for w in collection.records)

    def test_get_all_workouts_multi_page(self, client):
        """get_all_workouts fetches two pages and returns combined list."""
        pages = [
            {"records": [self._make_workout_record(i) for i in range(4)], "next_token": "wt2"},
            {"records": [self._make_workout_record(i) for i in range(4, 8)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        with patch.object(
            client._http_client, "request", return_value=mock_response
        ) as mock_req:
            workouts = client.get_all_workouts()

        assert len(workouts) == 8
        assert mock_req.call_count == 2


# =============================================================================
# Iterator Tests
# =============================================================================

class TestIterators:
    """Tests for generator-based iterators."""

    def _make_sleep_record(self, idx: int) -> dict:
        return {
            "id": f"sleep-iter-{idx:04d}",
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

    def _make_recovery_record(self, idx: int) -> dict:
        return {
            "cycle_id": idx,
            "sleep_id": f"a1b2c3d4-e5f6-7890-abcd-ef{idx:012d}",
            "user_id": 1,
            "created_at": "2024-01-15T08:00:00.000Z",
            "updated_at": "2024-01-15T08:30:00.000Z",
            "score_state": "SCORED",
            "score": {
                "user_calibrating": False,
                "recovery_score": 70.0,
                "resting_heart_rate": 52.0,
                "hrv_rmssd_milli": 60.0,
            },
        }

    def _make_workout_record(self, idx: int) -> dict:
        return {
            "id": f"workout-iter-{idx:04d}",
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

    def test_iter_sleep_yields_items(self, client):
        """iter_sleep should yield all Sleep objects from a single page."""
        page = {
            "records": [self._make_sleep_record(i) for i in range(3)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            items = list(client.iter_sleep())

        assert len(items) == 3
        assert all(isinstance(s, Sleep) for s in items)

    def test_iter_sleep_multi_page(self, client):
        """iter_sleep should yield items across multiple pages."""
        pages = [
            {"records": [self._make_sleep_record(i) for i in range(3)], "next_token": "p2"},
            {"records": [self._make_sleep_record(i) for i in range(3, 5)], "next_token": None},
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = pages

        with patch.object(client._http_client, "request", return_value=mock_response):
            items = list(client.iter_sleep())

        assert len(items) == 5

    def test_iter_cycles_yields_items(self, client):
        """iter_cycles should yield all Cycle objects from a single page."""
        page = {
            "records": [self._make_cycle_record(i) for i in range(1, 5)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            items = list(client.iter_cycles())

        assert len(items) == 4
        assert all(isinstance(c, Cycle) for c in items)

    def test_iter_recovery_yields_items(self, client):
        """iter_recovery should yield all Recovery objects."""
        page = {
            "records": [self._make_recovery_record(i) for i in range(1, 4)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            items = list(client.iter_recovery())

        assert len(items) == 3
        assert all(isinstance(r, Recovery) for r in items)

    def test_iter_workouts_yields_items(self, client):
        """iter_workouts should yield all Workout objects."""
        page = {
            "records": [self._make_workout_record(i) for i in range(5)],
            "next_token": None,
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = page

        with patch.object(client._http_client, "request", return_value=mock_response):
            items = list(client.iter_workouts())

        assert len(items) == 5
        assert all(isinstance(w, Workout) for w in items)


# =============================================================================
# HTTP Connection Pooling Tests
# =============================================================================

class TestHTTPConnectionPooling:
    """Tests for HTTP connection pooling and session management."""

    def test_client_reuses_session(self, client):
        """The same httpx.Client instance is used across multiple requests."""
        session_before = client._http_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "user_id": 1, "email": "a@b.com", "first_name": "A", "last_name": "B"
        }
        with patch.object(client._http_client, "request", return_value=mock_response):
            client.get_profile_basic()
            client.get_profile_basic()
        assert client._http_client is session_before

    def test_client_session_has_timeout_config(self, client):
        """Session should have the configured read timeout of 30s."""
        assert client._http_client.timeout.read == 30.0
        assert client._http_client.timeout.connect == 5.0

    def test_client_closes_session_on_exit(self, mock_auth):
        """Session should be closed after context manager exit."""
        with patch("whoopyy.client.OAuthHandler", return_value=mock_auth):
            with WhoopClient(
                client_id="test_id", client_secret="test_secret"
            ) as c:
                session = c._http_client
            assert session.is_closed


# =============================================================================
# Rate Limit Header Tests (WHOOP v2: X-RateLimit-Reset)
# =============================================================================

class TestRateLimitHeaders:
    """429 handling waits for the time given by WHOOP's rate limit headers."""

    @staticmethod
    def _rate_limited(headers) -> Mock:
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = headers
        mock_response.text = "Too Many Requests"
        return mock_response

    def test_waits_for_x_ratelimit_reset_then_retries(self, client) -> None:
        """A 429 with X-RateLimit-Reset sleeps that long and retries once."""
        responses = [
            self._rate_limited({"X-RateLimit-Reset": "7"}),
            _json_response({"ok": True}),
        ]
        with patch.object(
            client._http_client, "request", side_effect=responses
        ) as mock_request, patch("whoopyy.client.time.sleep") as mock_sleep:
            result = client._request("GET", "/test")

        assert result == {"ok": True}
        mock_sleep.assert_called_once_with(7)
        assert mock_request.call_count == 2

    def test_x_ratelimit_reset_preferred_over_retry_after(self, client) -> None:
        """X-RateLimit-Reset wins over Retry-After, for the wait and the error."""
        response = self._rate_limited({"Retry-After": "30", "X-RateLimit-Reset": "7"})
        with patch.object(client._http_client, "request", return_value=response), \
                patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

        mock_sleep.assert_called_once_with(7)
        assert exc.value.retry_after == 7

    def test_lowercase_dict_headers(self, client) -> None:
        """Lowercase header names in a plain dict are still honoured."""
        response = self._rate_limited({"x-ratelimit-reset": "9"})
        with patch.object(client._http_client, "request", return_value=response), \
                patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

        mock_sleep.assert_called_once_with(9)
        assert exc.value.retry_after == 9

    def test_wait_is_capped_at_120_seconds(self, client) -> None:
        """Long resets are capped at 2 minutes; the error reports the real value."""
        response = self._rate_limited({"X-RateLimit-Reset": "500"})
        with patch.object(client._http_client, "request", return_value=response) as mock_request, \
                patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

        mock_sleep.assert_called_once_with(120)
        assert exc.value.retry_after == 500
        assert mock_request.call_count == 2

    def test_defaults_to_60_without_headers(self, client) -> None:
        """Without rate limit headers the wait defaults to 60 seconds."""
        response = self._rate_limited({})
        with patch.object(client._http_client, "request", return_value=response), \
                patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

        mock_sleep.assert_called_once_with(60)
        assert exc.value.retry_after == 60

    def test_invalid_reset_falls_back_to_retry_after(self, client) -> None:
        """A negative X-RateLimit-Reset is ignored in favour of Retry-After."""
        response = self._rate_limited({"X-RateLimit-Reset": "-3", "Retry-After": "4"})
        with patch.object(client._http_client, "request", return_value=response), \
                patch("whoopyy.client.time.sleep") as mock_sleep:
            with pytest.raises(WhoopRateLimitError) as exc:
                client._request("GET", "/test")

        mock_sleep.assert_called_once_with(4)
        assert exc.value.retry_after == 4

    def test_real_httpx_headers_over_transport(self, client) -> None:
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

        _install_mock_transport(client, handler)
        with patch("whoopyy.client.time.sleep") as mock_sleep:
            profile = client.get_profile_basic()

        assert isinstance(profile, UserProfileBasic)
        mock_sleep.assert_called_once_with(5)
        assert len(calls) == 2
        assert str(calls[0].url) == "https://api.prod.whoop.com/developer/v2/user/profile/basic"


# =============================================================================
# Sleep For Cycle Tests (GET /developer/v2/cycle/{cycle_id}/sleep)
# =============================================================================

class TestSleepForCycle:
    """Tests for get_sleep_for_cycle()."""

    def test_get_sleep_for_cycle_path_and_parsing(self, client, sample_sleep_dict) -> None:
        """Requests the cycle's sleep and parses it into a Sleep model."""
        payload = dict(sample_sleep_dict, v1_id=93845)
        with patch.object(
            client._http_client, "request", return_value=_json_response(payload)
        ) as mock_request:
            sleep = client.get_sleep_for_cycle(100)

        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "/developer/v2/cycle/100/sleep"
        assert isinstance(sleep, Sleep)
        assert sleep.id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert sleep.cycle_id == 100
        assert sleep.v1_id == 93845

    def test_get_sleep_for_cycle_without_v1_id(self, client, sample_sleep_dict) -> None:
        """The deprecated v1_id is optional in the response."""
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_sleep_dict)
        ):
            sleep = client.get_sleep_for_cycle(100)

        assert sleep.v1_id is None

    @pytest.mark.parametrize("cycle_id", [0, -1])
    def test_get_sleep_for_cycle_invalid_id(self, client, cycle_id) -> None:
        """Non-positive cycle IDs are rejected before any HTTP call."""
        with patch.object(client._http_client, "request") as mock_request:
            with pytest.raises(ValueError, match="Invalid cycle_id"):
                client.get_sleep_for_cycle(cycle_id)
        mock_request.assert_not_called()

    def test_get_sleep_for_cycle_not_found(self, client) -> None:
        """A 404 (no sleep for the cycle) raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.text = "Not Found"
        with patch.object(client._http_client, "request", return_value=mock_response):
            with pytest.raises(WhoopNotFoundError):
                client.get_sleep_for_cycle(100)


# =============================================================================
# Activity ID Mapping Tests (GET /developer/v1/activity-mapping/{id})
# =============================================================================

class TestActivityMapping:
    """Tests for get_activity_mapping()."""

    def test_get_activity_mapping_path_and_parsing(
        self, client, sample_activity_mapping_dict
    ) -> None:
        """Requests the v1 mapping path and parses an ActivityIdMapping."""
        with patch.object(
            client._http_client,
            "request",
            return_value=_json_response(sample_activity_mapping_dict),
        ) as mock_request:
            mapping = client.get_activity_mapping(12345678)

        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["method"] == "GET"
        assert call_kwargs["url"] == "/developer/v1/activity-mapping/12345678"
        assert isinstance(mapping, ActivityIdMapping)
        assert mapping.v2_activity_id == "ecfc6a15-4661-442f-a9a4-f160dd7afae8"

    def test_mapping_result_feeds_get_sleep(
        self, client, sample_activity_mapping_dict, sample_sleep_dict
    ) -> None:
        """The mapped v2 UUID is accepted by get_sleep()."""
        responses = [
            _json_response(sample_activity_mapping_dict),
            _json_response(sample_sleep_dict),
        ]
        with patch.object(
            client._http_client, "request", side_effect=responses
        ) as mock_request:
            mapping = client.get_activity_mapping(93845)
            client.get_sleep(mapping.v2_activity_id)

        assert mock_request.call_args.kwargs["url"] == (
            "/developer/v2/activity/sleep/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    @pytest.mark.parametrize("activity_v1_id", [0, -5])
    def test_get_activity_mapping_invalid_id(self, client, activity_v1_id) -> None:
        """Non-positive v1 IDs are rejected before any HTTP call."""
        with patch.object(client._http_client, "request") as mock_request:
            with pytest.raises(ValueError, match="Invalid activity_v1_id"):
                client.get_activity_mapping(activity_v1_id)
        mock_request.assert_not_called()

    def test_get_activity_mapping_not_found(self, client) -> None:
        """An unknown v1 ID (404) raises WhoopNotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_response.text = "Activity mapping not found"
        with patch.object(client._http_client, "request", return_value=mock_response):
            with pytest.raises(WhoopNotFoundError):
                client.get_activity_mapping(1)


# =============================================================================
# Date Parameter Formatting Tests
# =============================================================================

class TestDateParamFormatting:
    """Tests for _format_date_param() and collection start/end params."""

    def test_date_only_string_expanded_to_midnight_utc(self, client) -> None:
        """WHOOP v2 rejects date-only strings, so YYYY-MM-DD becomes a date-time."""
        assert client._format_date_param("2024-01-15") == "2024-01-15T00:00:00.000Z"

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
    def test_other_strings_pass_through_unchanged(self, client, value) -> None:
        """Any string that is not exactly YYYY-MM-DD is passed through as-is."""
        assert client._format_date_param(value) == value

    def test_none_returns_none(self, client) -> None:
        assert client._format_date_param(None) is None

    def test_aware_datetime_unchanged_behaviour(self, client) -> None:
        dt = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert client._format_date_param(dt) == "2024-01-15T10:30:00+00:00"

    def test_naive_datetime_treated_as_utc(self, client) -> None:
        assert client._format_date_param(datetime(2024, 1, 15, 10, 30)) == (
            "2024-01-15T10:30:00+00:00"
        )

    def test_date_object_unchanged_behaviour(self, client) -> None:
        assert client._format_date_param(date(2024, 1, 15)) == "2024-01-15T00:00:00+00:00"

    def test_collection_request_sends_normalized_dates(self, client) -> None:
        """Date-only start/end strings reach the API as full date-times."""
        with patch.object(
            client._http_client,
            "request",
            return_value=_json_response({"records": [], "next_token": None}),
        ) as mock_request:
            client.get_cycle_collection(start="2024-01-01", end="2024-01-31", limit=5)

        params = mock_request.call_args.kwargs["params"]
        assert params["start"] == "2024-01-01T00:00:00.000Z"
        assert params["end"] == "2024-01-31T00:00:00.000Z"
        assert params["limit"] == 5
        assert mock_request.call_args.kwargs["url"] == "/developer/v2/cycle"


# =============================================================================
# Legacy v1 ID Rejection Tests
# =============================================================================

class TestLegacyIdRejection:
    """get_sleep / get_workout reject legacy v1 integer IDs locally."""

    @pytest.mark.parametrize("bad_id", [123, "12345678", " 42 "])
    def test_get_sleep_rejects_v1_ids(self, client, bad_id) -> None:
        with patch.object(client._http_client, "request") as mock_request:
            with pytest.raises(ValueError, match="Invalid sleep_id") as exc:
                client.get_sleep(bad_id)
        assert "get_activity_mapping" in str(exc.value)
        mock_request.assert_not_called()

    @pytest.mark.parametrize("bad_id", [123, "12345678", " 42 "])
    def test_get_workout_rejects_v1_ids(self, client, bad_id) -> None:
        with patch.object(client._http_client, "request") as mock_request:
            with pytest.raises(ValueError, match="Invalid workout_id") as exc:
                client.get_workout(bad_id)
        assert "get_activity_mapping" in str(exc.value)
        mock_request.assert_not_called()

    def test_get_sleep_rejects_whitespace(self, client) -> None:
        with pytest.raises(ValueError, match="Invalid sleep_id"):
            client.get_sleep("   ")

    def test_get_workout_rejects_whitespace(self, client) -> None:
        with pytest.raises(ValueError, match="Invalid workout_id"):
            client.get_workout("   ")

    def test_get_sleep_accepts_uuid_object(self, client, sample_sleep_dict) -> None:
        """A uuid.UUID is used as its string form in the path."""
        sleep_uuid = uuid.UUID("ecfc6a15-4661-442f-a9a4-f160dd7afae8")
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_sleep_dict)
        ) as mock_request:
            client.get_sleep(sleep_uuid)
        assert mock_request.call_args.kwargs["url"] == (
            "/developer/v2/activity/sleep/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    def test_get_workout_accepts_uuid_object(self, client, sample_workout_dict) -> None:
        """A uuid.UUID is used as its string form in the path."""
        workout_uuid = uuid.UUID("ecfc6a15-4661-442f-a9a4-f160dd7afae8")
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_workout_dict)
        ) as mock_request:
            client.get_workout(workout_uuid)
        assert mock_request.call_args.kwargs["url"] == (
            "/developer/v2/activity/workout/ecfc6a15-4661-442f-a9a4-f160dd7afae8"
        )

    @pytest.mark.parametrize("bad_id", [None, 1.5, b"abc"])
    def test_non_string_ids_get_no_legacy_hint(self, client, bad_id) -> None:
        """Only int / all-digit IDs mention get_activity_mapping()."""
        with pytest.raises(ValueError, match="Invalid sleep_id") as sleep_exc:
            client.get_sleep(bad_id)
        with pytest.raises(ValueError, match="Invalid workout_id") as workout_exc:
            client.get_workout(bad_id)
        assert "get_activity_mapping" not in str(sleep_exc.value)
        assert "get_activity_mapping" not in str(workout_exc.value)


# =============================================================================
# v2 Model Parsing Through The Client
# =============================================================================

class TestV2ResponseParsing:
    """v2-only fields parse correctly through the client methods."""

    def test_get_cycle_parses_step_count(self, client, sample_cycle_dict) -> None:
        payload = dict(sample_cycle_dict, step_count=8234)
        with patch.object(
            client._http_client, "request", return_value=_json_response(payload)
        ) as mock_request:
            cycle = client.get_cycle(999)

        assert mock_request.call_args.kwargs["url"] == "/developer/v2/cycle/999"
        assert cycle.step_count == 8234

    def test_get_cycle_null_step_count(self, client, sample_cycle_dict) -> None:
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_cycle_dict)
        ):
            cycle = client.get_cycle(999)

        assert cycle.step_count is None

    def test_get_workout_full_v2_payload(self, client, sample_workout_dict) -> None:
        """A full v2 workout (sport_name, zone_durations, v1_id) parses."""
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_workout_dict)
        ):
            workout = client.get_workout(sample_workout_dict["id"])

        assert workout.sport_name == "yoga"
        assert workout.v1_id == 1043
        assert workout.score is not None
        assert workout.score.zone_durations is not None
        assert workout.score.zone_durations.zone_two_milli == 900000

    def test_get_workout_without_sport_id(self, client, sample_workout_dict) -> None:
        """WHOOP drops the deprecated sport_id and v1_id; the workout still parses."""
        payload = dict(sample_workout_dict)
        del payload["sport_id"]
        del payload["v1_id"]
        with patch.object(
            client._http_client, "request", return_value=_json_response(payload)
        ):
            workout = client.get_workout(payload["id"])

        assert workout.sport_id is None
        assert workout.v1_id is None
        assert workout.sport_name == "yoga"

    def test_get_recovery_for_cycle_path(self, client, sample_recovery_dict) -> None:
        with patch.object(
            client._http_client, "request", return_value=_json_response(sample_recovery_dict)
        ) as mock_request:
            client.get_recovery_for_cycle(123)

        assert mock_request.call_args.kwargs["url"] == "/developer/v2/cycle/123/recovery"

    @pytest.mark.parametrize(
        "method_name, expected_url",
        [
            ("get_recovery_collection", "/developer/v2/recovery"),
            ("get_sleep_collection", "/developer/v2/activity/sleep"),
            ("get_cycle_collection", "/developer/v2/cycle"),
            ("get_workout_collection", "/developer/v2/activity/workout"),
        ],
    )
    def test_collection_paths_are_v2(self, client, method_name, expected_url) -> None:
        with patch.object(
            client._http_client,
            "request",
            return_value=_json_response({"records": [], "next_token": None}),
        ) as mock_request:
            getattr(client, method_name)(limit=3, next_token="tok")

        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["url"] == expected_url
        assert call_kwargs["params"] == {"limit": 3, "nextToken": "tok"}

    @pytest.mark.parametrize(
        "method_name, expected_url",
        [
            ("get_profile_basic", "/developer/v2/user/profile/basic"),
            ("get_body_measurement", "/developer/v2/user/measurement/body"),
        ],
    )
    def test_user_paths_are_v2(self, client, method_name, expected_url) -> None:
        payloads = {
            "get_profile_basic": {"user_id": 1, "email": "a@b.com",
                                  "first_name": "A", "last_name": "B"},
            "get_body_measurement": {"height_meter": 1.8, "weight_kilogram": 80.0,
                                     "max_heart_rate": 190},
        }
        with patch.object(
            client._http_client, "request", return_value=_json_response(payloads[method_name])
        ) as mock_request:
            getattr(client, method_name)()

        assert mock_request.call_args.kwargs["url"] == expected_url
