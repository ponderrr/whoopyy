# Audit 04: Test Suite Coverage Analysis

**Auditor:** Agent 4 (Claude Sonnet 4.6)
**Date:** 2026-03-14
**Scope:** `/home/frosty/whoopyy/tests/`
**Method:** Manual static analysis + live test execution via venv

---

## 1. Test Execution Results

### Environment Setup Issue

The test suite **cannot be run in the default system environment**. The package is not installed and there is no `conftest.py` to configure the Python path. Running `python -m pytest` naively produces 5 collection errors:

```
ModuleNotFoundError: No module named 'whoopyy'
```

This is a blocking infrastructure failure. The package maps `whoopyy -> src/` via `setup.py` (`package_dir={"whoopyy": "src"}`), but without installing the package first (e.g., `pip install -e .`), all test imports fail. **No CI configuration was found** to automate this.

### Actual Results (After Manual `pip install -e .`)

After installing into a fresh venv:

| File | Collected | Passed | Failed | Errors |
|---|---|---|---|---|
| `test_auth.py` | 23 | 23 | 0 | 0 |
| `test_client.py` | 26 | 18 | 8 | 0 |
| `test_async_client.py` | 25 | 17 | 8 | 0 |
| `test_models.py` | — | — | — | **COLLECTION ERROR** |
| `test_export.py` | — | — | — | **COLLECTION ERROR** |
| **TOTAL** | 74 | **60** | **14** | **2 collection errors** |

### Collection Errors (test_models.py, test_export.py)

Both files fail at import with:
```
ImportError: cannot import name 'CycleStrain' from 'whoopyy.models'
```
The test files reference `CycleStrain` (e.g., `tests/test_models.py:29`, `tests/test_export.py:35`), but the actual model class in `src/models.py` is named `CycleScore` (line 609). This means **the entire test_models.py and test_export.py test suites never execute at all**.

### Failures in test_client.py

| Test | Root Cause |
|---|---|
| `TestAuthentication::test_authenticate_success` | Mock auth has `has_valid_tokens()` returning `True`, so `client.authenticate()` skips the `authorize()` call entirely — correct production behavior, wrong test expectation |
| `TestRecoveryMethods::test_get_recovery` | Tests call `client.get_recovery(123)`, but the method is named `get_recovery_for_cycle()` (client.py:441) |
| `TestRecoveryMethods::test_get_recovery_invalid_id` | Same as above |
| `TestRecoveryMethods::test_get_recovery_collection` | Mock fixture passes `sleep_id` as `int` (value `1`), but `Recovery.sleep_id` field is typed `str` in models.py:262 |
| `TestRecoveryMethods::test_get_all_recovery` | Same `sleep_id` int/str mismatch |
| `TestRecoveryMethods::test_get_all_recovery_with_max_records` | Same |
| `TestSleepMethods::test_get_sleep` | Mock passes `id` as `int`, model expects `str`; also `cycle_id` is required but missing from fixture |
| `TestWorkoutMethods::test_get_workout` | Mock passes `id` as `int`, model requires `str`; `sport_name` is required but fixture omits it (uses `sport_id`) |

### Failures in test_async_client.py

Identical pattern to test_client.py — same method name mismatch (`get_recovery` vs `get_recovery_for_cycle`) and same fixture data type mismatches propagated from the shared fixture design.

---

## 2. Coverage Report (Tests That Execute)

From `pytest --cov=whoopyy` across the 3 runnable test files:

| Module | Statements | Covered | Miss | Coverage |
|---|---|---|---|---|
| `src/__init__.py` | 9 | 9 | 0 | **100%** |
| `src/constants.py` | 37 | 37 | 0 | **100%** |
| `src/type_defs.py` | 11 | 11 | 0 | **100%** |
| `src/auth.py` | 170 | 117 | 53 | **69%** |
| `src/models.py` | 321 | 225 | 96 | **70%** |
| `src/client.py` | 265 | 129 | 136 | **49%** |
| `src/async_client.py` | 264 | 112 | 152 | **42%** |
| `src/exceptions.py` | 40 | 23 | 17 | **58%** |
| `src/export.py` | 276 | 24 | 252 | **9%** |
| `src/logger.py` | 32 | 18 | 14 | **56%** |
| `src/utils.py` | 65 | 27 | 38 | **42%** |
| **TOTAL** | 1490 | 732 | 758 | **49%** |

`export.py` is almost entirely uncovered (9%) because `test_export.py` fails at collection.

