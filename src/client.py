"""
Main Whoop API client.

This module provides the primary interface for interacting with the Whoop API.
It handles authentication, request management, and data retrieval for all
supported endpoints.

Features:
    - Automatic OAuth token management
    - Type-safe responses with Pydantic models
    - Pagination handling for collection endpoints
    - Rate limit detection and reporting
    - Context manager support for resource cleanup

Example:
    >>> from whoopyy import WhoopClient
    >>> 
    >>> # Initialize and authenticate
    >>> client = WhoopClient(
    ...     client_id="your_client_id",
    ...     client_secret="your_client_secret"
    ... )
    >>> client.authenticate()
    >>> 
    >>> # Fetch data
    >>> profile = client.get_profile_basic()
    >>> print(f"Hello, {profile.first_name}!")
    >>> 
    >>> recoveries = client.get_recovery_collection(limit=7)
    >>> for recovery in recoveries.records:
    ...     if recovery.score:
    ...         print(f"Recovery: {recovery.score.recovery_score}%")

Context Manager:
    >>> with WhoopClient(client_id, client_secret) as client:
    ...     client.authenticate()
    ...     profile = client.get_profile_basic()
    ...     # Resources automatically cleaned up
"""

from datetime import date, datetime
from types import TracebackType
from typing import Any, Dict, Generator, List, Optional, Type, Union

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
    WhoopNetworkError,
    WhoopNotFoundError,
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

__all__ = ["WhoopClient"]


