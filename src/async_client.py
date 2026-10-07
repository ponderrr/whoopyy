"""
Async Whoop API client for concurrent operations.

This module provides an async/await interface for the Whoop API
(WHOOP Developer API v2), enabling concurrent requests for better
performance when fetching multiple data types simultaneously.

Features:
    - Full async/await support with httpx.AsyncClient
    - Concurrent data fetching with asyncio.gather
    - Same API surface as sync WhoopClient
    - Async context manager for resource cleanup

Example:
    >>> import asyncio
    >>> from whoopyy.async_client import AsyncWhoopClient
    >>> 
    >>> async def fetch_data():
    ...     async with AsyncWhoopClient(
    ...         client_id="your_client_id",
    ...         client_secret="your_client_secret"
    ...     ) as client:
    ...         client.authenticate()  # Sync - browser interaction
    ...         
    ...         # Fetch multiple data types concurrently
    ...         profile, recoveries, sleeps = await asyncio.gather(
    ...             client.get_profile_basic(),
    ...             client.get_recovery_collection(limit=7),
    ...             client.get_sleep_collection(limit=7)
    ...         )
    ...         
    ...         return profile, recoveries, sleeps
    >>> 
    >>> profile, recoveries, sleeps = asyncio.run(fetch_data())

Note:
    Authentication is synchronous because it requires browser interaction.
    All API data fetching methods are async.
"""

import asyncio
import logging
import re
import uuid

from datetime import date, datetime
from types import TracebackType
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union

import httpx
import time

from . import __version__
from .auth import OAuthHandler
from .constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TOKEN_FILE,
    ENDPOINTS,
    MAX_PAGE_LIMIT,
)
from .exceptions import (
    WhoopAPIError,
    WhoopAuthError,
    WhoopNetworkError,
    WhoopNotFoundError,
    WhoopRateLimitError,
    WhoopValidationError,
)
from .logger import get_logger
from .models import (
    ActivityIdMapping,
    BodyMeasurement,
    Cycle,
    CycleCollection,
    Recovery,
    RecoveryCollection,
    Sleep,
    SleepCollection,
    UserProfileBasic,
    Workout,
    WorkoutCollection,
)
from .utils import (
    _sanitize_error_response,
    format_datetime,
    parse_rate_limit_reset,
)

logger = get_logger(__name__)

__all__ = ["AsyncWhoopClient"]

_DATE_ONLY_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
"""Matches a date-only string (YYYY-MM-DD), which WHOOP v2 rejects for start/end."""


