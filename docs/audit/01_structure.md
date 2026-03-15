# Repository Structure Audit — whoopyy

**Generated:** 2026-03-14
**Auditor:** Agent 1 (Structure Audit)
**Branch:** master
**Working directory:** `/home/frosty/whoopyy`

---

## 1. Discovery Commands Output

### 1.1 Source Files (find output)

```
/home/frosty/whoopyy/examples/async_example.py
/home/frosty/whoopyy/examples/basic_usage.py
/home/frosty/whoopyy/examples/data_export.py
/home/frosty/whoopyy/setup.py
/home/frosty/whoopyy/src/async_client.py
/home/frosty/whoopyy/src/auth.py
/home/frosty/whoopyy/src/client.py
/home/frosty/whoopyy/src/constants.py
/home/frosty/whoopyy/src/exceptions.py
/home/frosty/whoopyy/src/export.py
/home/frosty/whoopyy/src/__init__.py
/home/frosty/whoopyy/src/logger.py
/home/frosty/whoopyy/src/models.py
/home/frosty/whoopyy/src/type_defs.py
/home/frosty/whoopyy/src/utils.py
/home/frosty/whoopyy/temp_web/app/api/whoop/auth/callback/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/auth/login/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/auth/logout/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/auth/refresh/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/cycles/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/profile/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/recovery/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/sleep/route.ts
/home/frosty/whoopyy/temp_web/app/api/whoop/workouts/route.ts
/home/frosty/whoopyy/temp_web/app/(auth)/callback/error/page.tsx
/home/frosty/whoopyy/temp_web/app/(auth)/callback/page.tsx
/home/frosty/whoopyy/temp_web/app/(auth)/layout.tsx
/home/frosty/whoopyy/temp_web/app/(auth)/login/page.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/layout.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/page.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/recovery/page.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/settings/page.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/sleep/page.tsx
/home/frosty/whoopyy/temp_web/app/dashboard/strain/page.tsx
/home/frosty/whoopyy/temp_web/app/error.tsx
/home/frosty/whoopyy/temp_web/app/layout.tsx
/home/frosty/whoopyy/temp_web/app/loading.tsx
/home/frosty/whoopyy/temp_web/app/not-found.tsx
/home/frosty/whoopyy/temp_web/app/page.tsx
/home/frosty/whoopyy/temp_web/components/auth/AuthError.tsx
/home/frosty/whoopyy/temp_web/components/auth/AuthLoadingScreen.tsx
/home/frosty/whoopyy/temp_web/components/auth/DashboardSkeleton.tsx
/home/frosty/whoopyy/temp_web/components/auth/SessionRefreshToast.tsx
/home/frosty/whoopyy/temp_web/components/charts/ChartLegend.tsx
/home/frosty/whoopyy/temp_web/components/charts/CustomTooltip.tsx
/home/frosty/whoopyy/temp_web/components/charts/LineChartComponent.tsx
/home/frosty/whoopyy/temp_web/components/charts/RecoveryGauge.tsx
/home/frosty/whoopyy/temp_web/components/charts/RecoveryTrendChart.tsx
/home/frosty/whoopyy/temp_web/components/charts/SleepChart.tsx
/home/frosty/whoopyy/temp_web/components/charts/StrainChart.tsx
/home/frosty/whoopyy/temp_web/components/charts/WorkoutDistributionChart.tsx
/home/frosty/whoopyy/temp_web/components/layout/PageContainer.tsx
/home/frosty/whoopyy/temp_web/components/layout/PageHeader.tsx
/home/frosty/whoopyy/temp_web/components/layout/ProtectedRoute.tsx
/home/frosty/whoopyy/temp_web/components/layout/TopNav.tsx
/home/frosty/whoopyy/temp_web/components/layout/WidgetGrid.tsx
/home/frosty/whoopyy/temp_web/components/shared/EmptyState.tsx
/home/frosty/whoopyy/temp_web/components/shared/Skeleton.tsx
/home/frosty/whoopyy/temp_web/components/ui/skeleton.tsx
/home/frosty/whoopyy/temp_web/components/ui/spinner.tsx
/home/frosty/whoopyy/temp_web/components/ui/status-badge.tsx
/home/frosty/whoopyy/temp_web/components/widgets/HRVTrendWidget.tsx
/home/frosty/whoopyy/temp_web/components/widgets/MetricWidgetSkeleton.tsx
/home/frosty/whoopyy/temp_web/components/widgets/MetricWidget.tsx
/home/frosty/whoopyy/temp_web/components/widgets/RecoveryWidget.tsx
/home/frosty/whoopyy/temp_web/components/widgets/SleepWidget.tsx
/home/frosty/whoopyy/temp_web/components/widgets/StrainWidget.tsx
/home/frosty/whoopyy/temp_web/components/widgets/WorkoutGridWidget.tsx
/home/frosty/whoopyy/temp_web/lib/api/errors.ts
/home/frosty/whoopyy/temp_web/lib/api/response.ts
/home/frosty/whoopyy/temp_web/lib/api/tokens.ts
/home/frosty/whoopyy/temp_web/lib/auth/context.tsx
/home/frosty/whoopyy/temp_web/lib/auth/errors.ts
/home/frosty/whoopyy/temp_web/lib/auth/server.ts
/home/frosty/whoopyy/temp_web/lib/charts/config.ts
/home/frosty/whoopyy/temp_web/lib/constants.ts
/home/frosty/whoopyy/temp_web/lib/utils/cn.ts
/home/frosty/whoopyy/temp_web/lib/utils/formatters.ts
/home/frosty/whoopyy/temp_web/middleware.ts
/home/frosty/whoopyy/temp_web/package.json
/home/frosty/whoopyy/temp_web/package-lock.json
/home/frosty/whoopyy/temp_web/tsconfig.json
/home/frosty/whoopyy/temp_web/types/whoop.ts
/home/frosty/whoopyy/tests/__init__.py
/home/frosty/whoopyy/tests/test_async_client.py
/home/frosty/whoopyy/tests/test_auth.py
/home/frosty/whoopyy/tests/test_client.py
/home/frosty/whoopyy/tests/test_export.py
/home/frosty/whoopyy/tests/test_models.py
```

### 1.2 Git Log (last 20 commits)

```
fcc5959 fix: migrate SDK from Whoop API v1 to v2
199a9e4 chore: add environment variable example file
90019e7 docs: add README documentation and changelog
a2773f6 test: add comprehensive unit tests
2553f41 docs: add data export example
8afe254 docs: add async usage example
620f72a docs: add basic usage example
9a40872 feat: add package exports and public API
6debf5e feat: add data export utilities and trend analysis
4ad4263 feat: implement async Whoop API client
c230c94 feat: implement synchronous Whoop API client
97641b0 feat: implement OAuth 2.0 authentication handler
793ab38 feat: add Pydantic models for Whoop API data structures
e78ca95 feat: add token management and datetime utilities
fbeca79 feat: add custom exception hierarchy with error classification
d7a6bd1 feat: add configurable logging utility
72e0d18 feat: add TypedDict definitions for API contracts
78bce74 feat: add API constants and OAuth configuration
923d45e docs: add proprietary software license
5a8cd5d chore: add git configuration files
```

