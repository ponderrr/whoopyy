# Changelog

All notable changes to WhoopYY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-10-06

WHOOP has retired its `/developer/v1` API. Commit `1cae589`, shipped in 0.2.0, moved every
data path from v2 to v1, so in 0.2.0 through 0.3.1 every data call targets an endpoint WHOOP
no longer supports. This release moves the SDK back to the v2 API and matches the models to
WHOOP's v2 OpenAPI spec. Everyone on 0.2.0–0.3.1 should upgrade.

### Breaking Changes
- All data endpoints now use `/developer/v2/...`. Sleep and workout IDs are UUID strings; cycle IDs stay integers
- `Workout.sport_name` is required again (`str`). WHOOP v2 always returns it, which reverses the 0.2.0 change
- `Workout.sport_id` is now `Optional[int]` and may be `None`. WHOOP has deprecated it ("will not exist past 09/01/2025")
- `WorkoutScore.zone_duration` renamed to `zone_durations` to match the v2 schema. The old input key is still accepted, and reading `.zone_duration` still works but emits a `DeprecationWarning`. `model_dump()` writes `zone_durations`
- `revoke_access()` now sends `DELETE /developer/v2/user/access` with the Bearer token, WHOOP's documented revocation method, instead of POSTing to `/oauth/oauth2/revoke`. Failures raise the standard request exceptions (`WhoopValidationError` on 400, `WhoopRateLimitError` on a 429 that persists after one automatic retry, `WhoopAuthError` on a 401 that persists after one refresh, `WhoopAPIError` otherwise) instead of always `WhoopAuthError`
- `get_sleep()` / `get_workout()` take a UUID string or a `uuid.UUID`. They raise `ValueError` for an `int` or all-digit ID (a legacy v1 ID), with a message that points to `get_activity_mapping()`
- `export_cycle_csv()` adds a ninth column, `Step Count`, at the end of each row

### Added
- `get_sleep_for_cycle(cycle_id)` on both clients — `GET /developer/v2/cycle/{cycle_id}/sleep`
- `get_activity_mapping(activity_v1_id)` on both clients — `GET /developer/v1/activity-mapping/{activity_v1_id}`, returns the v2 UUID for a legacy v1 sleep or workout ID. This is the only v1 path WHOOP still documents
- `ActivityIdMapping` model (`v2_activity_id: str`) and `ZoneDurations` (alias of `WorkoutZoneDuration`), both exported from `whoopyy`
- `Cycle.step_count` (`Optional[int]`); `None` when WHOOP has no step data for the cycle
- `Sleep.v1_id` and `Workout.v1_id` (`Optional[int]`, deprecated by WHOOP)
- `utils.parse_rate_limit_reset(headers, default=60)` — seconds to wait after a 429
- `TrainingLoadTrends.average_daily_steps` (mean over scored cycles that report steps); `generate_summary_report()` adds an "Average Daily Steps" line when step data exists
- `ENDPOINTS` keys `user_access`, `sleep_for_cycle` and `activity_mapping`
- `type_defs`: `RecoveryResponse`, `SleepResponse`, `SleepNeededResponse`, `CycleResponse`, `WorkoutResponse`, `ZoneDurationsResponse`, `ActivityIdMappingResponse`

