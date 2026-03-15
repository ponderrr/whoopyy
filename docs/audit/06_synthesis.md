# Audit Synthesis — whoopyy SDK

**Generated:** 2026-03-14
**Auditor:** Agent 6 (Synthesis)
**Source reports:** 01_structure.md, 02_api_coverage.md, 03_oauth_tokens.md, 04_test_coverage.md, 05_code_quality.md

---

## 1. Master Findings Table

Every finding from all five audit reports, de-duplicated and assigned a canonical ID. Where multiple reports raised the same underlying bug, the entries are merged and cross-references are noted.

| ID | Severity | Layer | Category | Finding Description | Effort |
|----|----------|-------|----------|---------------------|--------|
| **F01** | CRITICAL | Python SDK | API Correctness | All 10 data endpoint paths use `/developer/v2/` but the WHOOP API is at `/developer/v1/`. Every non-auth API call returns 404. (`constants.py` lines 36–55) | S |
| **F02** | CRITICAL | Python SDK | API Correctness | `revoke_access()` sends `DELETE /developer/v2/user/access` instead of `POST /oauth/oauth2/revoke`. Wrong HTTP method and wrong path. (`client.py:1150`, `async_client.py:927`, `constants.py:38`) | S |
| **F03** | CRITICAL | Python SDK | API Correctness | `MAX_PAGE_LIMIT = 50` but WHOOP API maximum page size is 25. Auto-pagination will either get 400 errors or silently return half the expected data. (`constants.py:136`) | S |
| **F04** | CRITICAL | Python SDK | Model Correctness | `Workout.sport_name` is required but the WHOOP API returns `sport_id`, not `sport_name`. Every workout deserialization fails with a Pydantic `ValidationError`. (`models.py:1073–1074`) | S |
| **F05** | CRITICAL | Python SDK | Test Infrastructure | `test_models.py` and `test_export.py` fail at collection because both import `CycleStrain`, which does not exist — the class is `CycleScore`. Both files produce zero test runs. (`tests/test_models.py:29`, `tests/test_export.py:35`) | S |
| **F06** | CRITICAL | Python SDK | Test Infrastructure | 14 of 74 tests fail on every run: 8 in `test_client.py`, 8 in `test_async_client.py`. Root causes: stale fixtures use integer IDs where models expect UUID strings; `get_recovery()` called but method is `get_recovery_for_cycle()`; `sport_name` missing from workout fixture. These tests provide zero regression protection. | M |
| **F07** | CRITICAL | Python SDK | Test Infrastructure | No package installation mechanism for CI. `import whoopyy` fails without `pip install -e .`. No `conftest.py`, no `pytest.ini`, no `pyproject.toml` testpaths, no CI configuration file anywhere in the repo. | S |
| **F08** | CRITICAL | Python SDK | Auth Reliability | No mutex or lock on `get_valid_token()` / `refresh_access_token()`. Concurrent callers that simultaneously detect an expired token will both issue refresh requests. If WHOOP uses one-time-use refresh token rotation, the second request will receive an invalid token, corrupting the session permanently. (`src/auth.py:652–690`) | M |
| **F09** | CRITICAL | Python SDK | Export / Runtime | `export_cycle_csv()` and `analyze_training_load()` access `CycleScore.score`, which does not exist — the field is `.strain`. Both functions raise `AttributeError` on every call with scored cycles. (`src/export.py:410, 715`) | S |
| **F10** | HIGH | Python SDK | Model Correctness | All 6 `WorkoutZoneDuration` zone duration fields are declared required `int` but the WHOOP API returns `null` for zones with no data. Every workout with sparse HR data fails Pydantic validation. (`models.py:793–798`) | S |
| **F11** | HIGH | Python SDK | Model Correctness | `RecoveryScore.resting_heart_rate` typed `int` but API returns `float` (e.g., `52.3`). Pydantic will coerce silently, truncating precision. Should be `float`. (`models.py:189`) | S |
| **F12** | HIGH | Python SDK | Model Correctness | `RecoveryScore.hrv_rmssd_milli` constraint is `gt=0` but the API can return `0.0` for users with very low HRV. A real API response will fail validation. Should be `ge=0`. (`models.py:194`) | S |
| **F13** | HIGH | Python SDK | Model Correctness | `get_sleep(sleep_id: int)` accepts `int` and guards with `<= 0`, but `Sleep.id` is a UUID `str`. The type annotation, guard clause, and URL interpolation are all wrong. (`client.py:645`, `async_client.py:547`) | S |
| **F14** | HIGH | Python SDK | Model Correctness | `get_workout(workout_id: int)` has the same UUID/int type mismatch as `get_sleep`. (`client.py:976`, `async_client.py:795`) | S |
| **F15** | HIGH | Python SDK | Auth Reliability | `_get_auth_headers()` in `AsyncWhoopClient` calls synchronous `get_valid_token()` which, when the token is expired, issues a blocking HTTP request via `httpx.Client` on the asyncio event loop thread. Blocks the event loop for the full refresh network round-trip. (`src/async_client.py:226–234`) | L |
| **F16** | HIGH | Python SDK | Auth Reliability | No automatic retry after receiving a 401. If a token expires in the window between the expiry check and the HTTP dispatch (TOCTOU), the caller receives `WhoopAuthError` and must implement their own retry. (`client.py:315–322`, `async_client.py:297–302`) | M |
| **F17** | HIGH | Python SDK | Security | Token file created with `open(filepath, "w")` using the default umask (`022`), resulting in world-readable `644` permissions. Both the access token and refresh token are readable by any local user. (`src/utils.py:62`) | S |
| **F18** | HIGH | Python SDK | Auth Reliability | Callback server `handle_request()` has no timeout. If the user never completes the browser OAuth flow the process hangs indefinitely. (`src/auth.py:426–432`) | S |
| **F19** | HIGH | Python SDK | Export / Runtime | `export_sleep_csv()` does `stages = sleep.score.stage_summary or {}` then calls `stages.get(...)`. `StageSummary` is a Pydantic model, not a dict. Calling `.get()` on it raises `AttributeError`. (`src/export.py:309–315`) | S |
| **F20** | HIGH | Python SDK | Error Handling | `WhoopNetworkError` is defined but never raised. `httpx.RequestError` (timeout, DNS failure, connection refused) is caught and re-raised as `WhoopAPIError`. The `is_retryable_error()` helper checks for `WhoopNetworkError` and will never return `True` for network errors. (`client.py:359–364`, `async_client.py:334–339`) | S |
| **F21** | HIGH | Python SDK | Error Handling | `WhoopNotFoundError` does not exist. 404 responses are indistinguishable from all other API errors — they are wrapped as generic `WhoopAPIError`. Users cannot catch "resource not found" separately. | S |
| **F22** | HIGH | Python SDK | Rate Limiting | No proactive throttling and no automatic retry-with-backoff on 429. `MAX_RETRIES = 3` and `RETRY_BACKOFF_BASE_SECONDS = 1.0` are defined in `constants.py` but never referenced anywhere. The SDK raises `WhoopRateLimitError` and drops the request — retry is left entirely to calling code. (`src/constants.py:123–127`) | L |
| **F23** | HIGH | Python SDK | Test Coverage | Token persistence (save/load/missing file/corrupted file) is never tested against real file I/O. All file operations are mocked. A bug in `utils.save_tokens` or `utils.load_tokens` would not be caught. `src/utils.py` is only 42% covered. | M |
| **F24** | HIGH | Python SDK | Test Coverage | 401-triggered token refresh-and-retry is not tested and not implemented. This is a common real-world failure scenario. Neither the test nor the code handles the case. | M |
| **F25** | HIGH | Python SDK | Test Coverage | No test for 500/5xx server errors. `WhoopAPIError` for server-side failures exists in the exception hierarchy but is never exercised. | S |
| **F26** | HIGH | Python SDK | Test Coverage | No test for network timeouts. `httpx.RequestError` path exists in `client.py:359` but is never triggered in tests. `WhoopNetworkError` exists but is never raised or tested. | S |
| **F27** | HIGH | Next.js | API Correctness | All five Next.js data proxy routes hardcode `/developer/v1/` but the Python SDK was migrated to `/developer/v2/` in commit `fcc5959`. The two halves of the project now target different API versions and different path structures. (`temp_web/app/api/whoop/*/route.ts`) | M |
| **F28** | MEDIUM | Python SDK | API Correctness | 8 collection method docstrings claim the `limit` parameter accepts `1-50` when the actual WHOOP API maximum is 25. (`client.py:487, 686, 857, 1016`; `async_client.py:427, 579, 710, 830`) | S |
| **F29** | MEDIUM | Python SDK | Model Correctness | `SleepScore.respiratory_rate` constraint is `gt=0` but the API can return `0`. Should be `ge=0`. (`models.py:451`) | S |
| **F30** | MEDIUM | Python SDK | Model Correctness | `sport_id` on `Workout` is marked `Optional[int]` with a "deprecated" comment but is in fact the primary API field. The comment is incorrect and misleading. (`models.py:1074`) | S |
| **F31** | MEDIUM | Python SDK | Model Correctness | `score_state` is typed as bare `str` in all four entity models (`Cycle`, `Recovery`, `Sleep`, `Workout`) instead of `Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]`. Invalid values pass silently. (`models.py:266, 552, 704, 1075`) | S |
| **F32** | MEDIUM | Python SDK | Auth Reliability | No warning or assertion when `refresh_token` is absent from the token exchange response even though `offline` scope was requested. The missing token surfaces much later as `WhoopTokenError`, making the failure mode non-obvious. (`src/auth.py:492`) | S |
| **F33** | MEDIUM | Python SDK | Auth Reliability | Transient 5xx errors from the token endpoint are treated as fatal `WhoopTokenError`, forcing a full browser re-auth. A network hiccup during refresh kicks the user out of their session unnecessarily. (`src/auth.py:598–617`) | M |
| **F34** | MEDIUM | Next.js | Auth Reliability | Same fatal-on-5xx issue as F33 in the Next.js refresh route. (`temp_web/app/api/whoop/auth/refresh/route.ts:31–34`) | M |
| **F35** | MEDIUM | Next.js | Auth Reliability | Access token cookie `maxAge` is hardcoded to 3600 regardless of the actual `expires_in` returned by the server. TTL mismatch between cookie and token. (`temp_web/lib/api/tokens.ts:41–46`) | S |
| **F36** | MEDIUM | Next.js | Auth Reliability | `requireAuth()` does not check token expiry. An expired cookie (not yet deleted by the browser) passes the auth guard and causes a 401 at the WHOOP API that is not handled. (`temp_web/lib/auth/server.ts:9–16`) | S |
| **F37** | MEDIUM | Python SDK | Auth Reliability | `_CallbackHandler` uses class-level attributes for `auth_code`, `auth_state`, and `error`. Multiple concurrent `OAuthHandler` instances share the same callback slot — one can overwrite another's auth code. Safe for single-user CLI use only. (`src/auth.py:72–74, 200–204`) | M |
| **F38** | MEDIUM | Python SDK | Export / Runtime | Optional sleep score fields (`sleep_performance_percentage`, `sleep_efficiency_percentage`, `respiratory_rate`) are collected into lists and passed to `sum()` without filtering `None` values. `TypeError` will be raised at runtime when any field is absent. (`src/export.py:662–664`) | S |
| **F39** | MEDIUM | Python SDK | Logging | `authorize()` calls `print()` directly to stdout inside library code when `auto_open_browser=False`. Library code must not write to stdout. Should be `logger.info()` or a callback. (`src/auth.py:368`) | S |
| **F40** | MEDIUM | Python SDK | Code Cleanliness | `_format_date_param()` is identically implemented in both `WhoopClient` and `AsyncWhoopClient`. Should be extracted to a module-level function in `utils.py`. (`client.py:366–387`, `async_client.py:341–354`) | S |
| **F41** | MEDIUM | Python SDK | Code Cleanliness | The `while True / if not next_token: break` pagination loop pattern is repeated across 16 methods in two client files. A shared pagination utility would remove this duplication. (`client.py`, `async_client.py` — 8 methods each) | M |
| **F42** | MEDIUM | Python SDK | Rate Limiting | Rate limit docstring states "per hour" but WHOOP's actual limit is 100 requests per minute. No constant exists for the 10,000 req/day limit. (`src/constants.py:93`) | S |
| **F43** | MEDIUM | Python SDK | Error Handling | 401 error handler does not include `response.text` in the exception message, unlike the 400 handler. Inconsistent and makes token debugging harder. (`client.py:316–322`, `async_client.py:298–303`) | S |
| **F44** | MEDIUM | Python SDK | Test Coverage | No `conftest.py`. `mock_auth` and fixture data are duplicated across `test_client.py`, `test_async_client.py`, `test_auth.py`, and `test_models.py`. Fixture updates require multi-file edits. | S |
| **F45** | MEDIUM | Python SDK | Test Coverage | CSRF state mismatch path in `_wait_for_callback` (`auth.py:448`) raises `WhoopAuthError("State parameter mismatch")` but this branch has no test. | S |
| **F46** | MEDIUM | Python SDK | Test Coverage | Auto-pagination (`get_all_sleep`, `get_all_cycles`, `get_all_workouts`) and collection endpoints for Sleep, Cycle, and Workout have zero passing tests. | M |
| **F47** | MEDIUM | Python SDK | Test Coverage | Concurrent token refresh thread safety has no test. `OAuthHandler` has no locking (F08) and this is not documented as a limitation. | M |
| **F48** | MEDIUM | Python SDK | Test Coverage | ISO8601 string-to-datetime deserialization is not directly tested. Tests pass `datetime` objects to models rather than ISO strings, bypassing the actual Pydantic deserialization code path. | S |
| **F49** | MEDIUM | Python SDK | Test Coverage | Proactive token expiry buffer (`TOKEN_REFRESH_BUFFER_SECONDS`) behavior is never tested. The buffer window (token expiring in < 60s should refresh) is not asserted anywhere. | S |
| **F50** | MEDIUM | Next.js | Security | `.env.local` with a weak `SESSION_SECRET` (`development_secret_key_12345`) is committed to the repository. Even mock credentials should not be tracked. (`temp_web/.env.local`) | S |
| **F51** | MEDIUM | Python SDK | Distribution | `python-dotenv` and `keyring` are listed as runtime dependencies in `setup.py` but are never imported anywhere in `src/`. Phantom dependencies forced on every user. | S |
| **F52** | MEDIUM | Next.js | Completeness | All dashboard pages render hardcoded mock data. The actual Next.js API proxy routes are implemented but not wired to any UI component. The web app does not fetch real WHOOP data. | L |
| **F53** | LOW | Python SDK | API Correctness | Orphaned `"sleep_for_cycle"` key defined in `ENDPOINTS` dict. Not called from any client method and no such endpoint exists in the WHOOP v1 API. Dead code. (`constants.py:47`) | S |
| **F54** | LOW | Python SDK | Model Correctness | `SleepStage` model (`models.py:322–357`) is dead code. The WHOOP v1 API returns aggregated stage durations, not individual stage objects. This model is not referenced anywhere and not exported. | S |
| **F55** | LOW | Python SDK | Security | Token file stored as plaintext JSON. No severity escalation beyond what Agent 2 and Agent 3 noted — it is documented in-source — but public documentation should warn consumers explicitly. (`utils.py:62`) | S |
| **F56** | LOW | Python SDK | API Correctness | `constants.py` uses `dict[str, str]` and `list[str]` (Python 3.9+ syntax) but `type_defs.py` uses `Dict` and `List` from `typing`. Setup.py declares `python_requires >= 3.9`. The inconsistency between files is confusing but not a runtime bug given the 3.9 floor. (`constants.py:34, 67`) | S |
| **F57** | LOW | Python SDK | Test Coverage | `iter_recovery`, `iter_sleep`, `iter_cycles`, `iter_workouts` generator methods have zero test coverage. | S |
| **F58** | LOW | Python SDK | Test Coverage | `revoke_access()` has no test. | S |
| **F59** | LOW | Python SDK | Test Coverage | `is_retryable_error()` helper function (`exceptions.py:235`) has zero test coverage and is effectively dead because `WhoopNetworkError` is never raised (F20). | S |
| **F60** | LOW | Python SDK | Test Coverage | `WorkoutZoneDuration` nullable path (`zone_duration=None`) is never tested. Neither are the nullable `distance_meter`, `altitude_gain_meter`, `altitude_change_meter` fields on `WorkoutScore`. | S |
| **F61** | LOW | Python SDK | Type Safety | `__iter__` return types missing on all four collection models (`RecoveryCollection`, `SleepCollection`, `CycleCollection`, `WorkoutCollection`). (`models.py:313, 600, 754, 1132`) | S |
| **F62** | LOW | Python SDK | Type Safety | `__exit__` / `__aexit__` methods missing argument type annotations in `OAuthHandler`, `WhoopClient`, `AsyncWhoopClient`. (`auth.py:744`, `client.py:1182`, `async_client.py:950`) | S |
| **F63** | LOW | Python SDK | Type Safety | `response.json()` returns `Any` but `_request()` declares `-> dict[str, Any]` — no cast. Mypy flags both. (`client.py:342`, `async_client.py:318`) | S |
| **F64** | LOW | Python SDK | Code Cleanliness | `ClassVar` is imported from `typing` in `models.py` but never used. (`models.py:47`) | S |
| **F65** | LOW | Python SDK | Code Cleanliness | `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` are defined in `constants.py` but never imported or referenced anywhere. Dead constants. (`constants.py:123–127`) | S |
| **F66** | LOW | Python SDK | Code Cleanliness | Inline magic conversion `1 / (1000 * 60 * 60)` in `export.py:310` instead of using the existing `milliseconds_to_hours()` utility. | S |
| **F67** | LOW | Python SDK | Logging | `WHOOPPY_LOG_LEVEL` environment variable name uses double-P, inconsistent with the package name `whoopyy`. (`src/logger.py:65`) | S |
| **F68** | LOW | Python SDK | Distribution | No `keywords` field in `setup.py`. Reduces PyPI discoverability. | S |
| **F69** | LOW | Python SDK | Distribution | No `pyproject.toml`. Project uses legacy `setup.py` only. `mypy`, `ruff`, and `black` configs cannot be consolidated. | S |
| **F70** | LOW | Next.js | Auth Reliability | `oauth_state` cookie `secure` flag is only set in production. State cookie is transmitted over plain HTTP in development, making it interceptable. (`temp_web/app/api/whoop/auth/login/route.ts:41`) | S |
| **F71** | LOW | Next.js | Auth Reliability | `expires_in` silently defaults to `3600` if absent in token exchange response. Masks malformed token responses. (`temp_web/app/api/whoop/auth/callback/route.ts:48`) | S |
| **F72** | LOW | Python SDK | Auth Reliability | Token file path is relative (`.whoop_tokens.json`). File location depends on the caller's working directory, which can change between `authorize()` and subsequent `get_valid_token()` calls. (`constants.py:113`) | S |
| **F73** | LOW | Next.js | Completeness | No `next.config.ts` / `next.config.js` present. Default Next.js configuration applies; no custom headers, image domains, or redirects configured. | S |
| **F74** | LOW | Python SDK | Type Safety | Missing `__all__` in all sub-modules except `__init__.py`. Wildcard import behavior and IDE auto-complete are degraded. | S |