---

## 3. Behavioral Coverage Checklist

### 3.1 Auth (`test_auth.py`)

| Behavior | Status | Notes |
|---|---|---|
| Auth URL has all required params (`response_type`, `client_id`, `redirect_uri`, `state`, `scope`) | ✅ | `test_build_authorization_url` (line 174), `test_url_contains_all_scopes` (line 186) |
| CSRF state generated and validated | ⚠️ | State is generated via `secrets.token_urlsafe()` in `auth.py:353` but the **uniqueness/randomness** of state is never asserted. `_CallbackHandler` CSRF mismatch path in `_wait_for_callback` (auth.py:448) is not tested. |
| Token exchange success | ✅ | `TestTokenExchange::test_exchange_code_for_tokens_success` (line 201) |
| Token exchange failure | ✅ | `TestTokenExchange::test_exchange_code_for_tokens_http_error` (line 223) |
| Token refresh success | ✅ | `TestTokenRefresh::test_refresh_token_success` (line 258) |
| Refresh with expired refresh token raises `WhoopAuthError` | ⚠️ | Tests cover "no tokens" and "no refresh_token" paths (lines 283, 297), raising `WhoopTokenError`. However `WhoopTokenError` is a subclass of `WhoopAuthError` — the test at line 341 confirms HTTP 401 on refresh raises `WhoopTokenError`, which is the closest case. A true "expired refresh token rejected by server with semantic error" is not tested separately. |
| Concurrent refresh only fires once (thread safety) | ❌ | No threading test exists anywhere in the suite. |
| Token persistence — saves tokens | ⚠️ | `save_tokens` is patched in `test_refresh_token_success` (line 277), confirming it is called, but **the actual file I/O path** is never tested. |
| Token persistence — loads tokens | ⚠️ | `load_tokens` is patched in `test_get_valid_token_from_file` (line 366) and `test_refresh_token_no_tokens_available` (line 283), but real file read is never exercised. |
| Token persistence — handles missing file | ❌ | Never tested. `utils.load_tokens` with a non-existent path is not covered (`utils.py` is only 42% covered). |
| Token persistence — handles corrupted file | ❌ | Never tested. `utils.load_tokens` with malformed JSON is not covered. |
| Proactive expiry check (refresh before token actually expires) | ⚠️ | `test_get_valid_token_auto_refresh` (line 379) uses `expires_at = time.time() - 100` (already expired). The pre-expiry buffer window (`TOKEN_REFRESH_BUFFER_SECONDS` from constants.py) is never tested — i.e., a token expiring in 30 seconds should also be refreshed. |

### 3.2 HTTP Layer (`test_client.py`, `test_async_client.py`)

| Behavior | Status | Notes |
|---|---|---|
| Correct Bearer header format | ✅ | `TestRequest::test_request_adds_auth_header` (client.py test line 210) asserts `"Bearer test_access_token"` |
| 429 raises `WhoopRateLimitError` with `retry_after` | ✅ | `test_request_rate_limit_handling` (line 229), asserts `retry_after == 60` and `status_code == 429` |
| 401 triggers refresh and retry | ❌ | Test at line 246 confirms 401 raises `WhoopAuthError`, but the SDK code (client.py:316) simply raises without attempting a token refresh + retry cycle. Neither the test nor the code implements refresh-on-401. |
| 404 raises `WhoopNotFoundError` | ❌ | `WhoopNotFoundError` does not exist in `src/exceptions.py`. 404 falls through to `response.raise_for_status()` which raises `httpx.HTTPStatusError`, caught and re-wrapped as `WhoopAPIError`. No dedicated 404 test exists. |
| 500 raises `WhoopAPIError` | ⚠️ | No explicit 500 test. The `httpx.HTTPStatusError` catch at client.py:344 covers 5xx, but it is not directly exercised by any test. |
| Network timeout raises appropriate exception | ❌ | `httpx.RequestError` is caught at client.py:359 and re-raised as `WhoopAPIError`, but there is no test that simulates a network timeout or `httpx.TimeoutException`. |

### 3.3 Per-Endpoint Coverage

#### Recovery

