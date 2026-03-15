# Elite Upgrade Plan — whoopyy SDK

**Generated:** 2026-03-14
**Author:** Agent 7 (Plan Writer)
**Input:** docs/audit/06_synthesis.md (F01–F74), docs/audit/01_structure.md
**Execution model:** One phase = one PR. Phases within a stream are ordered dependency-first. Stream A executes before all other streams. No phase may be skipped; no implementation detail may be deferred.

---

## Phase 0: Baseline Verification

**Work stream:** None (pre-work)
**Estimated effort:** S
**Dependencies:** None

**Goal:** Establish a clean, documented snapshot of the current broken state so every subsequent phase has a measurable before/after comparison.

**Context:** The repository has never had a CI run recorded, the test suite has at least 14 failing tests and two files that never collect, and mypy reports 20+ source errors. Without capturing this baseline, there is no way to verify that a phase genuinely improved things rather than merely reshuffled failures.

**Implementation:**

1. From the repository root `/home/frosty/whoopyy`, run:
   ```
   pip install -e ".[dev]" 2>&1 | tee docs/audit/baseline_install.txt
   ```
   If `[dev]` extras do not exist yet, run `pip install pytest pytest-asyncio pytest-cov mypy` manually and record the installed versions.

2. Run the full test suite and capture output:
   ```
   pytest --tb=short -q 2>&1 | tee docs/audit/baseline_pytest.txt
   ```
   Record: total collected, passed, failed, error count, coverage percentage if available.

3. Run mypy:
   ```
   mypy src/ --ignore-missing-imports 2>&1 | tee docs/audit/baseline_mypy.txt
   ```
   Record: total error count, files affected.

4. Run mypy on tests:
   ```
   mypy tests/ --ignore-missing-imports 2>&1 | tee docs/audit/baseline_mypy_tests.txt
   ```

5. Create `docs/audit/BASELINE.md` containing:
   - Date and Python version (`python --version`)
   - Full text of `baseline_pytest.txt`
   - Full text of `baseline_mypy.txt`
   - Summary table: tests collected / passed / failed / errored, mypy source errors, mypy test errors
   - Statement: "No fixes applied in this phase."

6. Stage and commit only `docs/audit/` files.

**Files to modify:**
- `docs/audit/BASELINE.md` (create)
- `docs/audit/baseline_install.txt` (create)
- `docs/audit/baseline_pytest.txt` (create)
- `docs/audit/baseline_mypy.txt` (create)
- `docs/audit/baseline_mypy_tests.txt` (create)

**Acceptance criteria:**
- [ ] `docs/audit/BASELINE.md` exists and contains pytest output showing exact pass/fail counts
- [ ] `docs/audit/BASELINE.md` contains mypy output showing exact error count
- [ ] No source files in `src/` or `tests/` were modified
- [ ] Commit contains only files under `docs/audit/`

**Commit message:** `chore: establish audit baseline`

---

## Phase 1: Fix API Endpoint Paths and Page Limit

**Work stream:** A (Critical Fixes)
**Estimated effort:** S
**Dependencies:** Phase 0

**Goal:** Every data endpoint URL resolves to a valid WHOOP API path and auto-pagination never requests more records than the API allows.

**Context:**
- `src/constants.py` lines 36–55: All 10 data endpoint paths use the prefix `/developer/v2/` (e.g., `"profile": "/developer/v2/user/profile/basic"`). The actual WHOOP v1 API is at `/developer/v1/`. Every non-auth call returns HTTP 404.
- `src/constants.py` line 136: `MAX_PAGE_LIMIT = 50`. The WHOOP API maximum page size is 25. Any request using this constant either receives HTTP 400 or silently returns a partial page.
- `src/constants.py` line 38: The `revoke` entry in `ENDPOINTS` points to `/developer/v2/user/access` which is both the wrong path and will be called with `DELETE` (the correct endpoint is `POST /oauth/oauth2/revoke`). This is addressed jointly here because it is in the same constants block; the client-side method fix is in Phase 2.

**Implementation:**

Open `src/constants.py`. Locate the `ENDPOINTS` dictionary (lines 36–55 approximately).

Change every occurrence of `/developer/v2/` in the data endpoint values to `/developer/v1/`. The affected keys are: `profile`, `body_measurement`, `recovery`, `cycle`, `sleep`, `workout`, `sport`, and any others present in the dict that use the v2 prefix.

Specifically, the following entries must be updated (verify exact current values by reading the file):
- `"profile": "/developer/v1/user/profile/basic"`
- `"body_measurement": "/developer/v1/user/measurement/body"`
- `"recovery": "/developer/v1/activity/recovery"`
- `"cycle": "/developer/v1/activity/cycle"`
- `"sleep": "/developer/v1/activity/sleep"`
- `"workout": "/developer/v1/activity/workout"`
- `"sport": "/developer/v1/activity/sport"`

Remove the `"revoke"` key entirely from `ENDPOINTS` — the revoke endpoint belongs to the OAuth base URL, not the API base URL, and will be hardcoded in the client method in Phase 2.

Remove the `"sleep_for_cycle"` key from `ENDPOINTS` — this is dead code (F53); no such endpoint exists in the WHOOP v1 API and no client method references it.

Change `MAX_PAGE_LIMIT = 50` to `MAX_PAGE_LIMIT = 25` on the line where it is defined.

**Tests sub-section:**

Add `tests/test_constants.py` (new file):
- `test_no_v2_in_data_endpoints`: Assert that no value in `ENDPOINTS` contains the substring `/developer/v2/`.
- `test_all_data_endpoints_use_v1`: Assert that every value in `ENDPOINTS` that starts with `/developer` contains `/developer/v1/`.
- `test_max_page_limit_is_25`: Assert `constants.MAX_PAGE_LIMIT == 25`.
- `test_sleep_for_cycle_not_in_endpoints`: Assert `"sleep_for_cycle" not in constants.ENDPOINTS`.
- `test_revoke_not_in_endpoints`: Assert `"revoke" not in constants.ENDPOINTS`.

**Files to modify:**
- `src/constants.py`
- `tests/test_constants.py` (create)

**Acceptance criteria:**
- [ ] `grep -r "/developer/v2/" src/constants.py` returns no matches
- [ ] `constants.ENDPOINTS` values for all data keys begin with `/developer/v1/`
- [ ] `constants.MAX_PAGE_LIMIT == 25`
- [ ] `"sleep_for_cycle" not in constants.ENDPOINTS`
- [ ] `"revoke" not in constants.ENDPOINTS`
- [ ] All 5 new tests in `test_constants.py` pass
- [ ] `pytest tests/test_constants.py -q` exits 0

**Commit message:** `fix: correct API endpoint paths from v2 to v1 and cap page limit at 25`

---

## Phase 2: Fix revoke_access() Method

**Work stream:** A (Critical Fixes)
**Estimated effort:** S
**Dependencies:** Phase 1

**Goal:** `revoke_access()` sends a correctly formed `POST` request to `POST /oauth/oauth2/revoke` with the token in the request body, matching the WHOOP OAuth spec.

**Context:**
- `src/client.py` line 1150: `revoke_access()` currently sends `self._session.delete(self._base_url + ENDPOINTS["revoke"], ...)`. After Phase 1 removes `"revoke"` from `ENDPOINTS`, this will raise a `KeyError`. The correct call is `POST {oauth_base_url}/oauth/oauth2/revoke` with `token=<access_token>` in the request body (standard OAuth 2.0 revocation per RFC 7009).
- `src/async_client.py` line 927: Same incorrect implementation in the async client.
- The OAuth base URL is separate from the API data base URL. Check `src/constants.py` for the `OAUTH_TOKEN_URL` or `AUTH_BASE_URL` constant — the revoke endpoint shares the same base host.

**Implementation:**

In `src/client.py`, locate `revoke_access()`. Replace the body entirely:
- Issue `POST` (not `DELETE`) to the WHOOP token revocation endpoint. Construct the URL as: `{oauth_base_url}/oauth/oauth2/revoke` where `oauth_base_url` is the value already used by `OAuthHandler` for token exchange (check `src/constants.py` for the constant name, likely `OAUTH_TOKEN_URL` base or `AUTH_BASE_URL`).
- Send `data={"token": self._auth_handler.get_valid_token()}` in the POST body (application/x-www-form-urlencoded), plus client credentials if required by the WHOOP server.
- On success (HTTP 200), clear the stored tokens by calling `self._auth_handler.clear_tokens()` if that method exists, or directly deleting the token file via `utils.delete_tokens()` if that helper exists. If neither exists, open the token file path from `constants.TOKEN_FILE_PATH` and delete it with `os.remove()`, catching `FileNotFoundError`.
- Raise `WhoopAuthError` on non-200 responses.

Apply the identical change in `src/async_client.py` `revoke_access()`, using `await self._session.post(...)` instead of the sync equivalent.

**Tests sub-section:**

In `tests/test_client.py`, add:
- `test_revoke_access_sends_post`: Mock the HTTP session; assert that `revoke_access()` calls `session.post` (not `session.delete`) with a URL containing `/oauth/oauth2/revoke`.
- `test_revoke_access_clears_tokens`: After `revoke_access()` succeeds, assert the token file no longer exists (or that the clear method was called).
- `test_revoke_access_raises_on_error`: Mock a 400 response; assert `WhoopAuthError` is raised.

In `tests/test_async_client.py`, add the same three tests using `pytest.mark.asyncio`.

**Files to modify:**
- `src/client.py`
- `src/async_client.py`

