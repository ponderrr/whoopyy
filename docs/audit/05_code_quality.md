# Code Quality Audit — WhoopYY SDK

**Agent:** 5 of swarm
**Date:** 2026-03-14
**Scope:** `/home/frosty/whoopyy/src/` — all source modules

---

## 1. Mypy Results

**Command:** `mypy . --ignore-missing-imports --strict`
**Total errors found:** 125 across 12 files

### Source-file errors (20 errors)

| File | Line | Error Type | Message |
|------|------|-----------|---------|
| `src/models.py` | 313 | `no-untyped-def` | `RecoveryCollection.__iter__` missing return type |
| `src/models.py` | 600 | `no-untyped-def` | `SleepCollection.__iter__` missing return type |
| `src/models.py` | 754 | `no-untyped-def` | `CycleCollection.__iter__` missing return type |
| `src/models.py` | 1132 | `no-untyped-def` | `WorkoutCollection.__iter__` missing return type |
| `src/export.py` | 309 | `var-annotated` | `stages` variable needs type annotation |
| `src/export.py` | 312–315 | `union-attr` | `stages.get(...)` — `StageSummary` has no `.get()` method (not a dict) |
| `src/export.py` | 410 | `attr-defined` | `CycleScore` has no attribute `score` (field is `.strain`) |
| `src/export.py` | 662–664 | `arg-type` | `sum()` on `list[float | None]` — Optional fields not filtered |
| `src/export.py` | 715 | `attr-defined` | `CycleScore` has no attribute `score` (field is `.strain`) |
| `src/auth.py` | 194 | `no-untyped-def` | `_CallbackHandler.log_message` missing arg type annotations |
| `src/auth.py` | 744 | `no-untyped-def` | `OAuthHandler.__exit__` missing arg type annotations |
| `src/client.py` | 342 | `no-any-return` | `response.json()` returns `Any`, declared return is `dict[str, Any]` |
| `src/client.py` | 1182 | `no-untyped-def` | `WhoopClient.__exit__` missing arg type annotations |
| `src/async_client.py` | 318 | `no-any-return` | `response.json()` returns `Any`, declared return is `dict[str, Any]` |
| `src/async_client.py` | 950 | `no-untyped-def` | `AsyncWhoopClient.__aexit__` missing arg type annotations |

The remaining 105 errors are exclusively in test files (`tests/test_client.py`, `tests/test_auth.py`, `tests/test_async_client.py`) — unannotated test functions and untyped decorators.

---

## 2. Type Safety

### [HIGH] `CycleScore` attribute mismatch — runtime crash risk

**Files:** `src/export.py:410`, `src/export.py:715`

`CycleScore` defines a field named `strain` (not `score`). Two locations in `export.py` access `cycle.score.score` which will raise `AttributeError` at runtime. The `export_cycle_csv()` function and `analyze_training_load()` function are both affected — these are public API functions.

```python
# export.py:410 — BUG: should be cycle.score.strain
f"{cycle.score.score:.1f}",

# export.py:715 — BUG: should be c.score.strain
strains = [c.score.score for c in scored_cycles if c.score is not None]
```

### [HIGH] `StageSummary` treated as `dict` in `export_sleep_csv()`

**File:** `src/export.py:309–315`

`sleep.score.stage_summary` is typed as `Optional[StageSummary]` (a Pydantic model), but `export_sleep_csv()` falls back to `or {}` and then calls `.get()` on the result — `StageSummary` has no `.get()` method. The fallback branch is dead code for the `StageSummary` case; the empty-dict fallback is never reachable because `StageSummary` is truthy when present. This will crash when `stage_summary` is `None` but other score data is present, because accessing attributes on `{}` via `.get()` would work but the `StageSummary` object would be treated as a dict incorrectly.

```python
stages = sleep.score.stage_summary or {}    # type: StageSummary | dict
light = stages.get("total_light_sleep_time_milli", 0) * ms_to_hours  # AttributeError on StageSummary
```

### [MEDIUM] Optional field values passed to `sum()` without None filtering

**File:** `src/export.py:662–664`

`sleep_performance_percentage`, `sleep_efficiency_percentage`, and `respiratory_rate` are all `Optional[float]` on `SleepScore`. When collected into lists and passed to `sum()`, any `None` values will cause a `TypeError` at runtime.