### 1.3 Git Branches

```
* master
  remotes/origin/HEAD -> origin/master
  remotes/origin/master
```

Single branch only. No feature branches, no development branch.

---

## 2. Repository Layout

```
whoopyy/
├── .env.example                    # Python SDK environment template
├── setup.py                        # Python package installer
├── src/                            # Python SDK source (maps to package "whoopyy")
│   ├── __init__.py                 # Public API surface, version 0.1.0
│   ├── async_client.py             # AsyncWhoopClient class
│   ├── auth.py                     # OAuthHandler class + _CallbackHandler
│   ├── client.py                   # WhoopClient class (sync)
│   ├── constants.py                # All API constants
│   ├── exceptions.py               # Exception hierarchy
│   ├── export.py                   # CSV export + trend analysis utilities
│   ├── logger.py                   # get_logger() / log utilities
│   ├── models.py                   # Pydantic v2 models for all API entities
│   ├── type_defs.py                # TypedDict raw API contracts
│   └── utils.py                    # Token I/O, datetime helpers
├── tests/                          # Python unit tests
│   ├── __init__.py
│   ├── test_async_client.py
│   ├── test_auth.py
│   ├── test_client.py
│   ├── test_export.py
│   └── test_models.py
├── examples/                       # Usage demonstration scripts
│   ├── async_example.py
│   ├── basic_usage.py
│   └── data_export.py
├── docs/                           # Documentation
│   ├── WHOOP_API_COMPLIANCE.md
│   └── audit/
│       └── 01_structure.md         # (this file)
├── temp_web/                       # Next.js 16 web application
│   ├── .env.example
│   ├── .env.local                  # Real (dev) env — contains mock secrets
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── middleware.ts
│   ├── types/
│   │   └── whoop.ts                # TypeScript API type definitions
│   ├── app/                        # Next.js App Router
│   │   ├── layout.tsx              # Root layout (AuthProvider + SessionRefreshToast)
│   │   ├── page.tsx                # Root redirects to /dashboard
│   │   ├── loading.tsx
│   │   ├── error.tsx
│   │   ├── not-found.tsx
│   │   ├── (auth)/                 # Auth route group
│   │   │   ├── layout.tsx
│   │   │   ├── login/page.tsx
│   │   │   └── callback/
│   │   │       ├── page.tsx
│   │   │       └── error/page.tsx
│   │   ├── dashboard/
│   │   │   ├── layout.tsx          # Server-side requireAuth() guard
│   │   │   ├── page.tsx            # Main dashboard (mock data)
│   │   │   ├── recovery/page.tsx
│   │   │   ├── sleep/page.tsx
│   │   │   ├── strain/page.tsx
│   │   │   └── settings/page.tsx
│   │   └── api/whoop/
│   │       ├── auth/
│   │       │   ├── login/route.ts
│   │       │   ├── callback/route.ts
│   │       │   ├── logout/route.ts
│   │       │   └── refresh/route.ts
│   │       ├── profile/route.ts
│   │       ├── recovery/route.ts
│   │       ├── sleep/route.ts
│   │       ├── cycles/route.ts
│   │       └── workouts/route.ts
│   ├── components/
│   │   ├── auth/
│   │   │   ├── AuthError.tsx
│   │   │   ├── AuthLoadingScreen.tsx
│   │   │   ├── DashboardSkeleton.tsx
│   │   │   └── SessionRefreshToast.tsx
│   │   ├── charts/
│   │   │   ├── ChartLegend.tsx
│   │   │   ├── CustomTooltip.tsx
│   │   │   ├── LineChartComponent.tsx
│   │   │   ├── RecoveryGauge.tsx
│   │   │   ├── RecoveryTrendChart.tsx
│   │   │   ├── SleepChart.tsx
│   │   │   ├── StrainChart.tsx
│   │   │   └── WorkoutDistributionChart.tsx
│   │   ├── layout/
│   │   │   ├── PageContainer.tsx
│   │   │   ├── PageHeader.tsx
│   │   │   ├── ProtectedRoute.tsx
│   │   │   └── TopNav.tsx
│   │   │   └── WidgetGrid.tsx
│   │   ├── shared/
│   │   │   ├── EmptyState.tsx
│   │   │   └── Skeleton.tsx
│   │   ├── ui/
│   │   │   ├── skeleton.tsx
│   │   │   ├── spinner.tsx
│   │   │   └── status-badge.tsx
│   │   └── widgets/
│   │       ├── HRVTrendWidget.tsx
│   │       ├── MetricWidget.tsx
│   │       ├── MetricWidgetSkeleton.tsx
│   │       ├── RecoveryWidget.tsx
│   │       ├── SleepWidget.tsx
│   │       ├── StrainWidget.tsx
│   │       └── WorkoutGridWidget.tsx
│   └── lib/
│       ├── api/
│       │   ├── errors.ts
│       │   ├── response.ts
│       │   └── tokens.ts
│       ├── auth/
│       │   ├── context.tsx
│       │   ├── errors.ts
│       │   └── server.ts
│       ├── charts/
│       │   └── config.ts
│       ├── constants.ts
│       └── utils/
│           ├── cn.ts
│           └── formatters.ts
```

---

## 3. Python SDK — Detailed File Analysis

### 3.1 `src/__init__.py`

**Purpose:** Package entry point. Defines public API surface for `whoopyy`.
**Version:** `0.1.0`
**Author:** Robert Ponder

**Exports (via `__all__`):**
- Clients: `WhoopClient`, `AsyncWhoopClient`
- Auth: `OAuthHandler`
- Exceptions: `WhoopError`, `WhoopAuthError`, `WhoopTokenError`, `WhoopAPIError`, `WhoopValidationError`, `WhoopRateLimitError`, `WhoopNetworkError`, `is_retryable_error`
- User Profile Models: `UserProfileBasic`, `BodyMeasurement`
- Recovery Models: `RecoveryScore`, `Recovery`, `RecoveryCollection`
- Sleep Models: `SleepStage`, `SleepScore`, `Sleep`, `SleepCollection`
- Cycle Models: `CycleScore`, `Cycle`, `CycleCollection`
- Workout Models: `WorkoutZoneDuration`, `WorkoutScore`, `Workout`, `WorkoutCollection`
- Helpers: `format_duration`, `get_sport_name`, `SPORT_NAMES`
- Export utilities: `RecoveryTrends`, `SleepTrends`, `TrainingLoadTrends`, `export_recovery_csv`, `export_sleep_csv`, `export_cycle_csv`, `export_workout_csv`, `analyze_recovery_trends`, `analyze_sleep_trends`, `analyze_training_load`, `generate_summary_report`, `calculate_moving_average`

**Imports from:** `.exceptions`, `.models`, `.auth`, `.client`, `.async_client`, `.export`

---

### 3.2 `src/constants.py`

**Purpose:** All static configuration. No magic numbers; every value is a named `Final` constant.

**Exports (all module-level `Final` constants):**