**Acceptance criteria:**
- [ ] `revoke_access()` in both clients issues `POST`, not `DELETE`
- [ ] The URL contains `/oauth/oauth2/revoke`
- [ ] The request body contains `token=<access_token>`
- [ ] All 6 new tests pass
- [ ] No `KeyError` on `ENDPOINTS["revoke"]`

**Commit message:** `fix: revoke_access() now POSTs to correct OAuth revocation endpoint`

---

## Phase 3: Fix Workout Model and Export Attribute Errors

**Work stream:** A (Critical Fixes)
**Estimated effort:** S
**Dependencies:** Phase 0

**Goal:** `Workout` model deserializes real WHOOP API responses without `ValidationError`; `export_cycle_csv()` and `export_sleep_csv()` run without `AttributeError`.

**Context:**
- `src/models.py` lines 1073–1074: `Workout` has `sport_name: str` as a required field. The WHOOP API does not return `sport_name` — it returns `sport_id: int`. This causes `ValidationError` on every workout deserialization. Additionally, `sport_name` has a misleading `# deprecated` comment on `sport_id`.
- `src/models.py` lines 793–798: All 6 fields on `WorkoutZoneDuration` (`zone_zero_milli` through `zone_five_milli`) are typed `int` (required). The WHOOP API returns `null` for zones with no data. Every workout with sparse HR zone data fails Pydantic validation.
- `src/export.py` line 410: `cycle.score.score` — the attribute does not exist. The `CycleScore` model's strain field is `.strain`, not `.score`. Raises `AttributeError` on every scored cycle.
- `src/export.py` line 715: Same bug — `cycle.score.score` used again in `analyze_training_load()`.
- `src/export.py` lines 309–315: `stages = sleep.score.stage_summary or {}` followed by `stages.get("total_slow_wave_sleep_milli", 0)` etc. `StageSummary` is a Pydantic model, not a dict. `.get()` does not exist on it. Raises `AttributeError`. Should use direct attribute access: `stages.total_slow_wave_sleep_milli` etc.

**Implementation:**

**`src/models.py` — Workout model:**

Locate the `Workout` model class (around line 1073). Make these changes:
1. Change `sport_id: Optional[int]` to `sport_id: int` (required, no default). Remove any `# deprecated` comment on this field.
2. Remove `sport_name: str` as a required field entirely. Instead, add `sport_name: Optional[str] = None` as an optional computed/alias field if backwards compatibility is desired, or remove it entirely. The safest approach: keep `sport_name` as `Optional[str] = Field(None, description="Deprecated: use sport_id. Not returned by WHOOP API.")`.
3. Fix the misleading docstring/comment on `sport_id` to read: `"Sport identifier returned by the WHOOP API. Use constants.SPORT_NAMES dict for human-readable name lookup."` (or equivalent).

**`src/models.py` — WorkoutZoneDuration model:**

Locate `WorkoutZoneDuration` (around line 793). Change all 6 zone fields from required `int` to `Optional[int]`:
- `zone_zero_milli: Optional[int] = None`
- `zone_one_milli: Optional[int] = None`
- `zone_two_milli: Optional[int] = None`
- `zone_three_milli: Optional[int] = None`
- `zone_four_milli: Optional[int] = None`
- `zone_five_milli: Optional[int] = None`

**`src/export.py` — CycleScore attribute:**

At line 410 (and line 715), change `cycle.score.score` to `cycle.score.strain`. Verify by checking the `CycleScore` model definition in `models.py` to confirm the field name is `strain`.

**`src/export.py` — StageSummary attribute access:**

Locate the block around lines 309–315. Replace the dict-style `.get()` calls with direct attribute access:
- `stages.get("total_slow_wave_sleep_milli", 0)` → `stages.total_slow_wave_sleep_milli or 0`
- `stages.get("total_rem_sleep_milli", 0)` → `stages.total_rem_sleep_milli or 0`
- `stages.get("total_light_sleep_milli", 0)` → `stages.total_light_sleep_milli or 0`
- `stages.get("total_awake_milli", 0)` → `stages.total_awake_milli or 0`
- Apply the same pattern to any other `.get()` call on the `stages` variable in that function.

Check whether `StageSummary` fields are `Optional`; if so, the `or 0` fallback is correct. Verify field names match the Pydantic model definition.

Also fix `src/export.py` lines 662–664 (F38): the optional sleep score fields `sleep_performance_percentage`, `sleep_efficiency_percentage`, and `respiratory_rate` are collected into lists and passed to `sum()` without filtering `None`. Change:
```python
# Before (approximately):
perf_values = [s.score.sleep_performance_percentage for s in sleeps if s.score]
avg_perf = sum(perf_values) / len(perf_values)
# After:
perf_values = [s.score.sleep_performance_percentage for s in sleeps if s.score and s.score.sleep_performance_percentage is not None]
avg_perf = sum(perf_values) / len(perf_values) if perf_values else 0.0
```
Apply the same None-filter pattern to `sleep_efficiency_percentage` and `respiratory_rate` in the same block.

**Tests sub-section:**

In `tests/test_models.py`, add:
- `test_workout_deserializes_with_sport_id`: Build a minimal workout dict with `sport_id=1` and no `sport_name`; assert `Workout.model_validate(data)` succeeds and `.sport_id == 1`.
- `test_workout_sport_name_is_optional`: Assert that a workout dict without `sport_name` parses without error and `.sport_name is None`.
- `test_workout_zone_durations_nullable`: Build a `WorkoutZoneDuration` dict with all zone fields set to `null`/`None`; assert it validates without error.
- `test_workout_zone_durations_with_values`: Build a `WorkoutZoneDuration` dict with all zone fields as integers; assert it validates and all values are accessible.

In `tests/test_export.py`, add:
- `test_export_cycle_csv_no_attribute_error`: Build a mock `Cycle` with a non-None `CycleScore`; call `export_cycle_csv([cycle], ...)` and assert it does not raise `AttributeError`.
- `test_analyze_training_load_no_attribute_error`: Call `analyze_training_load([cycle])` with a scored cycle; assert it returns without `AttributeError`.
- `test_export_sleep_csv_stage_summary_access`: Build a mock `Sleep` with a non-None `SleepScore` with a non-None `StageSummary`; call `export_sleep_csv([sleep], ...)` and assert it does not raise `AttributeError`.
- `test_export_sleep_csv_none_score_fields`: Build a mock `Sleep` where `sleep_performance_percentage` is `None`; assert `export_sleep_csv` completes without `TypeError`.

**Files to modify:**
- `src/models.py`
- `src/export.py`
- `tests/test_models.py`
- `tests/test_export.py`

**Acceptance criteria:**
- [ ] `Workout.model_validate({"sport_id": 44, ...})` succeeds (no `sport_name` required)
- [ ] `WorkoutZoneDuration.model_validate({"zone_zero_milli": None, ...})` succeeds
- [ ] `CycleScore` model has a field named `strain` (not `score`)
- [ ] `export_cycle_csv()` with a scored cycle does not raise `AttributeError`
- [ ] `export_sleep_csv()` with a non-null `StageSummary` does not raise `AttributeError`
- [ ] `export_sleep_csv()` with `None` optional fields does not raise `TypeError`
- [ ] All new tests in `test_models.py` and `test_export.py` pass
- [ ] `grep "cycle\.score\.score" src/export.py` returns no matches

**Commit message:** `fix: Workout model requires sport_id not sport_name; fix zone nullability and export attribute errors`

---

## Phase 4: Fix Test Infrastructure (Import Errors and Stale Fixtures)

**Work stream:** A (Critical Fixes)
**Estimated effort:** M
**Dependencies:** Phase 3

**Goal:** All 74 tests collect without import error and all previously-passing tests continue to pass; the 14 previously-failing tests are fixed and pass.

**Context:**
- `tests/test_models.py` line 29: `from whoopyy.models import CycleStrain` — `CycleStrain` does not exist; the class is `CycleScore`. This causes the entire file to fail at collection with `ImportError`.
- `tests/test_export.py` line 35: Same `from whoopyy.models import CycleStrain` import. Same collection failure.
- `tests/test_client.py`: 8 tests fail because fixtures use integer IDs where models now expect UUID strings (e.g., `cycle_id=1` instead of `cycle_id="abc123-..."`); a call to the non-existent `client.get_recovery()` instead of `client.get_recovery_for_cycle()`; a workout fixture missing `sport_id`.
- `tests/test_async_client.py`: Same 8 fixture/method-name issues as sync client.
- No `conftest.py` exists. `sys.path` is not configured to find `src/whoopyy`. Without `pip install -e .`, `import whoopyy` fails entirely.
- No `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` section, so pytest does not know where tests live or how to configure `asyncio_mode`.

**Implementation:**

**Step 1 — Package installability:**

Ensure `pip install -e .` works by verifying `setup.py` is correct. Then create `tests/conftest.py` with the following content:
```python
import sys
import os
# Ensure src/ is on the path for editable installs that haven't been run
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
```
This is a fallback; the primary mechanism should be `pip install -e .` in CI.

**Step 2 — Fix imports in test_models.py:**

Open `tests/test_models.py` line 29. Change:
```python
from whoopyy.models import CycleStrain
```
to:
```python
from whoopyy.models import CycleScore
```
Search the entire file for any remaining uses of `CycleStrain` and replace with `CycleScore`.

**Step 3 — Fix imports in test_export.py:**

Open `tests/test_export.py` line 35. Change:
```python
from whoopyy.models import CycleStrain
```
to:
```python
from whoopyy.models import CycleScore
```
Search the entire file for any remaining uses of `CycleStrain` and replace with `CycleScore`.

**Step 4 — Fix stale fixtures and method names in test_client.py:**