---

## 2. Six Direct Questions

### 1. Is the Python SDK actually getting all WHOOP data correctly right now?

No. The SDK is entirely broken for data retrieval in its current state. F01 is a complete, blanket failure: every data endpoint path uses `/developer/v2/` when the actual WHOOP API is at `/developer/v1/`. Every call to `get_profile_basic()`, `get_recovery_collection()`, `get_sleep()`, `get_workout()`, and all other data methods will receive a 404 response. Additionally, F04 means that even if the URL bug were fixed, all workout responses would fail to deserialize because the `Workout` model requires `sport_name` but the API returns `sport_id`. F10 means workouts with any null zone data also fail. F11 and F12 mean some recovery responses fail. F03 means auto-pagination sends requests with `limit=50` that the API rejects or silently truncates to 25.

The short answer: not a single data endpoint returns correctly parsed data right now.

### 2. Are there any endpoints or fields missing from the SDK?

The method-level coverage is complete — all 12 documented WHOOP v1 data endpoints and the three OAuth endpoints have corresponding methods. No endpoint is structurally absent. However, several fields are wrong rather than missing: `sport_name` (F04) is fabricated and blocks workout deserialization; `resting_heart_rate` type is wrong (F11); `hrv_rmssd_milli` constraint is wrong (F12); all six `WorkoutZoneDuration` fields are non-nullable when they should be `Optional` (F10). The `SleepStage` model (F54) is dead code for a non-existent API response shape. `score_state` on four models lacks enum validation (F31). The profile endpoint for body measurement uses a slightly different path structure internally but is mapped correctly.