| Name | Value | Description |
|------|-------|-------------|
| `API_BASE_URL` | `https://api.prod.whoop.com` | Base URL for all API requests |
| `AUTH_BASE_URL` | `https://api.prod.whoop.com/oauth` | OAuth base URL |
| `OAUTH_AUTHORIZE_URL` | `{AUTH_BASE_URL}/oauth2/auth` | Auth redirect URL |
| `OAUTH_TOKEN_URL` | `{AUTH_BASE_URL}/oauth2/token` | Token exchange/refresh URL |
| `ENDPOINTS` | dict[str, str] | 10 endpoint paths, all v2 (`/developer/v2/…`) |
| `SCOPES` | list[str] | 7 OAuth scopes including `offline` |
| `DEFAULT_RATE_LIMIT_REQUESTS` | 100 | Requests per hour |
| `RATE_LIMIT_WINDOW_SECONDS` | 3600 | 1 hour window |
| `TOKEN_EXPIRY_SECONDS` | 3600 | Default token lifetime |
| `TOKEN_REFRESH_BUFFER_SECONDS` | 60 | Proactive refresh buffer |
| `DEFAULT_TOKEN_FILE` | `.whoop_tokens.json` | Token persistence file |
| `DEFAULT_TIMEOUT_SECONDS` | 30.0 | HTTP timeout |
| `MAX_RETRIES` | 3 | Retry attempts |
| `RETRY_BACKOFF_BASE_SECONDS` | 1.0 | Exponential backoff base |
| `DEFAULT_PAGE_LIMIT` | 25 | Default page size |
| `MAX_PAGE_LIMIT` | 50 | Max page size (API constraint) |
| `RECOVERY_GREEN_THRESHOLD` | 67 | Recovery score green zone cutoff |
| `RECOVERY_YELLOW_THRESHOLD` | 34 | Recovery score yellow zone cutoff |

**Imports from:** `typing.Final`

---

### 3.3 `src/type_defs.py`

**Purpose:** TypedDict definitions for internal data contracts (raw API responses, token storage). Not intended for direct user consumption — use Pydantic models instead.

**Exports (TypedDict classes):**

| Class | Fields | Notes |
|-------|--------|-------|
| `TokenData` | `access_token`, `refresh_token`, `expires_in`, `expires_at`, `token_type`, `scope` | OAuth token storage structure |
| `PaginationParams` | `start`, `end`, `limit`, `nextToken` | All optional (`total=False`) |
| `PaginatedResponse` | `records: List[Dict]`, `next_token: Optional[str]` | Standard paginated response |
| `UserProfileBasicResponse` | `user_id`, `email`, `first_name`, `last_name` | Raw profile response |
| `BodyMeasurementResponse` | `height_meter`, `weight_kilogram`, `max_heart_rate` | All optional |
| `RecoveryScoreResponse` | 6 biometric fields | All optional |
| `SleepStageResponse` | 8 duration fields in milliseconds | All required |
| `SleepScoreResponse` | 6 fields including nested `SleepStageResponse` | All optional |
| `CycleScoreResponse` | `strain`, `kilojoule`, `average_heart_rate`, `max_heart_rate` | All optional |
| `WorkoutScoreResponse` | 9 workout metric fields | All optional |

**Imports from:** `typing` (TypedDict, Optional, List, Dict, Any)

---

### 3.4 `src/exceptions.py`

**Purpose:** Custom exception hierarchy with error classification helpers.

**Exception Hierarchy:**
```
Exception
└── WhoopError(message, status_code)
    ├── WhoopAuthError                   → FATAL, re-authenticate
    │   └── WhoopTokenError              → FATAL, re-authenticate
    ├── WhoopAPIError(message, status_code)  → 5xx RETRYABLE, 4xx FATAL
    │   └── WhoopValidationError         → FATAL, fix the request
    ├── WhoopRateLimitError(message, retry_after, status_code)  → RETRYABLE
    └── WhoopNetworkError                → RETRYABLE with backoff
```

**Exported function:**
- `is_retryable_error(error: WhoopError) -> bool` — classifies errors as retryable or fatal

**Imports from:** `typing.Optional`

---

### 3.5 `src/logger.py`

**Purpose:** Centralized logging configuration. Module-level logger cache to prevent duplicate handlers.

**Exported functions:**
- `get_logger(name: str, level: Optional[int] = None) -> logging.Logger` — get/create cached logger. Respects `WHOOPPY_LOG_LEVEL` env var (default: INFO). Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- `set_log_level(level: int) -> None` — dynamically change level for all SDK loggers
- `disable_logging() -> None` — suppress all SDK output (useful for tests)
- `enable_logging() -> None` — re-enable after disabling

**Internal state:** `_loggers: dict[str, logging.Logger]` module-level cache

**Imports from:** `logging`, `os`, `typing.Optional`

---

### 3.6 `src/utils.py`

**Purpose:** Token persistence (plaintext JSON file I/O), token expiry checking, datetime formatting for API compatibility.

**Exported functions:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `save_tokens` | `(tokens: TokenData, filepath: str) -> None` | Write tokens to JSON file |
| `load_tokens` | `(filepath: str) -> Optional[TokenData]` | Read tokens from JSON file; returns None if missing/invalid |
| `delete_tokens` | `(filepath: str) -> bool` | Delete token file; returns True if deleted |
| `is_token_expired` | `(tokens: TokenData, buffer_seconds: int) -> bool` | True if token expires within buffer window |
| `calculate_expiry` | `(expires_in: int) -> float` | Compute Unix timestamp from `expires_in` |
| `format_datetime` | `(dt: datetime) -> str` | ISO 8601 format; naive datetimes assumed UTC |
| `parse_datetime` | `(dt_str: str) -> datetime` | Parse ISO 8601; handles Z suffix |
| `milliseconds_to_hours` | `(milliseconds: int) -> float` | Utility conversion |
| `milliseconds_to_minutes` | `(milliseconds: int) -> float` | Utility conversion |

**Security note:** Tokens are stored as plaintext JSON. The docstring acknowledges this and suggests `keyring` for production use.

**Imports from:** `json`, `time`, `datetime`, `pathlib.Path`, `typing.Optional`, `.constants`, `.logger`, `.type_defs`

---

### 3.7 `src/auth.py`

**Purpose:** Complete OAuth 2.0 authorization code flow. Includes a local HTTP callback server to receive the OAuth redirect.

**Classes:**

**`_CallbackHandler(BaseHTTPRequestHandler)`** (private)
- Embedded HTTP server handler for OAuth callback
- Uses class-level attributes (`auth_code`, `auth_state`, `error`) to share data with caller
- Generates styled HTML success/error pages returned to the browser
- Suppresses default HTTP server logging

**`OAuthHandler`** (public)
- Full OAuth lifecycle management
- Constructor params: `client_id`, `client_secret`, `redirect_uri` (default: `http://localhost:8080/callback`), `scope`, `token_file`, `timeout`
- Uses `httpx.Client` for synchronous HTTP

**Public methods:**

| Method | Description |
|--------|-------------|
| `authorize(auto_open_browser=True) -> TokenData` | Full OAuth flow: builds auth URL, starts local server, waits for callback, exchanges code for tokens, saves to file |
| `refresh_access_token(refresh_token=None) -> TokenData` | POST to token URL with `grant_type=refresh_token` |
| `get_valid_token() -> str` | Load tokens, auto-refresh if expired, return access token string |
| `has_valid_tokens() -> bool` | Check token validity; True if non-expired or refreshable |
| `close() -> None` | Close HTTP client |
| `__enter__` / `__exit__` | Context manager protocol |