Open `tests/test_client.py`. Audit every fixture that builds a model instance:
- Anywhere a `cycle_id`, `sleep_id`, `workout_id`, or `recovery_id` is set to an integer (e.g., `1`, `42`), replace with a valid UUID string (e.g., `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`). Check `models.py` to confirm which ID fields are `str` vs `int`.
- Find all calls to `client.get_recovery(...)` and change to `client.get_recovery_for_cycle(...)`. Verify the correct method name by reading `src/client.py`.
- Find all workout fixture dicts that are missing `sport_id`. Add `"sport_id": 44` (any valid integer) to those dicts.
- Verify each fixture dict passes `model_validate` for its corresponding model before using it as a mock response.

**Step 5 — Fix stale fixtures and method names in test_async_client.py:**

Apply all the same changes from Step 4 to `tests/test_async_client.py`.

**Step 6 — Add pytest configuration:**

Create `pytest.ini` in the repository root with:
```ini
[pytest]
testpaths = tests
asyncio_mode = auto
```
This ensures pytest discovers all test files and `pytest-asyncio` handles async tests without per-test `@pytest.mark.asyncio` decorators (or keep the markers and set `asyncio_mode = strict` — choose one and apply consistently).

Alternatively, if `pyproject.toml` is being created in Stream F, add `[tool.pytest.ini_options]` there instead. Since Stream F is separate, use `pytest.ini` for now.

**Step 7 — Add CI configuration:**

Create `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest --tb=short -q
      - run: mypy src/ --ignore-missing-imports
```
Add a `[project.optional-dependencies]` / `extras_require` section to `setup.py` if it does not already exist:
```python
extras_require={
    "dev": ["pytest", "pytest-asyncio", "pytest-cov", "mypy", "httpx"],
}
```

**Tests sub-section:**

No new behavioral tests in this phase — the goal is to make existing tests collect and pass. Verify by running `pytest --tb=short -q` and confirming 0 collection errors and 0 failures among the 74 existing tests (after Phase 3 fixes are included).

**Files to modify:**
- `tests/conftest.py` (create)
- `tests/test_models.py`
- `tests/test_export.py`
- `tests/test_client.py`
- `tests/test_async_client.py`
- `pytest.ini` (create)
- `.github/workflows/ci.yml` (create)
- `setup.py`

**Acceptance criteria:**
- [ ] `pytest --collect-only` exits 0 with no `ImportError` or `CollectionError`
- [ ] `pytest --tb=short -q` exits 0 (all collected tests pass)
- [ ] `grep "CycleStrain" tests/test_models.py tests/test_export.py` returns no matches
- [ ] `grep "get_recovery(" tests/test_client.py tests/test_async_client.py` returns no matches (only `get_recovery_for_cycle`)
- [ ] `pytest.ini` or equivalent config exists and specifies `testpaths = tests`
- [ ] `.github/workflows/ci.yml` exists

**Commit message:** `fix: repair test collection errors, stale fixtures, and missing CI configuration`

---

## Phase 5: Fix Token Refresh Concurrency (Mutex)

**Work stream:** A (Critical Fixes)
**Estimated effort:** M
**Dependencies:** Phase 4

**Goal:** Concurrent callers that simultaneously detect an expired token issue exactly one refresh request; all other callers wait and reuse the result.

**Context:**
- `src/auth.py` lines 652–690: `get_valid_token()` checks expiry and calls `refresh_access_token()` if expired. No lock. With `asyncio.gather()` or multithreaded use, two callers simultaneously see the token as expired, both call `refresh_access_token()`, both send a POST to the token endpoint. If WHOOP rotates refresh tokens (standard OAuth behavior), the second refresh request uses an already-consumed token and receives an error, permanently corrupting the session.
- `src/async_client.py` line 226–234: `_get_auth_headers()` in the async client calls the synchronous `get_valid_token()`, which issues a blocking `httpx.Client` HTTP request on the asyncio event loop thread. This blocks the event loop for the full network round-trip duration of the refresh request.

**Implementation:**

**`src/auth.py` — Add threading lock:**

At the top of the `OAuthHandler` class `__init__` method, add:
```python
self._refresh_lock = threading.Lock()
```
Ensure `import threading` is at the top of the file.

In `get_valid_token()`, wrap the expiry-check-and-refresh block in `with self._refresh_lock:`. The structure should be:
```python
def get_valid_token(self) -> str:
    with self._refresh_lock:
        if self._is_token_expired():
            self.refresh_access_token()
    return self._access_token
```
The lock must cover both the expiry check and the refresh call atomically so that after the first caller refreshes, the second caller re-checks expiry with the new token and skips the refresh.

**`src/auth.py` — Add async-compatible refresh method:**

Add a new method `async_get_valid_token()` to `OAuthHandler`:
```python
async def async_get_valid_token(self) -> str:
    if not hasattr(self, "_async_refresh_lock"):
        self._async_refresh_lock = asyncio.Lock()
    async with self._async_refresh_lock:
        if self._is_token_expired():
            await self._async_refresh_access_token()
    return self._access_token
```

Add `_async_refresh_access_token()` as an async version of `refresh_access_token()` that uses `httpx.AsyncClient` for the token POST request. The logic is identical to the sync version, but uses `async with httpx.AsyncClient() as client:` and `await client.post(...)`.

**`src/async_client.py` — Use async token fetch:**

In `_get_auth_headers()` (or wherever `get_valid_token()` is called in the async client), change:
```python
token = self._auth_handler.get_valid_token()
```
to:
```python
token = await self._auth_handler.async_get_valid_token()
```
Make `_get_auth_headers()` an `async def` method and update all call sites with `await`.

**Tests sub-section:**

In `tests/test_auth.py`, add:
- `test_concurrent_refresh_issues_one_request`: Using `threading.Thread`, spawn 10 threads that simultaneously call `auth_handler.get_valid_token()` on an expired token. Mock the token endpoint to return a new token. Assert the mock was called exactly once (not 10 times).
- `test_second_caller_uses_refreshed_token`: After the first thread refreshes, assert all other threads return the new token without calling the endpoint again.
- `test_async_get_valid_token_uses_asyncio_lock`: Using `asyncio.gather()`, schedule 10 concurrent `async_get_valid_token()` calls on an expired token. Assert the async token endpoint mock was called exactly once.

In `tests/test_async_client.py`, add:
- `test_get_auth_headers_does_not_block_event_loop`: Assert that `_get_auth_headers()` is a coroutine (i.e., `asyncio.iscoroutinefunction(client._get_auth_headers)` is True).

**Files to modify:**
- `src/auth.py`
- `src/async_client.py`
- `tests/test_auth.py`
- `tests/test_async_client.py`

**Acceptance criteria:**
- [ ] `OAuthHandler.__init__` initializes `self._refresh_lock` as a `threading.Lock()`
- [ ] 10 concurrent threads on an expired token produce exactly 1 refresh HTTP request
- [ ] `AsyncWhoopClient._get_auth_headers` is `async def`
- [ ] `OAuthHandler.async_get_valid_token` exists and uses `asyncio.Lock`
- [ ] All new tests pass

**Commit message:** `fix: add threading and asyncio locks to prevent concurrent token refresh race`

---

## Phase 6: Fix Model Type Correctness (Recovery, Sleep, IDs)

**Work stream:** B (API Completeness)
**Estimated effort:** S
**Dependencies:** Phase 4

**Goal:** `RecoveryScore`, `SleepScore`, and all four entity models accurately represent WHOOP API response types; `get_sleep()` and `get_workout()` accept UUID strings.

**Context:**
- `src/models.py` line 189: `RecoveryScore.resting_heart_rate: int`. The WHOOP API returns floats (e.g., `52.3`). Pydantic will coerce and truncate, silently losing precision.
- `src/models.py` line 194: `RecoveryScore.hrv_rmssd_milli: float = Field(..., gt=0)`. The `gt=0` constraint rejects `0.0`, which the API can return for users with very low HRV. Must be `ge=0`.
- `src/models.py` line 451: `SleepScore.respiratory_rate: Optional[float] = Field(None, gt=0)`. Same `gt=0` issue — API can return `0`. Must be `ge=0`.
- `src/models.py` lines 266, 552, 704, 1075: `score_state` on `Cycle`, `Recovery`, `Sleep`, and `Workout` is typed as bare `str`. Should be `Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]` for validation.
- `src/client.py` line 645: `get_sleep(sleep_id: int)` with guard `if sleep_id <= 0`. `Sleep.id` is a UUID `str`. Should be `get_sleep(sleep_id: str)` with guard `if not sleep_id or not sleep_id.strip()`.
- `src/client.py` line 976: `get_workout(workout_id: int)`. Same UUID/int mismatch. Change to `str`.
- `src/async_client.py` lines 547 and 795: Same int-to-str fixes for `get_sleep` and `get_workout`.
- `src/models.py` line 1074: `sport_id` still has an incorrect `# deprecated` comment. Fix to accurately describe the field.

**Implementation:**

**`src/models.py`:**

1. `RecoveryScore.resting_heart_rate`: Change type annotation from `int` to `float`.
2. `RecoveryScore.hrv_rmssd_milli`: Change `Field(..., gt=0)` to `Field(..., ge=0)`.
3. `SleepScore.respiratory_rate`: Change `Field(None, gt=0)` to `Field(None, ge=0)`.
4. Add `from typing import Literal` to imports (or verify it is already imported).
5. On `Cycle` model, change `score_state: str` to `score_state: Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]`.
6. On `Recovery` model, same change.
7. On `Sleep` model, same change.
8. On `Workout` model, same change.
9. Fix the `sport_id` comment: remove the `# deprecated` comment and add a descriptive one instead.

