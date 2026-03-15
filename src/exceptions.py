"""
Custom exceptions for WhoopYY SDK.

Exception Hierarchy:
    Exception (built-in)
    └── WhoopError (base)
        ├── WhoopAuthError (authentication failures)
        │   └── WhoopTokenError (token-specific issues)
        ├── WhoopAPIError (API request failures)
        │   └── WhoopValidationError (data validation)
        └── WhoopRateLimitError (rate limiting)

Error Classification:
    - RETRYABLE: Network errors, rate limits, server errors (5xx)
    - FATAL: Auth errors, validation errors (4xx except 429)

Example:
    >>> from whoopyy.exceptions import WhoopRateLimitError
    >>> try:
    ...     client.get_recovery_collection()
    ... except WhoopRateLimitError as e:
    ...     print(f"Rate limited. Retry after {e.retry_after}s")
"""

from typing import Optional


class WhoopError(Exception):
    """
    Base exception for all Whoop SDK errors.
    
    All WhoopYY exceptions inherit from this class, allowing users to catch
    all SDK-related errors with a single except clause.
    
    Attributes:
        message: Human-readable error description.
        status_code: HTTP status code if applicable, None otherwise.
    
    Example:
        >>> try:
        ...     client.get_recovery(123)
        ... except WhoopError as e:
        ...     print(f"Whoop error: {e.message}")
    """
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None
    ) -> None:
        """
        Initialize WhoopError.
        
        Args:
            message: Human-readable error description.
            status_code: HTTP status code if applicable.
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
    
    def __repr__(self) -> str:
        """Return detailed string representation for debugging."""
        if self.status_code:
            return f"{self.__class__.__name__}(message={self.message!r}, status_code={self.status_code})"
        return f"{self.__class__.__name__}(message={self.message!r})"


class WhoopAuthError(WhoopError):
    """
    Authentication or authorization error.
    
    Raised when:
    - OAuth flow fails
    - Access token is invalid
    - Insufficient permissions for requested resource
    
    This is a FATAL error - do not retry. Re-authentication is required.
    
    Example:
        >>> try:
        ...     client.authenticate()
        ... except WhoopAuthError as e:
        ...     print("Auth failed - check credentials")
    """
    
    pass


class WhoopTokenError(WhoopAuthError):
    """
    Token-specific authentication error.
    
    Raised when:
    - Access token has expired
    - Refresh token is invalid
    - Token refresh fails
    
    This is a FATAL error - re-authentication is required.
    
    Example:
        >>> try:
        ...     client.refresh_access_token()
        ... except WhoopTokenError:
        ...     client.authenticate()  # Full re-auth needed
    """
    
    pass


class WhoopAPIError(WhoopError):
    """
    General API request error.
    
    Raised when:
    - API returns an error response
    - Request fails for non-auth reasons
    - Unexpected response format
    
    Check status_code to determine if error is retryable:
    - 5xx errors: RETRYABLE (server issues)
    - 4xx errors: FATAL (client issues, except 429)
    
    Example:
        >>> try:
        ...     client.get_recovery(invalid_id)
        ... except WhoopAPIError as e:
        ...     if e.status_code and e.status_code >= 500:
        ...         # Retry logic
        ...         pass
    """
    
    pass


class WhoopNotFoundError(WhoopAPIError):
    """Raised when the WHOOP API returns HTTP 404 Not Found."""
    pass


class WhoopValidationError(WhoopAPIError):
    """
    Data validation error.
    
    Raised when:
    - Request parameters are invalid (400 Bad Request)
    - Response data doesn't match expected schema
    - Pydantic model validation fails
    
    This is a FATAL error - do not retry. Fix the request.
    
    Example:
        >>> try:
        ...     client.get_recovery_collection(limit=999)  # Max is 50
        ... except WhoopValidationError as e:
        ...     print(f"Invalid request: {e.message}")
    """
    
    pass


class WhoopRateLimitError(WhoopError):
    """
    Rate limit exceeded error.
    
    Raised when:
    - API returns 429 Too Many Requests
    - Rate limit quota is exhausted
    
    This is a RETRYABLE error - wait and retry.
    
    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header).
    
    Example:
        >>> import time
        >>> try:
        ...     client.get_recovery_collection()
        ... except WhoopRateLimitError as e:
        ...     if e.retry_after:
        ...         time.sleep(e.retry_after)
        ...     # Retry the request
    """
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        status_code: Optional[int] = None
    ) -> None:
        """
        Initialize WhoopRateLimitError.
        
        Args:
            message: Human-readable error description.
            retry_after: Seconds to wait before retrying.
            status_code: HTTP status code (typically 429).
        """
        self.retry_after = retry_after
        super().__init__(message, status_code or 429)
    
    def __repr__(self) -> str:
        """Return detailed string representation for debugging."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"retry_after={self.retry_after}, "
            f"status_code={self.status_code})"
        )


class WhoopNetworkError(WhoopError):
    """
    Network connectivity error.
    
    Raised when:
    - Connection cannot be established
    - Request times out
    - DNS resolution fails
    
    This is a RETRYABLE error - use exponential backoff.
    
    Example:
        >>> import time
        >>> for attempt in range(3):
        ...     try:
        ...         client.get_recovery(123)
        ...         break
        ...     except WhoopNetworkError:
        ...         time.sleep(2 ** attempt)  # Exponential backoff
    """
    
    pass


# =============================================================================
# Error Classification Helpers
# =============================================================================

def is_retryable_error(error: WhoopError) -> bool:
    """
    Determine if an error should be retried.
    
    Retryable errors:
    - WhoopRateLimitError (wait for retry_after)
    - WhoopNetworkError (network issues)
    - WhoopAPIError with 5xx status codes (server errors)
    
    Fatal errors (do not retry):
    - WhoopAuthError (re-authenticate instead)
    - WhoopTokenError (re-authenticate instead)
    - WhoopValidationError (fix the request)
    - WhoopAPIError with 4xx status codes (client errors)
    
    Args:
        error: The WhoopError to classify.
    
    Returns:
        True if the error should be retried, False otherwise.
    
    Example:
        >>> from whoopyy.exceptions import is_retryable_error
        >>> try:
        ...     client.get_recovery(123)
        ... except WhoopError as e:
        ...     if is_retryable_error(e):
        ...         # Implement retry logic
        ...         pass
        ...     else:
        ...         raise  # Don't retry, fix the issue
    """
    # Rate limit - always retryable
    if isinstance(error, WhoopRateLimitError):
        return True
    
    # Network errors - always retryable
    if isinstance(error, WhoopNetworkError):
        return True
    
    # Auth errors - never retryable (need re-auth)
    if isinstance(error, WhoopAuthError):
        return False
    
    # Validation errors - never retryable (fix the request)
    if isinstance(error, WhoopValidationError):
        return False
    
    # API errors - retryable only for 5xx
    if isinstance(error, WhoopAPIError):
        if error.status_code and error.status_code >= 500:
            return True
        return False
    
    # Unknown error type - don't retry
    return False