```python
performances = [s.score.sleep_performance_percentage for s in scored if s.score is not None]
# sleep_performance_percentage is Optional[float] — None values not filtered
average_performance = sum(performances) / len(performances)  # TypeError if any None
```

### [MEDIUM] `__iter__` methods on collection models missing return type annotations

**File:** `src/models.py:313, 600, 754, 1132`

All four collection classes (`RecoveryCollection`, `SleepCollection`, `CycleCollection`, `WorkoutCollection`) define `__iter__` without a return type annotation. Correct annotation would be `-> Iterator[T]`.

### [MEDIUM] `__exit__` / `__aexit__` missing argument type annotations

**Files:** `src/auth.py:744`, `src/client.py:1182`, `src/async_client.py:950`

All three context-manager `__exit__` and `__aexit__` methods use bare `exc_type, exc_val, exc_tb` without type annotations. Correct annotations: `Optional[Type[BaseException]], Optional[BaseException], Optional[TracebackType]`.

### [LOW] `response.json()` returns `Any` — no cast to `dict[str, Any]`

**Files:** `src/client.py:342`, `src/async_client.py:318`

`httpx.Response.json()` has a return type of `Any`. Both `_request()` methods declare `-> dict[str, Any]` but return the bare `Any` value without a cast. Mypy flags this as `no-any-return`.

### [LOW] `Dict`, `List`, `Optional` from `typing` instead of built-in generics

Multiple files import `Dict`, `List`, `Optional` from `typing` rather than using the modern built-in `dict[...]`, `list[...]`, and `X | None` syntax (available since Python 3.10, which is in the supported range). This is a style issue but inconsistent with the `from typing import Final` approach in `constants.py` which uses `dict[str, str]` and `list[str]` directly.

### [LOW] Pydantic version

The SDK uses **Pydantic v2** (`from pydantic import BaseModel, Field, ConfigDict`). `ConfigDict(frozen=True)` is a v2-only API. `pydantic>=2.5.0` is correctly pinned in `setup.py`. This is appropriate.

### [LOW] Missing `__all__` in all sub-modules

Only `src/__init__.py` defines `__all__`. None of the sub-modules (`client.py`, `auth.py`, `models.py`, `exceptions.py`, `export.py`, `utils.py`, `logger.py`, `constants.py`, `type_defs.py`, `async_client.py`) define `__all__`, making wildcard imports and IDE tooling less precise.

### [LOW] `ClassVar` imported but unused

**File:** `src/models.py:47`

`ClassVar` is imported from `typing` but never used.

---

## 3. Error Handling

### Exception Hierarchy Assessment

The hierarchy is:

```
Exception
└── WhoopError
    ├── WhoopAuthError
    │   └── WhoopTokenError
    ├── WhoopAPIError
    │   └── WhoopValidationError
    ├── WhoopRateLimitError
    └── WhoopNetworkError
```

**Gaps relative to the required hierarchy:**

- `WhoopNotFoundError` — **not defined**. The 404 case is not handled in either `_request()` method; a 404 response will pass through `response.raise_for_status()` and be caught as a generic `WhoopAPIError`. Users cannot distinguish "resource not found" from other server errors.
- `WhoopNetworkError` — **defined but never raised** anywhere in the SDK. `httpx.RequestError` (connection timeout, DNS failure, etc.) is caught in `client.py:359` and `async_client.py:334` and re-raised as `WhoopAPIError`, not `WhoopNetworkError`. This makes the exception class dead code and breaks the `is_retryable_error()` classification logic that checks for `WhoopNetworkError`.

### [HIGH] `WhoopNetworkError` never raised — dead exception class

**Files:** `src/client.py:359–364`, `src/async_client.py:334–339`

```python
except httpx.RequestError as e:
    raise WhoopAPIError(f"Request failed: {e}")  # Should be WhoopNetworkError
```

Network-level failures (timeout, connection refused, DNS failure) are classified as `WhoopAPIError`. `is_retryable_error()` in `exceptions.py` explicitly checks `isinstance(error, WhoopNetworkError)` to mark them retryable, but they never arrive as that type. Users implementing retry logic using the SDK's own helper will not retry network errors.

### [HIGH] Missing `WhoopNotFoundError` — no 404 handling

**Files:** `src/client.py:_request()`, `src/async_client.py:_request()`