**`src/client.py`:**

1. `get_sleep(sleep_id: int, ...)`: Change parameter to `sleep_id: str`. Change guard from `if sleep_id <= 0: raise ...` to `if not sleep_id or not sleep_id.strip(): raise WhoopValidationError("sleep_id must be a non-empty string")`. Update the URL interpolation if needed (it likely already uses the variable correctly via f-string).
2. `get_workout(workout_id: int, ...)`: Same changes — change to `str`, update guard.

**`src/async_client.py`:**

Apply identical changes to `get_sleep` and `get_workout`.

**Tests sub-section:**

In `tests/test_models.py`, add:
- `test_recovery_score_resting_hr_accepts_float`: `RecoveryScore.model_validate({"resting_heart_rate": 52.3, ...})` asserts `.resting_heart_rate == 52.3`.
- `test_recovery_score_hrv_accepts_zero`: `RecoveryScore.model_validate({"hrv_rmssd_milli": 0.0, ...})` does not raise.
- `test_sleep_score_respiratory_rate_accepts_zero`: `SleepScore.model_validate({"respiratory_rate": 0.0, ...})` does not raise.
- `test_score_state_literal_valid`: Each of `"SCORED"`, `"PENDING_SCORE"`, `"UNSCORABLE"` passes validation on `Cycle`, `Recovery`, `Sleep`, `Workout` models.
- `test_score_state_literal_invalid`: `"INVALID_STATE"` raises `ValidationError` on all four models.

In `tests/test_client.py`, add:
- `test_get_sleep_accepts_uuid_string`: Assert `client.get_sleep("abc-123")` calls the HTTP layer correctly (mock the session).
- `test_get_sleep_rejects_empty_string`: Assert `client.get_sleep("")` raises a validation error.
- `test_get_workout_accepts_uuid_string`: Same pattern for workout.
- `test_get_workout_rejects_empty_string`: Same.

Apply the same 4 tests in `tests/test_async_client.py`.

**Files to modify:**
- `src/models.py`
- `src/client.py`
- `src/async_client.py`
- `tests/test_models.py`
- `tests/test_client.py`
- `tests/test_async_client.py`

**Acceptance criteria:**
- [ ] `RecoveryScore(resting_heart_rate=52.3, ...)` validates without coercion loss
- [ ] `RecoveryScore(hrv_rmssd_milli=0.0, ...)` validates without error
- [ ] `SleepScore(respiratory_rate=0.0, ...)` validates without error
- [ ] `Cycle(score_state="INVALID", ...)` raises `ValidationError`
- [ ] `client.get_sleep(sleep_id: str)` type annotation correct in both client files
- [ ] `grep "sleep_id: int" src/client.py src/async_client.py` returns no matches
- [ ] `grep "workout_id: int" src/client.py src/async_client.py` returns no matches
- [ ] All new tests pass

**Commit message:** `fix: correct RecoveryScore/SleepScore field types, score_state literals, and UUID method signatures`

---

## Phase 7: Fix Token File Security and Callback Timeout

**Work stream:** C (Auth Hardening)
**Estimated effort:** S
**Dependencies:** Phase 4

**Goal:** Token file is created with `600` (owner-only) permissions; the OAuth callback server exits cleanly after a configurable timeout instead of hanging forever.

**Context:**
- `src/utils.py` line 62: Token file is created with `open(filepath, "w")` using the process umask, typically producing world-readable `644` permissions. Access tokens and refresh tokens are readable by any local user on a shared system.
- `src/auth.py` lines 426–432: `_CallbackHandler.handle_request()` is called with no timeout on the underlying `HTTPServer`. If the user never completes the browser OAuth flow, the process hangs indefinitely. `HTTPServer` has a `timeout` attribute that can be set before `handle_request()`.
- `src/constants.py` line 113: `TOKEN_FILE_PATH` is a relative path (`.whoop_tokens.json`). File location depends on the caller's working directory. Should resolve to an absolute path in the user's home directory.

**Implementation:**

**`src/utils.py`:**

In the `save_tokens()` function, after the `with open(filepath, "w") as f: json.dump(...)` block, add:
```python
os.chmod(filepath, 0o600)
```
Ensure `import os` is present at the top of the file.

**`src/constants.py`:**

Change the `TOKEN_FILE_PATH` constant from:
```python
TOKEN_FILE_PATH = ".whoop_tokens.json"
```
to:
```python
TOKEN_FILE_PATH = os.path.join(os.path.expanduser("~"), ".whoop_tokens.json")
```
Add `import os` at the top of `constants.py` if not already present.

**`src/auth.py`:**

Locate the OAuth callback server setup, around lines 426–432. Before calling `server.handle_request()`, set the timeout:
```python
CALLBACK_TIMEOUT_SECONDS = 120  # 2 minutes
server.timeout = CALLBACK_TIMEOUT_SECONDS
server.handle_request()
```
After `handle_request()` returns, check whether the auth code was received. If `server.timeout` elapsed without receiving a request, `handle_request()` returns `None` without setting the auth code. Add a check:
```python
if not self._auth_code:
    raise WhoopAuthError(
        "OAuth callback timed out after 120 seconds. "
        "Please restart the authorization flow."
    )
```
The exact attribute name for the received auth code should match whatever `_CallbackHandler` sets; verify by reading `auth.py` lines 72–74 and 200–204.

**Tests sub-section:**

In `tests/test_auth.py`, add:
- `test_token_file_permissions`: Call `utils.save_tokens({"access_token": "x", "refresh_token": "y"}, filepath=tmp_path/"tokens.json")`. Assert `oct(os.stat(filepath).st_mode)[-3:] == "600"`.
- `test_callback_timeout_raises`: Mock `HTTPServer.handle_request` to return without setting the auth code (simulating a timeout). Assert `WhoopAuthError` is raised.
- `test_token_file_path_is_absolute`: Assert `constants.TOKEN_FILE_PATH` starts with `/` (i.e., is an absolute path).

**Files to modify:**
- `src/utils.py`
- `src/constants.py`
- `src/auth.py`
- `tests/test_auth.py`

**Acceptance criteria:**
- [ ] `save_tokens()` sets file permissions to `0o600` after writing
- [ ] `constants.TOKEN_FILE_PATH` starts with `/` (absolute path)
- [ ] `_wait_for_callback()` raises `WhoopAuthError` after timeout if no code received
- [ ] All 3 new tests pass
- [ ] `grep "\.whoop_tokens\.json\"" src/constants.py` shows absolute path

**Commit message:** `fix: set token file permissions to 600, make path absolute, add callback timeout`

---

## Phase 8: Fix Error Handling — WhoopNetworkError, WhoopNotFoundError, 401 Retry

**Work stream:** E (Code Polish) — CRITICAL/HIGH findings only
**Estimated effort:** M
**Dependencies:** Phase 4

**Goal:** Network failures raise `WhoopNetworkError`, 404 responses raise `WhoopNotFoundError`, and a single 401 mid-flight triggers one automatic token refresh and retry before raising.

**Context:**
- `src/client.py` lines 359–364 and `src/async_client.py` lines 334–339: `httpx.RequestError` (timeout, DNS failure, connection refused) is caught and re-raised as `WhoopAPIError`. `WhoopNetworkError` exists in `exceptions.py` but is never raised. `is_retryable_error()` checks for `WhoopNetworkError` and therefore always returns `False`.
- `src/exceptions.py`: `WhoopNotFoundError` does not exist as a class. 404 responses are wrapped as generic `WhoopAPIError`.
- `src/client.py` lines 315–322 and `src/async_client.py` lines 298–303: 401 responses raise `WhoopAuthError` immediately with no retry. A token that expires in the window between the expiry check and the HTTP dispatch causes a hard error with no recovery path.
- `src/client.py` lines 316–322 and `src/async_client.py` lines 298–303: The 401 error message does not include `response.text`, unlike the 400 handler. Inconsistent and unhelpful for debugging.

**Implementation:**

**`src/exceptions.py`:**

Add the `WhoopNotFoundError` class:
```python
class WhoopNotFoundError(WhoopAPIError):
    """Raised when the WHOOP API returns HTTP 404 Not Found."""
    pass
```
Place it after `WhoopAPIError` in the class hierarchy. Export it in `src/__init__.py`.

**`src/client.py` — `_request()` method:**

1. In the `except httpx.RequestError as e:` block (around line 359), change the re-raise from `raise WhoopAPIError(...)` to `raise WhoopNetworkError(str(e)) from e`.

2. In the 404 handler block, change from raising `WhoopAPIError` to raising `WhoopNotFoundError(f"Resource not found: {response.url}", status_code=404, response_text=response.text)`. If the constructor signature differs, adapt accordingly.

3. In the 401 handler block (lines 315–322), implement single-retry logic:
```python
elif response.status_code == 401:
    if _retry:  # prevent infinite recursion
        raise WhoopAuthError(
            f"Authentication failed after token refresh. "
            f"Status: 401. Response: {response.text}"
        )
    # Force token refresh and retry once
    self._auth_handler.refresh_access_token()
    return self._request(method, url, _retry=True, **kwargs)
```
Add `_retry: bool = False` as a parameter to `_request()`. The `_retry` flag prevents recursive retries.

4. In the 401 handler (whether retry or final raise), include `response.text` in the error message.

**`src/async_client.py` — `_request()` method:**

Apply the identical changes:
1. `except httpx.RequestError` → raise `WhoopNetworkError`.
2. 404 → raise `WhoopNotFoundError`.
3. 401 → single retry with `await self._auth_handler.async_get_valid_token()` forced refresh, then `return await self._request(method, url, _retry=True, **kwargs)`. Include `response.text` in error message.