### 3. Is the OAuth flow reliable enough to survive 30 days of daily use without breaking?

No. There are two critical reliability failures that will cause session corruption in real use:

F08 (no mutex on token refresh) is the most dangerous. In any concurrent usage — including the async client used with `asyncio.gather()` as shown in the SDK's own docstring examples — two coroutines will simultaneously detect an expired token and both send a refresh request. If WHOOP rotates refresh tokens on use (standard practice), the second request will be rejected and the session is permanently corrupted. This requires a full re-auth. Over 30 days of daily use with any async usage, this will trigger repeatedly.

F16 (no 401 retry) means that if a token expires in the sub-second window between the expiry check and the HTTP dispatch, the caller receives a hard exception with no recovery path.

F18 (no callback timeout) means an abandoned authorization flow hangs the process forever, though this is a first-run problem, not a daily-use problem.

F33 (5xx treated as fatal) means a single transient server error during the nightly token refresh will force a full browser re-auth the next morning.

Verdict: the auth flow works in a single-threaded, never-fails-network scenario. In any realistic production environment it will break within the first week.

### 4. Would the current test suite catch a regression if someone broke token refresh?

No, and this is not a close call. The test suite has two structural problems that make it nearly worthless for catching regressions:

First, 14 of 74 tests fail on every run right now (F06). Any CI system would show a red build permanently, causing developers to ignore failures — the classic "broken window" anti-pattern. F05 means two entire test files never execute at all.