### Changed
- 429 handling reads `X-RateLimit-Reset` (WHOOP's documented header) first, then `Retry-After`, then falls back to 60s. The wait is still capped at 120s with one automatic retry, and `WhoopRateLimitError.retry_after` carries the parsed value
- Date-only strings (`"YYYY-MM-DD"`) passed as `start`/`end` become `"YYYY-MM-DDT00:00:00.000Z"`, because v2 rejects date-only values. `datetime`/`date` objects and other strings are unchanged
- `Workout.sport_display_name` returns `sport_name` exactly as WHOOP sends it (lowercase, e.g. `"running"`, `"hiit"`), falls back to the deprecated `sport_id` lookup in `SPORT_NAMES`, and returns `"Unknown"` when neither is set. In 0.3.x it returned the `SPORT_NAMES` label (e.g. `"Running"`, `"HIIT"`)
- `export_workout_csv()` leaves the `Sport ID` cell empty when WHOOP omits `sport_id` (column order unchanged)
- `type_defs` required/optional keys now match the v2 spec; `WorkoutScoreResponse` uses `zone_durations`
- Collection `end` filters are documented as exclusive, per the spec

### Deprecated
- `WorkoutScore.zone_duration` attribute — use `zone_durations`
- `Workout.sport_id`, `Workout.v1_id` and `Sleep.v1_id` — deprecated by WHOOP

### Removed
- `revoke_access()` no longer calls `/oauth/oauth2/revoke`, which requires client authentication and is not WHOOP's documented revocation method

### Fixed
- Data calls reach WHOOP's supported v2 API again
- Docstring examples: `cycle.score.strain` (was the nonexistent `cycle.score.score`), UUID sleep/workout IDs, v2 paths
- Duplicate "Access token revoked" log line in `AsyncWhoopClient.revoke_access()`
- `revoke_access()` now signs the client out fully: on success it deletes the token file at `auth.token_file` and clears the response cache, as well as clearing the in-memory tokens. Previously `is_authenticated()` stayed `True`, `authenticate()` reused the revoked token from disk, and cached profile data was still served
- Export path validation (0.3.1) was inconsistent: on macOS it allowed `/etc`, `/private/etc`, `/Library` and `~/.ssh/authorized_keys` while blocking `/usr/local`. It now expands `~` and resolves symlinks before comparing, blocks system directories on both macOS and Linux (`/etc`, `/private/etc`, `/private/var`, `/var`, `/System`, `/Library`, `/bin`, `/sbin`, `/lib`, `/usr` except `/usr/local`, `/boot`, `/proc`, `/sys`, `/dev`) and sensitive paths under the home directory (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/gcloud`, shell rc files), compares whole path components case-insensitively, and refuses to overwrite an existing non-regular file (directory, FIFO, …). `/usr/local` and the macOS per-user temp directory stay writable
- `export_*_csv()` write to the validated, resolved path. A leading `~` in the destination is now expanded (0.3.x opened it literally, so `~/report.csv` went to `./~/report.csv`), and where the OS supports `O_NOFOLLOW` a symlink swapped in at the final path component after validation is refused instead of followed

### Migration from 0.3.x
- `score.zone_duration` → `score.zone_durations` (the old name still works, with a `DeprecationWarning`)
- Treat `workout.sport_id` as optional; use `workout.sport_name` or `workout.sport_display_name` instead
- `workout.sport_display_name` now returns WHOOP's lowercase `sport_name` (`"running"`, `"hiit"`) instead of the `SPORT_NAMES` label (`"Running"`, `"HIIT"`); format it yourself if you display it
- Code that builds `Workout` objects directly (tests, fixtures) must pass `sport_name`
- Stored v1 integer sleep/workout IDs: convert with `client.get_activity_mapping(v1_id).v2_activity_id`
- `revoke_access()`: catch `WhoopError` (or the specific subclasses above) rather than only `WhoopAuthError`. On success it now also deletes the token file at `client.auth.token_file`, so code that expected the file to survive a revoke must re-run `authenticate()`
- Cycle CSV readers that index columns by position: `Step Count` is now the last column

## [0.3.1] - 2026-03-15

### Security
- Atomic token file permissions — `os.open()` with `0o600` at creation (no race window)
- Sanitize API error responses in exceptions — truncate to 200 chars, strip JWT patterns
- Validate redirect URI to localhost only — prevents binding callback server to network
- Export path validation — blocks writes to protected system directories

### Performance
- Auto-retry on 429 rate limits with `Retry-After` backoff (capped at 120s)
- Proactive rate limit tracking via `X-RateLimit-Remaining` header
- TTL caching for stable endpoints — profile (1h), body measurement (24h)
- DRY `_build_collection_params()` helper — reduces ~80 lines of duplication
- Module-level `MS_TO_HOURS` constant in exports — avoids per-iteration computation
- Lazy `logger.extra` dict evaluation — skip dict construction when DEBUG disabled
- Async lock initialized in `__init__` — removes per-call `hasattr` check
- Removed redundant exception re-raising blocks

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

[0.4.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.4.0
[0.3.1]: https://github.com/ponderrr/whoopyy/releases/tag/v0.3.1
[0.3.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.3.0
[0.2.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.2.0
[0.1.0]: https://github.com/ponderrr/whoopyy/releases/tag/v0.1.0
