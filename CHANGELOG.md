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
- `save_tokens()` refuses to write through a symbolic link at the token path and raises `OSError` (`ELOOP`). Point `token_file` at the real file instead. The SDK checks the token path before it sends a refresh token or an authorization code: with a symlinked (or unwritable) token file, refreshing raises `WhoopTokenError` and `authenticate()` raises `WhoopAuthError` before the browser opens, and the stored refresh token stays valid

### Added
- `get_sleep_for_cycle(cycle_id)` on both clients — `GET /developer/v2/cycle/{cycle_id}/sleep`
- `get_activity_mapping(activity_v1_id)` on both clients — `GET /developer/v1/activity-mapping/{activity_v1_id}`, returns the v2 UUID for a legacy v1 sleep or workout ID. This is the only v1 path WHOOP still documents
- `ActivityIdMapping` model (`v2_activity_id: str`) and `ZoneDurations` (alias of `WorkoutZoneDuration`), both exported from `whoopyy`
- `Cycle.step_count` (`Optional[int]`); `None` when WHOOP has no step data for the cycle
- `Sleep.v1_id` and `Workout.v1_id` (`Optional[int]`, deprecated by WHOOP)
- `utils.parse_rate_limit_reset(headers, default=60)` — seconds to wait after a 429
- `format_sport_name(sport_name)` — display label for a v2 `sport_name`, exported from `whoopyy`
- `TrainingLoadTrends.average_daily_steps` (mean over scored cycles that report steps); `generate_summary_report()` adds an "Average Daily Steps" line when step data exists
- `ENDPOINTS` keys `user_access`, `sleep_for_cycle` and `activity_mapping`
- `type_defs`: `RecoveryResponse`, `SleepResponse`, `SleepNeededResponse`, `CycleResponse`, `WorkoutResponse`, `ZoneDurationsResponse`, `ActivityIdMappingResponse`
- `authenticate(auto_open_browser=True, force=False)` on both clients. `force=True` runs the browser flow even when usable tokens are stored, for example to switch accounts or grant new scopes
- `logout()` on both clients (a coroutine on `AsyncWhoopClient`). It clears the in-memory tokens, deletes the token file and clears the response cache, without contacting WHOOP. `revoke_access()` is still the way to revoke the grant remotely
- `use_pkce=False` keyword on `OAuthHandler`, `WhoopClient` and `AsyncWhoopClient`. With `True`, the authorization URL carries an S256 `code_challenge` and the code exchange sends the matching `code_verifier`, alongside the client secret. The verifier is 86 characters from `secrets` and is new for every flow. PKCE stays off by default until it has been verified against WHOOP's live OAuth server
- `OAuthHandler.refresh_if_stale(seen_access_token)` and `async_refresh_if_stale(seen_access_token)`, used by both clients after a 401. They refresh only if no other thread, coroutine or process has already replaced the rejected token
- `OAuthHandler.clear_tokens()` and `async_clear_tokens()`
- `utils.token_file_lock(filepath, *, timeout=None)` and `utils.async_token_file_lock(...)`, an exclusive cross-process lock on a `<filepath>.lock` sidecar file. It uses `fcntl.flock` on POSIX and `msvcrt.locking` on Windows, and is a logged no-op when neither exists or the lock file cannot be created. The async version waits with `asyncio.sleep`. The lock is not re-entrant: taking it again on the same thread or task raises `RuntimeError` instead of deadlocking. `timeout=0` tries once, and a timeout that runs out raises `TimeoutError`
- `whoopyy.auth` constants `CALLBACK_TIMEOUT_SECONDS` (120), `CALLBACK_SOCKET_TIMEOUT_SECONDS` (10) and `AUTHORIZATION_ENDED_MESSAGE`