**`src/exceptions.py`:**

Verify `WhoopNetworkError` already exists. If its constructor does not accept the same arguments as `WhoopAPIError`, normalize: all exception classes should accept at minimum `(message: str)`.

**Tests sub-section:**

In `tests/test_client.py`, add:
- `test_network_error_raises_whoop_network_error`: Mock `httpx.RequestError` being raised by the session. Assert `WhoopNetworkError` is raised (not `WhoopAPIError`).
- `test_404_raises_whoop_not_found_error`: Mock a 404 response. Assert `WhoopNotFoundError` is raised.
- `test_401_triggers_refresh_and_retry`: Mock: first request returns 401; `refresh_access_token` is mocked; second request returns 200. Assert the data method succeeds and `refresh_access_token` was called once.
- `test_401_double_triggers_raises_auth_error`: Mock both requests returning 401. Assert `WhoopAuthError` is raised and `refresh_access_token` was called once (not twice).
- `test_is_retryable_error_true_for_network_error`: Call `is_retryable_error(WhoopNetworkError("timeout"))`. Assert it returns `True`.

Apply identical tests in `tests/test_async_client.py` using async mocks.

**Files to modify:**
- `src/exceptions.py`
- `src/client.py`
- `src/async_client.py`
- `src/__init__.py`
- `tests/test_client.py`
- `tests/test_async_client.py`

**Acceptance criteria:**
- [ ] `WhoopNotFoundError` class exists in `src/exceptions.py` and is exported from `src/__init__.py`
- [ ] `httpx.RequestError` in `_request()` raises `WhoopNetworkError`, not `WhoopAPIError`
- [ ] 404 response raises `WhoopNotFoundError`, not `WhoopAPIError`
- [ ] 401 response triggers exactly one refresh-and-retry before raising
- [ ] `is_retryable_error(WhoopNetworkError(...))` returns `True`
- [ ] 401 error messages include `response.text`
- [ ] All 10 new tests (5 sync + 5 async) pass

**Commit message:** `fix: raise WhoopNetworkError on network failures, add WhoopNotFoundError, implement 401 retry`

---

## Phase 9: Fix Token Refresh Reliability (5xx Retry, Expiry Buffer Tests)

**Work stream:** C (Auth Hardening)
**Estimated effort:** M
**Dependencies:** Phase 5, Phase 8

**Goal:** Transient 5xx errors from the token endpoint are retried up to 3 times before raising `WhoopTokenError`; the proactive expiry buffer is tested and verified.

**Context:**
- `src/auth.py` lines 598–617: Token refresh error handler treats any non-200 response as a fatal `WhoopTokenError`. A 500 or 503 from the WHOOP token server forces full browser re-authentication. The correct behavior is to retry up to 3 times on 5xx before giving up.
- `src/constants.py` lines 123–127: `MAX_RETRIES = 3` and `RETRY_BACKOFF_BASE_SECONDS = 1.0` are defined but never referenced anywhere. These are the appropriate values to use.
- `src/auth.py` line 492: No warning when `refresh_token` is absent from the token exchange response despite `offline` scope being requested.

**Implementation:**

**`src/auth.py` — `refresh_access_token()` method:**

Wrap the token POST request in a retry loop using `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` from `constants.py`. Import them at the top of `auth.py`.

```python
import time
from .constants import MAX_RETRIES, RETRY_BACKOFF_BASE_SECONDS

# Inside refresh_access_token():
for attempt in range(MAX_RETRIES + 1):
    response = httpx.post(token_url, data=token_data, ...)
    if response.status_code == 200:
        break
    if response.status_code >= 500 and attempt < MAX_RETRIES:
        wait = RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
        logger.warning(
            "Token refresh received %d, retrying in %.1fs (attempt %d/%d)",
            response.status_code, wait, attempt + 1, MAX_RETRIES
        )
        time.sleep(wait)
        continue
    # 4xx or exhausted retries: fatal
    raise WhoopTokenError(
        f"Token refresh failed with status {response.status_code}: {response.text}"
    )
```

**`src/auth.py` — Missing refresh_token warning:**

After the successful token exchange (line 492 area), add:
```python
if "refresh_token" not in token_data:
    logger.warning(
        "No refresh_token received from token exchange. "
        "Long-lived sessions will not be possible. "
        "Ensure the 'offline' scope is requested."
    )
```

**`src/auth.py` — `_async_refresh_access_token()` (from Phase 5):**

Apply the same retry loop using `asyncio.sleep(wait)` instead of `time.sleep(wait)`.

**Tests sub-section:**

In `tests/test_auth.py`, add:
- `test_refresh_retries_on_503`: Mock the token endpoint to return 503 twice then 200. Assert `refresh_access_token()` succeeds and the endpoint was called 3 times.
- `test_refresh_raises_after_max_retries`: Mock the token endpoint to return 503 four times. Assert `WhoopTokenError` is raised after `MAX_RETRIES + 1` attempts.
- `test_refresh_fatal_on_4xx`: Mock the token endpoint to return 401. Assert `WhoopTokenError` is raised immediately (no retry).
- `test_missing_refresh_token_logs_warning`: Mock the token endpoint to return a response without `refresh_token`. Assert `logger.warning` is called with a message containing "refresh_token".
- `test_token_refresh_buffer`: Create a token that expires in 30 seconds (less than `TOKEN_REFRESH_BUFFER_SECONDS = 60`). Call `get_valid_token()`. Assert `refresh_access_token` was called (proactive refresh triggered).
- `test_token_refresh_buffer_not_triggered`: Create a token that expires in 300 seconds. Call `get_valid_token()`. Assert `refresh_access_token` was NOT called.

**Files to modify:**
- `src/auth.py`
- `tests/test_auth.py`

**Acceptance criteria:**
- [ ] Token refresh retries up to `MAX_RETRIES` times on 5xx responses
- [ ] Token refresh uses exponential backoff between retries
- [ ] A 4xx response does not retry; raises `WhoopTokenError` immediately
- [ ] Missing `refresh_token` in exchange response logs a warning
- [ ] `TOKEN_REFRESH_BUFFER_SECONDS` behavior is tested and passing
- [ ] All 6 new tests pass

**Commit message:** `fix: retry token refresh on 5xx errors with exponential backoff; warn on missing refresh token`

---

## Phase 10: Improve Test Coverage — File I/O, Pagination, Iterators

**Work stream:** D (Test Suite)
**Estimated effort:** M
**Dependencies:** Phase 4, Phase 6

**Goal:** Token file I/O paths, auto-pagination, collection endpoints, generator iterators, and ISO8601 deserialization all have direct test coverage.

**Context:**
- `src/utils.py` is only 42% covered. `save_tokens()` and `load_tokens()` are only tested with mocks; real file I/O paths (missing file, corrupted JSON) are untested.
- `get_all_sleep()`, `get_all_cycles()`, `get_all_workouts()`, `get_sleep_collection()`, `get_cycle_collection()`, `get_workout_collection()` have zero passing tests.
- `iter_recovery()`, `iter_sleep()`, `iter_cycles()`, `iter_workouts()` generator methods have zero test coverage.
- ISO8601 string-to-datetime deserialization is not tested against string input; only `datetime` objects are passed to models.
- The `conftest.py` created in Phase 4 has no shared fixtures yet; all fixtures are duplicated across test files.

**Implementation:**

**Expand `tests/conftest.py` with shared fixtures:**

Add the following fixtures so all test files can import them:
- `sample_recovery_dict`: Returns a dict matching the WHOOP API recovery response shape, with all required fields populated and valid UUIDs for string ID fields.
- `sample_sleep_dict`: Same for sleep.
- `sample_cycle_dict`: Same for cycle.
- `sample_workout_dict`: Same for workout (includes `sport_id: 44`, all `zone_*_milli` fields as `None`).
- `sample_stage_summary_dict`: For `StageSummary` sub-model.
- `mock_auth_handler`: A `MagicMock` or `patch` of `OAuthHandler` that returns a fixed token.
- `tmp_token_file(tmp_path)`: A `pytest.fixture` that returns a `pathlib.Path` pointing to a temp directory for token file tests.

Remove duplicate fixture definitions from individual test files and replace with imports/usage of the shared ones.

**Create `tests/test_utils.py`:**

New test file with:
- `test_save_tokens_creates_file`: Call `save_tokens(data, filepath)`. Assert the file exists and contains valid JSON matching `data`.
- `test_save_tokens_sets_permissions_600`: Assert `oct(stat(filepath).st_mode & 0o777) == "0o600"`.
- `test_load_tokens_reads_file`: Write a token file with known content. Assert `load_tokens(filepath)` returns the expected dict.
- `test_load_tokens_missing_file_raises`: Call `load_tokens("/nonexistent/path/tokens.json")`. Assert the appropriate exception (check what `utils.py` raises — likely `FileNotFoundError` or `WhoopTokenError`).
- `test_load_tokens_corrupted_json_raises`: Write a file with `{invalid json}`. Assert `load_tokens()` raises `WhoopTokenError` or `json.JSONDecodeError`.
- `test_datetime_helpers`: Test all datetime utility functions in `utils.py` with known inputs and expected outputs.

**Add pagination tests to `tests/test_client.py`:**

