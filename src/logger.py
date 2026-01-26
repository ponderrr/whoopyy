"""
Logging configuration for WhoopYY SDK.

Provides structured logging with contextual information for debugging
and monitoring API interactions.

Usage:
    >>> from whoopyy.logger import get_logger
    >>> logger = get_logger(__name__)
    >>> logger.info("Recovery fetched", extra={"recovery_id": 123, "score": 75.5})

Configuration:
    Set the WHOOPPY_LOG_LEVEL environment variable to control verbosity:
    - DEBUG: Detailed debugging information
    - INFO: General operational messages (default)
    - WARNING: Potential issues
    - ERROR: Error conditions
    - CRITICAL: Severe errors
"""

import logging
import os
from typing import Optional


# Module-level cache for loggers
_loggers: dict[str, logging.Logger] = {}


def get_logger(
    name: str,
    level: Optional[int] = None
) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Creates a logger with consistent formatting across the SDK.
    Loggers are cached to avoid duplicate handlers.
    
    Args:
        name: Logger name, typically __name__ from calling module.
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If None, uses WHOOPPY_LOG_LEVEL env var or defaults to INFO.
    
    Returns:
        Configured logging.Logger instance.
    
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Token refreshed", extra={"expires_in": 3600})
        2024-01-01 12:00:00 - whoopyy.auth - INFO - Token refreshed
        
        >>> logger.error(
        ...     "API request failed",
        ...     extra={"endpoint": "/recovery", "status_code": 500},
        ...     exc_info=True
        ... )
    """
    # Return cached logger if exists
    if name in _loggers:
        return _loggers[name]
    
    # Determine log level
    if level is None:
        env_level = os.environ.get("WHOOPPY_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers if they already exist (e.g., from parent logger)
    parent_has_handlers = logger.parent is not None and bool(logger.parent.handlers)
    if not logger.handlers and not parent_has_handlers:
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(level)
        
        # Create formatter with timestamp, logger name, level, and message
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    # Cache and return
    _loggers[name] = logger
    return logger


def set_log_level(level: int) -> None:
    """
    Set log level for all WhoopYY loggers.
    
    Useful for dynamically adjusting verbosity during debugging.
    
    Args:
        level: Logging level (e.g., logging.DEBUG, logging.INFO).
    
    Example:
        >>> import logging
        >>> from whoopyy.logger import set_log_level
        >>> set_log_level(logging.DEBUG)
        >>> # All whoopyy loggers now log at DEBUG level
    """
    for logger in _loggers.values():
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)


def disable_logging() -> None:
    """
    Disable all WhoopYY logging.
    
    Useful for tests or when logging is handled externally.
    
    Example:
        >>> from whoopyy.logger import disable_logging
        >>> disable_logging()
        >>> # No more log output from whoopyy
    """
    for logger in _loggers.values():
        logger.disabled = True


def enable_logging() -> None:
    """
    Re-enable WhoopYY logging after disabling.
    
    Example:
        >>> from whoopyy.logger import enable_logging
        >>> enable_logging()
        >>> # Logging restored
    """
    for logger in _loggers.values():
        logger.disabled = False
