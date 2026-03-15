"""
Unit tests for WhoopPy OAuth authentication handler.

Tests cover:
- Initialization and validation
- Authorization URL building
- Token exchange (mocked)
- Token refresh (mocked)
- Token management
- Error handling
"""

import json
import time
from unittest.mock import Mock, patch, MagicMock

import pytest
import httpx

from whoopyy.auth import (
    OAuthHandler,
    _CallbackHandler,
    _reset_callback_handler,
)
from whoopyy.exceptions import WhoopAuthError, WhoopTokenError
from whoopyy.constants import OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL, SCOPES


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def oauth_handler():
    """Create an OAuth handler for testing."""
    handler = OAuthHandler(
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8080/callback",
    )
    yield handler
    handler.close()


@pytest.fixture
def mock_token_response():
    """Create a mock token response."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "offline read:recovery read:sleep",
    }


@pytest.fixture
def mock_tokens():
    """Create mock token data."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "expires_at": time.time() + 3600,
        "token_type": "Bearer",
        "scope": "offline read:recovery",
    }


# =============================================================================
# Initialization Tests
# =============================================================================

class TestOAuthHandlerInit:
    """Tests for OAuthHandler initialization."""
    
    def test_valid_initialization(self) -> None:
        """Test creating handler with valid parameters."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        )
        
        assert handler.client_id == "test_id"
        assert handler.client_secret == "test_secret"
        assert handler.redirect_uri == "http://localhost:8080/callback"
        assert "offline" in handler.scope
        
        handler.close()
    
    def test_custom_redirect_uri(self) -> None:
        """Test custom redirect URI."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            redirect_uri="http://localhost:9000/oauth/callback",
        )
        
        assert handler.redirect_uri == "http://localhost:9000/oauth/callback"
        handler.close()
    
    def test_custom_scopes(self) -> None:
        """Test custom OAuth scopes."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            scope=["read:recovery", "read:sleep"],
        )
        
        # Should include offline scope automatically
        assert "offline" in handler.scope
        assert "read:recovery" in handler.scope
        assert "read:sleep" in handler.scope
        
        handler.close()
    
    def test_offline_scope_included_when_provided(self) -> None:
        """Test that offline scope is preserved when explicitly provided."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            scope=["offline", "read:recovery"],
        )
        
        # Should have exactly what was provided
        assert handler.scope == ["offline", "read:recovery"]
        handler.close()
    
    def test_empty_client_id_rejected(self) -> None:
        """Test that empty client_id raises error."""
        with pytest.raises(ValueError, match="client_id is required"):
            OAuthHandler(
                client_id="",
                client_secret="test_secret",
            )
    
    def test_empty_client_secret_rejected(self) -> None:
        """Test that empty client_secret raises error."""
        with pytest.raises(ValueError, match="client_secret is required"):
            OAuthHandler(
                client_id="test_id",
                client_secret="",
            )
    
    def test_default_token_file(self) -> None:
        """Test default token file path is absolute and in home directory."""
        import os
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        )

        assert handler.token_file == os.path.join(os.path.expanduser("~"), ".whoop_tokens.json")
        assert handler.token_file.startswith("/")
        handler.close()
    
    def test_custom_token_file(self) -> None:
        """Test custom token file path."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            token_file="/tmp/custom_tokens.json",
        )
        
        assert handler.token_file == "/tmp/custom_tokens.json"
        handler.close()


# =============================================================================
# Authorization URL Tests
# =============================================================================

class TestAuthorizationURL:
    """Tests for authorization URL building."""
    
    def test_build_authorization_url(self, oauth_handler: OAuthHandler) -> None:
        """Test building authorization URL."""
        state = "test_state_123"
        url = oauth_handler._build_authorization_url(state)
        
        assert url.startswith(OAUTH_AUTHORIZE_URL)
        assert "response_type=code" in url
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "state=test_state_123" in url
        assert "scope=" in url
    
    def test_url_contains_all_scopes(self, oauth_handler: OAuthHandler) -> None:
        """Test that URL contains all requested scopes."""
        url = oauth_handler._build_authorization_url("state")
        
        # Scopes are space-separated and URL encoded
        assert "scope=" in url


# =============================================================================
# Token Exchange Tests (Mocked)
# =============================================================================

class TestTokenExchange:
    """Tests for token exchange functionality."""
    
    def test_exchange_code_for_tokens_success(
        self,
        oauth_handler: OAuthHandler,
        mock_token_response: dict,
    ) -> None:
        """Test successful token exchange."""
        mock_response = Mock()
        mock_response.json.return_value = mock_token_response
        mock_response.raise_for_status = Mock()
        
        with patch.object(
            oauth_handler._http_client,
            "post",
            return_value=mock_response
        ):
            tokens = oauth_handler._exchange_code_for_tokens("test_auth_code")
        
        assert tokens["access_token"] == "test_access_token"
        assert tokens["refresh_token"] == "test_refresh_token"
        assert tokens["expires_in"] == 3600
        assert "expires_at" in tokens
    
    def test_exchange_code_for_tokens_http_error(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test token exchange with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        
        http_error = httpx.HTTPStatusError(
            "Bad Request",
            request=Mock(),
            response=mock_response,
        )
        mock_response.raise_for_status.side_effect = http_error
        
        with patch.object(
            oauth_handler._http_client,
            "post",
            return_value=mock_response
        ):
            with pytest.raises(WhoopAuthError) as exc:
                oauth_handler._exchange_code_for_tokens("bad_code")
            
            assert exc.value.status_code == 400
            assert "invalid_grant" in str(exc.value)


# =============================================================================
# Token Refresh Tests (Mocked)
# =============================================================================

class TestTokenRefresh:
    """Tests for token refresh functionality."""
    
    def test_refresh_token_success(
        self,
        oauth_handler: OAuthHandler,
        mock_token_response: dict,
        mock_tokens: dict,
    ) -> None:
        """Test successful token refresh."""
        # Set up stored tokens
        oauth_handler._tokens = mock_tokens
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response
        mock_response.raise_for_status = Mock()

        with patch.object(
            oauth_handler._http_client,
            "post",
            return_value=mock_response
        ):
            with patch("whoopyy.auth.save_tokens"):
                new_tokens = oauth_handler.refresh_access_token()

        assert new_tokens["access_token"] == "test_access_token"
        assert "expires_at" in new_tokens
    
    def test_refresh_token_no_tokens_available(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test refresh when no tokens are stored."""
        oauth_handler._tokens = None
        
        with patch("whoopyy.auth.load_tokens", return_value=None):
            with pytest.raises(WhoopTokenError) as exc:
                oauth_handler.refresh_access_token()
            
            assert "No tokens available" in str(exc.value)
    
    def test_refresh_token_no_refresh_token(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test refresh when no refresh token is stored."""
        tokens_without_refresh = {
            "access_token": "test",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "read:recovery",
            "refresh_token": None,
        }
        oauth_handler._tokens = None
        
        with patch("whoopyy.auth.load_tokens", return_value=tokens_without_refresh):
            with pytest.raises(WhoopTokenError) as exc:
                oauth_handler.refresh_access_token()
            
            assert "No refresh token available" in str(exc.value)
    
    def test_refresh_token_http_error(
        self,
        oauth_handler: OAuthHandler,
        mock_tokens: dict,
    ) -> None:
        """Test token refresh with HTTP error."""
        oauth_handler._tokens = mock_tokens
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "invalid_token"
        
        http_error = httpx.HTTPStatusError(
            "Unauthorized",
            request=Mock(),
            response=mock_response,
        )
        mock_response.raise_for_status.side_effect = http_error
        
        with patch.object(
            oauth_handler._http_client,
            "post",
            return_value=mock_response
        ):
            with pytest.raises(WhoopTokenError) as exc:
                oauth_handler.refresh_access_token()
            
            assert exc.value.status_code == 401


# =============================================================================
# Token Management Tests
# =============================================================================

class TestTokenManagement:
    """Tests for token management functionality."""
    
    def test_get_valid_token_from_memory(
        self,
        oauth_handler: OAuthHandler,
        mock_tokens: dict,
    ) -> None:
        """Test getting valid token from memory."""
        oauth_handler._tokens = mock_tokens
        
        token = oauth_handler.get_valid_token()
        
        assert token == "test_access_token"
    
    def test_get_valid_token_from_file(
        self,
        oauth_handler: OAuthHandler,
        mock_tokens: dict,
    ) -> None:
        """Test loading and getting token from file."""
        oauth_handler._tokens = None
        
        with patch("whoopyy.auth.load_tokens", return_value=mock_tokens):
            token = oauth_handler.get_valid_token()
        
        assert token == "test_access_token"
    
    def test_get_valid_token_auto_refresh(
        self,
        oauth_handler: OAuthHandler,
        mock_token_response: dict,
    ) -> None:
        """Test automatic token refresh when expired."""
        expired_tokens = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer",
            "scope": "offline",
        }
        oauth_handler._tokens = expired_tokens
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response
        mock_response.raise_for_status = Mock()

        with patch.object(
            oauth_handler._http_client,
            "post",
            return_value=mock_response
        ):
            with patch("whoopyy.auth.save_tokens"):
                token = oauth_handler.get_valid_token()

        assert token == "test_access_token"
    
    def test_get_valid_token_no_tokens(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test getting token when none available."""
        oauth_handler._tokens = None
        
        with patch("whoopyy.auth.load_tokens", return_value=None):
            with pytest.raises(WhoopTokenError) as exc:
                oauth_handler.get_valid_token()
            
            assert "No tokens available" in str(exc.value)
    
    def test_has_valid_tokens_true(
        self,
        oauth_handler: OAuthHandler,
        mock_tokens: dict,
    ) -> None:
        """Test has_valid_tokens when tokens are valid."""
        oauth_handler._tokens = mock_tokens
        
        assert oauth_handler.has_valid_tokens() is True
    
    def test_has_valid_tokens_false_no_tokens(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test has_valid_tokens when no tokens."""
        oauth_handler._tokens = None
        
        with patch("whoopyy.auth.load_tokens", return_value=None):
            assert oauth_handler.has_valid_tokens() is False
    
    def test_has_valid_tokens_expired_with_refresh(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test has_valid_tokens when expired but has refresh token."""
        expired_tokens = {
            "access_token": "old_token",
            "refresh_token": "valid_refresh",
            "expires_in": 3600,
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer",
            "scope": "offline",
        }
        oauth_handler._tokens = expired_tokens
        
        # Should be True because we can refresh
        assert oauth_handler.has_valid_tokens() is True
    
    def test_has_valid_tokens_expired_no_refresh(
        self,
        oauth_handler: OAuthHandler,
    ) -> None:
        """Test has_valid_tokens when expired and no refresh token."""
        expired_tokens = {
            "access_token": "old_token",
            "refresh_token": None,
            "expires_in": 3600,
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer",
            "scope": "read:recovery",
        }
        oauth_handler._tokens = expired_tokens
        
        # Should be False - can't refresh
        assert oauth_handler.has_valid_tokens() is False


# =============================================================================
# Callback Handler Tests
# =============================================================================

class TestCallbackHandler:
    """Tests for OAuth callback handler."""
    
    def test_reset_callback_handler(self) -> None:
        """Test resetting callback handler state."""
        # Set some values
        _CallbackHandler.auth_code = "test_code"
        _CallbackHandler.auth_state = "test_state"
        _CallbackHandler.error = "test_error"
        
        _reset_callback_handler()
        
        assert _CallbackHandler.auth_code is None
        assert _CallbackHandler.auth_state is None
        assert _CallbackHandler.error is None


# =============================================================================
# Context Manager Tests
# =============================================================================

class TestContextManager:
    """Tests for context manager functionality."""
    
    def test_context_manager_closes_client(self) -> None:
        """Test that context manager closes HTTP client."""
        with OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        ) as handler:
            assert handler._http_client is not None
        
        # Client should be closed after context
        assert handler._http_client.is_closed
    
    def test_context_manager_on_exception(self) -> None:
        """Test that context manager closes client on exception."""
        handler = None
        
        try:
            with OAuthHandler(
                client_id="test_id",
                client_secret="test_secret",
            ) as h:
                handler = h
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Client should still be closed
        assert handler._http_client.is_closed


# =============================================================================
# Repr Tests
# =============================================================================

class TestRepr:
    """Tests for string representation."""

    def test_repr(self, oauth_handler: OAuthHandler) -> None:
        """Test __repr__ output."""
        repr_str = repr(oauth_handler)

        assert "OAuthHandler" in repr_str
        assert "test_cli" in repr_str  # First 8 chars of client_id
        assert "localhost:8080" in repr_str


# =============================================================================
# Concurrent Token Refresh Tests
# =============================================================================

class TestConcurrentTokenRefresh:
    """Tests for thread-safe and async-safe token refresh."""

    def _make_expired_handler(self):
        """Helper: OAuthHandler with an already-expired token."""
        handler = OAuthHandler(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        handler._tokens = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer",
            "scope": "offline",
        }
        return handler

    def test_concurrent_refresh_issues_one_request(self) -> None:
        """10 threads simultaneously on expired token should only call refresh once."""
        import threading
        from unittest.mock import patch, Mock

        handler = self._make_expired_handler()
        call_count = {"n": 0}
        new_token_data = {
            "access_token": "new_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline",
        }

        original_refresh = handler.refresh_access_token

        def counting_refresh(*args, **kwargs):
            call_count["n"] += 1
            handler._tokens = new_token_data
            return new_token_data

        handler.refresh_access_token = counting_refresh

        results = []
        errors = []

        def call_get_valid_token():
            try:
                results.append(handler.get_valid_token())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_get_valid_token) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        assert call_count["n"] == 1, (
            f"Expected refresh called exactly once, got {call_count['n']}"
        )

    def test_second_caller_uses_refreshed_token(self) -> None:
        """After first thread refreshes, all threads should return the new token."""
        import threading

        handler = self._make_expired_handler()
        refreshed_token = "refreshed_access_token"
        new_token_data = {
            "access_token": refreshed_token,
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline",
        }

        def counting_refresh(*args, **kwargs):
            handler._tokens = new_token_data
            return new_token_data

        handler.refresh_access_token = counting_refresh

        results = []

        def call_get_valid_token():
            results.append(handler.get_valid_token())

        threads = [threading.Thread(target=call_get_valid_token) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(token == refreshed_token for token in results), (
            f"Not all threads returned the refreshed token: {results}"
        )

    @pytest.mark.asyncio
    async def test_async_get_valid_token_uses_asyncio_lock(self) -> None:
        """10 concurrent async calls on expired token should only refresh once."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        handler = OAuthHandler(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        handler._tokens = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer",
            "scope": "offline",
        }

        call_count = {"n": 0}
        new_token_data = {
            "access_token": "async_new_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline",
        }

        async def counting_async_refresh(*args, **kwargs):
            call_count["n"] += 1
            handler._tokens = new_token_data

        handler._async_refresh_access_token = counting_async_refresh

        tokens = await asyncio.gather(
            *[handler.async_get_valid_token() for _ in range(10)]
        )

        assert call_count["n"] == 1, (
            f"Expected async refresh called exactly once, got {call_count['n']}"
        )
        assert all(t == "async_new_token" for t in tokens), (
            f"Not all coroutines returned the new token: {tokens}"
        )


# =============================================================================
# Security and Timeout Tests
# =============================================================================

def test_token_file_permissions(tmp_path):
    """Token file should be created with 600 permissions."""
    import os
    from whoopyy import utils
    filepath = tmp_path / "tokens.json"
    utils.save_tokens({"access_token": "x", "refresh_token": "y"}, filepath=str(filepath))
    mode = oct(os.stat(filepath).st_mode & 0o777)
    assert mode == "0o600"


def test_callback_timeout_raises():
    """If no callback received, WhoopAuthError should be raised."""
    from unittest.mock import patch, MagicMock
    from whoopyy.auth import OAuthHandler, _CallbackHandler
    from whoopyy.exceptions import WhoopAuthError

    handler = OAuthHandler(
        client_id="test_client_id",
        client_secret="test_client_secret",
    )

    # Simulate handle_request returning without setting auth_code (timeout)
    def fake_handle_request():
        # Do not set _CallbackHandler.auth_code — simulates timeout
        pass

    mock_server = MagicMock()
    mock_server.handle_request.side_effect = fake_handle_request

    with patch("whoopyy.auth._CallbackHandler.auth_code", None), \
         patch("whoopyy.auth._CallbackHandler.error", None), \
         patch("whoopyy.auth.HTTPServer", return_value=mock_server):
        with pytest.raises(WhoopAuthError, match="timed out"):
            handler._wait_for_callback("some_state")

    handler.close()


def test_token_file_path_is_absolute():
    """TOKEN_FILE_PATH should be an absolute path."""
    from whoopyy import constants
    assert constants.TOKEN_FILE_PATH.startswith("/")


# =============================================================================
# Retry and Warning Tests
# =============================================================================

class TestTokenRefreshRetry:
    """Tests for 5xx retry logic and missing-refresh-token warning."""

    def _make_handler_with_tokens(self):
        handler = OAuthHandler(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        handler._tokens = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "Bearer",
            "scope": "offline",
        }
        return handler

    def _make_mock_response(self, status_code, json_data=None, text="error"):
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.text = text
        if json_data is not None:
            mock_resp.json.return_value = json_data
        return mock_resp

    def test_refresh_retries_on_503(self):
        """Token refresh should retry on 503, succeed on third attempt."""
        from whoopyy.constants import MAX_RETRIES

        handler = self._make_handler_with_tokens()

        good_response_data = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "offline",
        }

        responses = [
            self._make_mock_response(503),
            self._make_mock_response(503),
            self._make_mock_response(200, json_data=good_response_data),
        ]

        with patch.object(handler._http_client, "post", side_effect=responses) as mock_post:
            with patch("whoopyy.auth.save_tokens"):
                with patch("whoopyy.auth.time") as mock_time:
                    mock_time.sleep = Mock()
                    tokens = handler.refresh_access_token()

        assert tokens["access_token"] == "new_access_token"
        assert mock_post.call_count == 3

    def test_refresh_raises_after_max_retries(self):
        """Token refresh should raise WhoopTokenError after MAX_RETRIES+1 503 responses."""
        from whoopyy.constants import MAX_RETRIES

        handler = self._make_handler_with_tokens()

        responses = [self._make_mock_response(503) for _ in range(MAX_RETRIES + 1)]

        with patch.object(handler._http_client, "post", side_effect=responses) as mock_post:
            with patch("whoopyy.auth.time") as mock_time:
                mock_time.sleep = Mock()
                with pytest.raises(WhoopTokenError):
                    handler.refresh_access_token()

        assert mock_post.call_count == MAX_RETRIES + 1

    def test_refresh_fatal_on_4xx(self):
        """Token refresh should raise WhoopTokenError immediately on 4xx (no retry)."""
        handler = self._make_handler_with_tokens()

        responses = [self._make_mock_response(401, text="unauthorized")]

        with patch.object(handler._http_client, "post", side_effect=responses) as mock_post:
            with pytest.raises(WhoopTokenError) as exc_info:
                handler.refresh_access_token()

        assert mock_post.call_count == 1
        assert exc_info.value.status_code == 401

    def test_missing_refresh_token_logs_warning(self):
        """Missing refresh_token in exchange response should log a warning."""
        handler = self._make_handler_with_tokens()

        response_without_refresh = {
            "access_token": "new_access_token",
            # no refresh_token key
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "read:recovery",
        }

        mock_resp = self._make_mock_response(200, json_data=response_without_refresh)

        with patch.object(handler._http_client, "post", return_value=mock_resp):
            with patch("whoopyy.auth.save_tokens"):
                with patch("whoopyy.auth.logger") as mock_logger:
                    handler.refresh_access_token()

        warning_calls = mock_logger.warning.call_args_list
        assert any(
            "refresh_token" in str(call)
            for call in warning_calls
        ), f"Expected warning about missing refresh_token, got calls: {warning_calls}"

    def test_token_refresh_buffer_triggers(self):
        """Token expiring in 30s (< buffer of 60s) should trigger proactive refresh."""
        from whoopyy.constants import TOKEN_REFRESH_BUFFER_SECONDS

        handler = OAuthHandler(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        # Token expires in 30s, which is within the 60s buffer
        handler._tokens = {
            "access_token": "current_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 30,
            "token_type": "Bearer",
            "scope": "offline",
        }

        refresh_called = {"called": False}

        def mock_refresh(*args, **kwargs):
            refresh_called["called"] = True
            handler._tokens = {
                "access_token": "refreshed_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "expires_at": time.time() + 3600,
                "token_type": "Bearer",
                "scope": "offline",
            }
            return handler._tokens

        handler.refresh_access_token = mock_refresh

        handler.get_valid_token()

        assert refresh_called["called"], (
            "Expected refresh_access_token to be called when token expires in 30s "
            f"(buffer is {TOKEN_REFRESH_BUFFER_SECONDS}s)"
        )
        handler.close()

    def test_token_refresh_buffer_not_triggered(self):
        """Token expiring in 300s (> buffer of 60s) should not trigger proactive refresh."""
        from whoopyy.constants import TOKEN_REFRESH_BUFFER_SECONDS

        handler = OAuthHandler(
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        # Token expires in 300s, well outside the 60s buffer
        handler._tokens = {
            "access_token": "current_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "expires_at": time.time() + 300,
            "token_type": "Bearer",
            "scope": "offline",
        }

        refresh_called = {"called": False}

        def mock_refresh(*args, **kwargs):
            refresh_called["called"] = True

        handler.refresh_access_token = mock_refresh

        token = handler.get_valid_token()

        assert not refresh_called["called"], (
            "Expected refresh_access_token NOT to be called when token expires in 300s "
            f"(buffer is {TOKEN_REFRESH_BUFFER_SECONDS}s)"
        )
        assert token == "current_token"
        handler.close()
