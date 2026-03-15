"""
Async Whoop API client for concurrent operations.

This module provides an async/await interface for the Whoop API,
enabling concurrent requests for better performance when fetching
multiple data types simultaneously.

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

from datetime import date, datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx

from .auth import OAuthHandler
from .constants import (
    API_BASE_URL,
    AUTH_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TOKEN_FILE,
    ENDPOINTS,
    MAX_PAGE_LIMIT,
)
from .exceptions import (
    WhoopAPIError,
    WhoopAuthError,
    WhoopRateLimitError,
    WhoopValidationError,
)
from .logger import get_logger
from .models import (
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
from .utils import format_datetime

logger = get_logger(__name__)


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
    ) -> None:
        """
        Initialize async Whoop API client.
        
        Args:
            client_id: Whoop API client ID from developer portal.
            client_secret: Whoop API client secret from developer portal.
            redirect_uri: OAuth callback URI. Must match portal configuration.
            scope: List of OAuth scopes. Defaults to all available scopes.
            token_file: Path for storing authentication tokens.
            timeout: HTTP request timeout in seconds.
        
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
        )
        
        # Async HTTP client for API requests
        self._http_client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        
        self._authenticated = False
        
        logger.info(
            "AsyncWhoopClient initialized",
            extra={"client_id": client_id[:8] + "..."}
        )
    
    # =========================================================================
    # Authentication (Sync - requires browser interaction)
    # =========================================================================
    
    def authenticate(self, auto_open_browser: bool = True) -> None:
        """
        Perform OAuth authentication flow (synchronous).
        
        Note: Authentication is synchronous because it requires
        browser interaction. Use before async operations.
        
        Args:
            auto_open_browser: Whether to automatically open browser.
        
        Raises:
            WhoopAuthError: If authentication fails.
        
        Example:
            >>> async with AsyncWhoopClient(...) as client:
            ...     client.authenticate()  # Sync call
            ...     data = await client.get_recovery_collection()  # Async
        """
        logger.info("Starting authentication")
        
        # Check if we already have valid tokens
        if self.auth.has_valid_tokens():
            logger.info("Found existing valid tokens, skipping OAuth flow")
            self._authenticated = True
            return
        
        self.auth.authorize(auto_open_browser=auto_open_browser)
        self._authenticated = True
        
        logger.info("Authentication successful")
    
    def is_authenticated(self) -> bool:
        """
        Check if client has valid authentication.
        
        Returns:
            True if authenticated with valid tokens.
        """
        return self._authenticated or self.auth.has_valid_tokens()
    
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
    ) -> Dict[str, Any]:
        """
        Make async authenticated API request.
        
        Args:
            method: HTTP method (GET, POST, DELETE).
            endpoint: API endpoint path.
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

            logger.debug(
                "Making async API request",
                extra={
                    "method": method,
                    "endpoint": endpoint,
                }
            )
            
            response = await self._http_client.request(
                method=method,
                url=endpoint,
                params=params,
                json=data,
                headers=headers,
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After", "60")
                try:
                    retry_after = int(retry_after_header)
                except ValueError:
                    retry_after = 60
                
                logger.warning(
                    "Rate limit exceeded",
                    extra={"retry_after": retry_after}
                )
                raise WhoopRateLimitError(
                    "Rate limit exceeded. Please wait before retrying.",
                    retry_after=retry_after,
                    status_code=429,
                )
            
            # Handle auth errors
            if response.status_code == 401:
                raise WhoopAuthError(
                    "Authentication failed. Please re-authenticate.",
                    status_code=401,
                )
            
            # Handle validation errors
            if response.status_code == 400:
                raise WhoopValidationError(
                    f"Invalid request: {response.text}",
                    status_code=400,
                )
            
            # Handle other HTTP errors
            response.raise_for_status()
            
            # Return empty dict for 204 No Content
            if response.status_code == 204:
                return {}
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "Async API request failed",
                extra={
                    "status_code": e.response.status_code,
                    "error": e.response.text,
                }
            )
            raise WhoopAPIError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )
        except (WhoopRateLimitError, WhoopAuthError, WhoopValidationError):
            raise
        except httpx.RequestError as e:
            logger.error(
                "Async request error",
                extra={"error": str(e)}
            )
            raise WhoopAPIError(f"Request failed: {e}")
    
    def _format_date_param(
        self,
        value: Optional[Union[datetime, date, str]]
    ) -> Optional[str]:
        """Format date parameter for API request."""
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return format_datetime(value)
        elif isinstance(value, date):
            return format_datetime(datetime.combine(value, datetime.min.time()))
        else:
            return value
    
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
        logger.info("Fetching basic profile")
        
        data = await self._request("GET", ENDPOINTS["user_profile_basic"])
        return UserProfileBasic(**data)
    
    async def get_body_measurement(self) -> BodyMeasurement:
        """
        Get user body measurements.
        
        Returns:
            BodyMeasurement with height, weight, and max heart rate.
        """
        logger.info("Fetching body measurements")
        
        data = await self._request("GET", ENDPOINTS["user_body_measurement"])
        return BodyMeasurement(**data)
    
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
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            limit: Number of records per page (1-50).
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
        
        params: Dict[str, Any] = {"limit": limit}
        
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        
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
    
    async def get_sleep(self, sleep_id: int) -> Sleep:
        """
        Get specific sleep record by ID.
        
        Args:
            sleep_id: Sleep record ID.
        
        Returns:
            Sleep record with score and metadata.
        """
        if sleep_id <= 0:
            raise ValueError(f"Invalid sleep_id: {sleep_id}")
        
        logger.info(
            "Fetching sleep",
            extra={"sleep_id": sleep_id}
        )
        
        endpoint = ENDPOINTS["sleep_single"].format(sleep_id=sleep_id)
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
            limit: Number of records per page (1-50).
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
        
        params: Dict[str, Any] = {"limit": limit}
        
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        
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
            limit: Number of records per page (1-50).
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
        
        params: Dict[str, Any] = {"limit": limit}
        
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        
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
    
    async def get_workout(self, workout_id: int) -> Workout:
        """
        Get specific workout by ID.
        
        Args:
            workout_id: Workout ID.
        
        Returns:
            Workout record with score and metadata.
        """
        if workout_id <= 0:
            raise ValueError(f"Invalid workout_id: {workout_id}")
        
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
            limit: Number of records per page (1-50).
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
        
        params: Dict[str, Any] = {"limit": limit}
        
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        
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
    # Access Management
    # =========================================================================
    
    async def revoke_access(self) -> None:
        """
        Revoke current access token.
        
        This will invalidate the token and stop webhook delivery.
        """
        logger.info("Revoking access token")

        token = await self.auth.async_get_valid_token()
        revoke_url = f"{AUTH_BASE_URL}/oauth2/revoke"

        response = await self._http_client.post(
            revoke_url,
            data={"token": token},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code != 200:
            raise WhoopAuthError(
                f"Token revocation failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        self.auth._tokens = None
        self._authenticated = False

        logger.info("Access token revoked")
        
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
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"AsyncWhoopClient("
            f"client_id='{self.client_id[:8]}...', "
            f"authenticated={self._authenticated})"
        )