Neither `_request()` method handles HTTP 404. The response will call `raise_for_status()` which raises `httpx.HTTPStatusError`, caught by the subsequent `except httpx.HTTPStatusError` block and re-raised as a generic `WhoopAPIError`. This is functionally correct but prevents callers from catching specifically "record not found" vs other errors.

### [MEDIUM] Auth errors in `_request()` do not include response body in message

**File:** `src/client.py:316–322`

```python
if response.status_code == 401:
    raise WhoopAuthError(
        "Authentication failed. Please re-authenticate.",
        status_code=401,
    )
```

The response body (which may contain a descriptive error from the API) is not included. Compare with the 400 handler which includes `response.text`. This is inconsistent and makes debugging token issues harder.

The same pattern exists in `async_client.py:298–303`.

### No bare `except:` clauses — PASS

No bare `except:` statements were found in any source file.

### No swallowed `except Exception` — PASS

No `except Exception` clauses exist in the source code. All exception handling targets specific exception types (`httpx.HTTPStatusError`, `httpx.RequestError`, `OSError`, `json.JSONDecodeError`, `ValueError`).

### Error messages include status code and response body — PARTIAL

The `WhoopAPIError` raised from `httpx.HTTPStatusError` includes `e.response.text` and `status_code`. The 400 handler includes `response.text`. The 401 handler does **not** include the response body (see above). The 429 handler does not include the response body. The endpoint is not included in any error message.

---

## 4. Logging

### Logging module usage — PASS

All modules use Python's `logging` module via the `get_logger()` factory in `src/logger.py`. No `print()` calls exist in operational (non-docstring) library code, with **one exception**.

### [MEDIUM] `print()` in library code — `src/auth.py:368`

```python
# src/auth.py:368
print(f"\nPlease visit this URL to authorize:\n{auth_url}\n")
```

This `print()` call is inside the `authorize()` method's `else` branch (when `auto_open_browser=False`). Library code should not write directly to stdout. This should use `logger.info()` or, better, raise the URL in a callback/return value so the calling application can display it.

### Log level usage — PASS

- Requests are logged at `DEBUG` via `logger.debug("Making API request", ...)` in both `client.py:280` and `async_client.py:263`
- Token refreshes are logged at `INFO` via `logger.info("Access token expired, refreshing")` in `auth.py:687`
- Errors are logged at `ERROR` level throughout

### [LOW] Logger env variable name inconsistency

**File:** `src/logger.py:65`

The environment variable is `WHOOPPY_LOG_LEVEL` (double-P), while the package is named `whoopyy`. This is a confusing mismatch.

---

## 5. Rate Limiting

### [HIGH] No proactive rate limiting or automatic retry on 429

The SDK only provides **reactive** handling: when a 429 response is received, `WhoopRateLimitError` is raised with `retry_after` populated from the `Retry-After` header. There is no:

- Proactive throttling (request counting against the 100 req/min or 10,000 req/day limits)
- Automatic retry with backoff after receiving a 429
- Backoff logic of any kind in the request path

`MAX_RETRIES = 3` and `RETRY_BACKOFF_BASE_SECONDS = 1.0` are defined in `constants.py` but **never referenced** anywhere in the codebase. They are dead constants.

### `Retry-After` header is read — PASS

**Files:** `src/client.py:299–303`, `src/async_client.py:281–285`

The `Retry-After` header is read, parsed as int, and stored in `WhoopRateLimitError.retry_after`. A fallback of 60 seconds is applied if parsing fails.

### [MEDIUM] Rate limit constant documents wrong window

**File:** `src/constants.py:92–93`

```python
DEFAULT_RATE_LIMIT_REQUESTS: Final[int] = 100
"""Default rate limit: requests per hour."""
```

WHOOP's actual rate limit is 100 requests **per minute**, not per hour. The constant value is correct but the docstring is wrong. There is no constant for the 10,000 req/day limit.

### [LOW] No exponential backoff implementation

Despite constants `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` being defined, no backoff or retry logic is implemented. The constants are completely unused dead code.

---

## 6. Code Cleanliness

### TODO/FIXME Comments — NONE FOUND

No `TODO`, `FIXME`, `HACK`, or `XXX` comments were found in any source file.

### `# type: ignore` comments — NONE FOUND

No `# type: ignore` comments were found.

### [MEDIUM] Duplicated `_format_date_param()` method

**Files:** `src/client.py:366–387`, `src/async_client.py:341–354`