class AsyncWhoopClient:
    """
    Async Python client for Whoop API.
    
    Provides async/await interface for concurrent API requests.
    Use with `async with` for automatic resource cleanup.
    
    Attributes:
        client_id: Whoop API client ID.
        client_secret: Whoop API client secret.
        auth: OAuth handler for token management.
    
    Example:
        >>> import asyncio
        >>> 
        >>> async def main():
        ...     async with AsyncWhoopClient(
        ...         client_id="your_client_id",
        ...         client_secret="your_client_secret"
        ...     ) as client:
        ...         client.authenticate()
        ...         
        ...         # Concurrent requests
        ...         results = await asyncio.gather(
        ...             client.get_recovery_collection(limit=7),
        ...             client.get_sleep_collection(limit=7),
        ...             client.get_cycle_collection(limit=7),
        ...         )
        ...         
        ...         recoveries, sleeps, cycles = results
        ...         print(f"Fetched {len(recoveries)} recoveries")
        >>> 
        >>> asyncio.run(main())
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
        Initialize async Whoop API client.
        
        Args:
            client_id: Whoop API client ID from developer portal.
            client_secret: Whoop API client secret from developer portal.
            redirect_uri: OAuth callback URI. Must match portal configuration.
            scope: List of OAuth scopes. Defaults to all available scopes.
            token_file: Path for storing authentication tokens.
            timeout: HTTP request timeout in seconds, for API and token
                     requests (connecting to the API is capped at 5 seconds).
            use_pkce: Send a PKCE (S256) challenge during authenticate().
                      Defaults to False.
        
        Raises:
            ValueError: If client_id or client_secret is empty.
        
        Example:
            >>> client = AsyncWhoopClient(
            ...     client_id=os.getenv("WHOOP_CLIENT_ID"),
            ...     client_secret=os.getenv("WHOOP_CLIENT_SECRET"),
            ... )
        """
        # Guard clauses
        if not client_id:
            raise ValueError("client_id is required")
        if not client_secret:
            raise ValueError("client_secret is required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        
        # Initialize OAuth handler (sync - shares tokens with sync client)
        self.auth = OAuthHandler(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            token_file=token_file,
            timeout=timeout,
            use_pkce=use_pkce,
        )
        
        # Async HTTP client for API requests with connection pooling
        self._http_client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            # Honour the caller's timeout, with connecting capped at 5s. None
            # (accepted before) removes only the read, write and pool limits.
            timeout=httpx.Timeout(
                timeout, connect=5.0 if timeout is None else min(5.0, timeout)
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"whoopyy/{__version__}",
            },
        )
        
        self._authenticated = False
        self._cache: Dict[str, tuple[Any, float]] = {}  # {key: (value, expiry)}

        logger.info(
            "AsyncWhoopClient initialized",
            extra={"client_id": client_id[:8] + "..."}
        )
    
    # =========================================================================
    # Authentication (Sync - requires browser interaction)
    # =========================================================================
    
    def authenticate(self, auto_open_browser: bool = True, force: bool = False) -> None:
        """
        Perform OAuth authentication flow (synchronous).
        
        Note: Authentication is synchronous because it requires
        browser interaction. Use before async operations.

        If usable tokens are already stored (an unexpired access token, or a
        refresh token), the browser flow is skipped unless ``force`` is
        True. When WHOOP rejects the stored refresh token, the SDK clears the
        stored tokens and raises WhoopTokenError, so calling authenticate()
        afterwards runs the browser flow again.
        
        Args:
            auto_open_browser: Whether to automatically open browser.
            force: Run the browser flow even if tokens are already stored,
                   e.g. to switch accounts or re-consent to new scopes.
        
        Raises:
            WhoopAuthError: If authentication fails.
        
        Example:
            >>> async with AsyncWhoopClient(...) as client:
            ...     client.authenticate()  # Sync call
            ...     data = await client.get_recovery_collection()  # Async
        """
        logger.info("Starting authentication")
        
        # Check if we already have valid tokens
        if not force and self.auth.has_valid_tokens():
            logger.info("Found existing valid tokens, skipping OAuth flow")
            self._authenticated = True
            return

        if force:
            logger.info("Forced re-authentication, running OAuth flow")
        
        self.auth.authorize(auto_open_browser=auto_open_browser)
        self._authenticated = True
        # Cached responses may belong to a previously authorized account
        self._cache.clear()
        
        logger.info("Authentication successful")
    
    def is_authenticated(self) -> bool:
        """
        Check if client has valid authentication.

        Reflects the stored tokens, not whether authenticate() was called:
        after logout(), revoke_access() or a rejected refresh token (which
        clears the stored tokens) this returns False.
        
        Returns:
            True if authenticated with valid (or refreshable) tokens.
        """
        return self.auth.has_valid_tokens()

    async def logout(self) -> None:
        """
        Sign out locally: forget the stored tokens and cached responses.

        Clears the in-memory tokens, deletes the token file at
        ``auth.token_file`` and clears the response cache, so
        ``is_authenticated()`` returns False and the next ``authenticate()``
        runs the OAuth flow again. WHOOP is not contacted, so the grant stays
        valid on WHOOP's side; use ``revoke_access()`` to revoke it remotely.

        Example:
            >>> await client.logout()
            >>> client.authenticate()  # opens the browser again
        """
        await self._forget_session()
        logger.info("Logged out")

    async def _forget_session(self) -> None:
        """Clear stored tokens (memory and file), auth state and the cache."""
        await self.auth.async_clear_tokens()
        self._authenticated = False
        self._cache.clear()
    
    # =========================================================================
    # Internal Request Methods
    # =========================================================================
    
    async def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get request headers with valid access token (non-blocking).

        Returns:
            Headers dict with Authorization header.
        """
        token = await self.auth.async_get_valid_token()
        return {"Authorization": f"Bearer {token}"}
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        _retry: bool = False,
    ) -> Dict[str, Any]:
        """
        Make async authenticated API request.
        
        Args:
            method: HTTP method (GET, POST, DELETE).
            endpoint: API endpoint path (e.g., "/developer/v2/recovery").
            params: Query parameters.
            data: JSON body data.
        
        Returns:
            Response JSON data.
        
        Raises:
            WhoopAPIError: If request fails.
            WhoopRateLimitError: If rate limited (429).
            WhoopAuthError: If authentication fails (401).
        """
        try:
            headers = await self._get_auth_headers()
            # Remember which token this request used: on a 401, refresh only
            # if no other coroutine or process has replaced it already.
            used_token = headers["Authorization"].partition(" ")[2]

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Making async API request",
                    extra={
                        "method": method,
                        "endpoint": endpoint,
                    }
                )
            
            start = time.perf_counter()
            response = await self._http_client.request(
                method=method,
                url=endpoint,
                params=params,
                json=data,
                headers=headers,
            )
            elapsed = time.perf_counter() - start
            logger.debug(
                "%s %s → %d (%.0fms)",
                method.upper(), endpoint, response.status_code, elapsed * 1000,
            )

            # Track rate limit headers
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                try:
                    remaining_int = int(str(remaining))
                    if remaining_int <= 5:
                        logger.warning("API rate limit low: %d requests remaining", remaining_int)
                except (ValueError, TypeError):
                    pass

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = parse_rate_limit_reset(response.headers)

                if not _retry:
                    logger.warning("Rate limited, retrying after %ds", retry_after)
                    await asyncio.sleep(min(retry_after, 120))  # Cap at 2 minutes
                    return await self._request(method, endpoint, params=params, data=data, _retry=True)

                logger.warning("Rate limit exceeded after retry")
                raise WhoopRateLimitError(
                    "Rate limit exceeded. Please wait before retrying.",
                    retry_after=retry_after,
                    status_code=429,
                )
            
            # Handle auth errors
            if response.status_code == 401:
                if _retry:
                    raise WhoopAuthError(
                        f"Authentication failed after token refresh. "
                        f"Status: 401. Response: {_sanitize_error_response(response.text)}",
                        status_code=401,
                    )
                # Refresh (unless someone already did) without blocking the
                # event loop, then retry once
                logger.warning("Authentication failed - refreshing token and retrying")
                await self.auth.async_refresh_if_stale(used_token)
                return await self._request(method, endpoint, params=params, data=data, _retry=True)

            # Handle not found errors
            if response.status_code == 404:
                logger.error(
                    "Resource not found",
                    extra={"url": endpoint, "error": _sanitize_error_response(response.text)}
                )
                raise WhoopNotFoundError(
                    f"Resource not found: {endpoint}. Response: {_sanitize_error_response(response.text)}",
                    status_code=404,
                )

            # Handle validation errors
            if response.status_code == 400:
                raise WhoopValidationError(
                    f"Invalid request: {_sanitize_error_response(response.text)}",
                    status_code=400,
                )
            
            # Handle other HTTP errors
            response.raise_for_status()
            
            # Return empty dict for 204 No Content
            if response.status_code == 204:
                return {}
            
            result: Dict[str, Any] = response.json()
            return result

        except httpx.HTTPStatusError as e:
            logger.error(
                "Async API request failed",
                extra={
                    "status_code": e.response.status_code,
                    "error": _sanitize_error_response(e.response.text),
                }
            )
            raise WhoopAPIError(
                f"API request failed: {_sanitize_error_response(e.response.text)}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            logger.error(
                "Async request error",
                extra={"error": str(e)}
            )
            raise WhoopNetworkError(str(e)) from e
    
    def _cache_get(self, key: str) -> Any:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            del self._cache[key]
        return None

    def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL in seconds."""
        self._cache[key] = (value, time.time() + ttl)

    def _format_date_param(
        self,
        value: Optional[Union[datetime, date, str]]
    ) -> Optional[str]:
        """
        Format date parameter for API request.

        WHOOP v2 declares ``start`` and ``end`` as ``date-time`` and rejects
        date-only strings, so a string of exactly ``YYYY-MM-DD`` is expanded
        to midnight UTC (``YYYY-MM-DDT00:00:00.000Z``). Naive datetimes and
        ``date`` objects are treated as UTC. Any other string is passed
        through unchanged.

        Args:
            value: Date as datetime, date, or ISO string.

        Returns:
            ISO 8601 formatted string or None.

        Example:
            >>> client._format_date_param("2024-01-15")
            '2024-01-15T00:00:00.000Z'
        """
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return format_datetime(value)
        elif isinstance(value, date):
            return format_datetime(datetime.combine(value, datetime.min.time()))
        elif _DATE_ONLY_PATTERN.fullmatch(value):
            return f"{value}T00:00:00.000Z"
        else:
            return value  # Assume already formatted date-time string

    def _build_collection_params(
        self,
        limit: int,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        next_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build query parameters for paginated collection endpoints."""
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        return params

    # =========================================================================
    # User Profile Methods
    # =========================================================================
    
    async def get_profile_basic(self) -> UserProfileBasic:
        """
        Get basic user profile information.
        
        Returns:
            UserProfileBasic with user_id, email, first_name, last_name.
        
        Example:
            >>> profile = await client.get_profile_basic()
            >>> print(f"Hello, {profile.first_name}!")
        """
        cached = self._cache_get("profile_basic")
        if isinstance(cached, UserProfileBasic):
            return cached
        logger.info("Fetching basic profile")

        data = await self._request("GET", ENDPOINTS["user_profile_basic"])
        profile = UserProfileBasic(**data)
        self._cache_set("profile_basic", profile, 3600)  # Cache 1 hour
        return profile

    async def get_body_measurement(self) -> BodyMeasurement:
        """
        Get user body measurements.

        Returns:
            BodyMeasurement with height, weight, and max heart rate.
        """
        cached = self._cache_get("body_measurement")
        if isinstance(cached, BodyMeasurement):
            return cached
        logger.info("Fetching body measurements")

        data = await self._request("GET", ENDPOINTS["user_body_measurement"])
        measurement = BodyMeasurement(**data)
        self._cache_set("body_measurement", measurement, 86400)  # Cache 24 hours
        return measurement
    
    # =========================================================================
    # Recovery Methods
    # =========================================================================
    
    async def get_recovery_for_cycle(self, cycle_id: int) -> Recovery:
        """
        Get recovery record for a specific cycle.
        
        Args:
            cycle_id: Cycle ID to get recovery for.
        
        Returns:
            Recovery record with score and metadata.

        Raises:
            WhoopAPIError: If request fails or recovery not found.
            ValueError: If cycle_id is invalid.
        """
        if cycle_id <= 0:
            raise ValueError(f"Invalid cycle_id: {cycle_id}")
        
        logger.info(
            "Fetching recovery for cycle",
            extra={"cycle_id": cycle_id}
        )
        
        endpoint = ENDPOINTS["recovery_for_cycle"].format(cycle_id=cycle_id)
        data = await self._request("GET", endpoint)
        return Recovery(**data)
    
    async def get_recovery_collection(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        limit: int = 25,
        next_token: Optional[str] = None,
    ) -> RecoveryCollection:
        """
        Get collection of recovery records with pagination.
        
        Args:
            start: Start date/datetime for filtering (inclusive).
            end: End date/datetime for filtering (exclusive).
            limit: Number of records per page (1-25).
            next_token: Pagination token from previous response.
        
        Returns:
            RecoveryCollection with records and optional next_token.
        
        Example:
            >>> recoveries = await client.get_recovery_collection(limit=7)
            >>> for recovery in recoveries.records:
            ...     print(recovery.score.recovery_score)
        """
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise WhoopValidationError(
                f"limit must be 1-{MAX_PAGE_LIMIT}, got {limit}",
                status_code=400,
            )
        
        logger.info(
            "Fetching recovery collection",
            extra={"limit": limit}
        )

        params = self._build_collection_params(limit, start, end, next_token)

        data = await self._request("GET", ENDPOINTS["recovery_collection"], params=params)
        return RecoveryCollection(**data)
    
    async def get_all_recovery(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Recovery]:
        """
        Get all recovery records with automatic pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            max_records: Maximum total records to fetch.
        
        Returns:
            List of all Recovery records.
        """
        logger.info(
            "Fetching all recovery records",
            extra={"max_records": max_records}
        )
        
        all_records: List[Recovery] = []
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_recovery_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            all_records.extend(collection.records)
            
            if max_records and len(all_records) >= max_records:
                return all_records[:max_records]
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
        
        return all_records
    
    async def iter_recovery(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> AsyncGenerator[Recovery, None]:
        """
        Async iterate over all recovery records.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
        
        Yields:
            Recovery records one at a time.
        
        Example:
            >>> async for recovery in client.iter_recovery():
            ...     print(recovery.score.recovery_score)
        """
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_recovery_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            for record in collection.records:
                yield record
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Sleep Methods
    # =========================================================================
    
    async def get_sleep(self, sleep_id: Union[str, uuid.UUID]) -> Sleep:
        """
        Get specific sleep record by ID.

        Args:
            sleep_id: Sleep record UUID, as a string or ``uuid.UUID``. To
                look up the UUID for a legacy v1 integer sleep ID, use
                get_activity_mapping().

        Returns:
            Sleep record with score and metadata.

        Raises:
            WhoopAPIError: If request fails or sleep not found.
            ValueError: If sleep_id is empty or is a legacy v1 integer ID.

        Example:
            >>> sleep = await client.get_sleep("ecfc6a15-4661-442f-a9a4-f160dd7afae8")
            >>> print(f"Duration: {sleep.duration_hours}h")
        """
        if isinstance(sleep_id, uuid.UUID):
            sleep_id = str(sleep_id)
        if isinstance(sleep_id, int) or (
            isinstance(sleep_id, str) and sleep_id.strip().isdigit()
        ):
            raise ValueError(
                f"Invalid sleep_id: {sleep_id!r}. WHOOP v2 sleep IDs are UUID "
                "strings; use get_activity_mapping() to look up the UUID for a "
                "legacy v1 integer ID."
            )
        if not isinstance(sleep_id, str) or not sleep_id.strip():
            raise ValueError(f"Invalid sleep_id: {sleep_id!r}")
        
        logger.info(
            "Fetching sleep",
            extra={"sleep_id": sleep_id}
        )
        
        endpoint = ENDPOINTS["sleep_single"].format(sleep_id=sleep_id)
        data = await self._request("GET", endpoint)
        return Sleep(**data)
    
    async def get_sleep_for_cycle(self, cycle_id: int) -> Sleep:
        """
        Get the sleep record for a specific cycle.

        Args:
            cycle_id: Cycle ID to get sleep for.

        Returns:
            Sleep record with score and metadata.

        Raises:
            WhoopAPIError: If request fails or sleep not found.
            ValueError: If cycle_id is invalid.

        Example:
            >>> sleep = await client.get_sleep_for_cycle(93845)
            >>> print(f"Duration: {sleep.duration_hours}h")
        """
        if cycle_id <= 0:
            raise ValueError(f"Invalid cycle_id: {cycle_id}")

        logger.info(
            "Fetching sleep for cycle",
            extra={"cycle_id": cycle_id}
        )

        endpoint = ENDPOINTS["sleep_for_cycle"].format(cycle_id=cycle_id)
        data = await self._request("GET", endpoint)
        return Sleep(**data)

    async def get_sleep_collection(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        limit: int = 25,
        next_token: Optional[str] = None,
    ) -> SleepCollection:
        """
        Get collection of sleep records with pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            limit: Number of records per page (1-25).
            next_token: Pagination token.
        
        Returns:
            SleepCollection with records and optional next_token.
        """
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise WhoopValidationError(
                f"limit must be 1-{MAX_PAGE_LIMIT}, got {limit}",
                status_code=400,
            )
        
        logger.info(
            "Fetching sleep collection",
            extra={"limit": limit}
        )

        params = self._build_collection_params(limit, start, end, next_token)

        data = await self._request("GET", ENDPOINTS["sleep_collection"], params=params)
        return SleepCollection(**data)
    
    async def get_all_sleep(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Sleep]:
        """Get all sleep records with automatic pagination."""
        logger.info("Fetching all sleep records")
        
        all_records: List[Sleep] = []
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_sleep_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            all_records.extend(collection.records)
            
            if max_records and len(all_records) >= max_records:
                return all_records[:max_records]
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
        
        return all_records
    
    async def iter_sleep(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> AsyncGenerator[Sleep, None]:
        """Async iterate over all sleep records."""
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_sleep_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            for record in collection.records:
                yield record
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Cycle Methods
    # =========================================================================
    
    async def get_cycle(self, cycle_id: int) -> Cycle:
        """
        Get specific physiological cycle by ID.
        
        Args:
            cycle_id: Cycle ID.
        
        Returns:
            Cycle record with strain score and metadata.
        """
        if cycle_id <= 0:
            raise ValueError(f"Invalid cycle_id: {cycle_id}")
        
        logger.info(
            "Fetching cycle",
            extra={"cycle_id": cycle_id}
        )
        
        endpoint = ENDPOINTS["cycle_single"].format(cycle_id=cycle_id)
        data = await self._request("GET", endpoint)
        return Cycle(**data)
    
    async def get_cycle_collection(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        limit: int = 25,
        next_token: Optional[str] = None,
    ) -> CycleCollection:
        """
        Get collection of physiological cycles with pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            limit: Number of records per page (1-25).
            next_token: Pagination token.
        
        Returns:
            CycleCollection with records and optional next_token.
        """
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise WhoopValidationError(
                f"limit must be 1-{MAX_PAGE_LIMIT}, got {limit}",
                status_code=400,
            )
        
        logger.info(
            "Fetching cycle collection",
            extra={"limit": limit}
        )

        params = self._build_collection_params(limit, start, end, next_token)

        data = await self._request("GET", ENDPOINTS["cycle_collection"], params=params)
        return CycleCollection(**data)
    
    async def get_all_cycles(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Cycle]:
        """Get all cycle records with automatic pagination."""
        logger.info("Fetching all cycle records")
        
        all_records: List[Cycle] = []
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_cycle_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            all_records.extend(collection.records)
            
            if max_records and len(all_records) >= max_records:
                return all_records[:max_records]
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
        
        return all_records
    
    async def iter_cycles(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> AsyncGenerator[Cycle, None]:
        """Async iterate over all cycle records."""
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_cycle_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            for record in collection.records:
                yield record
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Workout Methods
    # =========================================================================
    
    async def get_workout(self, workout_id: Union[str, uuid.UUID]) -> Workout:
        """
        Get specific workout by ID.

        Args:
            workout_id: Workout UUID, as a string or ``uuid.UUID``. To
                look up the UUID for a legacy v1 integer workout ID, use
                get_activity_mapping().

        Returns:
            Workout record with score and metadata.

        Raises:
            WhoopAPIError: If request fails or workout not found.
            ValueError: If workout_id is empty or is a legacy v1 integer ID.

        Example:
            >>> workout = await client.get_workout("ecfc6a15-4661-442f-a9a4-f160dd7afae8")
            >>> print(f"{workout.sport_name}: {workout.duration_minutes:.0f}min")
        """
        if isinstance(workout_id, uuid.UUID):
            workout_id = str(workout_id)
        if isinstance(workout_id, int) or (
            isinstance(workout_id, str) and workout_id.strip().isdigit()
        ):
            raise ValueError(
                f"Invalid workout_id: {workout_id!r}. WHOOP v2 workout IDs are "
                "UUID strings; use get_activity_mapping() to look up the UUID "
                "for a legacy v1 integer ID."
            )
        if not isinstance(workout_id, str) or not workout_id.strip():
            raise ValueError(f"Invalid workout_id: {workout_id!r}")
        
        logger.info(
            "Fetching workout",
            extra={"workout_id": workout_id}
        )
        
        endpoint = ENDPOINTS["workout_single"].format(workout_id=workout_id)
        data = await self._request("GET", endpoint)
        return Workout(**data)
    
    async def get_workout_collection(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        limit: int = 25,
        next_token: Optional[str] = None,
    ) -> WorkoutCollection:
        """
        Get collection of workouts with pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            limit: Number of records per page (1-25).
            next_token: Pagination token.
        
        Returns:
            WorkoutCollection with records and optional next_token.
        """
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise WhoopValidationError(
                f"limit must be 1-{MAX_PAGE_LIMIT}, got {limit}",
                status_code=400,
            )
        
        logger.info(
            "Fetching workout collection",
            extra={"limit": limit}
        )

        params = self._build_collection_params(limit, start, end, next_token)

        data = await self._request("GET", ENDPOINTS["workout_collection"], params=params)
        return WorkoutCollection(**data)
    
    async def get_all_workouts(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Workout]:
        """Get all workout records with automatic pagination."""
        logger.info("Fetching all workout records")
        
        all_records: List[Workout] = []
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_workout_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            all_records.extend(collection.records)
            
            if max_records and len(all_records) >= max_records:
                return all_records[:max_records]
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
        
        return all_records
    
    async def iter_workouts(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> AsyncGenerator[Workout, None]:
        """Async iterate over all workout records."""
        next_token: Optional[str] = None
        
        while True:
            collection = await self.get_workout_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            for record in collection.records:
                yield record
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Concurrent Fetching
    # =========================================================================

    async def fetch_all(
        self,
        *,
        recovery: bool = True,
        sleep: bool = True,
        cycles: bool = True,
        workouts: bool = True,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Fetch multiple data types concurrently using asyncio.gather().

        Returns a dict with keys: 'recovery', 'sleep', 'cycles', 'workouts'.
        Only fetches the types requested (all True by default).
        Failed fetches return None for that key.

        Example:
            async with AsyncWhoopClient(client_id, client_secret) as client:
                data = await client.fetch_all(limit=7)
                print(data["recovery"].records[0].score.recovery_score)
        """
        tasks: Dict[str, Any] = {}
        if recovery:
            tasks["recovery"] = self.get_recovery_collection(limit=limit)
        if sleep:
            tasks["sleep"] = self.get_sleep_collection(limit=limit)
        if cycles:
            tasks["cycles"] = self.get_cycle_collection(limit=limit)
        if workouts:
            tasks["workouts"] = self.get_workout_collection(limit=limit)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        output: Dict[str, Any] = {}
        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error("fetch_all: %s failed: %s", key, result)
                output[key] = None
            else:
                output[key] = result
        return output

    async def fetch_dashboard(self) -> Dict[str, Any]:
        """
        Fetch the most recent record of each type concurrently.

        Optimized for dashboard display — returns single latest records.
        Returns: {'profile', 'recovery', 'sleep', 'cycle', 'workout'}
        — each a single model instance or None.
        """
        results = await asyncio.gather(
            self.get_profile_basic(),
            self.get_recovery_collection(limit=1),
            self.get_sleep_collection(limit=1),
            self.get_cycle_collection(limit=1),
            self.get_workout_collection(limit=1),
            return_exceptions=True,
        )
        labels = ["profile", "recovery", "sleep", "cycle", "workout"]
        output: Dict[str, Any] = {}
        for label, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.warning("fetch_dashboard: %s unavailable: %s", label, result)
                output[label] = None
            elif hasattr(result, "records"):
                output[label] = result.records[0] if result.records else None
            else:
                output[label] = result
        return output

    # =========================================================================
    # Activity ID Mapping
    # =========================================================================
    
    async def get_activity_mapping(self, activity_v1_id: int) -> ActivityIdMapping:
        """
        Look up the v2 UUID for a legacy v1 sleep or workout ID.

        WHOOP v2 identifies sleeps and workouts by UUID string, while the
        retired v1 API used integers. Use this to migrate stored v1 IDs.

        Args:
            activity_v1_id: Legacy v1 integer ID of a sleep or workout.

        Returns:
            ActivityIdMapping with the activity's v2 UUID (v2_activity_id).

        Raises:
            WhoopNotFoundError: If no mapping exists for the ID.
            WhoopAPIError: If request fails.
            ValueError: If activity_v1_id is invalid.

        Example:
            >>> mapping = await client.get_activity_mapping(12345678)
            >>> print(f"v2 ID: {mapping.v2_activity_id}")
            >>> sleep = await client.get_sleep(mapping.v2_activity_id)
        """
        if activity_v1_id <= 0:
            raise ValueError(f"Invalid activity_v1_id: {activity_v1_id}")
        
        logger.info(
            "Fetching activity ID mapping",
            extra={"activity_v1_id": activity_v1_id}
        )

        endpoint = ENDPOINTS["activity_mapping"].format(activity_v1_id=activity_v1_id)
        data = await self._request("GET", endpoint)
        return ActivityIdMapping(**data)

    # =========================================================================
    # Access Management
    # =========================================================================

    async def revoke_access(self) -> None:
        """
        Revoke the user's OAuth access for this application.

        Sends ``DELETE /developer/v2/user/access`` with the current access
        token. On success this will:
        - Invalidate the access token granted by the user
        - Stop webhook delivery for this user if configured
        - Clear the in-memory tokens, delete the token file at
          ``auth.token_file`` and clear the response cache, so
          ``is_authenticated()`` returns False and the next
          ``authenticate()`` runs the OAuth flow again

        If the request fails, the tokens, token file and cache are kept.

        Raises:
            WhoopAuthError: If not authenticated or authorization fails.
            WhoopRateLimitError: If rate limited (429).
            WhoopAPIError: If the revocation request fails.

        Example:
            >>> await client.revoke_access()
            >>> # User must re-authenticate to continue
        """
        logger.info("Revoking access token")

        await self._request("DELETE", ENDPOINTS["user_access"])

        # The revoked tokens would otherwise be reloaded from disk by
        # has_valid_tokens()/get_valid_token(), and cached responses belong
        # to the user who just revoked access.
        await self._forget_session()

        logger.info("Access token revoked")
    
    # =========================================================================
    # Lifecycle Management
    # =========================================================================
    
    async def close(self) -> None:
        """
        Close HTTP client and release resources.
        
        Must be called when done, or use `async with` for automatic cleanup.
        """
        await self._http_client.aclose()
        self.auth.close()
        logger.info("AsyncWhoopClient closed")
    
    async def __aenter__(self) -> "AsyncWhoopClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"AsyncWhoopClient("
            f"client_id='{self.client_id[:8]}...', "
            f"authenticated={self._authenticated})"
        )