class WhoopClient:
    """
    Complete Python client for Whoop API.
    
    Provides type-safe access to all Whoop API endpoints with automatic
    token management, pagination handling, and comprehensive error handling.
    
    Attributes:
        client_id: Whoop API client ID.
        client_secret: Whoop API client secret.
        auth: OAuth handler instance for token management.
    
    Example:
        >>> client = WhoopClient(
        ...     client_id="your_client_id",
        ...     client_secret="your_client_secret"
        ... )
        >>> client.authenticate()
        >>> 
        >>> # Get recovery data
        >>> recoveries = client.get_recovery_collection(limit=7)
        >>> for recovery in recoveries.records:
        ...     if recovery.score:
        ...         print(f"Recovery: {recovery.score.recovery_score}%")
        ...         print(f"HRV: {recovery.score.hrv_rmssd_milli}ms")
    
    Context Manager:
        >>> with WhoopClient(client_id, client_secret) as client:
        ...     client.authenticate()
        ...     profile = client.get_profile_basic()
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
        Initialize Whoop API client.
        
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
            >>> import os
            >>> client = WhoopClient(
            ...     client_id=os.getenv("WHOOP_CLIENT_ID"),
            ...     client_secret=os.getenv("WHOOP_CLIENT_SECRET"),
            ...     timeout=60.0
            ... )
        """
        # Guard clauses
        if not client_id:
            raise ValueError("client_id is required")
        if not client_secret:
            raise ValueError("client_secret is required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        
        # Initialize OAuth handler for token management
        self.auth = OAuthHandler(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            token_file=token_file,
            timeout=timeout,
        )
        
        # HTTP client for API requests
        self._http_client = httpx.Client(
            base_url=API_BASE_URL,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        
        self._authenticated = False
        
        logger.info(
            "WhoopClient initialized",
            extra={"client_id": client_id[:8] + "..."}
        )
    
    # =========================================================================
    # Authentication
    # =========================================================================
    
    def authenticate(self, auto_open_browser: bool = True) -> None:
        """
        Perform OAuth authentication flow.
        
        Opens browser for user to authorize the application. After successful
        authorization, tokens are stored for future use.
        
        Args:
            auto_open_browser: Whether to automatically open browser.
                              Set to False for headless environments.
        
        Raises:
            WhoopAuthError: If authentication fails or is denied.
        
        Example:
            >>> client = WhoopClient(client_id, client_secret)
            >>> client.authenticate()
            >>> # Browser opens, user grants permission
            >>> # Now client is ready to make API calls
            
            >>> # For headless environments
            >>> client.authenticate(auto_open_browser=False)
            Please visit this URL to authorize:
            https://api.prod.whoop.com/oauth/oauth2/auth?...
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
            True if authenticated with valid (or refreshable) tokens.
        
        Example:
            >>> if not client.is_authenticated():
            ...     client.authenticate()
        """
        return self._authenticated or self.auth.has_valid_tokens()
    
    # =========================================================================
    # Internal Request Methods
    # =========================================================================
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get request headers with valid access token.
        
        Automatically refreshes token if expired.
        
        Returns:
            Headers dict with Authorization header.
        
        Raises:
            WhoopAuthError: If no valid token available.
        """
        token = self.auth.get_valid_token()
        return {"Authorization": f"Bearer {token}"}
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        _retry: bool = False,
    ) -> Dict[str, Any]:
        """
        Make authenticated API request.
        
        Handles token refresh, rate limiting, and error responses.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.).
            endpoint: API endpoint path (e.g., "/developer/v1/recovery").
            params: Query parameters for the request.
            data: JSON body data for POST/PUT requests.
        
        Returns:
            Response JSON data as dictionary.
        
        Raises:
            WhoopAPIError: If request fails with 4xx/5xx error.
            WhoopRateLimitError: If rate limited (429).
            WhoopAuthError: If authentication fails.
        """
        try:
            headers = self._get_auth_headers()
            
            logger.debug(
                "Making API request",
                extra={
                    "method": method,
                    "endpoint": endpoint,
                    "params": params,
                }
            )
            
            response = self._http_client.request(
                method=method,
                url=endpoint,
                params=params,
                json=data,
                headers=headers,
            )
            
            # Handle rate limiting (429)
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
            
            # Handle authentication errors
            if response.status_code == 401:
                if _retry:
                    raise WhoopAuthError(
                        f"Authentication failed after token refresh. "
                        f"Status: 401. Response: {response.text}",
                        status_code=401,
                    )
                # Force refresh and retry once
                logger.warning("Authentication failed - refreshing token and retrying")
                self.auth.refresh_access_token()
                return self._request(method, endpoint, params=params, data=data, _retry=True)

            # Handle not found errors
            if response.status_code == 404:
                logger.error(
                    "Resource not found",
                    extra={"url": endpoint, "error": response.text}
                )
                raise WhoopNotFoundError(
                    f"Resource not found: {endpoint}. Response: {response.text}",
                    status_code=404,
                )

            # Handle validation errors
            if response.status_code == 400:
                error_detail = response.text
                logger.error(
                    "Validation error",
                    extra={"error": error_detail}
                )
                raise WhoopValidationError(
                    f"Invalid request: {error_detail}",
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
                "API request failed",
                extra={
                    "status_code": e.response.status_code,
                    "error": e.response.text,
                }
            )
            raise WhoopAPIError(
                f"API request failed: {e.response.text}",
                status_code=e.response.status_code,
            )
        except (WhoopRateLimitError, WhoopAuthError, WhoopNotFoundError, WhoopValidationError):
            # Re-raise our custom exceptions
            raise
        except httpx.RequestError as e:
            logger.error(
                "Request error",
                extra={"error": str(e)}
            )
            raise WhoopNetworkError(str(e)) from e
    
    def _format_date_param(
        self,
        value: Optional[Union[datetime, date, str]]
    ) -> Optional[str]:
        """
        Format date parameter for API request.
        
        Args:
            value: Date as datetime, date, or ISO string.
        
        Returns:
            ISO 8601 formatted string or None.
        """
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return format_datetime(value)
        elif isinstance(value, date):
            return format_datetime(datetime.combine(value, datetime.min.time()))
        else:
            return value  # Assume already formatted string
    
    # =========================================================================
    # User Profile Methods
    # =========================================================================
    
    def get_profile_basic(self) -> UserProfileBasic:
        """
        Get basic user profile information.
        
        Returns:
            UserProfileBasic with user_id, email, first_name, last_name.
        
        Raises:
            WhoopAPIError: If request fails.
            WhoopAuthError: If not authenticated.
        
        Example:
            >>> profile = client.get_profile_basic()
            >>> print(f"Hello, {profile.first_name} {profile.last_name}!")
            >>> print(f"User ID: {profile.user_id}")
        """
        logger.info("Fetching basic profile")
        
        data = self._request("GET", ENDPOINTS["user_profile_basic"])
        return UserProfileBasic(**data)
    
    def get_body_measurement(self) -> BodyMeasurement:
        """
        Get user body measurements.
        
        Returns:
            BodyMeasurement with height, weight, and max heart rate.
        
        Raises:
            WhoopAPIError: If request fails.
            WhoopAuthError: If not authenticated.
        
        Example:
            >>> body = client.get_body_measurement()
            >>> if body.weight_kilogram:
            ...     print(f"Weight: {body.weight_kilogram}kg ({body.weight_pounds}lbs)")
            >>> if body.height_meter:
            ...     print(f"Height: {body.height_meter}m ({body.height_feet}ft)")
        """
        logger.info("Fetching body measurements")
        
        data = self._request("GET", ENDPOINTS["user_body_measurement"])
        return BodyMeasurement(**data)
    
    # =========================================================================
    # Recovery Methods
    # =========================================================================
    
    def get_recovery_for_cycle(self, cycle_id: int) -> Recovery:
        """
        Get recovery record for a specific cycle.
        
        Args:
            cycle_id: Cycle ID to get recovery for.
        
        Returns:
            Recovery record with score and metadata.
        
        Raises:
            WhoopAPIError: If request fails or recovery not found.
            ValueError: If cycle_id is invalid.
        
        Example:
            >>> recovery = client.get_recovery_for_cycle(93845)
            >>> if recovery.score:
            ...     print(f"Recovery: {recovery.score.recovery_score}%")
            ...     print(f"HRV: {recovery.score.hrv_rmssd_milli}ms")
            ...     print(f"RHR: {recovery.score.resting_heart_rate}bpm")
        """
        if cycle_id <= 0:
            raise ValueError(f"Invalid cycle_id: {cycle_id}")
        
        logger.info(
            "Fetching recovery for cycle",
            extra={"cycle_id": cycle_id}
        )
        
        endpoint = ENDPOINTS["recovery_for_cycle"].format(cycle_id=cycle_id)
        data = self._request("GET", endpoint)
        return Recovery(**data)
    
    def get_recovery_collection(
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
            end: End date/datetime for filtering (inclusive).
            limit: Number of records per page (1-25). Defaults to 25.
            next_token: Pagination token from previous response.
        
        Returns:
            RecoveryCollection with records and optional next_token.
        
        Raises:
            WhoopAPIError: If request fails.
            WhoopValidationError: If limit is out of range.
        
        Example:
            >>> # Get last 7 days of recovery
            >>> recoveries = client.get_recovery_collection(limit=7)
            >>> for recovery in recoveries.records:
            ...     if recovery.score:
            ...         zone = recovery.score.recovery_zone
            ...         print(f"{recovery.score.recovery_score}% ({zone})")
            
            >>> # Pagination
            >>> page1 = client.get_recovery_collection(limit=10)
            >>> if page1.next_token:
            ...     page2 = client.get_recovery_collection(
            ...         next_token=page1.next_token
            ...     )
        """
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise WhoopValidationError(
                f"limit must be 1-{MAX_PAGE_LIMIT}, got {limit}",
                status_code=400,
            )
        
        logger.info(
            "Fetching recovery collection",
            extra={"limit": limit, "has_token": next_token is not None}
        )
        
        params: Dict[str, Any] = {"limit": limit}
        
        if start:
            params["start"] = self._format_date_param(start)
        if end:
            params["end"] = self._format_date_param(end)
        if next_token:
            params["nextToken"] = next_token
        
        data = self._request("GET", ENDPOINTS["recovery_collection"], params=params)
        return RecoveryCollection(**data)
    
    def get_all_recovery(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Recovery]:
        """
        Get all recovery records with automatic pagination.
        
        Fetches all pages automatically. Use max_records to limit total.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            max_records: Maximum total records to fetch. None for all.
        
        Returns:
            List of all Recovery records.
        
        Example:
            >>> # Get all recovery data for last month
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=30)
            >>> all_recoveries = client.get_all_recovery(start=start)
            >>> print(f"Fetched {len(all_recoveries)} records")
            
            >>> # Limit to 100 records
            >>> recoveries = client.get_all_recovery(max_records=100)
        """
        logger.info(
            "Fetching all recovery records",
            extra={"max_records": max_records}
        )
        
        all_records: List[Recovery] = []
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_recovery_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            all_records.extend(collection.records)
            
            # Check if we've reached max_records
            if max_records and len(all_records) >= max_records:
                logger.info(
                    "Reached max_records limit",
                    extra={"fetched": len(all_records)}
                )
                return all_records[:max_records]
            
            # Check if there are more pages
            if not collection.next_token:
                break
            
            next_token = collection.next_token
        
        logger.info(
            "Fetched all recovery records",
            extra={"total": len(all_records)}
        )
        return all_records
    
    def iter_recovery(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> Generator[Recovery, None, None]:
        """
        Iterate over all recovery records (memory-efficient).
        
        Uses generator to stream records without loading all into memory.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
        
        Yields:
            Recovery records one at a time.
        
        Example:
            >>> for recovery in client.iter_recovery():
            ...     if recovery.score and recovery.score.recovery_score > 80:
            ...         print(f"High recovery: {recovery.score.recovery_score}%")
        """
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_recovery_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            yield from collection.records
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Sleep Methods
    # =========================================================================
    
    def get_sleep(self, sleep_id: str) -> Sleep:
        """
        Get specific sleep record by ID.

        Args:
            sleep_id: Sleep record UUID string.

        Returns:
            Sleep record with score and metadata.

        Raises:
            WhoopAPIError: If request fails or sleep not found.
            ValueError: If sleep_id is invalid.

        Example:
            >>> sleep = client.get_sleep("abc-123")
            >>> print(f"Duration: {sleep.duration_hours}h")
            >>> if sleep.score:
            ...     print(f"Performance: {sleep.score.sleep_performance_percentage}%")
        """
        if not sleep_id or not sleep_id.strip():
            raise ValueError(f"Invalid sleep_id: {sleep_id!r}")
        
        logger.info(
            "Fetching sleep",
            extra={"sleep_id": sleep_id}
        )
        
        endpoint = ENDPOINTS["sleep_single"].format(sleep_id=sleep_id)
        data = self._request("GET", endpoint)
        return Sleep(**data)
    
    def get_sleep_collection(
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
            next_token: Pagination token from previous response.
        
        Returns:
            SleepCollection with records and optional next_token.
        
        Example:
            >>> sleeps = client.get_sleep_collection(limit=7)
            >>> for sleep in sleeps.records:
            ...     if sleep.score and not sleep.nap:
            ...         hours = sleep.score.total_sleep_duration_hours
            ...         print(f"Sleep: {hours:.1f}h")
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
        
        data = self._request("GET", ENDPOINTS["sleep_collection"], params=params)
        return SleepCollection(**data)
    
    def get_all_sleep(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Sleep]:
        """
        Get all sleep records with automatic pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            max_records: Maximum total records to fetch.
        
        Returns:
            List of all Sleep records.
        
        Example:
            >>> all_sleeps = client.get_all_sleep(max_records=30)
            >>> main_sleeps = [s for s in all_sleeps if not s.nap]
            >>> avg_hours = sum(
            ...     s.score.total_sleep_duration_hours 
            ...     for s in main_sleeps if s.score
            ... ) / len(main_sleeps)
            >>> print(f"Average sleep: {avg_hours:.1f}h")
        """
        logger.info(
            "Fetching all sleep records",
            extra={"max_records": max_records}
        )
        
        all_records: List[Sleep] = []
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_sleep_collection(
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
    
    def iter_sleep(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> Generator[Sleep, None, None]:
        """
        Iterate over all sleep records (memory-efficient).
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
        
        Yields:
            Sleep records one at a time.
        """
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_sleep_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            yield from collection.records
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Cycle Methods
    # =========================================================================
    
    def get_cycle(self, cycle_id: int) -> Cycle:
        """
        Get specific physiological cycle by ID.
        
        A cycle represents one full day of physiological data.
        
        Args:
            cycle_id: Cycle ID.
        
        Returns:
            Cycle record with strain score and metadata.
        
        Example:
            >>> cycle = client.get_cycle(123456)
            >>> if cycle.score:
            ...     print(f"Strain: {cycle.score.score}")
            ...     print(f"Calories: {cycle.score.calories}")
        """
        if cycle_id <= 0:
            raise ValueError(f"Invalid cycle_id: {cycle_id}")
        
        logger.info(
            "Fetching cycle",
            extra={"cycle_id": cycle_id}
        )
        
        endpoint = ENDPOINTS["cycle_single"].format(cycle_id=cycle_id)
        data = self._request("GET", endpoint)
        return Cycle(**data)
    
    def get_cycle_collection(
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
            next_token: Pagination token from previous response.
        
        Returns:
            CycleCollection with records and optional next_token.
        
        Example:
            >>> cycles = client.get_cycle_collection(limit=7)
            >>> for cycle in cycles.records:
            ...     if cycle.score:
            ...         level = cycle.score.strain_level
            ...         print(f"Strain: {cycle.score.score} ({level})")
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
        
        data = self._request("GET", ENDPOINTS["cycle_collection"], params=params)
        return CycleCollection(**data)
    
    def get_all_cycles(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Cycle]:
        """
        Get all cycle records with automatic pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            max_records: Maximum total records to fetch.
        
        Returns:
            List of all Cycle records.
        """
        logger.info(
            "Fetching all cycle records",
            extra={"max_records": max_records}
        )
        
        all_records: List[Cycle] = []
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_cycle_collection(
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
    
    def iter_cycles(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> Generator[Cycle, None, None]:
        """
        Iterate over all cycle records (memory-efficient).
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
        
        Yields:
            Cycle records one at a time.
        """
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_cycle_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            yield from collection.records
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Workout Methods
    # =========================================================================
    
    def get_workout(self, workout_id: str) -> Workout:
        """
        Get specific workout by ID.

        Args:
            workout_id: Workout UUID string.

        Returns:
            Workout record with score and metadata.

        Example:
            >>> workout = client.get_workout("abc-123")
            >>> print(f"{workout.sport_name}: {workout.duration_minutes:.0f}min")
            >>> if workout.score:
            ...     print(f"Strain: {workout.score.strain}")
            ...     print(f"Calories: {workout.score.calories}")
        """
        if not workout_id or not workout_id.strip():
            raise ValueError(f"Invalid workout_id: {workout_id!r}")
        
        logger.info(
            "Fetching workout",
            extra={"workout_id": workout_id}
        )
        
        endpoint = ENDPOINTS["workout_single"].format(workout_id=workout_id)
        data = self._request("GET", endpoint)
        return Workout(**data)
    
    def get_workout_collection(
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
            next_token: Pagination token from previous response.
        
        Returns:
            WorkoutCollection with records and optional next_token.
        
        Example:
            >>> workouts = client.get_workout_collection(limit=10)
            >>> for workout in workouts.records:
            ...     print(f"{workout.sport_name}: {workout.duration_minutes:.0f}min")
            ...     if workout.score:
            ...         print(f"  Strain: {workout.score.strain}")
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
        
        data = self._request("GET", ENDPOINTS["workout_collection"], params=params)
        return WorkoutCollection(**data)
    
    def get_all_workouts(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
        max_records: Optional[int] = None,
    ) -> List[Workout]:
        """
        Get all workout records with automatic pagination.
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
            max_records: Maximum total records to fetch.
        
        Returns:
            List of all Workout records.
        """
        logger.info(
            "Fetching all workout records",
            extra={"max_records": max_records}
        )
        
        all_records: List[Workout] = []
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_workout_collection(
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
    
    def iter_workouts(
        self,
        start: Optional[Union[datetime, date, str]] = None,
        end: Optional[Union[datetime, date, str]] = None,
    ) -> Generator[Workout, None, None]:
        """
        Iterate over all workout records (memory-efficient).
        
        Args:
            start: Start date/datetime for filtering.
            end: End date/datetime for filtering.
        
        Yields:
            Workout records one at a time.
        """
        next_token: Optional[str] = None
        
        while True:
            collection = self.get_workout_collection(
                start=start,
                end=end,
                limit=MAX_PAGE_LIMIT,
                next_token=next_token,
            )
            
            yield from collection.records
            
            if not collection.next_token:
                break
            
            next_token = collection.next_token
    
    # =========================================================================
    # Access Management
    # =========================================================================
    
    def revoke_access(self) -> None:
        """
        Revoke current access token.
        
        This will:
        - Invalidate the current access token
        - Stop webhook delivery if configured
        - Require re-authentication for future API calls
        
        Example:
            >>> client.revoke_access()
            >>> # User must re-authenticate to continue
        """
        logger.info("Revoking access token")

        token = self.auth.get_valid_token()
        revoke_url = f"{AUTH_BASE_URL}/oauth2/revoke"

        response = self._http_client.post(
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
    
    # =========================================================================
    # Lifecycle Management
    # =========================================================================
    
    def close(self) -> None:
        """
        Close HTTP clients and release resources.
        
        Should be called when done with the client, or use as
        context manager for automatic cleanup.
        
        Example:
            >>> client = WhoopClient(client_id, client_secret)
            >>> try:
            ...     client.authenticate()
            ...     data = client.get_recovery_collection()
            ... finally:
            ...     client.close()
        """
        self._http_client.close()
        self.auth.close()
        logger.info("WhoopClient closed")
    
    def __enter__(self) -> "WhoopClient":
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
            f"WhoopClient("
            f"client_id='{self.client_id[:8]}...', "
            f"authenticated={self._authenticated})"
        )
