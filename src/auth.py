"""
OAuth 2.0 authentication handler for Whoop API.

This module implements the complete OAuth 2.0 authorization code flow:
1. User authorization via browser redirect
2. Authorization code exchange for tokens
3. Automatic token refresh when expired
4. Secure token storage

Flow Diagram:
    User → Browser → Whoop Auth → Callback → Token Exchange → API Access

Example:
    >>> from whoopyy.auth import OAuthHandler
    >>> auth = OAuthHandler(
    ...     client_id="your_client_id",
    ...     client_secret="your_client_secret"
    ... )
    >>> # First time: interactive authorization
    >>> tokens = auth.authorize()
    >>> # Subsequent calls: automatic token management
    >>> token = auth.get_valid_token()
"""

import asyncio
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .constants import (
    DEFAULT_TOKEN_FILE,
    MAX_RETRIES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    RETRY_BACKOFF_BASE_SECONDS,
    SCOPES,
    DEFAULT_TIMEOUT_SECONDS,
)
from .exceptions import WhoopAuthError, WhoopTokenError
from .logger import get_logger
from .type_defs import TokenData
from .utils import (
    calculate_expiry,
    is_token_expired,
    load_tokens,
    save_tokens,
)

logger = get_logger(__name__)


# =============================================================================
# OAuth Callback Server
# =============================================================================