Second, even the 23 passing auth tests (the strongest file) do not cover the concurrent refresh race (F47), do not test against real file I/O (F23), and do not test the proactive expiry buffer behavior (F49). A developer who introduced a threading regression in token refresh would see all existing tests pass.

The specific answer: `test_refresh_token_success` (`test_auth.py:258`) verifies that the refresh method calls `save_tokens` and returns a new token. That test passes. But it does not test concurrent calls, does not test that the lock prevents double-refresh, and does not test that a 5xx from the token endpoint is retried rather than treated as fatal. A regression in any of those behaviors would go undetected.

### 5. Is the package ready to publish to PyPI right now?

No. The following blockers prevent publication:

- F01: All data endpoints return 404. Publishing a package that cannot retrieve any data would immediately generate user complaints and negative reviews.
- F04: All workout deserialization fails.
- F09, F19: `export_cycle_csv()` and `export_sleep_csv()` crash with `AttributeError` on valid input.
- F05/F06: The test suite does not validate the package works. A PyPI release should have a passing test suite.
- F51: Two phantom runtime dependencies (`python-dotenv`, `keyring`) force unnecessary installs on every user.
- F69: No `pyproject.toml` — the modern packaging standard. While `setup.py` alone will technically work, it is a PyPI presentation quality issue.