- `test_get_sleep_collection_single_page`: Mock one page of results with no `next_token`. Assert `get_sleep_collection()` returns all items and made one HTTP call.
- `test_get_sleep_collection_two_pages`: Mock two pages (first has `next_token`, second does not). Assert `get_sleep_collection()` made two HTTP calls and returned items from both pages.
- `test_get_all_sleep_follows_pagination`: Mock three pages. Assert `get_all_sleep()` returns all items concatenated and made three HTTP calls.
- `test_get_cycle_collection_basic`: One-page mock; assert correct deserialization.
- `test_get_workout_collection_basic`: One-page mock with `sport_id` in fixture; assert correct deserialization.
- `test_get_all_cycles_multi_page`: Two-page mock; assert total count correct.
- `test_get_all_workouts_multi_page`: Two-page mock; assert total count correct.

Apply identical pagination tests in `tests/test_async_client.py` using async mocks.

**Add iterator tests to `tests/test_client.py`:**

- `test_iter_sleep_yields_items`: Mock `get_all_sleep()` to return 3 items. Assert `list(client.iter_sleep())` has 3 items.
- `test_iter_cycles_yields_items`: Same pattern.
- `test_iter_recovery_yields_items`: Same pattern.
- `test_iter_workouts_yields_items`: Same pattern.

**Add ISO8601 deserialization tests to `tests/test_models.py`:**

- `test_cycle_deserializes_iso_string_dates`: Build a cycle dict with `created_at: "2024-01-15T08:30:00.000Z"` as a string. Assert Pydantic parses it to a `datetime` object.
- `test_sleep_deserializes_iso_string_dates`: Same for sleep.
- `test_recovery_deserializes_iso_string_dates`: Same for recovery.
- `test_workout_deserializes_iso_string_dates`: Same for workout.

**Add 5xx and network error tests:**

- `test_500_raises_whoop_api_error` in `tests/test_client.py`: Mock a 500 response. Assert `WhoopAPIError` (not a subtype, just the base API error) is raised.
- `test_network_timeout_raises_whoop_network_error` in `tests/test_client.py`: Already added in Phase 8; verify it exists.

**Files to modify:**
- `tests/conftest.py`
- `tests/test_utils.py` (create)
- `tests/test_client.py`
- `tests/test_async_client.py`
- `tests/test_models.py`

**Acceptance criteria:**
- [ ] `tests/test_utils.py` exists with all 6 utility tests passing
- [ ] `save_tokens` + `load_tokens` real file I/O paths all covered
- [ ] Pagination tests (7 sync + 7 async) all pass
- [ ] Iterator tests (4) all pass
- [ ] ISO8601 deserialization tests (4) all pass
- [ ] `pytest --cov=src --cov-report=term-missing` shows `src/utils.py` at ≥ 85% coverage
- [ ] `conftest.py` contains shared fixtures used by at least 3 test files

**Commit message:** `test: add file I/O, pagination, iterator, and ISO8601 deserialization coverage`

---

## Phase 11: Code Polish — Logging, Duplication, Type Annotations

**Work stream:** E (Code Polish)
**Estimated effort:** M
**Dependencies:** Phase 8

**Goal:** `print()` is removed from library code; duplicated `_format_date_param` and pagination loops are extracted to shared utilities; all public `__iter__`, `__exit__`, and `__aexit__` methods have complete type annotations; unused imports and dead constants are removed.

**Context:**
- `src/auth.py` line 368: `print(...)` call inside library code when `auto_open_browser=False`.
- `src/client.py` lines 366–387 and `src/async_client.py` lines 341–354: `_format_date_param()` is identically implemented in both files.
- `src/client.py` and `src/async_client.py`: The `while True / if not next_token: break` pagination loop is repeated across 16 methods (8 each).
- `src/models.py` lines 313, 600, 754, 1132: `__iter__` return types missing on `RecoveryCollection`, `SleepCollection`, `CycleCollection`, `WorkoutCollection`.
- `src/auth.py` line 744, `src/client.py` line 1182, `src/async_client.py` line 950: `__exit__` / `__aexit__` missing argument type annotations.
- `src/client.py` line 342, `src/async_client.py` line 318: `response.json()` returns `Any` but `_request()` declares `-> dict[str, Any]` — no cast.
- `src/models.py` line 47: `ClassVar` imported but never used.
- `src/constants.py` lines 123–127: `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` are now wired up (Phase 9), so they are no longer dead. If Phase 9 is complete, skip removal. If somehow Phase 9 is not yet done, remove them.
- `src/export.py` line 310: inline `1 / (1000 * 60 * 60)` should use `milliseconds_to_hours()`.
- `src/logger.py` line 65: `WHOOPPY_LOG_LEVEL` environment variable name has double-P; should be `WHOOPYY_LOG_LEVEL`.
- `src/constants.py` line 93: Rate limit docstring says "per hour" but WHOOP's limit is 100 requests per minute.
- `src/client.py` lines 487, 686, 857, 1016 and `src/async_client.py` lines 427, 579, 710, 830: 8 docstrings claim `limit` accepts `1-50`; correct to `1-25`.
- Missing `__all__` in all sub-modules.
- Typing inconsistency: `constants.py` uses `dict[str, str]` (3.9+ built-in generics) while `type_defs.py` uses `Dict` and `List` from `typing`. Standardize to built-in generics throughout since `setup.py` requires `python >= 3.9`.

**Implementation:**

**`src/auth.py` line 368:**
Change `print(f"Open this URL in your browser: {auth_url}")` to `logger.info("Open this URL in your browser: %s", auth_url)`. Verify `logger` is already defined in that module; if not, add `logger = get_logger(__name__)`.

**`src/utils.py` — extract `_format_date_param`:**
Add a module-level function:
```python
def format_date_param(date: Optional[Union[datetime, str]]) -> Optional[str]:
    """Format a date parameter for WHOOP API query strings."""
    if date is None:
        return None
    if isinstance(date, datetime):
        return date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return date  # already a string; caller validates format
```
(Adapt the exact implementation to match what currently exists in both client files.)

**`src/client.py`:**
1. Remove the `_format_date_param` instance method.
2. Import and use `utils.format_date_param` instead.
3. Add `from typing import cast` and change `return response.json()` to `return cast(dict[str, Any], response.json())`.

**`src/async_client.py`:**
1. Remove `_format_date_param` instance method.
2. Import and use `utils.format_date_param`.
3. Add `cast` import and apply to `response.json()`.

**Pagination refactor — `src/utils.py`:**
Add a sync pagination helper:
```python
from typing import TypeVar, Callable, Generator, Optional
T = TypeVar("T")

def paginate(
    fetch_page: Callable[[Optional[str]], tuple[list[T], Optional[str]]]
) -> Generator[T, None, None]:
    """Yield items from paginated API responses."""
    next_token: Optional[str] = None
    while True:
        items, next_token = fetch_page(next_token)
        yield from items
        if not next_token:
            break
```
In each of the 8 collection methods in `src/client.py`, refactor the `while True` loop body to call this helper. The function passed to `paginate` should be a lambda or nested function that calls the raw HTTP method with the given token. Ensure the refactor does not change the public method signatures or return types.

Apply equivalent async pagination helper for `src/async_client.py` using `AsyncGenerator`.

**`src/models.py` — `__iter__` return types:**
Add `from typing import Iterator` if not present. For each collection model's `__iter__` method, add the return type:
- `RecoveryCollection.__iter__` → `def __iter__(self) -> Iterator[Recovery]:`
- `SleepCollection.__iter__` → `def __iter__(self) -> Iterator[Sleep]:`
- `CycleCollection.__iter__` → `def __iter__(self) -> Iterator[Cycle]:`
- `WorkoutCollection.__iter__` → `def __iter__(self) -> Iterator[Workout]:`

**`src/auth.py`, `src/client.py`, `src/async_client.py` — `__exit__` / `__aexit__` annotations:**
Add full type annotations:
```python
from types import TracebackType
from typing import Optional, Type

def __exit__(
    self,
    exc_type: Optional[Type[BaseException]],
    exc_val: Optional[BaseException],
    exc_tb: Optional[TracebackType],
) -> None:
```
For `__aexit__`, same signature but `async def`.

**`src/models.py`:**
Remove `ClassVar` from imports if it is genuinely unused (grep first).

**`src/export.py` line 310:**
Change `/ (1000 * 60 * 60)` to use `milliseconds_to_hours()`. Import `milliseconds_to_hours` from `utils` if not already imported.

**`src/logger.py` line 65:**
Change `WHOOPPY_LOG_LEVEL` to `WHOOPYY_LOG_LEVEL` in the `os.getenv()` call and in any docstring/comment that references it.

**`src/constants.py` — docstring and limit fixes:**
Change the rate limit comment from "per hour" to "per minute". Add a constant `MAX_DAILY_REQUESTS = 10_000` with a comment.

**Docstrings — limit `1-50` → `1-25`:**
In `src/client.py` at lines 487, 686, 857, 1016 and `src/async_client.py` at lines 427, 579, 710, 830, change all occurrences of `limit: int = 25, max value 50` (or similar phrasing) to state `max value 25`.

**`src/type_defs.py`:**
Change `from typing import Dict, List` usages to `dict` and `list` built-in generics. E.g., `Dict[str, Any]` → `dict[str, Any]`, `List[str]` → `list[str]`. Remove the `Dict` and `List` imports from `typing` once all references are updated.

**Add `__all__` to each sub-module:**
In each of `src/auth.py`, `src/client.py`, `src/async_client.py`, `src/constants.py`, `src/exceptions.py`, `src/export.py`, `src/logger.py`, `src/models.py`, `src/type_defs.py`, `src/utils.py`, add an `__all__` list at the module level listing every public name (classes, functions, constants) that consumers should be able to import.

**Tests sub-section:**