class _CallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for OAuth callback.
    
    Receives the authorization code from Whoop's OAuth server after
    user grants permission. Uses class-level attributes to share
    data with the main thread.
    
    Attributes:
        auth_code: Authorization code received from callback.
        auth_state: State parameter for CSRF verification.
        error: Error message if authorization failed.
    """
    
    # Class-level attributes to share data between request handler and caller
    auth_code: Optional[str] = None
    auth_state: Optional[str] = None
    error: Optional[str] = None
    
    def do_GET(self) -> None:
        """
        Handle GET request from OAuth callback redirect.
        
        Extracts authorization code, state, and any errors from
        the query parameters and sends a user-friendly response.
        """
        # Parse query parameters from callback URL
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        # Extract authorization data
        _CallbackHandler.auth_code = params.get("code", [None])[0]
        _CallbackHandler.auth_state = params.get("state", [None])[0]
        _CallbackHandler.error = params.get("error", [None])[0]
        
        # Send response to browser
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        # Generate user-friendly HTML response
        if _CallbackHandler.auth_code:
            html = self._success_html()
        else:
            html = self._error_html(_CallbackHandler.error)
        
        self.wfile.write(html.encode("utf-8"))
    
    def _success_html(self) -> str:
        """Generate success HTML page."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>WhoopYY - Authorization Successful</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            backdrop-filter: blur(10px);
        }
        .success-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        h1 { color: #00D26B; margin-bottom: 10px; }
        p { color: #ccc; }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>Authorization Successful!</h1>
        <p>You can close this window and return to your application.</p>
    </div>
</body>
</html>
"""
    
    def _error_html(self, error: Optional[str]) -> str:
        """Generate error HTML page."""
        error_msg = error or "Unknown error occurred"
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>WhoopYY - Authorization Failed</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
        }}
        .container {{
            text-align: center;
            padding: 40px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            backdrop-filter: blur(10px);
        }}
        .error-icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        h1 {{ color: #FF4757; margin-bottom: 10px; }}
        p {{ color: #ccc; }}
        .error-detail {{ color: #ff6b6b; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>Authorization Failed</h1>
        <p class="error-detail">Error: {error_msg}</p>
        <p>Please close this window and try again.</p>
    </div>
</body>
</html>
"""
    
    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP server logging."""
        # We use our own logger instead
        pass


def _reset_callback_handler() -> None:
    """Reset callback handler state between authorization attempts."""
    _CallbackHandler.auth_code = None
    _CallbackHandler.auth_state = None
    _CallbackHandler.error = None


# =============================================================================
# OAuth Handler
# =============================================================================

class OAuthHandler:
    """
    OAuth 2.0 authentication handler for Whoop API.
    
    Manages the complete OAuth flow including:
    - Authorization code grant flow with PKCE-style state
    - Token exchange and refresh
    - Automatic token persistence
    - Proactive token refresh before expiry
    
    Attributes:
        client_id: Whoop API client ID.
        client_secret: Whoop API client secret.
        redirect_uri: OAuth callback URI.
        scope: List of OAuth scopes to request.
        token_file: Path for token storage.
    
    Example:
        >>> # Initialize handler
        >>> auth = OAuthHandler(
        ...     client_id="your_client_id",
        ...     client_secret="your_client_secret"
        ... )
        >>> 
        >>> # First time: perform interactive authorization
        >>> tokens = auth.authorize()
        >>> 
        >>> # Later: get valid token (auto-refreshes if needed)
        >>> token = auth.get_valid_token()
        >>> headers = {"Authorization": f"Bearer {token}"}
    
    Context Manager:
        >>> with OAuthHandler(client_id, client_secret) as auth:
        ...     tokens = auth.authorize()
        ...     # HTTP client automatically closed on exit
    """
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8080/callback",
        scope: Optional[List[str]] = None,
        token_file: str = DEFAULT_TOKEN_FILE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """
        Initialize OAuth handler.
        
        Args:
            client_id: Whoop API client ID from developer portal.
            client_secret: Whoop API client secret from developer portal.
            redirect_uri: OAuth callback URI. Must match portal configuration.
                         Defaults to http://localhost:8080/callback.
            scope: List of OAuth scopes to request. Defaults to all available.
            token_file: Path for storing tokens. Defaults to .whoop_tokens.json.
            timeout: HTTP request timeout in seconds. Defaults to 30.
        
        Raises:
            ValueError: If client_id or client_secret is empty.
        
        Example:
            >>> auth = OAuthHandler(
            ...     client_id=os.getenv("WHOOP_CLIENT_ID"),
            ...     client_secret=os.getenv("WHOOP_CLIENT_SECRET"),
            ...     scope=["offline", "read:recovery", "read:sleep"]
            ... )
        """
        # Guard clauses
        if not client_id:
            raise ValueError("client_id is required")
        if not client_secret:
            raise ValueError("client_secret is required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file
        
        # Default to all scopes if not specified
        # "offline" is required for refresh tokens
        if scope is None:
            self.scope = SCOPES.copy()
        else:
            # Ensure "offline" scope is included for refresh tokens
            if "offline" not in scope:
                logger.warning(
                    "Adding 'offline' scope - required for refresh tokens"
                )
                scope = ["offline"] + scope
            self.scope = scope
        
        # Internal state
        self._tokens: Optional[TokenData] = None
        self._http_client = httpx.Client(timeout=timeout)
        self._refresh_lock = threading.Lock()
        
        logger.info(
            "OAuth handler initialized",
            extra={
                "client_id": client_id[:8] + "...",
                "redirect_uri": redirect_uri,
                "scopes": len(self.scope),
            }
        )
    
    # =========================================================================
    # Authorization Flow
    # =========================================================================
    
    def authorize(self, auto_open_browser: bool = True) -> TokenData:
        """
        Perform OAuth authorization code flow.
        
        Opens browser for user to grant permission, then exchanges
        the authorization code for access and refresh tokens.
        
        Args:
            auto_open_browser: Whether to automatically open browser.
                              If False, prints URL for manual navigation.
        
        Returns:
            TokenData containing access_token, refresh_token, and expiry info.
        
        Raises:
            WhoopAuthError: If authorization fails or is denied.
        
        Example:
            >>> auth = OAuthHandler(client_id, client_secret)
            >>> tokens = auth.authorize()
            >>> print(f"Access token: {tokens['access_token'][:20]}...")
            
            >>> # Manual browser mode for headless environments
            >>> tokens = auth.authorize(auto_open_browser=False)
            Please visit this URL to authorize:
            https://api.prod.whoop.com/oauth/oauth2/auth?...
        """
        logger.info("Starting OAuth authorization flow")
        
        # Reset callback handler state
        _reset_callback_handler()
        
        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Build authorization URL
        auth_url = self._build_authorization_url(state)
        
        logger.info(
            "Authorization URL generated",
            extra={"url_length": len(auth_url)}
        )
        
        # Open browser or print URL
        if auto_open_browser:
            logger.info("Opening browser for authorization")
            webbrowser.open(auth_url)
        else:
            print(f"\nPlease visit this URL to authorize:\n{auth_url}\n")
        
        # Start callback server and wait for response
        auth_code = self._wait_for_callback(state)
        
        # Exchange code for tokens
        tokens = self._exchange_code_for_tokens(auth_code)
        
        # Store tokens
        self._tokens = tokens
        save_tokens(tokens, self.token_file)
        
        logger.info("Authorization complete")
        return tokens
    
    def _build_authorization_url(self, state: str) -> str:
        """
        Build OAuth authorization URL with all required parameters.
        
        Args:
            state: CSRF protection state parameter.
        
        Returns:
            Complete authorization URL.
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scope),
            "state": state,
        }
        
        return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    
    def _wait_for_callback(self, expected_state: str) -> str:
        """
        Start callback server and wait for authorization response.
        
        Args:
            expected_state: State parameter to verify against CSRF.
        
        Returns:
            Authorization code from callback.
        
        Raises:
            WhoopAuthError: If callback contains error or state mismatch.
        """
        # Extract port from redirect URI
        parsed = urlparse(self.redirect_uri)
        port = parsed.port or 8080
        
        logger.info(
            "Starting callback server",
            extra={"port": port}
        )
        
        # Create and run callback server
        server = HTTPServer(("localhost", port), _CallbackHandler)
        CALLBACK_TIMEOUT_SECONDS = 120
        server.timeout = CALLBACK_TIMEOUT_SECONDS

        try:
            # Handle single request (blocking, with timeout)
            server.handle_request()
        finally:
            server.server_close()

        if not _CallbackHandler.auth_code and not _CallbackHandler.error:
            raise WhoopAuthError(
                "OAuth callback timed out after 120 seconds. "
                "Please restart the authorization flow."
            )

        # Check for errors
        if _CallbackHandler.error:
            raise WhoopAuthError(
                f"Authorization denied: {_CallbackHandler.error}",
                status_code=401
            )
        
        if not _CallbackHandler.auth_code:
            raise WhoopAuthError(
                "No authorization code received in callback",
                status_code=400
            )
        
        # Verify state to prevent CSRF attacks
        if _CallbackHandler.auth_state != expected_state:
            raise WhoopAuthError(
                "State parameter mismatch - possible CSRF attack",
                status_code=400
            )
        
        logger.info("Authorization code received")
        return _CallbackHandler.auth_code
    
    def _exchange_code_for_tokens(self, code: str) -> TokenData:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            code: Authorization code from callback.
        
        Returns:
            TokenData with tokens and expiry information.
        
        Raises:
            WhoopAuthError: If token exchange fails.
        """
        logger.info("Exchanging authorization code for tokens")
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }
        
        try:
            response = self._http_client.post(
                OAUTH_TOKEN_URL,
                data=data,
            )
            response.raise_for_status()
            
            token_response = response.json()
            
            # Calculate absolute expiry timestamp
            tokens: TokenData = {
                "access_token": token_response["access_token"],
                "refresh_token": token_response.get("refresh_token"),
                "expires_in": token_response["expires_in"],
                "expires_at": calculate_expiry(token_response["expires_in"]),
                "token_type": token_response.get("token_type", "Bearer"),
                "scope": token_response.get("scope", " ".join(self.scope)),
            }
            
            logger.info(
                "Token exchange successful",
                extra={"expires_in": tokens["expires_in"]}
            )
            return tokens
            
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            logger.error(
                "Token exchange failed",
                extra={
                    "status_code": e.response.status_code,
                    "error": error_detail,
                }
            )
            raise WhoopAuthError(
                f"Token exchange failed: {error_detail}",
                status_code=e.response.status_code
            )
        except httpx.RequestError as e:
            logger.error(
                "Token exchange request error",
                extra={"error": str(e)}
            )
            raise WhoopAuthError(f"Token exchange request failed: {e}")
    
    # =========================================================================
    # Token Management
    # =========================================================================
    
    def refresh_access_token(
        self,
        refresh_token: Optional[str] = None
    ) -> TokenData:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token to use. If None, uses stored token.
        
        Returns:
            New TokenData with refreshed access token.
        
        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        
        Example:
            >>> # Auto-refresh using stored token
            >>> new_tokens = auth.refresh_access_token()
            
            >>> # Explicit refresh token
            >>> new_tokens = auth.refresh_access_token(
            ...     refresh_token="stored_refresh_token"
            ... )
        """
        logger.info("Refreshing access token")
        
        # Get refresh token
        if refresh_token is None:
            refresh_token = self._get_stored_refresh_token()
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(self.scope),
        }
        
        for attempt in range(MAX_RETRIES + 1):
            response = self._http_client.post(
                OAUTH_TOKEN_URL,
                data=data,
            )
            if response.status_code == 200:
                break
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Token refresh received %d, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, wait, attempt + 1, MAX_RETRIES
                )
                time.sleep(wait)
                continue
            # 4xx or exhausted retries: fatal
            raise WhoopTokenError(
                f"Token refresh failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        token_response = response.json()

        if "refresh_token" not in token_response:
            logger.warning(
                "No refresh_token received from token exchange. "
                "Long-lived sessions will not be possible. "
                "Ensure the 'offline' scope is requested."
            )

        # Build token data
        tokens: TokenData = {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get(
                "refresh_token", refresh_token
            ),
            "expires_in": token_response["expires_in"],
            "expires_at": calculate_expiry(token_response["expires_in"]),
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(self.scope)),
        }

        # Update stored tokens
        self._tokens = tokens
        save_tokens(tokens, self.token_file)

        logger.info(
            "Token refresh successful",
            extra={"expires_in": tokens["expires_in"]}
        )
        return tokens
    
    def _get_stored_refresh_token(self) -> str:
        """
        Get refresh token from memory or file storage.
        
        Returns:
            Refresh token string.
        
        Raises:
            WhoopTokenError: If no refresh token is available.
        """
        # Load from memory
        if self._tokens is not None:
            refresh_token = self._tokens.get("refresh_token")
            if refresh_token:
                return refresh_token
        
        # Load from file
        self._tokens = load_tokens(self.token_file)
        
        if self._tokens is None:
            raise WhoopTokenError(
                "No tokens available. Please call authorize() first."
            )
        
        refresh_token = self._tokens.get("refresh_token")
        if not refresh_token:
            raise WhoopTokenError(
                "No refresh token available. Please re-authorize with "
                "'offline' scope."
            )
        
        return refresh_token
    
    def get_valid_token(self) -> str:
        """
        Get a valid access token, automatically refreshing if needed.
        
        This is the primary method for obtaining an access token for
        API requests. It handles:
        - Loading tokens from storage
        - Checking token expiry
        - Automatic refresh when expired
        
        Returns:
            Valid access token string.
        
        Raises:
            WhoopTokenError: If no tokens available or refresh fails.
        
        Example:
            >>> token = auth.get_valid_token()
            >>> response = httpx.get(
            ...     "https://api.prod.whoop.com/developer/v1/recovery",
            ...     headers={"Authorization": f"Bearer {token}"}
            ... )
        """
        # Load tokens if not in memory
        if self._tokens is None:
            self._tokens = load_tokens(self.token_file)

        # No tokens available
        if self._tokens is None:
            raise WhoopTokenError(
                "No tokens available. Please call authorize() first."
            )

        # Check if token is expired or about to expire (thread-safe)
        with self._refresh_lock:
            if is_token_expired(self._tokens):
                logger.info("Access token expired, refreshing")
                self.refresh_access_token()

        return self._tokens["access_token"]
    
    async def async_get_valid_token(self) -> str:
        """
        Get a valid access token asynchronously, refreshing if needed.

        Uses an asyncio.Lock to prevent concurrent coroutines from issuing
        multiple simultaneous refresh requests.

        Returns:
            Valid access token string.

        Raises:
            WhoopTokenError: If no tokens available or refresh fails.
        """
        if not hasattr(self, "_async_refresh_lock"):
            self._async_refresh_lock = asyncio.Lock()

        # Load tokens if not in memory
        if self._tokens is None:
            self._tokens = load_tokens(self.token_file)

        if self._tokens is None:
            raise WhoopTokenError(
                "No tokens available. Please call authorize() first."
            )

        async with self._async_refresh_lock:
            if is_token_expired(self._tokens):
                logger.info("Access token expired, refreshing (async)")
                await self._async_refresh_access_token()

        return self._tokens["access_token"]

    async def _async_refresh_access_token(
        self,
        refresh_token: Optional[str] = None,
    ) -> None:
        """
        Async version of refresh_access_token() using httpx.AsyncClient.

        Args:
            refresh_token: Refresh token to use. If None, uses stored token.

        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        """
        logger.info("Refreshing access token (async)")

        if refresh_token is None:
            refresh_token = self._get_stored_refresh_token()

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(self.scope),
        }

        for attempt in range(MAX_RETRIES + 1):
            async with httpx.AsyncClient() as client:
                response = await client.post(OAUTH_TOKEN_URL, data=data)
            if response.status_code == 200:
                break
            if response.status_code >= 500 and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Token refresh received %d, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, wait, attempt + 1, MAX_RETRIES
                )
                await asyncio.sleep(wait)
                continue
            # 4xx or exhausted retries: fatal
            raise WhoopTokenError(
                f"Token refresh failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        token_response = response.json()

        if "refresh_token" not in token_response:
            logger.warning(
                "No refresh_token received from token exchange. "
                "Long-lived sessions will not be possible. "
                "Ensure the 'offline' scope is requested."
            )

        tokens: TokenData = {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get(
                "refresh_token", refresh_token
            ),
            "expires_in": token_response["expires_in"],
            "expires_at": calculate_expiry(token_response["expires_in"]),
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(self.scope)),
        }

        self._tokens = tokens
        save_tokens(tokens, self.token_file)

        logger.info(
            "Async token refresh successful",
            extra={"expires_in": tokens["expires_in"]},
        )

    def has_valid_tokens(self) -> bool:
        """
        Check if valid tokens are available.
        
        Returns:
            True if tokens exist and haven't expired, False otherwise.
        
        Example:
            >>> if auth.has_valid_tokens():
            ...     token = auth.get_valid_token()
            ... else:
            ...     auth.authorize()
        """
        # Load tokens if not in memory
        if self._tokens is None:
            self._tokens = load_tokens(self.token_file)
        
        if self._tokens is None:
            return False
        
        # Check if we can refresh (have refresh token or token not expired)
        if is_token_expired(self._tokens):
            # Can only consider valid if we have refresh token
            return self._tokens.get("refresh_token") is not None
        
        return True
    
    # =========================================================================
    # Lifecycle Management
    # =========================================================================
    
    def close(self) -> None:
        """
        Close the HTTP client and release resources.
        
        Should be called when done with the handler, or use as
        context manager for automatic cleanup.
        
        Example:
            >>> auth = OAuthHandler(client_id, client_secret)
            >>> try:
            ...     tokens = auth.authorize()
            ... finally:
            ...     auth.close()
        """
        self._http_client.close()
        logger.info("OAuth handler closed")
    
    def __enter__(self) -> "OAuthHandler":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"OAuthHandler("
            f"client_id='{self.client_id[:8]}...', "
            f"redirect_uri='{self.redirect_uri}')"
        )