**CSRF protection:** State parameter generated with `secrets.token_urlsafe(32)`, verified on callback.

**Imports from:** `secrets`, `webbrowser`, `http.server`, `urllib.parse`, `httpx`, `.constants`, `.exceptions`, `.logger`, `.type_defs`, `.utils`

---

### 3.8 `src/models.py`

**Purpose:** Pydantic v2 models for all Whoop API response entities. All models use `model_config = ConfigDict(frozen=True)` — instances are immutable.

**User Profile Models:**

| Class | Key Fields | Notable Properties |
|-------|-----------|-------------------|
| `UserProfileBasic` | `user_id: int`, `email`, `first_name`, `last_name` | `full_name` property |
| `BodyMeasurement` | `height_meter?`, `weight_kilogram?`, `max_heart_rate?` | `height_feet`, `weight_pounds` conversion properties |

**Recovery Models:**

| Class | Key Fields | Notable Properties |
|-------|-----------|-------------------|
| `RecoveryScore` | `user_calibrating`, `recovery_score: float [0-100]`, `resting_heart_rate`, `hrv_rmssd_milli`, `spo2_percentage?`, `skin_temp_celsius?` | `recovery_zone` → "green"/"yellow"/"red" |
| `Recovery` | `cycle_id`, `sleep_id: str (UUID)`, `user_id`, `created_at`, `updated_at`, `score_state`, `score?: RecoveryScore` | `is_scored` |
| `RecoveryCollection` | `records: List[Recovery]`, `next_token?` | `__len__`, `__iter__` |

**Sleep Models:**

| Class | Key Fields | Notable Properties |
|-------|-----------|-------------------|
| `SleepStage` | `stage_id`, `start_millis`, `end_millis` | `duration_seconds`, `duration_minutes`, `stage_name` |
| `StageSummary` | 8 millisecond duration fields | `total_sleep_time_milli`, `total_sleep_hours`, `in_bed_hours` |
| `SleepNeeded` | 4 millisecond baseline/debt fields | `total_needed_milli`, `total_needed_hours` |
| `SleepScore` | `stage_summary?: StageSummary`, `sleep_needed?: SleepNeeded`, `respiratory_rate?`, 3 percentage scores | `total_sleep_duration_hours`, `deep_sleep_hours`, `rem_sleep_hours`, `light_sleep_hours`, `awake_hours` |
| `Sleep` | `id: str (UUID)`, `cycle_id`, `user_id`, `start`, `end`, `timezone_offset`, `nap: bool`, `score_state`, `score?: SleepScore` | `duration_hours`, `duration_minutes`, `is_scored` |
| `SleepCollection` | `records`, `next_token?` | `__len__`, `__iter__` |

**Cycle (Daily Strain) Models:**

| Class | Key Fields | Notable Properties |
|-------|-----------|-------------------|
| `CycleScore` | `strain: float [0-21]`, `kilojoule`, `average_heart_rate`, `max_heart_rate` | `calories`, `strain_level` → "Light"/"Moderate"/"Strenuous"/"All Out" |
| `Cycle` | `id: int`, `user_id`, `created_at`, `updated_at`, `start`, `end?: datetime`, `timezone_offset`, `score_state`, `score?: CycleScore` | `is_current`, `duration_hours`, `is_scored` |
| `CycleCollection` | `records`, `next_token?` | `__len__`, `__iter__` |

**Workout Models:**

| Class | Key Fields | Notable Properties |
|-------|-----------|-------------------|
| `WorkoutZoneDuration` | 6 HR zone millisecond fields (zone_zero → zone_five) | 6 `*_minutes` properties, `total_minutes` |
| `WorkoutScore` | `strain [0-21]`, `average_heart_rate`, `max_heart_rate`, `kilojoule`, `percent_recorded`, `distance_meter?`, `altitude_gain_meter?`, `altitude_change_meter?`, `zone_duration?: WorkoutZoneDuration` | `calories`, `distance_km`, `distance_miles` |
| `Workout` | `id: str (UUID)`, `user_id`, `created_at`, `updated_at`, `start`, `end`, `timezone_offset`, `sport_name: str`, `sport_id?: int`, `score_state`, `score?: WorkoutScore` | `sport_display_name`, `duration_hours`, `duration_minutes`, `is_scored` |
| `WorkoutCollection` | `records`, `next_token?` | `__len__`, `__iter__` |

**Module-level constants:**
- `SPORT_NAMES: Dict[int, str]` — maps 80+ sport IDs to human-readable names (e.g., `0: "Running"`, `44: "Yoga"`, `101: "Pickleball"`)

**Helper functions:**
- `format_duration(milliseconds: int) -> str` — e.g., `"7h 45m"`
- `get_sport_name(sport_id: int) -> str` — lookup from `SPORT_NAMES`

**Imports from:** `datetime`, `typing`, `pydantic`

---

### 3.9 `src/client.py`

**Purpose:** Synchronous Whoop API client. Primary interface for application code.

**Class: `WhoopClient`**

Constructor params: `client_id`, `client_secret`, `redirect_uri`, `scope`, `token_file`, `timeout`

Internally holds:
- `self.auth: OAuthHandler` — delegates all token management
- `self._http_client: httpx.Client` — base URL set to `API_BASE_URL`, default JSON headers

**Public methods by domain:**

_Authentication:_
- `authenticate(auto_open_browser=True) -> None` — runs OAuth flow (skips if valid tokens exist)
- `is_authenticated() -> bool`

_User Profile:_
- `get_profile_basic() -> UserProfileBasic`
- `get_body_measurement() -> BodyMeasurement`

_Recovery:_
- `get_recovery_for_cycle(cycle_id: int) -> Recovery`
- `get_recovery_collection(start?, end?, limit=25, next_token?) -> RecoveryCollection`
- `get_all_recovery(start?, end?, max_records?) -> List[Recovery]` — auto-paginates
- `iter_recovery(start?, end?) -> Generator[Recovery]` — memory-efficient generator

_Sleep:_
- `get_sleep(sleep_id: int) -> Sleep`
- `get_sleep_collection(...)` / `get_all_sleep(...)` / `iter_sleep(...)`

_Cycles:_
- `get_cycle(cycle_id: int) -> Cycle`
- `get_cycle_collection(...)` / `get_all_cycles(...)` / `iter_cycles(...)`

_Workouts:_
- `get_workout(workout_id: int) -> Workout`
- `get_workout_collection(...)` / `get_all_workouts(...)` / `iter_workouts(...)`

_Access Management:_
- `revoke_access() -> None` — DELETE to `/developer/v2/user/access`

_Lifecycle:_
- `close() -> None`, `__enter__` / `__exit__`

**Internal `_request` method:** Handles 401/400/429/5xx cases, raises typed exceptions. Does NOT implement automatic retry — that is left to the caller.

**Imports from:** `datetime`, `typing`, `httpx`, `.auth`, `.constants`, `.exceptions`, `.logger`, `.models`, `.utils`

---

### 3.10 `src/async_client.py`