The `_format_date_param()` method is identically implemented in both `WhoopClient` and `AsyncWhoopClient`. This logic should be extracted to a module-level function in `utils.py` (where `format_datetime` already lives) and imported by both classes.

### [MEDIUM] Duplicated pagination loop pattern (8 occurrences)

The `while True: ... if not collection.next_token: break` pagination pattern is repeated identically in:
- `client.py`: `get_all_recovery`, `iter_recovery`, `get_all_sleep`, `iter_sleep`, `get_all_cycles`, `iter_cycles`, `get_all_workouts`, `iter_workouts`
- `async_client.py`: same 8 methods

This is 16 near-identical loops. A shared pagination utility would significantly reduce this duplication.

### [MEDIUM] `export_cycle_csv()` references non-existent `cycle.score.score`

**File:** `src/export.py:410`

As noted in the type safety section, `CycleScore` has no `.score` attribute — the field is `.strain`. This is not just a type error; it is a runtime `AttributeError` that will crash every call to `export_cycle_csv()` for any scored cycle.

### [LOW] Dead constants `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS`

**File:** `src/constants.py:123–127`

```python
MAX_RETRIES: Final[int] = 3
RETRY_BACKOFF_BASE_SECONDS: Final[float] = 1.0
```

Neither constant is imported or referenced anywhere in the codebase.

### [LOW] `ClassVar` imported but unused in `src/models.py`

**File:** `src/models.py:47`

`ClassVar` is listed in the import but no class variable annotations use it.

### [LOW] Inline magic number `1 / (1000 * 60 * 60)` in `export.py`

**File:** `src/export.py:310`

```python
ms_to_hours = 1 / (1000 * 60 * 60)
```

This is an inline magic conversion. `utils.milliseconds_to_hours()` already exists for this purpose and is not used here.

---

## 7. HTTP Session Management

### Session reuse — PASS

Both `WhoopClient` and `AsyncWhoopClient` create a single `httpx.Client` / `httpx.AsyncClient` instance in `__init__()` stored as `self._http_client` and reuse it for all requests. Connection pooling is correctly maintained across calls.

`OAuthHandler` similarly creates one `httpx.Client` instance in `__init__()` for token operations.

---

## 8. Package Distribution

### `setup.py` completeness

| Field | Present | Value |
|-------|---------|-------|
| `name` | Yes | `whoopyy` |
| `version` | Yes | `0.1.0` |
| `description` | Yes | "Complete Python SDK for Whoop API" |
| `author` | Yes | Robert Ponder |
| `author_email` | Yes | robert.ponder@selu.edu |
| `license` | **Implicit only** — via classifier string; no `license=` keyword argument |
| `python_requires` | Yes | `>=3.9` |
| `classifiers` | Yes | 8 classifiers including dev status, audience, license, Python versions |
| `keywords` | **MISSING** | No `keywords` argument |
| `long_description` | Yes | Reads from `README.md` |
| `url` | Yes | GitHub URL |

### [LOW] No `keywords` field in `setup.py`

**File:** `setup.py`

The `keywords` argument is absent, which reduces discoverability on PyPI. Relevant keywords would include: `whoop`, `fitness`, `health`, `api`, `sdk`, `oauth`.

### [LOW] No `pyproject.toml`

The project uses only `setup.py` with no `pyproject.toml`. Modern Python packaging best practice is to use `pyproject.toml` with `[build-system]` and `[project]` tables (PEP 517/518/621). The absence of `pyproject.toml` means `mypy`, `ruff`, and `black` configurations must be placed in separate config files rather than consolidated.

### LICENSE file — PASS

`/home/frosty/whoopyy/LICENSE` exists. It is a proprietary license (not OSI-approved). The classifier `"License :: Other/Proprietary License"` matches.

### Build test — PASS

```
Successfully built whoopyy-0.1.0.tar.gz and whoopyy-0.1.0-py3-none-any.whl
```

The package builds successfully with `python -m build --no-isolation` after installing `setuptools`.

---

## 9. Summary Table

