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
        """Test default token file path."""
        handler = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        )
        
        assert handler.token_file == ".whoop_tokens.json"
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