**Purpose:** Async/await variant of `WhoopClient`. Same API surface, all data-fetch methods are `async`. Uses `httpx.AsyncClient`.

**Class: `AsyncWhoopClient`**

Mirrors `WhoopClient` exactly with these differences:
- `_http_client: httpx.AsyncClient`
- All data methods are `async def`
- `authenticate()` is **synchronous** (browser interaction cannot be async)
- `iter_*` methods return `AsyncGenerator` using `async for`
- `close()` is `async def` calling `await self._http_client.aclose()`
- Context manager uses `__aenter__` / `__aexit__`

All the same domain method groups: profile, recovery, sleep, cycles, workouts, access management.

**Imports from:** same as `client.py` but `typing.AsyncGenerator` instead of `Generator`

---

### 3.11 `src/export.py`

**Purpose:** Data export to CSV and trend analysis/reporting utilities.

**Data classes (exported):**

| Class | Fields |
|-------|--------|
| `RecoveryTrends` | `average_score`, `min_score`, `max_score`, `average_hrv`, `average_resting_hr`, `green_days`, `yellow_days`, `red_days`, `hrv_coefficient_of_variation`, `recent_trend`, `record_count` |
| `SleepTrends` | `average_duration_hours`, `average_performance`, `average_efficiency`, `average_respiratory_rate`, `consistency_score`, `nights_below_7h`, `nap_count`, `record_count` |
| `TrainingLoadTrends` | `total_strain`, `average_daily_strain`, `max_strain`, `low_strain_days`, `moderate_strain_days`, `high_strain_days`, `workout_count`, `total_workout_minutes`, `record_count` |

**CSV export functions:**

| Function | CSV columns | Notes |
|----------|------------|-------|
| `export_recovery_csv(recoveries, filepath, include_unscored=False) -> int` | Date, Recovery Score, Recovery Zone, HRV, RHR, SpO2, Skin Temp, User Calibrating, Cycle ID, Sleep ID, Score State | Returns record count |
| `export_sleep_csv(sleeps, filepath, include_unscored=False, include_naps=True) -> int` | Date, Start/End Time, Duration, Total Sleep, Performance%, Efficiency%, Respiratory Rate, Light/SWS/REM/Awake hours, Is Nap, Score State | |
| `export_cycle_csv(cycles, filepath, include_unscored=False) -> int` | Date, Start, End, Strain Score, Avg HR, Max HR, Kilojoules, Score State | **Bug**: references `cycle.score.score` but `CycleScore` field is named `strain` not `score` |
| `export_workout_csv(workouts, filepath, include_unscored=False) -> int` | Date, Start/End, Sport, Sport ID, Duration, Strain, Avg HR, Max HR, Calories, Distance, Altitude | |

**Analysis functions:**

| Function | Description |
|----------|-------------|
| `analyze_recovery_trends(recoveries, recent_days=7) -> RecoveryTrends` | Computes stats, zone distribution, HRV coefficient of variation, recent vs older average trend |
| `analyze_sleep_trends(sleeps, include_naps=False) -> SleepTrends` | Duration/performance/efficiency stats, consistency score (% nights within 1h of average) |
| `analyze_training_load(cycles, workouts=None) -> TrainingLoadTrends` | Strain distribution, workout count/duration |
| `generate_summary_report(recoveries, sleeps, cycles, workouts=None, output=None) -> str` | Text report with recovery, sleep, training sections + recommendations |
| `calculate_moving_average(values, window=7) -> List[Optional[float]]` | Standard moving average; returns `None` for positions with insufficient data |

**Bug identified:** `export_cycle_csv` references `cycle.score.score` (line 410) but the `CycleScore` model has no `.score` attribute — the field is `.strain`. This would raise `AttributeError` at runtime.

**Imports from:** `csv`, `dataclasses`, `datetime`, `pathlib`, `typing`, `.constants`, `.logger`, `.models`

---

### 3.12 `setup.py`

**Purpose:** Python package configuration for `whoopyy` v0.1.0.

```
name:           whoopyy
version:        0.1.0
author:         Robert Ponder (robert.ponder@selu.edu)
url:            https://github.com/ponderrr/whoopyy
package_dir:    {"whoopyy": "src"}
python_requires: >=3.9
```

**Runtime dependencies:**

| Package | Pinned version | Status |
|---------|---------------|--------|
| `httpx` | `>=0.27.0` | Unpinned upper bound. Current latest is 0.28.x. Acceptable floor but no upper pin. |
| `pydantic` | `>=2.5.0` | Unpinned upper bound. Pydantic v2 is used (`ConfigDict`, `model_config`). No pin against v3 when it releases. |
| `python-dotenv` | `>=1.0.0` | Unpinned. **Not actually imported anywhere in `src/`** — appears to be an unused dependency. |
| `keyring` | `>=24.3.0` | Unpinned. **Not actually imported anywhere in `src/`** — listed in setup.py docstring suggestion but never used. |

**Dev dependencies (extras_require["dev"]):**

| Package | Version floor | Notes |
|---------|-------------|-------|
| `pytest` | `>=7.4.0` | |
| `pytest-asyncio` | `>=0.21.0` | |
| `pytest-cov` | `>=4.1.0` | |
| `black` | `>=23.12.0` | |
| `mypy` | `>=1.7.0` | |
| `ruff` | `>=0.1.8` | |

**Flags:** No `pyproject.toml` present. `setup.py` is the legacy packaging format. No `setup.cfg`. No lock file for Python dependencies. All version pins are lower-bound only — no pinning against breaking changes.

---

## 4. Next.js Web Application — Detailed File Analysis

### 4.1 `temp_web/package.json`

```json
{
  "name": "temp_web",
  "version": "0.1.0",
  "private": true
}
```

**Scripts:** `dev`, `build`, `start`, `lint` (eslint only, no type-check script).

**Production dependencies:**

| Package | Version | Status |
|---------|---------|--------|
| `next` | `16.1.6` | Exact pin. Next 16 is a very recent major. Reasonable to pin exactly. |
| `react` | `19.2.3` | Exact pin. React 19. |
| `react-dom` | `19.2.3` | Exact pin. |
| `recharts` | `^3.7.0` | Caret. Recharts 3.x. |
| `clsx` | `^2.1.1` | Caret. Class utility. |
| `tailwind-merge` | `^3.4.0` | Caret. |

**Dev dependencies:**

| Package | Version | Notes |
|---------|---------|-------|
| `@tailwindcss/postcss` | `^4` | Tailwind v4 PostCSS plugin |
| `@types/node` | `^20` | |
| `@types/react` | `^19` | |
| `@types/react-dom` | `^19` | |
| `eslint` | `^9` | |
| `eslint-config-next` | `16.1.6` | Matches Next version |
| `tailwindcss` | `^4` | Tailwind v4 |
| `typescript` | `^5` | |

**Missing:** No `next-config` file found in the file list (no `next.config.ts` or `next.config.js`). No test framework in the Next.js app.

**Observations:**
- `next` version `16.1.6` is pinned exactly — good for reproducibility.
- `react` `19.2.3` is exact — React 19 is the current stable.
- Tailwind v4 with `@tailwindcss/postcss` plugin — new architecture, no `tailwind.config.js` visible in the file tree.
- `SESSION_SECRET` env var is referenced in `.env.example` but not used anywhere in the scanned code.
- No `vitest`, `jest`, or `@testing-library` present — the Next.js app has zero tests.