Even after fixing the critical bugs, the package would benefit from F68 (keywords) and F69 (pyproject.toml) before publishing. The license is proprietary, which limits adoption but is not a technical blocker.

### 6. What is the single biggest risk if someone ran this in production today?

The single biggest risk is F01 combined with F08. In practice: a user will successfully authenticate (the OAuth flow works), call any data method, receive a 404 error, and have no data. If they somehow missed that and were running a background polling loop, the first time two concurrent async tasks hit an expired token simultaneously (F08), the session is permanently corrupted and requires manual re-authentication. The user has no data and no session and no automatic recovery path.

If forced to name one finding: F01 is the single biggest risk because it makes the SDK's entire value proposition — accessing WHOOP data — completely non-functional. The user does not get anything for their OAuth credentials.

---

## 3. Scorecard

### API Coverage — 5/10

All 12 endpoints have corresponding methods. That is the only positive. F01 makes every method return 404 at runtime. F04 makes workout deserialization always fail. F10 makes workout deserialization fail for any workout with null zone data. F03 makes auto-pagination broken. The coverage is structurally present but functionally zero.

### OAuth Reliability — 5/10

The core happy-path OAuth flow is correctly implemented: proper PKCE-style state, correct scopes, correct token exchange parameters, proactive expiry checking, per-request header injection. These are done well. The score is not lower because the design decisions are sound. However, F08 (no mutex), F15 (blocking event loop), F16 (no 401 retry), F18 (no timeout), and F33 (5xx treated as fatal) are four independent ways the auth flow breaks under real-world conditions. A score of 5 reflects "correct design, inadequate implementation of the hard parts."