| # | Severity | Category | Issue | File(s) | Line(s) |
|---|----------|----------|-------|---------|---------|
| 1 | **CRITICAL** | Type Safety / Runtime | `export_cycle_csv()` and `analyze_training_load()` access `CycleScore.score` — field does not exist; always `AttributeError` | `src/export.py` | 410, 715 |
| 2 | **HIGH** | Type Safety / Runtime | `export_sleep_csv()` calls `.get()` on `StageSummary` Pydantic model (not a dict) | `src/export.py` | 309–315 |
| 3 | **HIGH** | Error Handling | `WhoopNetworkError` defined but never raised; network errors (`httpx.RequestError`) are wrapped as `WhoopAPIError`, breaking `is_retryable_error()` | `src/client.py`, `src/async_client.py` | 359–364, 334–339 |
| 4 | **HIGH** | Error Handling | No 404 handler — `WhoopNotFoundError` does not exist; 404 responses indistinguishable from other errors | `src/client.py`, `src/async_client.py` | `_request()` |
| 5 | **HIGH** | Rate Limiting | No proactive throttling, no automatic retry on 429; `MAX_RETRIES` and `RETRY_BACKOFF_BASE_SECONDS` constants are dead code | `src/client.py`, `src/async_client.py`, `src/constants.py` | — |
| 6 | **MEDIUM** | Type Safety / Runtime | Optional sleep score fields (`sleep_performance_percentage`, etc.) not filtered before `sum()` — `TypeError` if any are `None` | `src/export.py` | 662–664 |
| 7 | **MEDIUM** | Logging | `print()` in library code — `authorize()` prints OAuth URL to stdout instead of using logger | `src/auth.py` | 368 |
| 8 | **MEDIUM** | Code Cleanliness | `_format_date_param()` duplicated between `WhoopClient` and `AsyncWhoopClient` | `src/client.py`, `src/async_client.py` | 366–387, 341–354 |
| 9 | **MEDIUM** | Code Cleanliness | 16 near-identical pagination loops across `client.py` and `async_client.py` | `src/client.py`, `src/async_client.py` | Multiple |
| 10 | **MEDIUM** | Rate Limiting | Rate limit docstring states "per hour" but WHOOP limit is 100 req/min; no daily (10,000) limit constant | `src/constants.py` | 93 |
| 11 | **MEDIUM** | Error Handling | 401 error handler does not include `response.text` in message (inconsistent with 400 handler) | `src/client.py`, `src/async_client.py` | 316–322, 298–303 |
| 12 | **LOW** | Type Safety | `__iter__` methods on 4 collection models missing return type annotations | `src/models.py` | 313, 600, 754, 1132 |
| 13 | **LOW** | Type Safety | `__exit__`/`__aexit__` missing arg type annotations in 3 classes | `src/auth.py`, `src/client.py`, `src/async_client.py` | 744, 1182, 950 |
| 14 | **LOW** | Type Safety | `response.json()` returns `Any` but `_request()` declares `dict[str, Any]` — no cast | `src/client.py`, `src/async_client.py` | 342, 318 |
| 15 | **LOW** | Type Safety | `ClassVar` imported but unused | `src/models.py` | 47 |
| 16 | **LOW** | Type Safety | Missing `__all__` in all sub-modules except `__init__.py` | All `src/*.py` except `__init__.py` | — |
| 17 | **LOW** | Code Cleanliness | Dead constants `MAX_RETRIES`, `RETRY_BACKOFF_BASE_SECONDS` — defined but never referenced | `src/constants.py` | 123–127 |
| 18 | **LOW** | Code Cleanliness | Magic millisecond-to-hours inline constant instead of using existing `milliseconds_to_hours()` utility | `src/export.py` | 310 |
| 19 | **LOW** | Logging | `WHOOPPY_LOG_LEVEL` env var name has double-P, inconsistent with package name `whoopyy` | `src/logger.py` | 65 |
| 20 | **LOW** | Distribution | No `keywords` field in `setup.py` | `setup.py` | — |
| 21 | **LOW** | Distribution | No `pyproject.toml` — project uses legacy `setup.py` only | repo root | — |

---

## 10. Mypy Error Count by Type (source files only)

| Error Code | Count | Description |
|-----------|-------|-------------|
| `no-untyped-def` | 8 | Missing type annotations on functions/methods |
| `attr-defined` | 2 | Accessing non-existent attribute (`CycleScore.score`) |
| `union-attr` | 4 | Calling `.get()` on `StageSummary | dict` union |
| `var-annotated` | 1 | Missing type annotation on `stages` variable |
| `no-any-return` | 2 | Returning `Any` from typed function |
| `arg-type` | 3 | `sum()` called with `list[float | None]` |
| **Total (src/)** | **20** | — |
| Total (tests/) | 105 | Unannotated test functions |
| **Grand Total** | **125** | — |