| Behavior | Status | Notes |
|---|---|---|
| `get_recovery_for_cycle` returns correct model | ❌ | Test calls `client.get_recovery(123)` (test_client.py:361) — wrong method name. Real method is `get_recovery_for_cycle`. Test fails at runtime. |
| Collection returns paginated list | ❌ | `test_get_recovery_collection` (line 373) fails due to `sleep_id` int/str type mismatch in mock fixture |
| Auto-pagination follows `next_token` until null | ❌ | `test_get_all_recovery` (line 420) fails due to same fixture mismatch |
| Empty collection works | ⚠️ | `TestRecoveryCollection::test_empty_collection` in test_models.py (line 304) tests the model directly, but that file never executes (collection error) |
| Date range filters work | ⚠️ | `test_get_recovery_collection_with_dates` (line 398) passes and does verify params are forwarded, but the request still fails downstream due to fixture mismatch when collection is parsed |
| `PENDING_SCORE` score_state handled | ⚠️ | `TestRecovery::test_is_scored_false_pending` in test_models.py (line 286) tests the model, but that file never executes |
| `UNSCORABLE` score_state handled | ❌ | Not tested anywhere (neither test_models.py, nor test_client.py) |

#### Cycle

| Behavior | Status | Notes |
|---|---|---|
| `get_cycle` returns correct model | ✅ | `TestCycleMethods::test_get_cycle` (line 566) passes — mock uses `id` as int but Cycle model uses `int` for `id` (models.py:685), so no type mismatch here |
| Collection returns paginated list | ❌ | No `get_cycle_collection` test in test_client.py |
| Auto-pagination | ❌ | `get_all_cycles` not tested |
| Empty collection | ❌ | Not tested |
| Date range filters | ❌ | Not tested for cycles |
| `PENDING_SCORE` / `UNSCORABLE` | ❌ | Not tested for cycles |

#### Sleep

| Behavior | Status | Notes |
|---|---|---|
| `get_sleep` returns correct model | ❌ | `TestSleepMethods::test_get_sleep` (line 525) fails — mock passes `id=123` (int) but `Sleep.id` is typed `str` (models.py:543); also `cycle_id` is required but missing from fixture |
| Collection returns paginated list | ❌ | No `get_sleep_collection` test in test_client.py |
| Auto-pagination | ❌ | `get_all_sleep` not tested |
| Empty collection | ❌ | Not tested |
| Date range filters | ❌ | Not tested for sleep |
| `PENDING_SCORE` / `UNSCORABLE` | ❌ | Not tested for sleep in client tests |
| Nap filtering | ⚠️ | `TestExportSleepCsv::test_exclude_naps` (test_export.py:377) tests the export layer, but test_export.py never executes. `TestSleep::test_nap_sleep` (test_models.py:457) tests the model directly, but that file never executes either. |
| Nullable score fields | ⚠️ | `get_sleep` test passes `score=None` but the test itself fails before parsing |

#### Workout

| Behavior | Status | Notes |
|---|---|---|
| `get_workout` returns correct model | ❌ | `TestWorkoutMethods::test_get_workout` (line 602) fails — mock passes `id=123` (int) but `Workout.id` is `str` (models.py:1066); mock omits required `sport_name` field, using `sport_id` instead |
| Collection returns paginated list | ❌ | No `get_workout_collection` test |
| Auto-pagination | ❌ | `get_all_workouts` not tested |
| Empty collection | ❌ | Not tested |
| Date range filters | ❌ | Not tested |
| `PENDING_SCORE` / `UNSCORABLE` | ❌ | Not tested |
| Nullable `zone_duration` | ❌ | Not tested |
| Nullable `distance_meter` / `altitude_gain_meter` | ❌ | Not tested |

### 3.4 Profile

| Behavior | Status | Notes |
|---|---|---|
| `get_profile_basic` returns `UserProfileBasic` | ✅ | `TestProfileMethods::test_get_profile_basic` (line 300) passes, asserts `isinstance` and field values |
| `get_body_measurement` returns `BodyMeasurement` | ✅ | `TestProfileMethods::test_get_body_measurement` (line 319) passes |

### 3.5 Models (`test_models.py`)

**This entire file never executes due to collection error (`CycleStrain` import failure at line 29).**

Despite the failure, a static review of the test content shows:

| Behavior | Status | Notes |
|---|---|---|
| ISO8601 strings parse to `datetime` objects | ⚠️ | Models use `datetime` fields, but test_models.py constructs datetimes directly rather than passing ISO strings and confirming Pydantic parses them. The deserialization path (string → datetime) is only exercised indirectly in test_client.py fixtures (`"2024-01-15T08:00:00.000Z"` in mock responses). |
| Optional fields accept `None` | ✅ | `TestBodyMeasurement::test_optional_fields` (line 104) creates `BodyMeasurement()` with all None. Multiple models pass `score=None`. |
| Invalid data raises `ValidationError` | ✅ | `test_score_above_100_rejected` (line 212), `test_negative_hrv_rejected` (line 232), `test_negative_height_rejected` (line 124), `test_strain_above_21_rejected` (line 544) etc. — but none execute. |