In `tests/test_client.py`, add:
- `test_format_date_param_datetime_input`: Call `utils.format_date_param(datetime(2024, 1, 15, 8, 30, 0))`. Assert result is `"2024-01-15T08:30:00.000Z"`.
- `test_format_date_param_string_passthrough`: Call `utils.format_date_param("2024-01-15T08:30:00.000Z")`. Assert result is the same string.
- `test_format_date_param_none_returns_none`: Call `utils.format_date_param(None)`. Assert result is `None`.

**Files to modify:**
- `src/auth.py`
- `src/client.py`
- `src/async_client.py`
- `src/utils.py`
- `src/models.py`
- `src/export.py`
- `src/logger.py`
- `src/constants.py`
- `src/type_defs.py`
- `src/auth.py`, `src/client.py`, `src/async_client.py`, `src/constants.py`, `src/exceptions.py`, `src/export.py`, `src/logger.py`, `src/models.py`, `src/type_defs.py`, `src/utils.py` (add `__all__`)
- `tests/test_client.py`

**Acceptance criteria:**
- [ ] `grep "print(" src/auth.py` returns no matches in library code
- [ ] `_format_date_param` appears only in `src/utils.py`, not in `src/client.py` or `src/async_client.py`
- [ ] All 4 collection model `__iter__` methods have `-> Iterator[T]` return types
- [ ] All `__exit__` / `__aexit__` methods have full arg type annotations
- [ ] `grep "ClassVar" src/models.py` returns no matches (if unused)
- [ ] `grep "WHOOPPY_LOG_LEVEL" src/logger.py` returns no matches
- [ ] `grep "1-50" src/client.py src/async_client.py` returns no matches in docstrings
- [ ] All sub-modules have `__all__` defined
- [ ] `mypy src/ --ignore-missing-imports` shows fewer errors than baseline
- [ ] All 3 new `format_date_param` tests pass

**Commit message:** `refactor: extract shared date/pagination utilities, fix type annotations, remove dead code`

---

## Phase 12: Package Distribution — pyproject.toml, Dependencies, Security

**Work stream:** F (Package Shipping)
**Estimated effort:** M
**Dependencies:** Phase 11

**Goal:** Package builds cleanly with `python -m build`, installs only genuine runtime dependencies, has a modern `pyproject.toml`, and does not commit secrets.

**Context:**
- `setup.py` `install_requires` contains `python-dotenv` and `keyring` — both are imported nowhere in `src/`. Every user installs two phantom dependencies.
- No `pyproject.toml` exists. Modern packaging requires or strongly prefers it.
- `temp_web/.env.local` is committed to the repository with a weak `SESSION_SECRET` (`development_secret_key_12345`). Even mock credentials in git are a bad practice.
- `setup.py` has no `keywords` field, reducing PyPI discoverability.
- `src/utils.py` plaintext token storage is documented in-source but not warned about in public documentation.

**Implementation:**

**`setup.py`:**
1. Remove `"python-dotenv"` and `"keyring"` from `install_requires`.
2. Add `keywords=["whoop", "fitness", "health", "api", "sdk", "oauth", "wearable"]` to the `setup()` call.
3. Verify the remaining `install_requires` entries are actually imported in `src/`. The expected genuine dependencies are: `httpx`, `pydantic`, and any others verified by grep.

**Create `pyproject.toml`:**
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "whoopyy"
version = "0.1.0"
description = "Python SDK for the WHOOP API"
requires-python = ">=3.9"
# Keep install_requires in setup.py for now; this section is for tooling config

[tool.mypy]
python_version = "3.11"
strict = false
ignore_missing_imports = true
warn_unused_ignores = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py39"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I"]

[tool.black]
line-length = 100
target-version = ["py39"]
```
Once `pyproject.toml` is created, remove `pytest.ini` if it was created in Phase 4 (consolidate into `pyproject.toml`).

**`temp_web/.env.local`:**
Remove from git tracking:
```
git rm --cached temp_web/.env.local
```
Add to `.gitignore`:
```
temp_web/.env.local
temp_web/.env*.local
```
Create `temp_web/.env.local.example` (if `temp_web/.env.example` does not already cover it) documenting the required keys with placeholder values.

**README plaintext token warning:**
In the project's top-level `README.md`, add a security note section that explicitly states: "Access tokens and refresh tokens are stored in plaintext JSON at `~/.whoop_tokens.json`. On multi-user systems, ensure this file's permissions are set to `600` (the SDK does this automatically). Do not commit this file."

**`temp_web/` — Next.js route API version alignment (F27):**
All five data proxy routes in `temp_web/app/api/whoop/` (cycles, profile, recovery, sleep, workouts) hardcode `/developer/v1/`. The Python SDK was incorrectly at `v2` and is now fixed back to `v1` in Phase 1. Verify the Next.js routes and the Python SDK now agree. If the Next.js routes are at `v1`, no change needed. If they are at a different version, align them to `v1`.

**`temp_web/next.config.ts`:**
Create with minimum security headers:
```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
```

**Tests sub-section:**

In `tests/test_constants.py` (from Phase 1), add:
- `test_no_phantom_dependencies`: Programmatically parse `setup.py` or import `setuptools` and assert `python-dotenv` and `keyring` are not in `install_requires`. (Alternative: just grep in CI — acceptable to leave this as a CI check rather than a unit test.)

**Files to modify:**
- `setup.py`
- `pyproject.toml` (create)
- `pytest.ini` (remove, contents moved to `pyproject.toml`)
- `.gitignore`
- `temp_web/.env.local` (remove from tracking)
- `temp_web/next.config.ts` (create)
- `README.md`
- `temp_web/app/api/whoop/cycles/route.ts` (verify version, fix if needed)
- `temp_web/app/api/whoop/profile/route.ts` (verify version, fix if needed)
- `temp_web/app/api/whoop/recovery/route.ts` (verify version, fix if needed)
- `temp_web/app/api/whoop/sleep/route.ts` (verify version, fix if needed)
- `temp_web/app/api/whoop/workouts/route.ts` (verify version, fix if needed)

**Acceptance criteria:**
- [ ] `python -m build` exits 0 and produces a `.tar.gz` and `.whl` in `dist/`
- [ ] `pip install dist/whoopyy-*.whl` does not install `python-dotenv` or `keyring`
- [ ] `pyproject.toml` exists with `[tool.mypy]`, `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.black]` sections
- [ ] `git ls-files temp_web/.env.local` returns empty (file not tracked)
- [ ] `temp_web/.env.local` in `.gitignore`
- [ ] `temp_web/next.config.ts` exists
- [ ] README contains a security note about token file plaintext storage
- [ ] `grep "python-dotenv" setup.py` returns no match in `install_requires`

**Commit message:** `chore: add pyproject.toml, remove phantom deps, gitignore secrets, add Next.js security headers`

---

## Phase 13: Next.js Auth Hardening

**Work stream:** C (Auth Hardening) — Next.js findings
**Estimated effort:** M
**Dependencies:** Phase 12

**Goal:** The Next.js application correctly detects expired tokens before hitting the API, sets cookie `maxAge` from the actual `expires_in` value, retries transient 5xx token endpoint errors, and does not transmit the OAuth state cookie over plain HTTP in development.

**Context:**
- `temp_web/lib/auth/server.ts` lines 9–16: `requireAuth()` checks for cookie presence but not token expiry. An expired cookie passes the auth guard and causes a 401 at the WHOOP API.
- `temp_web/lib/api/tokens.ts` lines 41–46: Access token cookie `maxAge` is hardcoded to `3600` regardless of the actual `expires_in` returned by the token exchange.
- `temp_web/app/api/whoop/auth/refresh/route.ts` lines 31–34: Transient 5xx errors from the token endpoint are treated as fatal, forcing full re-authentication.
- `temp_web/app/api/whoop/auth/callback/route.ts` line 48: `expires_in` silently defaults to `3600` if absent; should log a warning.
- `temp_web/app/api/whoop/auth/login/route.ts` line 41: `oauth_state` cookie `secure` flag only set in production; transmitted over HTTP in development.

**Implementation:**

**`temp_web/lib/auth/server.ts`:**

Add token expiry detection to `requireAuth()`. The function should:
1. Check if the access token cookie exists (existing logic).
2. Decode the token's `exp` claim (if it is a JWT) or check a separately stored expiry timestamp cookie. The simpler approach: store a separate `token_expires_at` cookie containing the Unix timestamp when the access token expires. Check `Date.now() / 1000 > token_expires_at`.
3. If expired and a refresh token cookie exists, call the refresh endpoint internally before returning the access token.
4. If expired and no refresh token, redirect to login.

Add the `token_expires_at` cookie write to `temp_web/lib/api/tokens.ts` (see below) so it is available here.

**`temp_web/lib/api/tokens.ts`:**

In the function that sets the access token cookie:
1. Change `maxAge: 3600` to `maxAge: expiresIn` where `expiresIn` is passed as a parameter (the actual `expires_in` value from the token response).
2. Also set a separate `token_expires_at` cookie: `cookies().set("token_expires_at", String(Math.floor(Date.now() / 1000) + expiresIn), { httpOnly: true, ... })`.
3. Update all call sites to pass `expires_in` from the token response.

**`temp_web/app/api/whoop/auth/callback/route.ts`:**

At line 48, change the silent default:
```typescript
// Before:
const expiresIn = tokenData.expires_in ?? 3600;
// After:
if (!tokenData.expires_in) {
  console.warn("[WHOOP] Token response missing expires_in; defaulting to 3600");
}
const expiresIn = tokenData.expires_in ?? 3600;
```
Pass `expiresIn` to the token-setting function.

**`temp_web/app/api/whoop/auth/refresh/route.ts`:**

Wrap the token endpoint POST in a retry loop (up to 3 attempts with exponential backoff) for 5xx responses:
```typescript
let lastError: Error | null = null;
for (let attempt = 0; attempt < 3; attempt++) {
  const resp = await fetch(TOKEN_URL, { method: "POST", body: ... });
  if (resp.ok) {
    // handle success
    break;
  }
  if (resp.status >= 500 && attempt < 2) {
    await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)));
    continue;
  }
  // 4xx or exhausted retries
  return NextResponse.json({ error: "Token refresh failed" }, { status: 401 });
}
```

**`temp_web/app/api/whoop/auth/login/route.ts`:**

At line 41, change the `secure` flag to always be `true`:
```typescript
// Before:
secure: process.env.NODE_ENV === "production",
// After:
secure: true,
```
If this breaks local development with plain HTTP, document in the project README that local development should use `https://localhost` (e.g., via `next dev --experimental-https`).

