"""
WhoopYY - Complete Python SDK for Whoop API.

A type-safe, robust Python client for accessing Whoop's developer API.

Example:
    >>> from whoopyy import WhoopClient
    >>> client = WhoopClient(
    ...     client_id="your_client_id",
    ...     client_secret="your_client_secret"
    ... )
    >>> client.authenticate()
    >>> profile = client.get_profile_basic()
    >>> print(f"Hello, {profile.first_name}!")
"""

__version__ = "0.1.0"
__author__ = "Robert Ponder"

# Exceptions
from .exceptions import (
    WhoopError,
    WhoopAuthError,
    WhoopTokenError,
    WhoopAPIError,
    WhoopValidationError,
    WhoopRateLimitError,
    WhoopNetworkError,
    is_retryable_error,
)

# Models
from .models import (
    # User Profile
    UserProfileBasic,
    BodyMeasurement,
    # Recovery
    RecoveryScore,
    Recovery,
    RecoveryCollection,
    # Sleep
    SleepStage,
    SleepScore,
    Sleep,
    SleepCollection,
    # Cycle
    CycleScore,
    Cycle,
    CycleCollection,
    # Workout
    WorkoutZoneDuration,
    WorkoutScore,
    Workout,
    WorkoutCollection,
    # Helpers
    format_duration,
    get_sport_name,
    SPORT_NAMES,
)

# Authentication
from .auth import OAuthHandler

# Clients
from .client import WhoopClient
from .async_client import AsyncWhoopClient

# Export utilities
from .export import (
    # Data classes
    RecoveryTrends,
    SleepTrends,
    TrainingLoadTrends,
    # CSV export functions
    export_recovery_csv,
    export_sleep_csv,
    export_cycle_csv,
    export_workout_csv,
    # Analysis functions
    analyze_recovery_trends,
    analyze_sleep_trends,
    analyze_training_load,
    # Report generation
    generate_summary_report,
    calculate_moving_average,
)

__all__ = [
    # Package info
    "__version__",
    "__author__",
    # Clients
    "WhoopClient",
    "AsyncWhoopClient",
    # Authentication
    "OAuthHandler",
    # Exceptions
    "WhoopError",
    "WhoopAuthError",
    "WhoopTokenError",
    "WhoopAPIError",
    "WhoopValidationError",
    "WhoopRateLimitError",
    "WhoopNetworkError",
    "is_retryable_error",
    # User Profile Models
    "UserProfileBasic",
    "BodyMeasurement",
    # Recovery Models
    "RecoveryScore",
    "Recovery",
    "RecoveryCollection",
    # Sleep Models
    "SleepStage",
    "SleepScore",
    "Sleep",
    "SleepCollection",
    # Cycle Models
    "CycleScore",
    "Cycle",
    "CycleCollection",
    # Workout Models
    "WorkoutZoneDuration",
    "WorkoutScore",
    "Workout",
    "WorkoutCollection",
    # Helpers
    "format_duration",
    "get_sport_name",
    "SPORT_NAMES",
    # Export utilities - Data classes
    "RecoveryTrends",
    "SleepTrends",
    "TrainingLoadTrends",
    # Export utilities - CSV functions
    "export_recovery_csv",
    "export_sleep_csv",
    "export_cycle_csv",
    "export_workout_csv",
    # Export utilities - Analysis
    "analyze_recovery_trends",
    "analyze_sleep_trends",
    "analyze_training_load",
    "generate_summary_report",
    "calculate_moving_average",
]