### Test Coverage — 2/10

49% line coverage with 2 entire files never executing and 14 tests failing on every run. The 49% coverage number is misleading — the two files that never run cover 41% of the uncovered lines. `export.py` has 9% coverage. The async client has 42% coverage. The critical behaviors — concurrent refresh, file I/O, auto-pagination for 3 of 4 entity types, network timeout handling, 401 retry — are either failing or untested. This score would be a 1 except that `test_auth.py` is genuinely well-constructed for the cases it covers.

### Type Safety — 6/10

Pydantic v2 models with `ConfigDict(frozen=True)` is the right foundation. `type_defs.py` with TypedDicts is a good pattern. Mypy reports 20 errors in source files (not counting 105 in test files). The most serious type errors are in `export.py` (runtime crashes, not just warnings). Missing return types on `__iter__`, missing arg types on `__exit__`, and `Any` returns from `_request()` are real gaps. The `Optional` field handling on `WorkoutZoneDuration` (F10) is a type modeling failure that causes runtime breakage, not just a mypy warning.

### Error Handling — 4/10

The exception hierarchy is well-designed: `WhoopError → WhoopAuthError → WhoopTokenError` and `WhoopAPIError → WhoopValidationError` are clean and catchable. That design is good. But the implementation undercuts it: `WhoopNetworkError` is never raised (F20), `WhoopNotFoundError` does not exist (F21), `is_retryable_error()` therefore never returns `True` for network errors, 401 responses never trigger a refresh-and-retry (F16), and 5xx errors during refresh force full re-auth (F33). The hierarchy promises retryable network errors and catchable 404s; the runtime delivers neither.

### Code Quality — 6/10

No `TODO`/`FIXME` comments. No bare `except:`. No `# type: ignore`. HTTP session reuse is correct. Logging uses the standard `logging` module throughout except for one `print()` call (F39). The duplicate pagination loops (F41) and duplicate `_format_date_param()` (F40) are genuine code quality problems in two large files. The `export.py` module has multiple runtime-crashing bugs that suggest it was written and never executed against real data. The dead constants `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` (F65) imply an unimplemented feature was planned and abandoned.

### Documentation — 6/10

Docstrings are present on all public methods in both client classes. The README exists and is reasonably comprehensive. The examples directory has three working examples. Deductions: docstrings claim limit range `1-50` when the actual maximum is 25 (F28); rate limit docstring says "per hour" but is per minute (F42); `sport_id` is marked "deprecated" in the model when it is the primary field (F30); `WhoopNetworkError` is described as a retryable error but the implementation never raises it (F20). The documentation describes a contract that the implementation does not honor.

### Production Readiness — 2/10