### Changed
- 429 handling reads `X-RateLimit-Reset` (WHOOP's documented header) first, then `Retry-After`, then falls back to 60s. The wait is still capped at 120s with one automatic retry, and `WhoopRateLimitError.retry_after` carries the parsed value
- Date-only strings (`"YYYY-MM-DD"`) passed as `start`/`end` become `"YYYY-MM-DDT00:00:00.000Z"`, because v2 rejects date-only values. `datetime`/`date` objects and other strings are unchanged
- `Workout.sport_display_name` formats WHOOP's v2 `sport_name` (lowercase, e.g. `"hiit"`) with the new `format_sport_name()`: the curated `SPORT_NAMES` label when the name matches one ignoring case, spaces, hyphens and underscores (`"hiit"` → `"HIIT"`, `"functional-fitness"` → `"Functional Fitness"`), otherwise each word capitalized. It falls back to the deprecated `sport_id` lookup and returns `"Unknown"` when neither is set. Use `sport_name` for the raw value
- `export_workout_csv()` leaves the `Sport ID` cell empty when WHOOP omits `sport_id` (column order unchanged)
- `type_defs` required/optional keys now match the v2 spec; `WorkoutScoreResponse` uses `zone_durations`
- Collection `end` filters are documented as exclusive, per the spec
- A refresh token that the token endpoint rejects (`invalid_grant` or `token_inactive` on a 400/401) now ends the authorization. The SDK first re-reads the token file in case another process rotated the token. If none did, it clears the in-memory tokens, deletes the token file and raises `WhoopTokenError` whose message starts "WHOOP authorization has ended". Calls that were waiting for that refresh, and later calls on the same handler, raise the same error (not "No tokens available") until new tokens are stored or `logout()`/`clear_tokens()` runs. If the token file cannot be deleted, the message says so and the handler ignores its contents. `invalid_client` and other failures keep the tokens
- When a refresh fails, the callers of the same process that were waiting for it (threads, coroutines) get its error instead of each repeating the refresh, including its 5xx retries, one after another
- Before a refresh token or an authorization code is sent, the SDK checks that the token file can be saved: not a symbolic link or a non-regular file, and either its directory or the file itself writable. Otherwise refreshing raises `WhoopTokenError` (`authenticate()`: `WhoopAuthError`, before the browser opens) and nothing is sent. If saving still fails after a successful refresh or sign-in, `WhoopTokenError` is raised instead of a raw `OSError`; the new tokens are kept in memory
- `save_tokens()` rewrites an existing token file in place (not atomically, with a warning) when its directory does not allow creating the temp file, or when the file is a mount point (`os.replace` fails with `EBUSY`, e.g. a Docker single-file bind mount). These set-ups worked in 0.3.x and keep working
- An async refresh (`async_get_valid_token()`, `async_refresh_if_stale()`) runs in its own task. Cancelling the caller (`asyncio.wait_for`, a client disconnect) no longer cancels a refresh that WHOOP may already have answered, so the rotated refresh token is saved
- `authenticate()` / `authorize()` raise `WhoopAuthError` before opening the browser when called on an event loop thread while an async refresh of the same token file is in progress there. The flow would otherwise block that refresh and fail with `RuntimeError` after the code exchange
- The "No tokens available" message now says to call `authenticate()` (or `OAuthHandler.authorize()`)
- `is_authenticated()` reflects the stored tokens. It returns `False` once they are cleared (`logout()`, `revoke_access()`, a rejected refresh token), even if `authenticate()` succeeded earlier
- `has_valid_tokens()` no longer counts an expired access token with an empty refresh token as usable
- Every refresh holds the in-process lock (`threading.RLock` for sync code, an `asyncio.Lock` for async code) and then the token file lock, and re-reads the token file before refreshing
- A `<token_file>.lock` file (mode 0600) now sits next to the token file. It is created the first time the SDK locks the token file (sign-in, refresh, logout) and is never deleted, not even by `delete_tokens()` or `logout()`
- `load_tokens()` returns `None` for a token file that holds valid JSON that is not an object, and for invalid UTF-8
- `authenticate()` clears the response cache after a completed browser flow
- The OAuth callback server is bound before the browser opens, so a busy port or a non-loopback redirect URI raises `WhoopAuthError` without opening the browser. Each flow keeps its result on its own server object
- For a `localhost` redirect URI the callback server listens on both `127.0.0.1` and `::1` (where the machine has IPv6). A port on which another program already accepts connections on one of the loopback addresses raises `WhoopAuthError` (see Security)

### Deprecated
- `WorkoutScore.zone_duration` attribute — use `zone_durations`
- `Workout.sport_id`, `Workout.v1_id` and `Sleep.v1_id` — deprecated by WHOOP

### Removed
- `revoke_access()` no longer calls `/oauth/oauth2/revoke`, which requires client authentication and is not WHOOP's documented revocation method
- Private `whoopyy.auth._reset_callback_handler()` and the shared result attributes on `_CallbackHandler`. The callback result now lives on the per-flow `_CallbackServer`

### Fixed
- Data calls reach WHOOP's supported v2 API again
- Ship a PEP 561 `py.typed` marker in the sdist and wheel, so downstream type checkers use whoopyy's annotations instead of treating the package as untyped
- README license section said "Proprietary — All Rights Reserved"; it now matches the LICENSE file and package metadata (GPL-3.0-only)
- Docstring examples: `cycle.score.strain` (was the nonexistent `cycle.score.score`), UUID sleep/workout IDs, v2 paths
- Duplicate "Access token revoked" log line in `AsyncWhoopClient.revoke_access()`
- `revoke_access()` now signs the client out fully: on success it deletes the token file at `auth.token_file` and clears the response cache, as well as clearing the in-memory tokens. Previously `is_authenticated()` stayed `True`, `authenticate()` reused the revoked token from disk, and cached profile data was still served
- Export path validation (0.3.1) was inconsistent: on macOS it allowed `/etc`, `/private/etc`, `/Library` and `~/.ssh/authorized_keys` while blocking `/usr/local`. It now expands `~` and resolves symlinks before comparing, blocks system directories on both macOS and Linux (`/etc`, `/private/etc`, `/private/var`, `/var`, `/System`, `/Library`, `/bin`, `/sbin`, `/lib`, `/usr` except `/usr/local`, `/boot`, `/proc`, `/sys`, `/dev`) and sensitive paths under the home directory (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/gcloud`, shell rc files), compares whole path components case-insensitively, and refuses to overwrite an existing non-regular file (directory, FIFO, …). `/usr/local` and the macOS per-user temp directory stay writable
- `export_*_csv()` write to the validated, resolved path. A leading `~` in the destination is now expanded (0.3.x opened it literally, so `~/report.csv` went to `./~/report.csv`), and where the OS supports `O_NOFOLLOW` a symlink swapped in at the final path component after validation is refused instead of followed
- `generate_summary_report(output=...)` wrote a `str`/`Path` destination with no validation at all, bypassing the export path checks. It now validates and writes the resolved path exactly like the CSV exporters (protected locations and non-regular files raise `ValueError` before anything is written, `~` is expanded). File-like objects and `output=None` behave as before
- Concurrent 401s refreshed once each, bypassing the refresh lock. WHOOP rotates the refresh token, so every refresh after the first presented a spent token and failed with `invalid_grant`. A 401 now goes through `refresh_if_stale()` / `async_refresh_if_stale()`, which refresh once under the locks and let the other callers reuse the new token, across threads, coroutines and processes
- `AsyncWhoopClient` refreshed after a 401 with the blocking sync refresh, including `time.sleep` backoff, which stalled the event loop. It now refreshes with `httpx.AsyncClient` (using the handler's timeout) and backs off with `asyncio.sleep`
- The `asyncio.Lock` was created in `OAuthHandler.__init__`. On Python 3.9 that bound it to whichever loop was current, so a handler built outside a running loop or in a worker thread failed ("attached to a different loop", "There is no current event loop"). On 3.10+ a handler could not be reused in a second `asyncio.run()` ("bound to a different event loop"). The lock is now created inside the running loop on first use and recreated when the loop changes
- The documented recovery from a dead refresh token did not work, because `authenticate()` skipped the browser flow while any refresh token was on disk. The tokens are now cleared (see Changed), so calling `authenticate()` again signs the user in
- Token file writes happened in place. A concurrent reader could see a truncated file and report "no tokens". A failed write could truncate or corrupt the only valid refresh token, and it raised `OSError: [Errno 9] Bad file descriptor` from a double close that hid the real error. `save_tokens()` now writes atomically (see Security), and `load_tokens()` retries a read that raced a write
- The token file got mode 0600 only when it was first created, so an existing 0644 file stayed 0644. Every save now leaves it at 0600
- `_sanitize_error_response()` did not remove JWTs. Its pattern only inserted `...`, so all three segments survived. JWTs are now replaced with `[REDACTED]` before the 200-character truncation (see Security)
- OAuth callback server: a request to any other path (for example `/favicon.ico`) ended the flow with a false "timed out" error and the real callback was refused; a code arriving on any path was accepted; an `error` parameter was acted on, and reflected unescaped into the page, before `state` was checked; an idle connection blocked the flow; and a `[::1]` redirect URI failed because the server bound IPv4 only
- `WhoopClient(timeout=...)` and `AsyncWhoopClient(timeout=...)` only applied to token requests. API requests always used a 5s connect / 30s read / 10s write / 5s pool timeout. They now use `httpx.Timeout(timeout, connect=min(5.0, timeout))`. `timeout=None` removes the read, write and pool limits for API requests (connecting stays capped at 5s) and means no timeout for token requests; in 0.3.x it left the API limits at 5/30/10/5s
- `get_valid_token()`, `async_get_valid_token()` and `has_valid_tokens()` could raise `AttributeError` if another thread cleared the tokens (logout, revoke, rejected refresh token) during the call. A first, unlocked load of the token file that raced `logout()` or a refresh could also bring back the cleared or outdated tokens in memory; such a load is no longer cached
- A cancelled `async_get_valid_token()` could drop the refresh token WHOOP had just rotated (see Changed)
- The `OAuthHandler` docstring described the `state` parameter as "PKCE-style", but PKCE was not implemented. It now describes the `state` parameter as CSRF protection, and PKCE is available as an option (see Added)

### Security
- Atomic, owner-only token file writes. The tokens are written to a temp file in the same directory, created with `O_CREAT | O_EXCL | O_NOFOLLOW` and mode 0600 and then `fchmod`ed to 0600. The temp file is fsynced, moved over the token file with `os.replace()`, and the directory is fsynced (best effort). A failed write (full disk, serialization error, interrupt) removes the temp file and leaves the previous token file byte-for-byte intact
- A symbolic link at the token path is refused, so tokens are never written to wherever the link points
- A cross-process lock on `<token_file>.lock` covers every refresh and save, including the reload of the token file just before a refresh, so two processes that share a token file never both refresh with the same rotating refresh token. Plain reads rely on the atomic replace instead
- OAuth callback server hardening:
  - `state` is compared in constant time before `code` or `error` is used, and a mismatch gets a 400 and is ignored
  - Requests to any path other than the redirect URI's get a 404 and are ignored
  - Reflected text is HTML-escaped
  - Responses send `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`
  - Each connection is served on its own thread with a 10s read timeout and is closed after 10s at most. At most 16 connections are open at once (a new one closes the oldest), and all are closed when the flow ends, so no handler thread outlives the flow. The flow waits up to 120s for a valid callback
  - With a `localhost` redirect URI, another program listening on `[::1]:PORT` or a dual-stack `[::]:PORT` could receive the authorization code from browsers that resolve `localhost` to `::1`, while the SDK waited on `127.0.0.1` and timed out. The SDK now listens on both loopback addresses and refuses a port on which another program already accepts connections, before the browser opens
- Opt-in PKCE (S256) with `use_pkce=True`
- Error text redaction now works. JWTs (signed, encrypted, unsigned and lone `eyJ...` segments), the values of `access_token`, `refresh_token`, `id_token` and `client_secret` in JSON or form bodies, and Ory opaque tokens (`ory_at_...`, `ory_rt_...`) are replaced with `[REDACTED]` before truncation. The 0.3.1 claim "strip JWT patterns" was not true until this release

### Migration from 0.3.x
- `score.zone_duration` → `score.zone_durations` (the old name still works, with a `DeprecationWarning`)
- Treat `workout.sport_id` as optional; use `workout.sport_name` or `workout.sport_display_name` instead
- `workout.sport_display_name` still returns readable labels (`"Running"`, `"HIIT"`), now derived from `sport_name`; a sport missing from `SPORT_NAMES` gets capitalized words (`"non-sleep-deep-rest"` → `"Non Sleep Deep Rest"`)
- Code that builds `Workout` objects directly (tests, fixtures) must pass `sport_name`
- Stored v1 integer sleep/workout IDs: convert with `client.get_activity_mapping(v1_id).v2_activity_id`
- `revoke_access()`: catch `WhoopError` (or the specific subclasses above) rather than only `WhoopAuthError`. On success it now also deletes the token file at `client.auth.token_file`, so code that expected the file to survive a revoke must re-run `authenticate()`
- Cycle CSV readers that index columns by position: `Step Count` is now the last column
- A symlinked token file, such as one managed by GNU Stow or another dotfiles tool, is now refused. Set `token_file` to the real file. The SDK refuses before it uses the stored refresh token, so changing `token_file` afterwards needs no new sign-in
- Expect a `<token_file>.lock` file next to the token file, for example `~/.whoop_tokens.json.lock`. Leave it in place, and keep it out of version control
- When a call raises `WhoopTokenError` saying the authorization has ended, the token file has already been deleted (if it could not be deleted, the message says so; delete it or call `authenticate(force=True)`); call `authenticate()` to sign in again
- Code that matched the exact text "Please call authorize() first" must match "No tokens available" instead
- `is_authenticated()` no longer returns `True` only because `authenticate()` ran earlier; it checks the stored tokens
- `AsyncWhoopClient.logout()` is a coroutine: `await client.logout()`
- `timeout=` now applies to API requests as well. A short timeout that was meant only for the token endpoint now also limits API calls
- Code or tests that used `_CallbackHandler`'s class attributes or `_reset_callback_handler()` (private API) must read the result from `_CallbackServer` instead

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
- Integration test suite against the real WHOOP API (20 tests, skipped without credentials). Correction: this entry originally said the suite was "verified against real WHOOP credentials"; it had not been run. Use `scripts/live_check.py` (0.4.0) to verify against your own account
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
