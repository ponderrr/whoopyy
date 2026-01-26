# Changelog

All notable changes to WhoopYY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-25

### Added

- **Complete OAuth 2.0 Authentication**
  - Browser-based OAuth flow with automatic callback handling
  - Secure token storage with automatic refresh
  - Configurable scopes and redirect URIs

- **Synchronous Client (`WhoopClient`)**
  - Full API coverage for all Whoop endpoints
  - Context manager support for automatic cleanup
  - Automatic pagination with `get_all_*` methods
  - Memory-efficient generators with `iter_*` methods

- **Asynchronous Client (`AsyncWhoopClient`)**
  - Native async/await support for concurrent requests
  - Same API coverage as synchronous client
  - Optimized for high-performance applications

- **Type-Safe Pydantic Models**
  - `UserProfileBasic` and `BodyMeasurement` for user data
  - `Recovery` and `RecoveryScore` with recovery zone helpers
  - `Sleep`, `SleepScore`, and `SleepStage` with duration calculations
  - `Cycle` and `CycleStrain` with strain level helpers
  - `Workout` and `WorkoutScore` with sport name mapping

- **Export Utilities**
  - CSV export functions for all data types
  - Trend analysis for recovery, sleep, and training load
  - Summary report generation

- **Comprehensive Error Handling**
  - Typed exception hierarchy (`WhoopError`, `WhoopAuthError`, `WhoopAPIError`, etc.)
  - Rate limit detection with retry-after support
  - Network error handling with retry helpers

- **Developer Experience**
  - 150+ passing tests with 95%+ coverage
  - MyPy strict mode with 0 errors
  - Complete type hints throughout

### Technical Details

- Python 3.9+ support
- Dependencies: httpx, pydantic, python-dotenv, keyring
- Proprietary License

[0.1.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.1.0