### 3.6 Exceptions

| Behavior | Status | Notes |
|---|---|---|
| All exception types are catchable | ⚠️ | `WhoopRateLimitError`, `WhoopAuthError`, `WhoopValidationError` are exercised. `WhoopNetworkError` and `WhoopAPIError` (for 5xx) are never raised in tests. `WhoopNotFoundError` does not exist. |
| Hierarchy is correct (`WhoopTokenError` isa `WhoopAuthError` isa `WhoopError`) | ⚠️ | The hierarchy exists in code (exceptions.py:90), but no test verifies `isinstance(WhoopTokenError(), WhoopAuthError)` or catches parent types. |
| `is_retryable_error` helper | ❌ | The `is_retryable_error` function (exceptions.py:235) is never tested |

---

## 4. Test Quality Assessment

### What Is Done Well

- **HTTP mocking approach is sound.** Tests consistently use `unittest.mock.patch.object` on `client._http_client.request`, which isolates the HTTP layer correctly without hitting the network. Auth is mocked via `patch("whoopyy.client.OAuthHandler", return_value=mock_auth)`.
- **Test_auth.py is the strongest file.** 23 tests, all passing, good behavioral coverage of initialization, URL building, token exchange, and refresh. Tests check specific error message text and status codes.
- **Pydantic validation tests** (in test_models.py, if it could run) are behavioral — they verify field bounds, not just method existence.
- **Async tests use `pytest.mark.asyncio` correctly** and `AsyncMock` for the async HTTP client.

### Significant Quality Failures

1. **Fixtures are stale relative to the model.** The test fixtures predate the API v2 migration. They pass integer IDs where models now expect UUIDs (strings), and they reference fields (`sleep_id` as int, `sport_id` instead of `sport_name`) that changed. This causes 14 test failures.

2. **Wrong method names.** Tests call `client.get_recovery()` (test_client.py:361) but the method is `get_recovery_for_cycle()` (client.py:441). This is a stale test — it was likely written before a method was renamed and never updated.

3. **No `conftest.py`.** There is no shared fixture configuration file at all. Each test file independently defines its own `mock_auth`, `oauth_handler`, and `mock_profile_response` fixtures with largely identical content. This means:
   - Fixture updates must be made in multiple places
   - The `mock_recovery_collection_response` fixture is duplicated between `test_client.py` (line 100) and `test_async_client.py` (line 72), with slightly different shapes

4. **Model import name is wrong.** `CycleStrain` (imported at test_models.py:29 and test_export.py:35) does not exist — the class is `CycleScore`. Two entire test files are dead.

5. **Tests check structure, not round-trip behavior.** For instance, `test_get_recovery` asserts `isinstance(recovery, Recovery)` and `recovery.cycle_id == 123`, but the full model round-trip (API JSON → Pydantic model with proper UUID `sleep_id`, datetime parsing, etc.) is not exercised because the fixture data is wrong.

6. **No integration-style tests.** There are no tests that exercise the full path: mock HTTP response → `_request()` → model parsing → property access. Every single test that touches a model constructor directly bypasses the serialization layer.

---

## 5. Findings Summary by Severity

### [CRITICAL]

- **C1: test_models.py and test_export.py never execute** — both fail at collection due to `CycleStrain` import (does not exist; class is `CycleScore`). This wipes out all model validation tests and all export tests. `tests/test_models.py:29`, `tests/test_export.py:35`.
- **C2: 14 of 74 tests fail on every run** — due to stale fixtures (int IDs where str expected), wrong method name (`get_recovery` vs `get_recovery_for_cycle`), and missing required field (`sport_name`). These tests provide zero regression protection in their current state.
- **C3: No package installation mechanism for CI** — `import whoopyy` fails without `pip install -e .`. There is no `conftest.py`, no `pytest.ini`, no `pyproject.toml` with testpaths, and no CI configuration to bootstrap the environment.

### [HIGH]