The SDK cannot retrieve any data (F01). Export functions crash (F09, F19, F38). The async client blocks its event loop during token refresh (F15). The test suite has a 19% failure rate and two files that never run. No CI configuration exists. Phantom runtime dependencies inflate install footprint (F51). No retry logic despite constants implying it exists. A developer running this in production would encounter a 404 on the first API call, an `AttributeError` on the first export attempt, and a hung process on the first abandoned auth flow.

---

## 4. Work Streams

### Stream A: Critical Fixes
*Must fix before anything else. The SDK does not function without these.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F01 | Fix all endpoint paths from `/developer/v2/` to `/developer/v1/` in `constants.py` |
| 2 | F04 | Fix `Workout` model: make `sport_id` required `int`, remove `sport_name` as required field (or add as computed property via `SPORT_NAMES` lookup) |
| 3 | F03 | Fix `MAX_PAGE_LIMIT` from 50 to 25 |
| 4 | F09 | Fix `export.py:410` and `export.py:715`: `cycle.score.score` → `cycle.score.strain` |
| 5 | F19 | Fix `export_sleep_csv()`: replace `stages.get(...)` dict-style access with proper attribute access on `StageSummary` |
| 6 | F10 | Fix all 6 `WorkoutZoneDuration` zone fields to `Optional[int] = Field(None, ...)` |
| 7 | F02 | Fix `revoke_access()`: use `POST /oauth/oauth2/revoke` instead of `DELETE /developer/v2/user/access` |
| 8 | F05 | Fix `CycleStrain` import in `test_models.py:29` and `test_export.py:35` to `CycleScore` — unblocks two entire test files |
| 9 | F06 | Fix stale test fixtures: correct integer IDs to UUID strings, fix `get_recovery()` → `get_recovery_for_cycle()`, add missing `sport_id` to workout fixture |
| 10 | F07 | Add `conftest.py` with `sys.path` setup (or install package) and add CI configuration |

---

### Stream B: API Completeness
*Endpoint and model correctness gaps that affect data integrity.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F11 | Change `RecoveryScore.resting_heart_rate` from `int` to `float` |
| 2 | F12 | Change `RecoveryScore.hrv_rmssd_milli` constraint from `gt=0` to `ge=0` |
| 3 | F13 | Change `get_sleep(sleep_id: int)` to `get_sleep(sleep_id: str)` with non-empty string check |
| 4 | F14 | Change `get_workout(workout_id: int)` to `get_workout(workout_id: str)` with non-empty string check |
| 5 | F29 | Change `SleepScore.respiratory_rate` constraint from `gt=0` to `ge=0` |
| 6 | F31 | Change `score_state` on all four entity models from bare `str` to `Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]` |
| 7 | F28 | Fix 8 docstrings claiming limit range `1-50` to `1-25` |
| 8 | F30 | Fix `sport_id` deprecation comment in `Workout` model |
| 9 | F38 | Filter `None` values before `sum()` in `export.py:662–664` |
| 10 | F53 | Remove orphaned `"sleep_for_cycle"` from `ENDPOINTS` dict |
| 11 | F54 | Remove dead `SleepStage` model |

---

### Stream C: Auth Hardening
*OAuth and token lifecycle reliability for concurrent and long-running use.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F08 | Add `threading.Lock` to `OAuthHandler.get_valid_token()` / `refresh_access_token()` to prevent concurrent double-refresh |
| 2 | F15 | Make `AsyncWhoopClient` token refresh async: use `httpx.AsyncClient` for refresh requests, or add an `asyncio.Lock` and an async `get_valid_token()` |
| 3 | F18 | Set `server.timeout` on the callback `HTTPServer` before calling `handle_request()` (2-minute timeout recommended) |
| 4 | F16 | Implement single-retry loop in `_request()`: on 401, force-refresh token and retry the request once before raising |
| 5 | F17 | Add `os.chmod(filepath, 0o600)` after writing the token file |
| 6 | F33 | Distinguish 5xx (transient, retryable) from 4xx (fatal) in the token refresh error handler; retry on 5xx before raising `WhoopTokenError` |
| 7 | F34 | Same fix as F33 for the Next.js refresh route |
| 8 | F36 | Add `isTokenExpired()` check to `requireAuth()` in `server.ts` |
| 9 | F35 | Set access token cookie `maxAge` from actual `expires_in` rather than hardcoded 3600 |
| 10 | F32 | Add explicit warning/log when `refresh_token` is absent from token exchange response |
| 11 | F37 | Convert `_CallbackHandler` class-level attributes to instance attributes and thread-scope properly |
| 12 | F72 | Make token file path absolute (resolve relative to user home directory, not CWD) |

---

