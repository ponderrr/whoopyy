"""
OAuth 2.0 authentication handler for Whoop API.

This module implements the complete OAuth 2.0 authorization code flow:
1. User authorization via browser redirect
2. Authorization code exchange for tokens
3. Automatic token refresh when expired
4. Secure token storage

Flow Diagram:
    User → Browser → Whoop Auth → Callback → Token Exchange → API Access

WHOOP rotates the refresh token on every refresh: the refresh token in the
response is the only valid one afterwards, and a second refresh with the old
token fails. Every refresh therefore runs under an in-process lock (a
thread lock for sync code, an ``asyncio.Lock`` for async code) and a
cross-process lock on the token file, and re-reads the token file first, so
a refresh token that another thread, coroutine or process already rotated is
never presented again. Before a refresh token or an authorization code is
sent, the token file is checked to be writable, so a result that could not
be saved never spends the grant; and an async refresh runs in its own task,
so cancelling its caller cannot drop the rotated refresh token.

Example:
    >>> from strapkit.auth import OAuthHandler
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
import base64
import errno
import hashlib
import html
import secrets
import socket
import socketserver
import threading
import time
import webbrowser
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType
from typing import (
    Any,
    AsyncIterator,
    Coroutine,
    Dict,
    Iterator,
    List,
    NamedTuple,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
)
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .constants import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TOKEN_FILE,
    MAX_RETRIES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    RETRY_BACKOFF_BASE_SECONDS,
    SCOPES,
)
from .exceptions import WhoopAuthError, WhoopTokenError
from .logger import get_logger
from .type_defs import TokenData
from .utils import (
    _check_token_file_writable,
    _file_lock_held_by_current_thread,
    _sanitize_error_response,
    async_token_file_lock,
    calculate_expiry,
    delete_tokens,
    is_token_expired,
    load_tokens,
    save_tokens,
    token_file_lock,
)

logger = get_logger(__name__)

__all__ = ["OAuthHandler"]

# =============================================================================
# Constants
# =============================================================================

CALLBACK_TIMEOUT_SECONDS: float = 120.0
"""How long authorize() waits for the browser to deliver the OAuth callback."""

CALLBACK_SOCKET_TIMEOUT_SECONDS: float = 10.0
"""
Read timeout for each connection to the local callback server, and the
longest any one connection may stay open.