- **H1: Token persistence (save/load/missing/corrupted) is never tested against real file I/O** — all file operations are mocked. A bug in `utils.save_tokens` or `utils.load_tokens` would go undetected. `src/utils.py` is only 42% covered.
- **H2: 401 refresh-and-retry not tested and not implemented** — the SDK raises `WhoopAuthError` on 401 without attempting a token refresh. This is a common real-world scenario (access token expires mid-session). Neither behavior is tested.
- **H3: No test for 500/5xx server errors** — `WhoopAPIError` for server errors is documented and in the exception hierarchy but never tested. `src/exceptions.py:111`.
- **H4: No test for network timeouts** — `httpx.RequestError` (timeout, DNS failure) path exists at client.py:359 but is never exercised. `WhoopNetworkError` exists in `src/exceptions.py:207` but is never raised or tested.
- **H5: `UNSCORABLE` score_state never tested** — `is_scored` property logic in all four entity types (Recovery, Sleep, Cycle, Workout) is partially tested at best, but `UNSCORABLE` is a documented real API state.

### [MEDIUM]

- **M1: No conftest.py for shared fixtures** — fixture duplication across 4 test files. `mock_auth` appears in test_client.py:47, test_async_client.py:38 identically. No shared fixture file exists.
- **M2: CSRF state mismatch path in `_wait_for_callback` not tested** — `auth.py:448` raises `WhoopAuthError("State parameter mismatch")` but this path has no test.
- **M3: Auto-pagination `get_all_*` methods for Sleep, Cycle, and Workout not tested** — only `get_all_recovery` is tested (and it currently fails). `get_all_sleep`, `get_all_cycles`, `get_all_workouts` have zero test coverage.
- **M4: Collection endpoints for Cycle, Sleep, and Workout not tested** in test_client.py — only `get_recovery_collection` is attempted (and fails). Three collection endpoints have zero passing tests.
- **M5: Concurrent token refresh thread safety not tested** — `OAuthHandler` has no locking and `refresh_access_token` is not thread-safe. Not tested and not documented as a limitation.
- **M6: ISO8601 string-to-datetime parsing not directly tested** — tests pass `datetime` objects directly to models rather than ISO strings that would exercise Pydantic's deserialization, which is the actual production code path.
- **M7: Proactive token expiry buffer not tested** — `TOKEN_REFRESH_BUFFER_SECONDS` constant exists but the behavior (refreshing a token that expires within the buffer) is never asserted.

### [LOW]

- **L1: `iter_recovery`, `iter_sleep`, `iter_cycles`, `iter_workouts` generator methods not tested** — these are undocumented entry points with zero coverage.
- **L2: `revoke_access` not tested** — `WhoopClient.revoke_access()` (client.py:1135) has no test.
- **L3: `is_retryable_error` helper function not tested** — `exceptions.py:235`, 0% coverage.
- **L4: `WhoopError.__repr__` not tested** — `exceptions.py:62`. Exception hierarchy correctness (catching parent types) not verified by any `isinstance` assertion.
- **L5: `WorkoutScore.zone_duration` nullable path not tested** — `WorkoutScore.zone_duration` is typed `Optional[WorkoutZoneDuration]` but the None path is never tested.
- **L6: Workout `distance_meter` and altitude fields nullable path not tested** — `WorkoutScore.distance_meter`, `altitude_gain_meter`, `altitude_change_meter` are all `Optional` but null cases not tested.

---

## 6. File-by-File Summary

| File | Lines | Tests | Pass | Fail | Key Missing Behaviors |
|---|---|---|---|---|---|
| `tests/__init__.py` | 2 | — | — | — | Empty |
| `tests/test_auth.py` | 549 | 23 | 23 | 0 | Thread safety, file I/O, CSRF mismatch path, proactive expiry buffer |
| `tests/test_client.py` | 668 | 26 | 18 | 8 | 8 failures (stale fixtures + wrong method name); missing: 404, 500, timeout, cycle/sleep/workout collections, auto-pagination for sleep/cycle/workout |
| `tests/test_async_client.py` | 462 | 25 | 17 | 8 | Same failures as test_client.py duplicated for async; no async context manager teardown for HTTP client |
| `tests/test_models.py` | 700 | 0 | 0 | 0 | **Collection error** — `CycleStrain` import fails; entire file dead |
| `tests/test_export.py` | 508 | 0 | 0 | 0 | **Collection error** — same `CycleStrain` import; entire file dead |

**Overall: 60 passed, 14 failed, 2 collection errors (0 tests run from 2 files), 49% line coverage.**