**Files to modify:**
- `temp_web/lib/auth/server.ts`
- `temp_web/lib/api/tokens.ts`
- `temp_web/app/api/whoop/auth/callback/route.ts`
- `temp_web/app/api/whoop/auth/refresh/route.ts`
- `temp_web/app/api/whoop/auth/login/route.ts`

**Acceptance criteria:**
- [ ] `requireAuth()` returns a redirect to login (not the access token) when the stored token is past its expiry timestamp
- [ ] Access token cookie `maxAge` matches the `expires_in` from the token response, not a hardcoded value
- [ ] Token refresh route retries on 5xx up to 3 times
- [ ] `oauth_state` cookie `secure: true` unconditionally
- [ ] Missing `expires_in` in callback logs a warning
- [ ] Manual testing: expiring a token early and refreshing the dashboard page triggers automatic refresh without a login redirect

**Commit message:** `fix: Next.js auth checks token expiry, dynamic maxAge, retry on 5xx, always-secure state cookie`

---

## Phase 14: Final Certification

**Work stream:** All
**Estimated effort:** M
**Dependencies:** All previous phases

**Goal:** The package passes all quality gates required for a production PyPI release: ≥ 90% test coverage, 0 mypy strict errors, clean build, all data types verified against real WHOOP credentials, accurate README, tagged version.

**Context:** All previous phases have fixed functional bugs, hardened auth, improved test coverage, and modernized packaging. This phase performs final validation, corrects any documentation inaccuracies, and tags the release.

**Implementation:**

**Step 1 — Run full test suite with coverage:**
```
pytest --cov=src --cov-report=term-missing --cov-report=html --tb=short -q
```
Coverage must be ≥ 90% overall. Identify any uncovered lines. If any module is below 80%, add targeted tests before proceeding. The HTML report goes to `htmlcov/`; add `htmlcov/` to `.gitignore`.

**Step 2 — Run mypy strict:**
```
mypy src/ --strict --ignore-missing-imports
```
All errors must be resolved. Common remaining errors after Phase 11:
- Any `Any` return types not yet cast
- Missing `Optional` on fields that can be `None`
- Missing return type on any public function

Fix each error directly in the source file. Do not add `# type: ignore` — resolve the root cause.

**Step 3 — Verify package builds:**
```
python -m build
pip install dist/whoopyy-*.whl --dry-run
```
Both must exit 0. Verify the wheel contains all expected files: `src/*.py`, no `tests/` directory, no `.env` files.

**Step 4 — Real credentials integration test:**
Create `tests/integration/test_real_api.py` (skipped by default; runs only when `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, and `WHOOP_REFRESH_TOKEN` environment variables are set):
```python
import pytest, os
from whoopyy import WhoopClient, OAuthHandler

pytestmark = pytest.mark.skipif(
    not os.getenv("WHOOP_REFRESH_TOKEN"),
    reason="Integration tests require real WHOOP credentials"
)

def test_get_profile():
    ...  # assert profile.user_id is a non-empty string

def test_get_recovery_collection():
    ...  # assert returns list, each item is Recovery with valid score_state

def test_get_sleep_collection():
    ...  # assert returns list, each item is Sleep, StageSummary accessible

def test_get_cycle_collection():
    ...  # assert returns list, each item is Cycle with strain accessible

def test_get_workout_collection():
    ...  # assert returns list, each item is Workout with sport_id int

def test_export_cycle_csv(tmp_path):
    ...  # assert CSV file created with correct columns, no AttributeError

def test_export_sleep_csv(tmp_path):
    ...  # assert CSV file created, stage fields populated or None-safe
```

**Step 5 — README accuracy audit:**
Read `README.md` fully. Verify:
- All code examples use the correct method names (`get_recovery_for_cycle`, not `get_recovery`).
- `limit` parameter docs say max 25, not 50.
- OAuth flow instructions are accurate.
- Dependency list matches what is actually in `setup.py` after Phase 12.
- Security note about token file plaintext storage is present.
- Any mention of `sport_name` is updated to reflect that `sport_id` is the primary field.

Make all necessary corrections in `README.md`.

**Step 6 — Update CHANGELOG:**
Add a `## [0.2.0] - 2026-03-14` (or current date) section to `CHANGELOG.md` (create if absent) documenting all breaking changes, fixes, and improvements from Phases 1–13. Key entries:
- BREAKING: `get_sleep(sleep_id)` now accepts `str` not `int`
- BREAKING: `get_workout(workout_id)` now accepts `str` not `int`
- BREAKING: `Workout.sport_name` is no longer required; use `sport_id`
- FIX: API endpoint paths corrected from v2 to v1 (all data calls now succeed)
- FIX: `MAX_PAGE_LIMIT` corrected from 50 to 25
- FIX: `export_cycle_csv()` and `export_sleep_csv()` no longer crash
- FIX: Token file permissions set to 600
- FIX: Concurrent token refresh race condition resolved
- NEW: `WhoopNotFoundError` exception for 404 responses
- NEW: Automatic 401 retry with token refresh
- NEW: `WhoopNetworkError` now raised on network failures

**Step 7 — Tag the release:**
```
git tag -a v0.2.0 -m "Release v0.2.0: fix all critical bugs, harden auth, ≥90% test coverage"
```

**Files to modify:**
- `README.md`
- `CHANGELOG.md` (create or update)
- `setup.py` (bump version to `0.2.0`)
- `src/__init__.py` (bump `__version__ = "0.2.0"`)
- `tests/integration/test_real_api.py` (create)
- `.gitignore` (add `htmlcov/`)

**Acceptance criteria:**
- [ ] `pytest --cov=src --cov-report=term-missing -q` shows overall coverage ≥ 90%
- [ ] `mypy src/ --strict --ignore-missing-imports` exits 0 with 0 errors
- [ ] `python -m build` exits 0 and produces both `.tar.gz` and `.whl`
- [ ] Integration tests pass with real WHOOP credentials (manual verification)
- [ ] `grep "1-50" README.md` returns no matches
- [ ] `grep "get_recovery(" README.md` returns no matches (only `get_recovery_for_cycle`)
- [ ] `CHANGELOG.md` exists with a `[0.2.0]` entry listing breaking changes
- [ ] `git tag -l v0.2.0` shows the tag
- [ ] `src/__init__.py` `__version__` is `"0.2.0"`
- [ ] `setup.py` version is `"0.2.0"`

**Commit message:** `chore: release v0.2.0 — all critical fixes, ≥90% coverage, 0 mypy strict errors`

---

## Phase Summary Table

| Phase | Stream | Severity | Effort | Findings Fixed | Key Outcome |
|-------|--------|----------|--------|---------------|-------------|
| 0 | — | — | S | — | Baseline snapshot created |
| 1 | A | CRITICAL | S | F01, F03, F53 | All data endpoints return valid responses |
| 2 | A | CRITICAL | S | F02 | `revoke_access()` correct |
| 3 | A | CRITICAL | S | F04, F09, F10, F19, F38 | Workout/export deserialization functional |
| 4 | A | CRITICAL | M | F05, F06, F07 | All 74 tests collect and pass, CI exists |
| 5 | A | CRITICAL | M | F08, F15 | Token refresh race condition eliminated |
| 6 | B | HIGH | S | F11, F12, F13, F14, F29, F30, F31 | Models match API types; UUID IDs correct |
| 7 | C | HIGH | S | F17, F18, F72 | Token file secure; callback timeout enforced |
| 8 | E | HIGH | M | F20, F21, F16, F43 | Network/404 errors catchable; 401 auto-retries |
| 9 | C | MEDIUM | M | F33, F34, F32, F49 | Token refresh survives transient 5xx |
| 10 | D | HIGH/MEDIUM | M | F23, F24, F25, F26, F44, F46, F47, F48, F57, F58, F59, F60 | File I/O, pagination, iterators, ISO8601 all tested |
| 11 | E | MEDIUM/LOW | M | F39, F40, F41, F42, F43, F56, F61, F62, F63, F64, F65, F66, F67, F74, F28 | Type-clean, no duplication, no dead code |
| 12 | F | MEDIUM | M | F50, F51, F55, F68, F69, F27, F73 | Package builds, no phantom deps, no secrets |
| 13 | C | MEDIUM | M | F34, F35, F36, F37, F70, F71 | Next.js auth hardened |
| 14 | All | — | M | F22, F45, F52 (partial) | ≥90% coverage, 0 mypy errors, tagged release |

**Total findings addressed:** F01–F74 (all 74)

**Estimated total effort:** 5–8 engineering days for a single developer executing phases sequentially, with Phase 4 and Phase 11 being the most time-intensive.