### Stream D: Test Suite
*Behavioral coverage gaps that leave the codebase unprotected against regression.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F44 | Create `conftest.py` with shared fixtures (`mock_auth`, `mock_recovery_response`, etc.) — prerequisite for all other test work |
| 2 | F23 | Write real file I/O tests for `utils.save_tokens()` and `utils.load_tokens()` including missing-file and corrupted-file paths |
| 3 | F24 | Write test verifying 401 triggers token refresh and request retry |
| 4 | F47 | Write threading test verifying concurrent `get_valid_token()` calls issue at most one refresh request |
| 5 | F46 | Write passing tests for `get_sleep_collection()`, `get_cycle_collection()`, `get_workout_collection()`, `get_all_sleep()`, `get_all_cycles()`, `get_all_workouts()` |
| 6 | F25 | Add test simulating 500 server error raising `WhoopAPIError` |
| 7 | F26 | Add test simulating network timeout raising `WhoopNetworkError` (after F20 is fixed) |
| 8 | F45 | Add test for CSRF state mismatch path in `_wait_for_callback` |
| 9 | F48 | Add tests passing ISO8601 strings to Pydantic models and asserting correct `datetime` parsing |
| 10 | F49 | Add test asserting token is refreshed when it expires within `TOKEN_REFRESH_BUFFER_SECONDS` |
| 11 | F57 | Add tests for `iter_recovery()`, `iter_sleep()`, `iter_cycles()`, `iter_workouts()` generator methods |
| 12 | F58 | Add test for `revoke_access()` |
| 13 | F59 | Add test for `is_retryable_error()` (after F20 is fixed so `WhoopNetworkError` is actually raised) |
| 14 | F60 | Add tests for nullable `zone_duration`, `distance_meter`, and altitude fields on `WorkoutScore` |

---

### Stream E: Code Polish
*Type annotations, error handling, logging, and cleanup. No functional changes.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F20 | Raise `WhoopNetworkError` from `httpx.RequestError` instead of `WhoopAPIError` in both clients |
| 2 | F21 | Add `WhoopNotFoundError(WhoopAPIError)` exception class and handle 404 responses explicitly in `_request()` |
| 3 | F22 | Implement retry-with-exponential-backoff using the existing (currently dead) `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` constants |
| 4 | F42 | Fix rate limit docstring: "per hour" → "per minute"; add constant for 10,000 req/day limit |
| 5 | F43 | Include `response.text` in the 401 error message, consistent with the 400 handler |
| 6 | F39 | Replace `print()` in `auth.py:368` with `logger.info()` |
| 7 | F40 | Extract `_format_date_param()` to a module-level function in `utils.py` |
| 8 | F41 | Extract the pagination loop pattern to a shared utility function |
| 9 | F61 | Add `-> Iterator[T]` return type annotations to all four `__iter__` methods on collection models |
| 10 | F62 | Add `Optional[Type[BaseException]], Optional[BaseException], Optional[TracebackType]` annotations to all `__exit__` / `__aexit__` methods |
| 11 | F63 | Add `cast(dict[str, Any], response.json())` in both `_request()` methods |
| 12 | F64 | Remove unused `ClassVar` import from `models.py` |
| 13 | F65 | Remove dead constants `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` if retry logic (F22) is not implemented, or wire them up if it is |
| 14 | F66 | Replace inline `1 / (1000 * 60 * 60)` with `milliseconds_to_hours()` utility call in `export.py:310` |
| 15 | F67 | Rename `WHOOPPY_LOG_LEVEL` to `WHOOPYY_LOG_LEVEL` in `logger.py` |
| 16 | F74 | Add `__all__` to each sub-module |
| 17 | F56 | Standardize typing imports: use `typing.Dict`/`typing.List` consistently or switch everything to built-in generics |

---

### Stream F: Package Shipping
*Changes required to make the package distributable on PyPI.*

| Priority | ID | Description |
|----------|----|-------------|
| 1 | F51 | Remove `python-dotenv` and `keyring` from `setup.py` install_requires — both are phantom dependencies |
| 2 | F50 | Remove `temp_web/.env.local` from git history and add it to `.gitignore` |
| 3 | F69 | Add `pyproject.toml` with `[build-system]`, `[project]`, and tool configuration sections (consolidates `mypy`, `ruff`, `black` config) |
| 4 | F68 | Add `keywords` argument to `setup.py` (`whoop`, `fitness`, `health`, `api`, `sdk`, `oauth`) |
| 5 | F55 | Add plaintext token storage warning to public README/documentation |
| 6 | F27 | Resolve Next.js vs Python SDK API version split: either update Next.js routes to v1 paths or document the divergence explicitly |
| 7 | F73 | Add `next.config.ts` to `temp_web/` with at minimum security headers |

---

*End of synthesis.*