---

### 4.2 `temp_web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "strict": true,
    "noEmit": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "paths": { "@/*": ["./*"] }
  }
}
```

`strict: true` is correctly enabled. `moduleResolution: "bundler"` is the correct Next.js 13+ setting. `@/*` alias maps to the `temp_web/` root.

---

### 4.3 `temp_web/types/whoop.ts`

**Purpose:** TypeScript type definitions mirroring the Whoop v2 API. Also exports utility functions.

**Exported interfaces:**
- `RecoveryScore`, `WhoopRecovery`, `RecoveryCollection`
- `SleepStage`, `SleepNeeded`, `SleepScore`, `WhoopSleep`, `SleepCollection`
- `CycleScore`, `WhoopCycle`, `CycleCollection`
- `WorkoutScore`, `WhoopWorkout`, `WorkoutCollection`
- `UserProfile`, `BodyMeasurement`
- `MetricZone` (union: `'green' | 'yellow' | 'red' | 'neutral'`)
- `RecoveryStatus` (union: `'success' | 'warning' | 'error'`)
- `MetricValue` (value, unit?, zone?)

**Exported functions:**
- `getRecoveryZone(score: number): MetricZone` — ≥67 green, ≥34 yellow, else red
- `getRecoveryStatus(score: number): RecoveryStatus`
- `getSleepPerformanceZone(percentage: number): MetricZone` — ≥85 green, ≥70 yellow
- `getStrainZone(strain: number): MetricZone` — ≥14 red, ≥10 yellow, ≥0 green
- `millisToHours(millis: number): number`
- `formatSleepDuration(millis: number): string`

---

### 4.4 `temp_web/lib/constants.ts`

**Exports:**
- `APP_NAME = 'WHOOP Insights'`
- `APP_DESCRIPTION`
- `ROUTES` — page routes as const object: HOME, LOGIN, CALLBACK, DASHBOARD, RECOVERY, SLEEP, STRAIN, SETTINGS
- `API_ROUTES` — API route paths as const object
- `CACHE_DURATIONS` — Next.js fetch revalidate values: RECOVERY=3600, SLEEP=21600, CYCLES=3600, WORKOUTS=900, PROFILE=86400

---

### 4.5 `temp_web/middleware.ts`

**Purpose:** Next.js route-level middleware for authentication gating.

- Protected routes: `/dashboard` (all sub-paths)
- Auth routes: `/login`, `/callback`
- Token check: reads `whoop_access_token` cookie
- Protected + no token → redirect to `/login?redirect=<pathname>`
- Auth route + token (not `/callback`) → redirect to `/dashboard`
- Matcher excludes `_next/static`, `_next/image`, `favicon.ico`, `api/`, and image file extensions

---

### 4.6 API Routes

All API routes follow the same error-handling pattern: check token, check expiry, call WHOOP API, handle 429/non-OK, return `successResponse` or typed `errorResponse`.

#### `GET /api/whoop/auth/login`
Builds OAuth authorization URL with all scopes + `offline`, stores `oauth_state` cookie (10-min TTL), redirects user to WHOOP OAuth server.

#### `GET /api/whoop/auth/callback`
Verifies `state` parameter against `oauth_state` cookie (CSRF protection), exchanges auth code for tokens via WHOOP token endpoint, stores tokens in HTTP-only cookies via `setTokens()`, redirects to `/dashboard`. Clears `oauth_state` cookie.

#### `POST /api/whoop/auth/logout`
Calls `clearTokens()` to delete all three auth cookies. Returns `{ message: 'Logged out successfully' }`.

#### `POST /api/whoop/auth/refresh`
Reads refresh token from cookie, posts `grant_type=refresh_token` to WHOOP token URL, stores new tokens, handles token rotation (falls back to old refresh token if new one not returned).

#### `GET /api/whoop/profile`
Fetches user profile and body measurements **in parallel** with `Promise.all`. Returns `{ profile, body }`. Body measurement failure is non-fatal (returns null).

**Critical bug:** This route uses `WHOOP_API_URL = 'https://api.prod.whoop.com/developer/v1'` — the **v1** endpoint — while the Python SDK was migrated to v2 in the most recent commit (`fcc5959`). All five data routes have this same v1 URL.

#### `GET /api/whoop/recovery`
Proxies to `WHOOP_API_URL/activity/recovery?limit=<limit>`. Default limit: 7. Cache: 1 hour.

**Same v1 endpoint issue as above.** The correct v2 path should be `/developer/v2/recovery`.

#### `GET /api/whoop/sleep`
Proxies to `WHOOP_API_URL/activity/sleep?limit=<limit>`. Default limit: 7. Cache: 6 hours.

#### `GET /api/whoop/cycles`
Proxies to `WHOOP_API_URL/cycle?limit=<limit>`. Default limit: 7. Cache: 1 hour.

#### `GET /api/whoop/workouts`
Proxies to `WHOOP_API_URL/activity/workout?limit=<limit>`. Default limit: 10. Cache: 15 minutes.

---

### 4.7 Page Routes

| Route | File | Type | Description |
|-------|------|------|-------------|
| `/` | `app/page.tsx` | Server Component | Immediately redirects to `/dashboard` |
| `/login` | `app/(auth)/login/page.tsx` | Server Component | WHOOP login page with OAuth link button. Redirects to `/dashboard` if token exists. |
| `/callback` | `app/(auth)/callback/page.tsx` | Client Component | Loading spinner shown while API route handles redirect. Note: the actual OAuth exchange happens in the API route at `/api/whoop/auth/callback`, not here. |
| `/callback/error` | `app/(auth)/callback/error/page.tsx` | Server Component | Error page for auth failures. Reads `?message=` query param. |
| `/dashboard` | `app/dashboard/page.tsx` | Server Component | Main overview with 3-column WidgetGrid (Recovery, Sleep, Strain) + 4-column HRV/RHR/SleepNeed/Calories. **Currently uses hardcoded mock data.** |
| `/dashboard/recovery` | `app/dashboard/recovery/page.tsx` | Server Component | RecoveryGauge + RecoveryTrendChart side by side + 3 MetricWidgets. **Mock data.** |
| `/dashboard/sleep` | `app/dashboard/sleep/page.tsx` | Server Component | SleepChart + 3 MetricWidgets. **Mock data.** |
| `/dashboard/strain` | `app/dashboard/strain/page.tsx` | Server Component | StrainChart + WorkoutDistributionChart. **Mock data.** |
| `/dashboard/settings` | `app/dashboard/settings/page.tsx` | Server Component | Placeholder: "Settings coming soon..." |

**Dashboard layout** (`app/dashboard/layout.tsx`): Server Component. Calls `requireAuth()` which redirects to `/login` if no access token cookie. Renders `<TopNav />` above children.

---

### 4.8 Lib Files

#### `lib/api/tokens.ts`
Server-side cookie management for three auth cookies:
- `whoop_access_token` — httpOnly, secure in prod, `sameSite: lax`, 1 hour TTL
- `whoop_refresh_token` — httpOnly, secure, 7 day TTL
- `whoop_token_expires_at` — stores Unix timestamp as string, 7 day TTL

Exports: `getAccessToken()`, `getRefreshToken()`, `getTokens()`, `setTokens(tokens: Tokens)`, `clearTokens()`, `isTokenExpired()` (5-minute buffer window)

#### `lib/api/errors.ts`
TypeScript error hierarchy:
- `APIError(message, statusCode, code)` — base
- `AuthError` extends `APIError` — 401, `AUTH_ERROR`
- `RateLimitError` extends `APIError` — 429, `RATE_LIMIT_ERROR`, optional `retryAfter`
- `WhoopAPIError` extends `APIError` — arbitrary status, `WHOOP_API_ERROR`

#### `lib/api/response.ts`
Response factories for API routes:
- `successResponse<T>(data, status=200)` → `{ success: true, data }`
- `errorResponse(message, status=500, code?)` → `{ success: false, error: { message, code } }`
- `setCookies(response, cookies)` — utility to batch-set cookies on a `NextResponse`

#### `lib/auth/context.tsx`
Client-side `AuthProvider` and `useAuth()` hook.
- `user` state initialized by calling `/api/whoop/profile` on mount
- Auto-refresh interval: every 50 minutes (before 1-hour token expiry)
- Session refresh dispatches `CustomEvent('whoop-session-refreshed')` for `SessionRefreshToast`
- `logout()` calls `POST /api/whoop/auth/logout`, clears user state, redirects to `/login`

#### `lib/auth/server.ts`
`requireAuth()` — server-side auth guard for use in Server Components/layouts. Reads access token cookie, calls `redirect('/login')` if absent.

#### `lib/auth/errors.ts`
- `AuthenticationError(message, code: AuthErrorCode)` — custom Error subclass
- `AuthErrorCode` union: `'AUTH_ERROR' | 'SESSION_EXPIRED' | 'NETWORK_ERROR' | 'WHOOP_REJECT'`
- `getAuthErrorMessage(error: unknown) -> string` — safe error message extractor

#### `lib/charts/config.ts`
Recharts dark-theme configuration constants:
- `CHART_COLORS` — HSL values for recovery (green), sleep (blue), strain (amber), HRV (cyan), RHR (red), calories, workouts
- `CHART_THEME` — grid, axis, tooltip, legend styling tokens
- `CHART_MARGINS` — default and withLegend margin objects

#### `lib/constants.ts`
See section 4.4 above.

#### `lib/utils/cn.ts`
`cn(...inputs: ClassValue[]): string` — Tailwind class merging via `clsx` + `tailwind-merge`.

#### `lib/utils/formatters.ts`
- `formatNumber(num, decimals=0): string`
- `formatDate(date): string` — "Jan 1, 2024" format
- `formatTime(date): string` — "1:30 PM" format
- `formatDuration(hours): string` — "7h 30m" format

---

### 4.9 Components Summary

#### Auth Components (`components/auth/`)
- `AuthError.tsx` — Error display component
- `AuthLoadingScreen.tsx` — Full-screen loading state
- `DashboardSkeleton.tsx` — Placeholder skeleton for Suspense fallback on dashboard pages
- `SessionRefreshToast.tsx` — Fixed bottom-right toast, listens for `whoop-session-refreshed` event, auto-hides after 5s

#### Chart Components (`components/charts/`)
All charts use Recharts with the dark theme from `lib/charts/config.ts`:
- `LineChartComponent.tsx` — Reusable Recharts `LineChart` wrapper, accepts `lines[]` config
- `RecoveryTrendChart.tsx` — Wraps `LineChartComponent` with recovery + optional HRV lines
- `RecoveryGauge.tsx` — Gauge-style recovery score display
- `SleepChart.tsx` — Sleep duration + performance chart
- `StrainChart.tsx` — Daily strain trend chart
- `WorkoutDistributionChart.tsx` — Workout distribution visualization
- `ChartLegend.tsx` — Reusable legend component
- `CustomTooltip.tsx` — Reusable custom tooltip

#### Layout Components (`components/layout/`)
- `TopNav.tsx` — Client component. Shows nav links (Dashboard/Recovery/Sleep/Strain), Settings link, user initials avatar, Logout button. Reads `useAuth()` for user state and `usePathname()` for active link styling. Uses text-only design (no icons, no logo by design).
- `PageContainer.tsx` — Consistent page wrapper with max-width and padding
- `PageHeader.tsx` — Title + subtitle heading component
- `WidgetGrid.tsx` — Responsive grid container accepting `columns` prop
- `ProtectedRoute.tsx` — Client-side secondary auth guard (redirects to `/login` if not authenticated after loading)

#### Widget Components (`components/widgets/`)
- `RecoveryWidget.tsx` — Recovery score + HRV + RHR card. Uses `getRecoveryZone()` for color.
- `SleepWidget.tsx` — Sleep hours + performance + efficiency card
- `StrainWidget.tsx` — Strain score + calories + workouts card
- `HRVTrendWidget.tsx` — HRV current/average + trend indicator card
- `MetricWidget.tsx` — Generic single-metric display card
- `MetricWidgetSkeleton.tsx` — Loading skeleton for MetricWidget
- `WorkoutGridWidget.tsx` — Workout list/grid display

#### Shared Components (`components/shared/`)
- `EmptyState.tsx` — Empty data state display
- `Skeleton.tsx` — Base skeleton animation component

#### UI Primitives (`components/ui/`)
- `skeleton.tsx` — Skeleton CSS animation primitive
- `spinner.tsx` — Loading spinner with `size` prop
- `status-badge.tsx` — Color-coded status badge (success/warning/error)

---

## 5. Configuration Files

### 5.1 `.env.example` (Python SDK root)
```
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here
WHOOP_REDIRECT_URI=http://localhost:8080/callback
```

### 5.2 `temp_web/.env.example`
```
WHOOP_CLIENT_ID=your_client_id_here
WHOOP_CLIENT_SECRET=your_client_secret_here
WHOOP_REDIRECT_URI=http://localhost:3000/api/whoop/auth/callback
NEXT_PUBLIC_APP_URL=http://localhost:3000
SESSION_SECRET=your_session_secret_here
```

### 5.3 `temp_web/.env.local` — COMMITTED TO REPO
```
WHOOP_CLIENT_ID=mock_client_id
WHOOP_CLIENT_SECRET=mock_client_secret
WHOOP_REDIRECT_URI=http://localhost:3000/api/whoop/auth/callback
NEXT_PUBLIC_APP_URL=http://localhost:3000
SESSION_SECRET=development_secret_key_12345
```

**Security flag:** `.env.local` is committed to the repository. Although the values are mock/development credentials, `.env.local` files should be gitignored. The `SESSION_SECRET` value `development_secret_key_12345` is weak and publicly visible in the repo. This file should be removed from git history and added to `.gitignore`.

### 5.4 `temp_web/tsconfig.json`
See section 4.2 above.

### 5.5 No `.cursorrules` file found.
### 5.6 No `next.config.ts` / `next.config.js` found in `temp_web/`.

---

## 6. Tests

Python tests live in `/home/frosty/whoopyy/tests/`. Five test files cover: async client, auth handler, sync client, export utilities, and Pydantic models. The test suite was added in a single commit (`a2773f6`).

The Next.js application (`temp_web/`) has **no tests** — no test framework is installed, no test files exist.

---

## 7. Identified Bugs and Issues

### 7.1 CRITICAL — API Version Mismatch (Next.js routes use v1, SDK uses v2)

All five Next.js data proxy routes hardcode:
```typescript
const WHOOP_API_URL = 'https://api.prod.whoop.com/developer/v1'
```

The most recent Python SDK commit (`fcc5959 fix: migrate SDK from Whoop API v1 to v2`) migrated all Python endpoints to `/developer/v2/`. The Next.js web app was not updated. Every data fetch in the web app will hit deprecated or invalid endpoints:

| Route file | v1 path used | Correct v2 path |
|-----------|-------------|----------------|
| `recovery/route.ts` | `/developer/v1/activity/recovery` | `/developer/v2/recovery` |
| `sleep/route.ts` | `/developer/v1/activity/sleep` | `/developer/v2/activity/sleep` |
| `cycles/route.ts` | `/developer/v1/cycle` | `/developer/v2/cycle` |
| `workouts/route.ts` | `/developer/v1/activity/workout` | `/developer/v2/activity/workout` |
| `profile/route.ts` | `/developer/v1/user/profile/basic` and `/developer/v1/user/body_measurement` | `/developer/v2/user/profile/basic` and `/developer/v2/user/measurement/body` |

Note also that the profile route uses `/user/body_measurement` (v1) while the Python SDK uses `/user/measurement/body` (v2) — the path changed too, not just the version prefix.

### 7.2 HIGH — Bug in `export_cycle_csv`

In `/home/frosty/whoopyy/src/export.py` at line ~410:
```python
f"{cycle.score.score:.1f}",
```
The `CycleScore` model (`src/models.py`) has no attribute `.score`. The strain field is named `.strain`. This will raise `AttributeError: 'CycleScore' object has no attribute 'score'` at runtime whenever `export_cycle_csv` is called with scored cycles.

The `analyze_training_load` function at line ~715 has the same issue:
```python
strains = [c.score.score for c in scored_cycles if c.score is not None]
```
Should be `c.score.strain`.

### 7.3 HIGH — `export_sleep_csv` accesses `StageSummary` via dict-style get

In `export.py` lines ~312-315:
```python
stages = sleep.score.stage_summary or {}
light = stages.get("total_light_sleep_time_milli", 0) * ms_to_hours
```
`SleepScore.stage_summary` is a `StageSummary` Pydantic model instance, not a dict. Calling `.get()` on it will raise `AttributeError`. Should access as `sleep.score.stage_summary.total_light_sleep_time_milli if sleep.score.stage_summary else 0`.

### 7.4 MEDIUM — `python-dotenv` and `keyring` listed as dependencies but never imported

`setup.py` lists `python-dotenv>=1.0.0` and `keyring>=24.3.0` as runtime dependencies. Neither package is imported anywhere in `src/`. These are phantom dependencies that force unnecessary installation on users.

### 7.5 MEDIUM — `.env.local` committed to repository

`temp_web/.env.local` is tracked in git. This file contains credentials and a weak `SESSION_SECRET`. Even though they are mock values currently, this is a security anti-pattern that will cause issues if real credentials are later placed in the file.

### 7.6 MEDIUM — All dashboard pages use hardcoded mock data

Every dashboard page (`/dashboard`, `/dashboard/recovery`, `/dashboard/sleep`, `/dashboard/strain`) uses inline `const mockData = {...}` and does not call any API routes or the auth-context fetch. The web API proxy routes exist but are not wired to the UI. This is consistent with a work-in-progress state noted with comments like `// Mock data (matches Phase 20 instructions)`.

### 7.7 LOW — No `next.config.ts` present

Next.js 16 conventionally expects a `next.config.ts` (or `.js`). Without it, default configuration applies. This may mean missing optimizations (image domains, headers, redirects) but is not a blocker.

### 7.8 LOW — No retry logic in either client

Both `WhoopClient` and `AsyncWhoopClient` expose `is_retryable_error()` and document retry behavior in docstrings, but neither client performs automatic retries. The constants `MAX_RETRIES = 3` and `RETRY_BACKOFF_BASE_SECONDS = 1.0` are defined but unused. Retry responsibility falls entirely to calling code.

### 7.9 LOW — `sleep_id` type inconsistency in Python models

`Recovery.sleep_id` is typed as `str` (UUID) in `models.py`. The `WhoopRecovery` TypeScript interface uses `recovery_id: string` (different field name entirely) and omits `sleep_id`. The Python model documentation comment says `"Associated sleep ID (UUID)"` but the v2 API may return this as an integer ID in some contexts. Verification against the live API response is needed.

---

## 8. Dependency Summary with Flag Status

### Python SDK

| Dependency | Version Constraint | Flag |
|-----------|-------------------|------|
| `httpx` | `>=0.27.0` | No upper pin |
| `pydantic` | `>=2.5.0` | No upper pin; v3 breaking changes possible |
| `python-dotenv` | `>=1.0.0` | **Unused — phantom dependency** |
| `keyring` | `>=24.3.0` | **Unused — phantom dependency** |

No `pyproject.toml`. No lock file. All pins are floor-only.

### Next.js App

| Dependency | Version | Flag |
|-----------|---------|------|
| `next` | `16.1.6` (exact) | OK |
| `react` | `19.2.3` (exact) | OK |
| `react-dom` | `19.2.3` (exact) | OK |
| `recharts` | `^3.7.0` | Caret — minor/patch updates allowed |
| `clsx` | `^2.1.1` | Caret |
| `tailwind-merge` | `^3.4.0` | Caret |
| `tailwindcss` | `^4` | **Major version caret** — any Tailwind v4.x allowed |
| `@tailwindcss/postcss` | `^4` | **Major version caret** |
| `typescript` | `^5` | Major version caret |
| `eslint` | `^9` | Major version caret |
| `eslint-config-next` | `16.1.6` (exact) | OK |

`package-lock.json` is present — this provides a true lock for npm installs.

---

## 9. Summary

The repository contains two distinct sub-projects:

1. **`whoopyy` Python SDK** (`src/`): A well-structured, type-safe Pydantic v2 SDK for the Whoop API. The architecture is clean with clear separation of concerns. The most recent commit migrated all endpoints from v1 to v2. Two significant bugs exist in `export.py` (incorrect field name references). Two phantom runtime dependencies should be removed from `setup.py`. No `pyproject.toml` or lock file.

2. **`temp_web` Next.js 16 app**: A React 19 + Tailwind v4 dashboard UI. The auth flow (OAuth login → callback → cookie storage → middleware guard → server-side `requireAuth()`) is fully implemented. All dashboard pages currently render hardcoded mock data and are not wired to the API proxy routes. All five data proxy routes use the v1 Whoop API URL despite the Python SDK having migrated to v2. `.env.local` is committed to git.

The web app `temp_web/` naming suggests it is a temporary or prototype implementation. It shares the same OAuth credentials and WHOOP API integration domain as the Python SDK but is developed independently with no shared code.