Every connection is served on its own thread, so an idle connection (for
example a browser's speculative pre-connect) can neither delay the real
callback nor keep the flow waiting past CALLBACK_TIMEOUT_SECONDS. All
connections are closed when the flow ends.
"""

_CALLBACK_MAX_CONNECTIONS = 16
"""
Connections the callback server serves at once.

A new connection beyond this closes the oldest open one, so idle or
trickling connections can neither pile up handler threads nor lock the
browser's callback out.
"""

_CALLBACK_REAP_INTERVAL_SECONDS = 0.25
"""How often the waiting flow closes connections older than the socket timeout."""

_PORT_PROBE_TIMEOUT_SECONDS = 0.5
"""Connect timeout when checking whether another program listens on the callback port."""

_NO_IPV6_ERRNOS = frozenset(
    code
    for code in (
        getattr(errno, "EADDRNOTAVAIL", None),
        getattr(errno, "EAFNOSUPPORT", None),
        getattr(errno, "EPROTONOSUPPORT", None),
    )
    if code is not None
)
"""Errors that mean this host has no IPv6 loopback to bind for a "localhost" redirect."""

_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
"""Redirect URI hosts the callback server accepts."""

_PKCE_VERIFIER_BYTES = 64
"""Random bytes in a PKCE code verifier (86 base64url characters, RFC 7636 allows 43-128)."""

_REJECTED_REFRESH_TOKEN_ERRORS = frozenset({"invalid_grant", "token_inactive"})
"""
OAuth error codes with which the token endpoint rejects the refresh token itself.

``invalid_grant`` is the RFC 6749 code for an invalid, expired or revoked
grant. Ory Hydra/fosite, which WHOOP's OAuth server is based on, may answer
``token_inactive`` instead when a refresh token is presented a second time.
``invalid_client`` (bad client credentials) is deliberately not included.
"""

_NO_TOKENS_MESSAGE = (
    "No tokens available. Please call authenticate() (or OAuthHandler.authorize()) first."
)

AUTHORIZATION_ENDED_MESSAGE = (
    "WHOOP authorization has ended: the token endpoint rejected the stored "
    "refresh token (it was revoked, expired or already used). The stored "
    "tokens were cleared; call authenticate() again to sign in."
)
"""Message of the WhoopTokenError raised when the refresh token is dead."""


# =============================================================================
# PKCE
# =============================================================================

def _generate_pkce_pair() -> Tuple[str, str]:
    """
    Create a PKCE code verifier and its S256 code challenge (RFC 7636).

    Returns:
        Tuple of (code_verifier, code_challenge). The verifier is 86
        unreserved characters from ``secrets``; the challenge is the
        base64url-encoded SHA-256 of the verifier without padding.
    """
    verifier = secrets.token_urlsafe(_PKCE_VERIFIER_BYTES)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# =============================================================================
# OAuth Callback Server
# =============================================================================

def _shutdown_socket(sock: Any) -> None:
    """
    Shut down a connection so the handler thread blocked on it returns.

    The handler thread still closes the socket itself.

    Args:
        sock: A connected socket.
    """
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _first_param(params: Dict[str, List[str]], name: str) -> Optional[str]:
    """
    Return the first value of a query parameter.

    Args:
        params: Parsed query string from ``parse_qs``.
        name: Parameter name.

    Returns:
        The first value, or None if the parameter is absent.
    """
    values = params.get(name)
    return values[0] if values else None


class _CallbackResult:
    """
    Outcome of one OAuth flow, shared by every server listening for it.

    Attributes:
        ready: Set once a callback with a valid state has arrived.
        code: Authorization code from the accepted callback.
        error: OAuth ``error`` from the accepted callback.
        error_description: OAuth ``error_description`` from the accepted callback.
    """

    def __init__(self) -> None:
        """Create an empty result."""
        self.ready = threading.Event()
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.error_description: Optional[str] = None
        self._lock = threading.Lock()

    def record(
        self,
        code: Optional[str],
        error: Optional[str],
        error_description: Optional[str],
    ) -> None:
        """
        Store the first callback with a valid state and wake the waiter.

        Args:
            code: Authorization code, if any.
            error: OAuth error code, if any.
            error_description: OAuth error description, if any.
        """
        with self._lock:
            if self.ready.is_set():
                return
            self.code = code
            self.error = error
            self.error_description = error_description
            self.ready.set()


class _CallbackServer(socketserver.ThreadingMixIn, HTTPServer):
    """
    Loopback HTTP server that receives a single OAuth redirect.

    Each connection is handled on its own daemon thread with a socket read
    timeout. At most ``max_connections`` are open at a time: a new one
    closes the oldest. Only a GET to
    ``callback_path`` whose ``state`` matches ``expected_state`` is accepted
    as the result; anything else is answered and ignored, and the server
    keeps waiting. For a ``localhost`` redirect URI one server listens on
    127.0.0.1 and a sibling on ::1, sharing one result.

    Attributes:
        expected_state: State value sent in the authorization URL.
        callback_path: Path component of the redirect URI.
        socket_timeout: Read timeout for each connection, in seconds, and
            the longest a connection may stay open.
        max_connections: Connections served at once.
        result: The flow's result, possibly shared with sibling servers.
        siblings: Further servers (other loopback addresses) of the same flow.
    """

    daemon_threads = True
    block_on_close = False

    def __init__(
        self,
        server_address: Tuple[str, int],
        address_family: int,
        expected_state: str,
        callback_path: str,
        socket_timeout: float,
        result: Optional[_CallbackResult] = None,
        max_connections: Optional[int] = None,
    ) -> None:
        """
        Bind the server (it does not serve until serve_forever() runs).

        Args:
            server_address: (host, port) to bind.
            address_family: socket.AF_INET or socket.AF_INET6.
            expected_state: State value sent in the authorization URL.
            callback_path: Path component of the redirect URI.
            socket_timeout: Read timeout for each connection, in seconds.
            result: Result shared with other servers of the same flow, or
                None for a new one.
            max_connections: Connections served at once. Defaults to
                _CALLBACK_MAX_CONNECTIONS.

        Raises:
            OSError: If the address cannot be bound (e.g. port in use).
        """
        self.address_family = address_family
        self.expected_state = expected_state
        self.callback_path = callback_path
        self.socket_timeout = socket_timeout
        self.max_connections = (
            _CALLBACK_MAX_CONNECTIONS if max_connections is None else max_connections
        )
        self.result = result if result is not None else _CallbackResult()
        self.siblings: List["_CallbackServer"] = []
        self._connections: Dict[Any, float] = {}
        self._connections_lock = threading.Lock()
        self._closing = False
        super().__init__(server_address, _CallbackHandler)

    @property
    def result_ready(self) -> threading.Event:
        """Event set once a callback with a valid state has arrived."""
        return self.result.ready

    @property
    def auth_code(self) -> Optional[str]:
        """Authorization code from the accepted callback."""
        return self.result.code

    @property
    def error(self) -> Optional[str]:
        """OAuth ``error`` from the accepted callback."""
        return self.result.error

    @property
    def error_description(self) -> Optional[str]:
        """OAuth ``error_description`` from the accepted callback."""
        return self.result.error_description

    def server_bind(self) -> None:
        """Bind the socket without HTTPServer's reverse DNS lookup of the host."""
        if self.address_family == socket.AF_INET6 and hasattr(socket, "IPV6_V6ONLY"):
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            except OSError:
                logger.debug("Could not set IPV6_V6ONLY on the callback socket", exc_info=True)
        socketserver.TCPServer.server_bind(self)
        sockname = self.socket.getsockname()
        self.server_name = str(sockname[0])
        self.server_port = int(sockname[1])

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Log handler errors at debug level instead of printing a traceback."""
        logger.debug("Error while handling an OAuth callback request", exc_info=True)

    def process_request(self, request: Any, client_address: Any) -> None:
        """
        Serve a new connection on its own thread, closing the oldest if too many.

        Args:
            request: The accepted socket.
            client_address: The peer address.
        """
        evicted: List[Any] = []
        with self._connections_lock:
            closing = self._closing
            if not closing:
                while len(self._connections) >= self.max_connections:
                    oldest = next(iter(self._connections))
                    del self._connections[oldest]
                    evicted.append(oldest)
                self._connections[request] = time.monotonic()
        for sock in evicted:
            logger.debug("Closing the oldest callback connection: too many open connections")
            _shutdown_socket(sock)
        if closing:
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request: Any) -> None:
        """
        Forget and close a finished connection.

        Args:
            request: The socket to close.
        """
        with self._connections_lock:
            self._connections.pop(request, None)
        super().shutdown_request(request)

    def close_connections(self, older_than: Optional[float] = None) -> None:
        """
        Shut down open connections so their handler threads exit.

        Args:
            older_than: Only connections open at least this many seconds.
                None shuts down all of them and refuses new ones.
        """
        now = time.monotonic()
        with self._connections_lock:
            if older_than is None:
                self._closing = True
            doomed = [
                sock for sock, opened in self._connections.items()
                if older_than is None or now - opened >= older_than
            ]
        for sock in doomed:
            _shutdown_socket(sock)

    def state_matches(self, state: Optional[str]) -> bool:
        """
        Compare a callback's state with the expected one in constant time.

        Args:
            state: The ``state`` query parameter, or None if absent.

        Returns:
            True if the state matches.
        """
        if state is None:
            return False
        return secrets.compare_digest(
            state.encode("utf-8"), self.expected_state.encode("utf-8")
        )

    def record_result(
        self,
        code: Optional[str],
        error: Optional[str],
        error_description: Optional[str],
    ) -> None:
        """
        Store the first callback with a valid state and wake the waiter.

        Args:
            code: Authorization code, if any.
            error: OAuth error code, if any.
            error_description: OAuth error description, if any.
        """
        self.result.record(code, error, error_description)

    def all_servers(self) -> List["_CallbackServer"]:
        """Return this server followed by its siblings."""
        return [self] + self.siblings

    def server_close(self) -> None:
        """Close the listening sockets of this server and its siblings."""
        for sibling in self.siblings:
            sibling.server_close()
        super().server_close()


class _CallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the OAuth callback.

    Receives the authorization code from Whoop's OAuth server after the
    user grants permission and hands it to the owning _CallbackServer.
    The state parameter is verified before ``code`` or ``error`` is looked
    at, requests to other paths get a 404, and everything reflected into
    the HTML response is escaped.
    """

    def setup(self) -> None:
        """Apply the server's per-connection read timeout before reading."""
        super().setup()
        server = self.server
        if isinstance(server, _CallbackServer):
            self.connection.settimeout(server.socket_timeout)

    def do_GET(self) -> None:
        """
        Handle GET request from OAuth callback redirect.

        Verifies path and state, records the code or error on the server
        and sends a user-friendly response.
        """
        server = self.server
        if not isinstance(server, _CallbackServer):
            self.send_error(500)
            return

        parsed = urlparse(self.path)
        if parsed.path != server.callback_path:
            logger.debug(
                "Ignoring request to an unexpected path on the callback server",
                extra={"path": parsed.path[:64]}
            )
            self._send_page(404, self._not_found_html())
            return

        params = parse_qs(parsed.query)
        if not server.state_matches(_first_param(params, "state")):
            logger.warning(
                "Ignoring OAuth callback with a missing or mismatched state "
                "parameter (possible CSRF attempt)"
            )
            self._send_page(
                400,
                self._error_html(
                    "Invalid or missing state parameter. This request does not "
                    "belong to the authorization you started."
                ),
            )
            return

        code = _first_param(params, "code")
        error = _first_param(params, "error")
        try:
            # Answer the browser first: once the result is recorded the
            # waiting thread may shut the server down.
            if error is None and code:
                self._send_page(200, self._success_html())
            else:
                self._send_page(200, self._error_html(error or "No authorization code received"))
        finally:
            server.record_result(
                code=code,
                error=error,
                error_description=_first_param(params, "error_description"),
            )

    def _send_page(self, status: int, page: str) -> None:
        """
        Send an HTML response with defensive headers.

        Args:
            status: HTTP status code.
            page: HTML document to send.
        """
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _success_html(self) -> str:
        """Generate success HTML page."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>strapkit - Authorization Successful</title>
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
        """Generate error HTML page (the error text is HTML-escaped)."""
        error_msg = html.escape(error or "Unknown error occurred")
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>strapkit - Authorization Failed</title>
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

    def _not_found_html(self) -> str:
        """Generate the page for requests to paths other than the callback."""
        return "<!DOCTYPE html><html><body><p>Not found.</p></body></html>"

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default HTTP server logging."""
        # We use our own logger instead
        pass


def _something_listens_on(family: int, address: str, port: int) -> bool:
    """
    Tell whether another program already accepts connections on a loopback port.

    A browser sends the OAuth redirect to whichever program answers on the
    redirect URI's address, so such a port must not be used even where the
    operating system would let the callback server bind it too.

    Args:
        family: socket.AF_INET or socket.AF_INET6.
        address: Loopback address to probe.
        port: TCP port.

    Returns:
        True if a connection succeeded; False if it was refused, timed out
        or the address family is unavailable.
    """
    try:
        probe = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.settimeout(_PORT_PROBE_TIMEOUT_SECONDS)
        probe.connect((address, port))
    except OSError:
        return False
    finally:
        probe.close()
    return True


# =============================================================================
# Token Response Helpers
# =============================================================================

def _has_access_token(tokens: Optional[TokenData]) -> bool:
    """
    Tell whether loaded token data holds an access token.

    Args:
        tokens: Token data from memory or the token file.

    Returns:
        True if ``tokens`` is a dict with a non-empty access_token.
    """
    if not isinstance(tokens, dict):
        return False
    access_token = tokens.get("access_token")
    return isinstance(access_token, str) and bool(access_token)


def _expires_at(tokens: TokenData) -> float:
    """
    Read the absolute expiry of token data, treating bad values as expired.

    Args:
        tokens: Token data.

    Returns:
        The expires_at timestamp, or 0.0 if missing or not a number.
    """
    value = tokens.get("expires_at", 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_rejected_refresh_token(response: httpx.Response) -> bool:
    """
    Tell whether a token endpoint response rejects the refresh token itself.

    Args:
        response: Response from the token endpoint.

    Returns:
        True for a 400/401 whose OAuth ``error`` says the grant is invalid,
        expired, revoked or already used. Client authentication errors
        (``invalid_client``) and unparseable bodies return False.
    """
    if response.status_code not in (400, 401):
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    return isinstance(error, str) and error in _REJECTED_REFRESH_TOKEN_ERRORS


class _RefreshFailure(NamedTuple):
    """
    A refresh attempt that failed.

    Attributes:
        attempt: Number of the attempt (OAuthHandler._refresh_attempts after it).
        refresh_token: Refresh token that was current when it started.
        error: What it raised.
    """

    attempt: int
    refresh_token: Optional[str]
    error: Exception


_T = TypeVar("_T")


def _log_task_error(task: "asyncio.Future[Any]") -> None:
    """
    Retrieve the outcome of a shielded refresh task whose caller may be gone.

    Args:
        task: The finished task.
    """
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.debug("Token refresh task failed", exc_info=error)


async def _run_shielded(coro: Coroutine[Any, Any, _T]) -> _T:
    """
    Run ``coro`` in its own task that cancelling the caller does not cancel.

    WHOOP rotates the refresh token as soon as it receives a refresh
    request. If the coroutine that sent it were cancelled (asyncio.wait_for,
    a client disconnect) before saving the response, the only valid refresh
    token would be lost. The task therefore always runs to completion.

    Args:
        coro: Coroutine to run.

    Returns:
        The coroutine's result.

    Raises:
        Exception: Whatever ``coro`` raises.
        asyncio.CancelledError: If the caller is cancelled (the task goes on).
    """
    task = asyncio.ensure_future(coro)
    task.add_done_callback(_log_task_error)
    return await asyncio.shield(task)


# =============================================================================
# OAuth Handler
# =============================================================================

class OAuthHandler:
    """
    OAuth 2.0 authentication handler for Whoop API.

    Manages the complete OAuth flow including:
    - Authorization code grant flow with a random ``state`` parameter
      (CSRF protection) and, with ``use_pkce=True``, PKCE (S256)
    - Token exchange and refresh
    - Automatic token persistence
    - Proactive token refresh before expiry
    - Refresh coordination across threads, coroutines and processes that
      share the token file (WHOOP rotates refresh tokens)

    Attributes:
        client_id: Whoop API client ID.
        client_secret: Whoop API client secret.
        redirect_uri: OAuth callback URI.
        scope: List of OAuth scopes to request.
        token_file: Path for token storage.
        use_pkce: Whether the authorization flow sends a PKCE challenge.

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
        use_pkce: bool = False,
    ) -> None:
        """
        Initialize OAuth handler.

        Args:
            client_id: Whoop API client ID from developer portal.
            client_secret: Whoop API client secret from developer portal.
            redirect_uri: OAuth callback URI. Must match portal configuration.
                         Defaults to http://localhost:8080/callback.
            scope: List of OAuth scopes to request. Defaults to all available.
            token_file: Path for storing tokens. Defaults to ~/.whoop_tokens.json.
            timeout: HTTP request timeout in seconds. Defaults to 30.
            use_pkce: Send a PKCE S256 code challenge in the authorization
                      request and the matching code verifier in the code
                      exchange (in addition to the client secret). Defaults
                      to False until verified against WHOOP.

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
        self.use_pkce = use_pkce

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
        self._timeout = timeout
        self._http_client = httpx.Client(timeout=timeout)
        # Re-entrant so refresh_access_token() can be called while the lock
        # is held (get_valid_token, refresh_if_stale); _lock_depth makes the
        # non-re-entrant token file lock follow the same nesting.
        self._refresh_lock = threading.RLock()
        self._lock_depth = 0
        # The asyncio lock is created lazily inside the running event loop
        # (see _async_refresh_lock), never here: on Python 3.9 asyncio.Lock()
        # binds to the current loop at construction, and on 3.10+ a lock
        # cannot be reused in a later asyncio.run() loop.
        self._async_lock: Optional[asyncio.Lock] = None
        self._async_lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_lock_guard = threading.Lock()
        # Every store or clear of self._tokens bumps the generation, so a
        # lock-free reader never caches tokens it loaded before a logout or
        # a refresh (see _load_unlocked).
        self._tokens_guard = threading.Lock()
        self._tokens_generation = 0
        # Refresh attempts finished so far, and the latest one if it failed:
        # callers that waited for the locks while it ran share its error
        # instead of repeating it (see _raise_if_refresh_failed_since).
        self._refresh_attempts = 0
        self._last_refresh_failure: Optional[_RefreshFailure] = None
        # The error of a refresh token WHOOP rejected, reported again until
        # new tokens are stored or the tokens are cleared on purpose.
        self._authorization_ended: Optional[WhoopTokenError] = None
        # Access token of a token file that could not be deleted when the
        # tokens were cleared; such file contents are ignored.
        self._discarded_access_token: Optional[str] = None

        logger.info(
            "OAuth handler initialized",
            extra={
                "client_id": client_id[:8] + "...",
                "redirect_uri": redirect_uri,
                "scopes": len(self.scope),
            }
        )

    # =========================================================================
    # Locking
    # =========================================================================

    @property
    def _async_refresh_lock(self) -> asyncio.Lock:
        """
        The asyncio.Lock for the running event loop, created on first use.

        A new lock is created whenever the running loop differs from the one
        the current lock was made for, so one handler works across several
        ``asyncio.run()`` calls and can be constructed outside any loop.

        Raises:
            RuntimeError: If no event loop is running.
        """
        loop = asyncio.get_running_loop()
        with self._async_lock_guard:
            if self._async_lock is None or self._async_lock_loop is not loop:
                self._async_lock = asyncio.Lock()
                self._async_lock_loop = loop
            return self._async_lock

    @contextmanager
    def _token_lock(self) -> Iterator[None]:
        """
        Hold the thread lock, then the cross-process token file lock.

        Re-entrant within one thread: nested use only takes the file lock
        once.

        If another thread holds the thread lock while this thread's event
        loop has a task suspended with the token file lock (an async refresh
        in progress), that thread may be waiting for the task, and the task
        cannot resume until this synchronous code returns. Waiting would
        deadlock, so RuntimeError is raised instead.

        Yields:
            None, while both locks are held.

        Raises:
            RuntimeError: If waiting for the locks would deadlock (see above,
                and token_file_lock()).
        """
        if not self._refresh_lock.acquire(blocking=False):
            if _file_lock_held_by_current_thread(self.token_file):
                raise RuntimeError(
                    "Synchronous token code cannot run on this thread now: an asyncio "
                    "task on this thread's event loop holds the token file lock for "
                    f"{self.token_file} (an async token refresh is in progress) while "
                    "another thread holds this handler's lock and may be waiting for "
                    "that task, so waiting here could deadlock. Use the async API on "
                    "the event loop thread, or run the synchronous call in a worker "
                    "thread."
                )
            self._refresh_lock.acquire()
        try:
            if self._lock_depth:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return
            with token_file_lock(self.token_file):
                self._lock_depth = 1
                try:
                    yield
                finally:
                    self._lock_depth = 0
        finally:
            self._refresh_lock.release()

    @asynccontextmanager
    async def _async_token_lock(self) -> AsyncIterator[None]:
        """
        Hold this loop's asyncio lock, then the token file lock, without blocking.

        Not re-entrant: callers must not nest it.

        Yields:
            None, while both locks are held.
        """
        async with self._async_refresh_lock:
            async with async_token_file_lock(self.token_file):
                yield

    # =========================================================================
    # Authorization Flow
    # =========================================================================

    def authorize(self, auto_open_browser: bool = True) -> TokenData:
        """
        Perform OAuth authorization code flow.

        Opens browser for user to grant permission, then exchanges
        the authorization code for access and refresh tokens. Before the
        browser opens, the token file is checked (it must be writable and
        not a symbolic link) and the local callback server is started, so
        an unusable token file, an invalid redirect URI or a busy port fails
        early, before the user signs in.

        Args:
            auto_open_browser: Whether to automatically open browser.
                              If False, logs the URL for manual navigation.

        Returns:
            TokenData containing access_token, refresh_token, and expiry info.

        Raises:
            WhoopAuthError: If authorization fails, is denied or times out,
                if the token file cannot be written, or if called on an
                event loop thread while an async refresh of the same token
                file is in progress there. WhoopTokenError (a subclass) if
                the new tokens cannot be saved; they are kept in memory.

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

        if _file_lock_held_by_current_thread(self.token_file):
            # The flow blocks this thread for up to CALLBACK_TIMEOUT_SECONDS,
            # and storing its tokens needs the lock that task holds.
            raise WhoopAuthError(
                "authorize() cannot run on this thread now: an async token refresh "
                f"for {self.token_file} is in progress on this thread's event loop. "
                "Call authenticate() before starting async work, or from a worker "
                "thread (for example with asyncio.to_thread)."
            )
        self._ensure_token_file_writable(
            "The browser was not opened.", error_type=WhoopAuthError
        )

        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        code_verifier: Optional[str] = None
        code_challenge: Optional[str] = None
        if self.use_pkce:
            code_verifier, code_challenge = _generate_pkce_pair()

        # Build authorization URL
        auth_url = self._build_authorization_url(state, code_challenge=code_challenge)

        logger.info(
            "Authorization URL generated",
            extra={"url_length": len(auth_url), "pkce": self.use_pkce}
        )

        # Bind the callback server before sending the user to WHOOP
        server = self._create_callback_server(state)

        # Open browser or print URL
        try:
            if auto_open_browser:
                logger.info("Opening browser for authorization")
                webbrowser.open(auth_url)
            else:
                logger.info("Please visit this URL to authorize: %s", auth_url)
        except BaseException:
            server.server_close()
            raise

        # Wait for the callback (closes the server)
        auth_code = self._wait_for_callback(state, server=server)

        # Exchange code for tokens
        tokens = self._exchange_code_for_tokens(auth_code, code_verifier=code_verifier)

        # Store tokens
        with self._token_lock():
            self._store_tokens(tokens)

        logger.info("Authorization complete")
        return tokens

    def _build_authorization_url(
        self,
        state: str,
        code_challenge: Optional[str] = None,
    ) -> str:
        """
        Build OAuth authorization URL with all required parameters.

        Args:
            state: CSRF protection state parameter.
            code_challenge: PKCE S256 code challenge, or None to omit PKCE.

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
        if code_challenge is not None:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    def _create_callback_server(self, expected_state: str) -> _CallbackServer:
        """
        Validate the redirect URI and bind the loopback callback server.

        For a ``localhost`` redirect URI the server listens on 127.0.0.1 and,
        where the host has IPv6, on ::1 as well: browsers may resolve
        localhost to either address. A port on which another program
        already accepts connections is refused, so the authorization code
        cannot be delivered to that program.

        Args:
            expected_state: State parameter the callback must carry.

        Returns:
            A bound (not yet serving) _CallbackServer; sibling servers for
            further loopback addresses are in its ``siblings``.

        Raises:
            WhoopAuthError: If the redirect host is not a loopback host or
                the port is in use or cannot be bound.
        """
        parsed = urlparse(self.redirect_uri)
        host = parsed.hostname
        if host not in _LOOPBACK_HOSTS:
            raise WhoopAuthError("Redirect URI must use localhost for security")
        port = parsed.port or 8080
        callback_path = parsed.path or "/"

        # (family, address, required): ::1 is optional for "localhost" only
        targets: List[Tuple[int, str, bool]]
        if host == "::1":
            targets = [(socket.AF_INET6, "::1", True)]
        elif host == "127.0.0.1":
            targets = [(socket.AF_INET, "127.0.0.1", True)]
        else:
            targets = [(socket.AF_INET, "127.0.0.1", True), (socket.AF_INET6, "::1", False)]

        for family, address, _required in targets:
            if _something_listens_on(family, address, port):
                raise WhoopAuthError(
                    f"Could not start the OAuth callback server on port {port}: another "
                    f"program is already listening on {address} port {port} and could "
                    "receive the authorization code. Free the port or configure a "
                    "different redirect_uri."
                )

        servers: List[_CallbackServer] = []
        try:
            for family, address, required in targets:
                try:
                    servers.append(
                        _CallbackServer(
                            (address, port),
                            address_family=family,
                            expected_state=expected_state,
                            callback_path=callback_path,
                            socket_timeout=CALLBACK_SOCKET_TIMEOUT_SECONDS,
                            result=servers[0].result if servers else None,
                        )
                    )
                except OSError as e:
                    if not required and e.errno in _NO_IPV6_ERRNOS:
                        logger.debug(
                            "No IPv6 loopback, the callback server listens on 127.0.0.1 only",
                            extra={"error": str(e)}
                        )
                        continue
                    raise WhoopAuthError(
                        f"Could not start the OAuth callback server on port {port}: {e}. "
                        "Free the port or configure a different redirect_uri."
                    ) from e
        except BaseException:
            for server in servers:
                server.server_close()
            raise

        server = servers[0]
        server.siblings = servers[1:]
        logger.info(
            "Starting callback server",
            extra={"port": port, "addresses": [s.server_name for s in servers]}
        )
        return server

    def _wait_for_callback(
        self,
        expected_state: str,
        server: Optional[_CallbackServer] = None,
    ) -> str:
        """
        Serve the callback endpoint until a valid callback or the deadline.

        Requests to other paths and callbacks with a wrong or missing state
        are answered and ignored; the server keeps waiting until a callback
        with the expected state arrives or CALLBACK_TIMEOUT_SECONDS pass.
        Connections open longer than the socket timeout are closed while
        waiting, and every connection is closed when the flow ends.

        Args:
            expected_state: State parameter to verify against CSRF.
            server: Bound callback server from _create_callback_server().
                    Created here if None. Always closed on return.

        Returns:
            Authorization code from callback.

        Raises:
            WhoopAuthError: If the callback carries an error or no code, or
                no valid callback arrives in time.
        """
        if server is None:
            server = self._create_callback_server(expected_state)

        timeout = CALLBACK_TIMEOUT_SECONDS
        servers = server.all_servers()
        threads = [
            threading.Thread(
                target=s.serve_forever,
                kwargs={"poll_interval": 0.1},
                name="strapkit-oauth-callback",
                daemon=True,
            )
            for s in servers
        ]
        try:
            for thread in threads:
                thread.start()
            received = self._await_callback(server, time.monotonic() + timeout)
        finally:
            for s, thread in zip(servers, threads):
                if thread.is_alive():
                    s.shutdown()
            for s in servers:
                s.close_connections()
            server.server_close()

        if not received:
            raise WhoopAuthError(
                f"OAuth callback timed out after {timeout:g} seconds. "
                "Please restart the authorization flow."
            )

        if server.error is not None:
            detail = _sanitize_error_response(server.error)
            if server.error_description:
                detail += f" ({_sanitize_error_response(server.error_description)})"
            raise WhoopAuthError(
                f"Authorization denied: {detail}",
                status_code=401
            )

        if not server.auth_code:
            raise WhoopAuthError(
                "No authorization code received in callback",
                status_code=400
            )

        logger.info("Authorization code received")
        return server.auth_code

    @staticmethod
    def _await_callback(server: _CallbackServer, deadline: float) -> bool:
        """
        Wait for the flow's result, closing connections that stay open too long.

        Args:
            server: The flow's (primary) callback server.
            deadline: time.monotonic() value at which to give up.

        Returns:
            True if a callback with a valid state arrived in time.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return server.result_ready.is_set()
            if server.result_ready.wait(min(remaining, _CALLBACK_REAP_INTERVAL_SECONDS)):
                return True
            for s in server.all_servers():
                s.close_connections(older_than=s.socket_timeout)

    def _exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: Optional[str] = None,
    ) -> TokenData:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from callback.
            code_verifier: PKCE code verifier matching the challenge sent in
                           the authorization URL, or None without PKCE.

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
        if code_verifier is not None:
            data["code_verifier"] = code_verifier

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
            error_detail = _sanitize_error_response(e.response.text)
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

        Runs under the handler's thread lock and the cross-process token
        file lock. Without an explicit ``refresh_token``, the newest tokens
        (from memory or the token file) are used, so a refresh token that
        another process already rotated is never presented again. Before
        the refresh token is sent, the token file is checked: if it cannot
        be written (or is a symbolic link), WhoopTokenError is raised and
        the refresh token stays unused.

        If WHOOP rejects the stored refresh token (``invalid_grant``), the
        token file is re-read first: if another process rotated it, its
        newer tokens are used. Otherwise the authorization has ended: the
        tokens are cleared from memory, the token file is deleted and
        WhoopTokenError is raised telling the caller to authenticate again.

        Args:
            refresh_token: Refresh token to use. If None, uses stored token.

        Returns:
            New TokenData with refreshed access token.

        Raises:
            WhoopTokenError: If refresh fails, no refresh token is available,
                or the new tokens cannot be saved (they are kept in memory).

        Example:
            >>> # Auto-refresh using stored token
            >>> new_tokens = auth.refresh_access_token()

            >>> # Explicit refresh token
            >>> new_tokens = auth.refresh_access_token(
            ...     refresh_token="stored_refresh_token"
            ... )
        """
        with self._token_lock():
            if refresh_token is None:
                self._adopt_newest_tokens()
            return self._attempt_refresh(refresh_token)

    def refresh_if_stale(self, seen_access_token: Optional[str]) -> str:
        """
        Refresh after a rejected access token, unless someone already did.

        Call this when the API answered 401 for ``seen_access_token``.
        Under the thread lock and the token file lock, the tokens are
        reloaded from disk. If the current access token differs from
        ``seen_access_token`` and has not expired, another thread or process
        has already refreshed and that token is returned without a new
        refresh. If a refresh attempt that this call waited for failed and
        nothing has changed since, its error is raised again instead of
        repeating the attempt. Otherwise the token is refreshed once.

        Args:
            seen_access_token: The access token the failed request used.
                None means unknown: a current unexpired token is returned
                as is.

        Returns:
            An access token to retry the request with.

        Raises:
            WhoopTokenError: If no tokens are available or the refresh fails
                (see refresh_access_token()).

        Example:
            >>> token = auth.get_valid_token()
            >>> # ... the API answers 401 for this token ...
            >>> token = auth.refresh_if_stale(token)
        """
        attempts = self._refresh_attempts
        with self._token_lock():
            current = self._adopt_newest_tokens()
            if current is None:
                raise self._no_tokens_error()
            if not is_token_expired(current) and current["access_token"] != seen_access_token:
                logger.info("Access token was already refreshed by another caller, reusing it")
                return current["access_token"]
            self._raise_if_refresh_failed_since(attempts, current)
            logger.info("Access token rejected or expired, refreshing")
            return self.refresh_access_token()["access_token"]

    async def async_refresh_if_stale(self, seen_access_token: Optional[str]) -> str:
        """
        Async twin of refresh_if_stale() that never blocks the event loop.

        Waits for this event loop's asyncio lock and the token file lock
        (polling with ``asyncio.sleep``), reloads the tokens and refreshes
        with httpx.AsyncClient only if no other coroutine, thread or process
        has already replaced ``seen_access_token``. The locked part runs in
        its own task: if the caller is cancelled, a refresh already under
        way still completes and saves the rotated tokens.

        Args:
            seen_access_token: The access token the failed request used.
                None means unknown: a current unexpired token is returned
                as is.

        Returns:
            An access token to retry the request with.

        Raises:
            WhoopTokenError: If no tokens are available or the refresh fails.

        Example:
            >>> token = await auth.async_get_valid_token()
            >>> # ... the API answers 401 for this token ...
            >>> token = await auth.async_refresh_if_stale(token)
        """
        attempts = self._refresh_attempts
        return await _run_shielded(
            self._async_refresh_if_stale_locked(seen_access_token, attempts)
        )

    async def _async_refresh_if_stale_locked(
        self,
        seen_access_token: Optional[str],
        attempts: int,
    ) -> str:
        """
        Body of async_refresh_if_stale(), run in a shielded task.

        Args:
            seen_access_token: The access token the failed request used.
            attempts: _refresh_attempts when the caller arrived.

        Returns:
            An access token to retry the request with.
        """
        async with self._async_token_lock():
            current = self._adopt_newest_tokens()
            if current is None:
                raise self._no_tokens_error()
            if not is_token_expired(current) and current["access_token"] != seen_access_token:
                logger.info("Access token was already refreshed by another caller, reusing it")
                return current["access_token"]
            self._raise_if_refresh_failed_since(attempts, current)
            logger.info("Access token rejected or expired, refreshing (async)")
            await self._async_refresh_access_token()
            return self._current_access_token()

    def _attempt_refresh(self, refresh_token: Optional[str]) -> TokenData:
        """
        Run one refresh attempt and record its outcome; the caller holds the lock.

        Args:
            refresh_token: Refresh token to present, or None for the stored one.

        Returns:
            The new (or adopted) TokenData.

        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        """
        presented = self._presented_refresh_token(refresh_token)
        try:
            tokens = self._refresh_locked(refresh_token)
        except Exception as e:
            self._record_refresh_outcome(presented, e)
            raise
        self._record_refresh_outcome(presented, None)
        return tokens

    def _presented_refresh_token(self, refresh_token: Optional[str]) -> Optional[str]:
        """
        Name the refresh token an attempt is about to use, for its record.

        Args:
            refresh_token: Explicit refresh token, or None for the stored one.

        Returns:
            The explicit token, else the in-memory one (None if there is none).
        """
        if refresh_token is not None:
            return refresh_token
        tokens = self._tokens
        return tokens.get("refresh_token") if tokens else None

    def _record_refresh_outcome(
        self,
        refresh_token: Optional[str],
        error: Optional[Exception],
    ) -> None:
        """
        Count a finished refresh attempt and remember whether it failed.

        Call with the token lock held.

        Args:
            refresh_token: Refresh token that was current when it started.
            error: What the attempt raised, or None if it succeeded.
        """
        self._refresh_attempts += 1
        if error is None:
            self._last_refresh_failure = None
        else:
            self._last_refresh_failure = _RefreshFailure(
                self._refresh_attempts, refresh_token, error
            )

    def _raise_if_refresh_failed_since(self, attempts: int, current: TokenData) -> None:
        """
        Re-raise the error of a failed attempt that the caller waited for.

        Without this, every caller queued on the locks behind a failing
        refresh (an outage, a hung token endpoint) would repeat the whole
        refresh, retries included, one after another. Call with the token
        lock held.

        Args:
            attempts: _refresh_attempts when the caller arrived, before it
                waited for the locks.
            current: The current tokens.

        Raises:
            Exception: The failed attempt's error (a fresh WhoopTokenError
                for WhoopTokenError), if an attempt finished while the
                caller waited, the latest attempt failed and it used the
                current refresh token.
        """
        failure = self._last_refresh_failure
        if (
            failure is None
            or attempts == self._refresh_attempts
            or failure.attempt != self._refresh_attempts
            or failure.refresh_token != current.get("refresh_token")
        ):
            return
        logger.info("A token refresh this call waited for failed; reporting its error")
        error = failure.error
        if type(error) is WhoopTokenError:
            raise WhoopTokenError(error.message, status_code=error.status_code) from error
        raise error

    def _ensure_token_file_writable(
        self,
        consequence: str,
        error_type: Type[WhoopAuthError] = WhoopTokenError,
    ) -> None:
        """
        Fail before spending a refresh token or a sign-in if saving would fail.

        Args:
            consequence: Sentence saying what was not done, for the message.
            error_type: Exception class to raise.

        Raises:
            WhoopAuthError: ``error_type``, if the token file is a symbolic
                link or not a regular file, or cannot be written.
        """
        try:
            _check_token_file_writable(self.token_file)
        except OSError as e:
            raise error_type(
                f"Cannot save tokens to {self.token_file!r}: {e.strerror or e}. "
                f"{consequence} Point token_file at a writable regular file "
                "(not a symbolic link) and try again."
            ) from e

    def _refresh_locked(
        self,
        refresh_token: Optional[str],
        allow_recovery: bool = True,
    ) -> TokenData:
        """
        Refresh the tokens; the caller holds the token lock.

        Args:
            refresh_token: Refresh token to present, or None for the stored one.
            allow_recovery: Whether a rejected stored token may be retried
                once with a newer refresh token found in the token file.

        Returns:
            The new (or adopted) TokenData.

        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        """
        logger.info("Refreshing access token")

        from_storage = refresh_token is None
        presented = self._get_stored_refresh_token() if refresh_token is None else refresh_token
        self._ensure_token_file_writable("The refresh token was not sent, so it is still valid.")

        data = self._refresh_request_data(presented)
        attempt = 0
        while True:
            response = self._http_client.post(OAUTH_TOKEN_URL, data=data)
            if response.status_code < 500 or attempt >= MAX_RETRIES:
                break
            wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning(
                "Token refresh received %d, retrying in %.1fs (attempt %d/%d)",
                response.status_code, wait, attempt + 1, MAX_RETRIES
            )
            time.sleep(wait)
            attempt += 1

        if response.status_code != 200:
            if from_storage and _is_rejected_refresh_token(response):
                rotated = self._adopt_rotated_tokens(presented)
                if rotated is not None and not is_token_expired(rotated):
                    return rotated
                if rotated is not None and allow_recovery:
                    return self._refresh_locked(None, allow_recovery=False)
                self._end_authorization(response)
            raise self._refresh_failed_error(response)

        tokens = self._tokens_from_response(response, presented)
        self._store_tokens(tokens)

        logger.info(
            "Token refresh successful",
            extra={"expires_in": tokens["expires_in"]}
        )
        return tokens

    def _refresh_request_data(self, refresh_token: str) -> Dict[str, str]:
        """
        Build the form body of a refresh request.

        Args:
            refresh_token: Refresh token to present.

        Returns:
            Form fields for the token endpoint.
        """
        return {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(self.scope),
        }

    def _tokens_from_response(
        self,
        response: httpx.Response,
        presented_refresh_token: str,
    ) -> TokenData:
        """
        Build TokenData from a successful refresh response.

        Args:
            response: 200 response from the token endpoint.
            presented_refresh_token: Refresh token that was sent, kept if
                the response carries no new one.

        Returns:
            The new TokenData.

        Raises:
            WhoopTokenError: If the response body is not a valid token response.
        """
        try:
            token_response = response.json()
            access_token = token_response["access_token"]
            expires_in = token_response["expires_in"]
        except (ValueError, KeyError, TypeError) as e:
            raise WhoopTokenError(
                f"Token refresh returned an invalid response: {type(e).__name__}",
                status_code=response.status_code,
            ) from e

        if "refresh_token" not in token_response:
            logger.warning(
                "No refresh_token received from token exchange. "
                "Long-lived sessions will not be possible. "
                "Ensure the 'offline' scope is requested."
            )

        tokens: TokenData = {
            "access_token": access_token,
            "refresh_token": token_response.get(
                "refresh_token", presented_refresh_token
            ),
            "expires_in": expires_in,
            "expires_at": calculate_expiry(expires_in),
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(self.scope)),
        }
        return tokens

    def _refresh_failed_error(self, response: httpx.Response) -> WhoopTokenError:
        """
        Build the error for a failed refresh request.

        Args:
            response: Non-200 response from the token endpoint.

        Returns:
            WhoopTokenError with the sanitized response text.
        """
        return WhoopTokenError(
            f"Token refresh failed with status {response.status_code}: "
            f"{_sanitize_error_response(response.text)}",
            status_code=response.status_code,
        )

    def _set_tokens(self, tokens: Optional[TokenData]) -> None:
        """
        Replace the in-memory tokens (lock held) and invalidate unlocked loads.

        Args:
            tokens: New tokens, or None to forget them.
        """
        with self._tokens_guard:
            self._tokens = tokens
            self._tokens_generation += 1

    def _load_disk_tokens(self) -> Optional[TokenData]:
        """
        Load the token file, ignoring contents that were discarded.

        Returns:
            The token file's tokens, or None if there are none or they are
            the ones a failed delete left behind (see _clear_tokens_locked).
        """
        tokens = load_tokens(self.token_file)
        discarded = self._discarded_access_token
        if (
            tokens is not None
            and discarded is not None
            and tokens.get("access_token") == discarded
        ):
            logger.debug("Ignoring cleared tokens in a token file that could not be deleted")
            return None
        return tokens

    def _load_unlocked(self) -> Optional[TokenData]:
        """
        Load the token file without the token lock, caching it if still current.

        The loaded tokens are kept in memory only if no store or clear
        happened during the load, so a reader that raced logout() or a
        refresh can never bring back cleared or outdated tokens.

        Returns:
            The token file's tokens, or None.
        """
        generation = self._tokens_generation
        tokens = self._load_disk_tokens()
        if tokens is not None:
            with self._tokens_guard:
                if self._tokens_generation == generation:
                    self._tokens = tokens
        return tokens

    def _store_tokens(self, tokens: TokenData) -> None:
        """
        Keep tokens in memory and save them to the token file.

        Args:
            tokens: Tokens to store.

        Raises:
            WhoopTokenError: If the token file cannot be written. The tokens
                are kept in memory, so this handler keeps working.
        """
        self._set_tokens(tokens)
        self._authorization_ended = None
        self._discarded_access_token = None
        try:
            save_tokens(tokens, self.token_file)
        except OSError as e:
            raise WhoopTokenError(
                f"New tokens were issued but could not be saved to {self.token_file!r}: "
                f"{e.strerror or e}. They are kept in memory, so this handler keeps "
                "working, but other processes and later runs will find the previous "
                "tokens; fix the token file before this process exits."
            ) from e

    def _adopt_newest_tokens(self) -> Optional[TokenData]:
        """
        Make the newer of the in-memory and on-disk tokens current.

        Call with the token lock held. The token file wins unless the
        in-memory tokens expire later (e.g. a save failed after a refresh).

        Returns:
            The current tokens, or None if there are none.
        """
        disk = self._load_disk_tokens()
        memory = self._tokens
        if not _has_access_token(disk):
            disk = None
        if not _has_access_token(memory):
            memory = None

        newest: Optional[TokenData]
        if disk is None:
            newest = memory
        elif memory is None:
            newest = disk
        else:
            newest = disk if _expires_at(disk) >= _expires_at(memory) else memory
        self._set_tokens(newest)
        return newest

    def _adopt_rotated_tokens(self, rejected_refresh_token: str) -> Optional[TokenData]:
        """
        After a rejected refresh token, look for newer tokens on disk.

        Another process may have rotated the refresh token (and saved the
        result) after we read it. Call with the token lock held.

        Args:
            rejected_refresh_token: The refresh token WHOOP just rejected.

        Returns:
            The token file's tokens if they carry a different refresh token
            (they become current), otherwise None.
        """
        disk = self._load_disk_tokens()
        if disk is None or not _has_access_token(disk):
            return None
        refresh_token = disk.get("refresh_token")
        if not refresh_token or refresh_token == rejected_refresh_token:
            return None
        logger.info(
            "Refresh token was rotated by another process; using the newer "
            "tokens from the token file"
        )
        self._set_tokens(disk)
        return disk

    def _end_authorization(self, response: httpx.Response) -> NoReturn:
        """
        Forget tokens whose refresh token WHOOP rejected, then raise.

        Call with the token lock held. The error is remembered and raised
        again, instead of "No tokens available", by later calls (including
        callers that were waiting for the lock) until new tokens are stored
        or clear_tokens() is called.

        Args:
            response: The token endpoint's rejection.

        Raises:
            WhoopTokenError: Always, saying the authorization has ended.
        """
        detail = _sanitize_error_response(response.text)
        logger.error(
            "Refresh token rejected, authorization has ended; clearing stored tokens",
            extra={"status_code": response.status_code, "error": detail}
        )
        deleted = self._clear_tokens_locked()
        message = (
            f"{AUTHORIZATION_ENDED_MESSAGE} "
            f"(token endpoint returned {response.status_code}: {detail})"
        )
        if not deleted:
            message += (
                f" The token file {self.token_file!r} could not be deleted; delete "
                "it, or call authenticate(force=True)."
            )
        error = WhoopTokenError(message, status_code=response.status_code)
        self._authorization_ended = error
        raise error

    def _clear_tokens_locked(self) -> bool:
        """
        Clear in-memory tokens and delete the token file (lock held).

        If the file cannot be deleted (e.g. its directory is read-only), its
        contents are ignored by this handler from now on, so the cleared
        tokens do not come back from disk.

        Returns:
            True if no token file is left; False if it could not be deleted.
        """
        self._set_tokens(None)
        self._discarded_access_token = None
        if delete_tokens(self.token_file):
            return True
        # False means "no file" or "could not delete it": tell them apart
        leftover = load_tokens(self.token_file)
        if leftover is None:
            return True
        self._discarded_access_token = leftover.get("access_token") or None
        logger.error(
            "Token file could not be deleted; its tokens are ignored by this handler",
            extra={"filepath": self.token_file}
        )
        return False

    def _no_tokens_error(self) -> WhoopTokenError:
        """
        Build the error for "there are no tokens".

        Returns:
            A copy of the "authorization has ended" error if a rejected
            refresh token cleared the tokens, else the plain "No tokens
            available" error.
        """
        ended = self._authorization_ended
        if ended is not None:
            return WhoopTokenError(ended.message, status_code=ended.status_code)
        return WhoopTokenError(_NO_TOKENS_MESSAGE)

    def _current_access_token(self) -> str:
        """
        Return the in-memory access token.

        Returns:
            The current access token.

        Raises:
            WhoopTokenError: If no tokens are in memory.
        """
        tokens = self._tokens
        if tokens is None:
            raise self._no_tokens_error()
        return tokens["access_token"]

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
        tokens = self._load_disk_tokens()
        self._set_tokens(tokens)

        if tokens is None:
            raise self._no_tokens_error()

        refresh_token = tokens.get("refresh_token")
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
        - Automatic refresh when expired, under the thread and token file
          locks, after re-reading the token file (another process may
          already have refreshed). Callers that waited for a refresh that
          failed get its error instead of repeating it.

        Returns:
            Valid access token string.

        Raises:
            WhoopTokenError: If no tokens available or refresh fails.

        Example:
            >>> token = auth.get_valid_token()
            >>> response = httpx.get(
            ...     "https://api.prod.whoop.com/developer/v2/recovery",
            ...     headers={"Authorization": f"Bearer {token}"}
            ... )
        """
        # Read self._tokens once: another thread may clear it at any moment
        # (logout, or a refresh token WHOOP rejected).
        tokens = self._tokens
        if tokens is None:
            # Load tokens if not in memory
            tokens = self._load_unlocked()
            if tokens is None:
                raise self._no_tokens_error()

        # Fast path — no lock needed if token is valid
        if not is_token_expired(tokens):
            return tokens["access_token"]

        # Slow path — need to refresh, acquire locks
        attempts = self._refresh_attempts
        with self._token_lock():
            # Re-check after reloading (another thread/process may have refreshed)
            current = self._adopt_newest_tokens()
            if current is None:
                raise self._no_tokens_error()
            if is_token_expired(current):
                self._raise_if_refresh_failed_since(attempts, current)
                logger.info("Access token expired, refreshing")
                self.refresh_access_token()
            return self._current_access_token()

    async def async_get_valid_token(self) -> str:
        """
        Get a valid access token asynchronously, refreshing if needed.

        Uses an asyncio.Lock (bound lazily to the running loop) and the
        token file lock to prevent concurrent coroutines and processes from
        issuing multiple simultaneous refresh requests, without blocking
        the event loop. A refresh runs in its own task, so cancelling the
        caller cannot lose the rotated tokens.

        Returns:
            Valid access token string.

        Raises:
            WhoopTokenError: If no tokens available or refresh fails.
        """
        # Read self._tokens once: another thread or task may clear it at
        # any moment (logout, or a refresh token WHOOP rejected).
        tokens = self._tokens
        if tokens is None:
            # Load tokens if not in memory
            tokens = self._load_unlocked()
            if tokens is None:
                raise self._no_tokens_error()

        # Fast path — no lock needed if token is valid
        if not is_token_expired(tokens):
            return tokens["access_token"]

        # Slow path — need to refresh, acquire locks
        attempts = self._refresh_attempts
        return await _run_shielded(self._async_get_valid_token_locked(attempts))

    async def _async_get_valid_token_locked(self, attempts: int) -> str:
        """
        Slow path of async_get_valid_token(), run in a shielded task.

        Args:
            attempts: _refresh_attempts when the caller arrived.

        Returns:
            Valid access token string.
        """
        async with self._async_token_lock():
            # Re-check after reloading (another coroutine/process may have refreshed)
            current = self._adopt_newest_tokens()
            if current is None:
                raise self._no_tokens_error()
            if is_token_expired(current):
                self._raise_if_refresh_failed_since(attempts, current)
                logger.info("Access token expired, refreshing (async)")
                await self._async_refresh_access_token()
            return self._current_access_token()

    def _make_async_http_client(self) -> httpx.AsyncClient:
        """
        Create the short-lived async HTTP client used for one refresh.

        Returns:
            An httpx.AsyncClient using the handler's timeout.
        """
        return httpx.AsyncClient(timeout=self._timeout)

    async def _async_refresh_access_token(
        self,
        refresh_token: Optional[str] = None,
        *,
        _allow_recovery: bool = True,
    ) -> None:
        """
        Async version of refresh_access_token() using httpx.AsyncClient.

        Callers hold the async token lock (async_get_valid_token,
        async_refresh_if_stale). Backoff uses ``asyncio.sleep``, so the
        event loop is never blocked. The attempt is recorded like a sync
        one, and a rejected stored refresh token is handled as in
        refresh_access_token().

        Args:
            refresh_token: Refresh token to use. If None, uses stored token.

        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        """
        presented = self._presented_refresh_token(refresh_token)
        try:
            await self._async_refresh_locked(refresh_token, _allow_recovery)
        except Exception as e:
            self._record_refresh_outcome(presented, e)
            raise
        self._record_refresh_outcome(presented, None)

    async def _async_refresh_locked(
        self,
        refresh_token: Optional[str],
        allow_recovery: bool,
    ) -> None:
        """
        Async twin of _refresh_locked(); the caller holds the async token lock.

        Args:
            refresh_token: Refresh token to use. If None, uses stored token.
            allow_recovery: Whether a rejected stored token may be retried
                once with a newer refresh token found in the token file.

        Raises:
            WhoopTokenError: If refresh fails or no refresh token available.
        """
        logger.info("Refreshing access token (async)")

        from_storage = refresh_token is None
        presented = self._get_stored_refresh_token() if refresh_token is None else refresh_token
        self._ensure_token_file_writable("The refresh token was not sent, so it is still valid.")

        data = self._refresh_request_data(presented)
        async with self._make_async_http_client() as client:
            attempt = 0
            while True:
                response = await client.post(OAUTH_TOKEN_URL, data=data)
                if response.status_code < 500 or attempt >= MAX_RETRIES:
                    break
                wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Token refresh received %d, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, wait, attempt + 1, MAX_RETRIES
                )
                await asyncio.sleep(wait)
                attempt += 1

        if response.status_code != 200:
            if from_storage and _is_rejected_refresh_token(response):
                rotated = self._adopt_rotated_tokens(presented)
                if rotated is not None and not is_token_expired(rotated):
                    return
                if rotated is not None and allow_recovery:
                    await self._async_refresh_locked(None, allow_recovery=False)
                    return
                self._end_authorization(response)
            raise self._refresh_failed_error(response)

        tokens = self._tokens_from_response(response, presented)
        self._store_tokens(tokens)

        logger.info(
            "Async token refresh successful",
            extra={"expires_in": tokens["expires_in"]},
        )

    def clear_tokens(self) -> None:
        """
        Forget the stored tokens locally.

        Clears the in-memory tokens and deletes the token file, under the
        thread and token file locks so a concurrent refresh cannot write
        them back. WHOOP is not contacted. If the file cannot be deleted,
        an error is logged and this handler ignores its contents.

        Example:
            >>> auth.clear_tokens()
            >>> auth.has_valid_tokens()
            False
        """
        with self._token_lock():
            self._clear_tokens_locked()
            self._authorization_ended = None
        logger.info("Stored tokens cleared")

    async def async_clear_tokens(self) -> None:
        """
        Async twin of clear_tokens() that never blocks the event loop.

        Example:
            >>> await auth.async_clear_tokens()
        """
        async with self._async_token_lock():
            self._clear_tokens_locked()
            self._authorization_ended = None
        logger.info("Stored tokens cleared")

    def has_valid_tokens(self) -> bool:
        """
        Check if valid tokens are available.

        Returns:
            True if tokens exist and haven't expired (or can be refreshed),
            False otherwise.

        Example:
            >>> if auth.has_valid_tokens():
            ...     token = auth.get_valid_token()
            ... else:
            ...     auth.authorize()
        """
        # Read self._tokens once: another thread may clear it at any moment
        tokens = self._tokens
        if tokens is None:
            # Load tokens if not in memory
            tokens = self._load_unlocked()
            if tokens is None:
                return False

        # Check if we can refresh (have refresh token or token not expired)
        if is_token_expired(tokens):
            # Can only consider valid if we have a (non-empty) refresh token
            return bool(tokens.get("refresh_token"))

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

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Context manager exit - ensures cleanup."""
        self.close()

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"OAuthHandler("
            f"client_id='{self.client_id[:8]}...', "
            f"redirect_uri='{self.redirect_uri}')"
        )
