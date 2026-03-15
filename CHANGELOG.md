# Changelog

All notable changes to WhoopYY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-15

### Performance
- HTTP connection pooling with keepalive — eliminates per-request connection overhead
- Double-checked locking on token hot path — no lock contention on valid tokens
- In-memory token cache — zero disk reads after startup
- Streaming-compatible CSV exports (Sequence type hints) — handles large datasets efficiently
- `frozen=True`, `str_strip_whitespace=True`, `populate_by_name=True` on all Pydantic models
- Per-request timing logs via `logger.debug` for performance monitoring

### Added
- `AsyncWhoopClient.fetch_all()` — fetch all data types concurrently with `asyncio.gather()`
- `AsyncWhoopClient.fetch_dashboard()` — fetch latest single record of each type concurrently
- Comprehensive integration test suite verified against real WHOOP credentials (17 tests)
- `scripts/perf_check.py` for async performance sanity checks

### Fixed
- mypy strict mode now passes with 0 errors (previously 3 pre-existing errors)

## [0.2.0] - 2026-03-14

### Breaking Changes
- `get_sleep(sleep_id)` now accepts `str` (UUID) instead of `int`
- `get_workout(workout_id)` now accepts `str` (UUID) instead of `int`
- `Workout.sport_name` is no longer required; use `sport_id` (int) instead
- Collection models no longer override `__iter__`; iterate via `.records`

### Fixed
- All API endpoint paths corrected from v2 to v1 (data calls now work)
- `MAX_PAGE_LIMIT` corrected from 50 to 25
- `export_cycle_csv()` and `export_sleep_csv()` no longer crash with AttributeError
- Token file permissions set to 600, path is now absolute (~/.whoop_tokens.json)
- Concurrent token refresh race condition resolved with threading/asyncio locks
- 401 responses now trigger automatic token refresh and retry
- `revoke_access()` now POSTs to correct OAuth revocation endpoint
- RecoveryScore.resting_heart_rate accepts float (was truncating to int)
- RecoveryScore.hrv_rmssd_milli allows zero values
- score_state fields now validate against Literal enum
- Token refresh retries on transient 5xx errors with exponential backoff
- OAuth callback server times out after 120 seconds instead of hanging forever
- All mypy type errors resolved (WorkoutZoneDuration Optional handling, Collection __iter__ override)

### Added
- `WhoopNotFoundError` exception for 404 responses
- `WhoopNetworkError` now properly raised on network failures
- `async_get_valid_token()` for non-blocking async token management
- pyproject.toml with tool configurations
- CI workflow (.github/workflows/ci.yml)
- Comprehensive test suite (360+ tests, 90%+ coverage)
- Integration test stubs (tests/integration/test_real_api.py)

### Removed
- Phantom dependencies: python-dotenv, keyring

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
  - `Cycle` and `CycleScore` with strain level helpers
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
- Dependencies: httpx, pydantic
- Proprietary License

[0.2.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.2.0
[0.1.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.1.0
