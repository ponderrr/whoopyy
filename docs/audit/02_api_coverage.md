# WHOOP API v2 Coverage Audit — whoopyy SDK

**Generated:** 2026-03-14
**Auditor:** Agent 2 (API Coverage Audit)
**Branch:** master
**Working directory:** `/home/frosty/whoopyy`

---

## Executive Summary

The SDK covers all 12 WHOOP v2 data endpoints and all 3 OAuth endpoints at the method level. However, there are **critical versioning bugs**, **model field gaps**, **pagination limit mismatches**, **incorrect token revocation method**, and several **type constraint errors** that will cause runtime failures or silently corrupt data in production. The overall health of endpoint coverage is good structurally but has significant correctness issues.

**Findings by severity:**
- [CRITICAL]: 4
- [HIGH]: 7
- [MEDIUM]: 5
- [LOW]: 4

---

## 1. Endpoint URL Audit

### 1.1 Constants File — `/home/frosty/whoopyy/src/constants.py`

The `ENDPOINTS` dict at lines 34–56 uses `/developer/v2/` for all data paths.

**The official WHOOP developer API is versioned at `/developer/v1/`, not `/developer/v2/`.**

Every data endpoint in the SDK is pointed at a non-existent v2 path. The actual WHOOP API paths are:
- `GET /developer/v1/user/profile/basic`
- `GET /developer/v1/user/measurement/body`
- `GET /developer/v1/cycle`
- `GET /developer/v1/cycle/{cycleId}`
- `GET /developer/v1/cycle/{cycleId}/recovery`
- `GET /developer/v1/recovery`
- `GET /developer/v1/activity/sleep`
- `GET /developer/v1/activity/sleep/{sleepId}`
- `GET /developer/v1/activity/workout`
- `GET /developer/v1/activity/workout/{workoutId}`

> **[CRITICAL] `constants.py` lines 36–55:** All 10 data endpoints use `/developer/v2/` instead of `/developer/v1/`. Every API call to any data endpoint will return 404. This is a complete, blanket failure for all non-auth functionality.

Additionally, the SDK defines an endpoint `sleep_for_cycle` at line 47 (`/developer/v2/cycle/{cycle_id}/sleep`) that is not used by either client and has no corresponding method. No such endpoint exists in the documented WHOOP v2 API.

> **[MEDIUM] `constants.py` line 47:** Orphaned endpoint key `"sleep_for_cycle"` is defined but never called from any client method, and has no corresponding WHOOP v1 API endpoint. Dead code.

### 1.2 OAuth Endpoints

| Endpoint | Constant | Correct? |
|---|---|---|
| `GET /oauth/oauth2/auth` | `OAUTH_AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"` | ✅ |
| `POST /oauth/oauth2/token` (exchange) | `OAUTH_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"` | ✅ |
| `POST /oauth/oauth2/token` (refresh) | Same `OAUTH_TOKEN_URL`, `grant_type=refresh_token` | ✅ |
| `POST /oauth/oauth2/revoke` | Not implemented — see §1.3 below | ❌ |

### 1.3 Token Revocation

The WHOOP spec for token revocation is `POST /oauth/oauth2/revoke`.

The SDK implements `revoke_access()` in `client.py` (line 1150) and `async_client.py` (line 927) as:
```python
self._request("DELETE", ENDPOINTS["user_access_revoke"])
```

The endpoint key `"user_access_revoke"` maps to `/developer/v2/user/access` (constants.py line 38), which is a data API path — not the OAuth revoke endpoint. The HTTP method is `DELETE`, but the spec calls for `POST`. Neither the path nor the method is correct.

> **[CRITICAL] `client.py` line 1150, `async_client.py` line 927, `constants.py` line 38:** `revoke_access()` uses `DELETE /developer/v2/user/access` instead of `POST /oauth/oauth2/revoke`. Wrong path and wrong HTTP method.

---

## 2. Endpoint Method Coverage

All endpoint methods are present in both `WhoopClient` and `AsyncWhoopClient` with symmetric signatures. The table below covers the functional coverage before the v1/v2 path bug is corrected.

### 2.1 Auth Endpoints

| Endpoint | Sync | Async | Notes |
|---|---|---|---|
| `GET /oauth/oauth2/auth` | ✅ `authenticate()` → `auth.authorize()` | ✅ `authenticate()` (sync) | Correct URL, correct flow |
| `POST /oauth/oauth2/token` (exchange) | ✅ `_exchange_code_for_tokens()` | N/A (sync in async client too) | Correct |
| `POST /oauth/oauth2/token` (refresh) | ✅ `refresh_access_token()` | N/A (sync in async client too) | Correct |
| `POST /oauth/oauth2/revoke` | ❌ Wrong path + method | ❌ Wrong path + method | See §1.3 |

### 2.2 Profile Endpoints

| Endpoint | SDK Method | Status |
|---|---|---|
| `GET /developer/v1/user/profile/basic` | `get_profile_basic()` | ⚠️ Path bug (v2 instead of v1) |
| `GET /developer/v1/user/measurement/body` | `get_body_measurement()` | ⚠️ Path bug (v2 instead of v1) |

### 2.3 Cycles Endpoints

| Endpoint | SDK Method | Status |
|---|---|---|
| `GET /developer/v1/cycle` | `get_cycle_collection()` | ⚠️ Path bug (v2 instead of v1) |
| `GET /developer/v1/cycle/{cycleId}` | `get_cycle()` | ⚠️ Path bug (v2 instead of v1) |

### 2.4 Recovery Endpoints

| Endpoint | SDK Method | Status |
|---|---|---|
| `GET /developer/v1/recovery` | `get_recovery_collection()` | ⚠️ Path bug (v2 instead of v1) |
| `GET /developer/v1/cycle/{cycleId}/recovery` | `get_recovery_for_cycle()` | ⚠️ Path bug (v2 instead of v1) |

### 2.5 Sleep Endpoints

| Endpoint | SDK Method | Status |
|---|---|---|
| `GET /developer/v1/activity/sleep` | `get_sleep_collection()` | ⚠️ Path bug (v2 instead of v1) |
| `GET /developer/v1/activity/sleep/{sleepId}` | `get_sleep()` | ⚠️ Path bug (v2 instead of v1) |

### 2.6 Workout Endpoints

| Endpoint | SDK Method | Status |
|---|---|---|
| `GET /developer/v1/activity/workout` | `get_workout_collection()` | ⚠️ Path bug (v2 instead of v1) |
| `GET /developer/v1/activity/workout/{workoutId}` | `get_workout()` | ⚠️ Path bug (v2 instead of v1) |

---

## 3. Model Field-by-Field Audit

### 3.1 `CycleScore` — `models.py` lines 609–668

**Expected fields** (WHOOP v1 API):
- `strain` (float)
- `kilojoule` (float)
- `average_heart_rate` (int)
- `max_heart_rate` (int)

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `strain` | ✅ line 624 | `float` | `ge=0, le=21` | ✅ |
| `kilojoule` | ✅ line 630 | `float` | `ge=0` | ✅ |
| `average_heart_rate` | ✅ line 635 | `int` | `gt=0` | ✅ |
| `max_heart_rate` | ✅ line 640 | `int` | `gt=0` | ✅ |

All required `CycleScore` fields are present and correctly typed. No gaps.

### 3.2 `Cycle` — `models.py` lines 671–729

**Expected fields:**
- `id` (int)
- `user_id` (int)
- `created_at` (datetime)
- `updated_at` (datetime)
- `start` (datetime)
- `end` (Optional[datetime] — nullable for current cycle)
- `timezone_offset` (str)
- `score_state` (str enum: SCORED | PENDING_SCORE | UNSCORABLE)
- `score` (Optional[CycleScore])

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `id` | ✅ line 697 | `int` | required | ✅ |
| `user_id` | ✅ line 698 | `int` | required | ✅ |
| `created_at` | ✅ line 699 | `datetime` | required | ✅ |
| `updated_at` | ✅ line 700 | `datetime` | required | ✅ |
| `start` | ✅ line 701 | `datetime` | required | ✅ |
| `end` | ✅ line 702 | `Optional[datetime]` | nullable | ✅ |
| `timezone_offset` | ✅ line 703 | `str` | required | ✅ |
| `score_state` | ✅ line 704 | `str` | required | ⚠️ plain `str`, not enum — see note |
| `score` | ✅ line 708 | `Optional[CycleScore]` | nullable | ✅ |

> **[LOW] `models.py` lines 266, 552, 704, 1075 (all `score_state` fields):** `score_state` is typed as bare `str` in all models (`Cycle`, `Recovery`, `Sleep`, `Workout`). The WHOOP API defines it as an enum with values `SCORED`, `PENDING_SCORE`, `UNSCORABLE`. Using `str` means no validation; an API typo or new enum value passes silently. Should be `Literal["SCORED", "PENDING_SCORE", "UNSCORABLE"]` or an `Enum`.

### 3.3 `RecoveryScore` — `models.py` lines 151–227

**Expected fields:**
- `user_calibrating` (bool)
- `recovery_score` (float, 0–100)
- `resting_heart_rate` (int)
- `hrv_rmssd_milli` (float)
- `spo2_percentage` (Optional[float] — nullable)
- `skin_temp_celsius` (Optional[float] — nullable)

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `user_calibrating` | ✅ line 179 | `bool` | required | ✅ |
| `recovery_score` | ✅ line 183 | `float` | `ge=0, le=100` | ✅ |
| `resting_heart_rate` | ✅ line 189 | `int` | `gt=0` | ⚠️ See note |
| `hrv_rmssd_milli` | ✅ line 194 | `float` | `gt=0` | ⚠️ See note |
| `spo2_percentage` | ✅ line 199 | `Optional[float]` | `ge=0, le=100` | ✅ |
| `skin_temp_celsius` | ✅ line 205 | `Optional[float]` | none | ✅ |

> **[HIGH] `models.py` line 189:** `resting_heart_rate` is declared `int` with `gt=0`. The WHOOP API actually returns `resting_heart_rate` as a `float` in many responses (e.g., `52.3`). The `int` type with Pydantic v2 strict mode will coerce floats but using `int` semantics will truncate precision silently. The field should be `float`. The `type_defs.py` line 132 correctly types it as `float` (`resting_heart_rate: float`) — this is an inconsistency between the TypedDict and the Pydantic model.

> **[HIGH] `models.py` line 194:** `hrv_rmssd_milli` is declared with `gt=0`. The WHOOP API can return `hrv_rmssd_milli: 0.0` for users with very low HRV readings. A value of exactly `0.0` will fail Pydantic validation (`gt=0` excludes zero). This should be `ge=0`.

### 3.4 `Recovery` — `models.py` lines 230–278

**Expected fields:**
- `cycle_id` (int)
- `sleep_id` (str — UUID)
- `user_id` (int)
- `created_at` (datetime)
- `updated_at` (datetime)
- `score_state` (str)
- `score` (Optional[RecoveryScore])

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `cycle_id` | ✅ line 261 | `int` | required | ✅ |
| `sleep_id` | ✅ line 262 | `str` | required | ✅ |
| `user_id` | ✅ line 263 | `int` | required | ✅ |
| `created_at` | ✅ line 264 | `datetime` | required | ✅ |
| `updated_at` | ✅ line 265 | `datetime` | required | ✅ |
| `score_state` | ✅ line 266 | `str` | required | ⚠️ not enum |
| `score` | ✅ line 270 | `Optional[RecoveryScore]` | nullable | ✅ |

All fields present. Note the `score_state` enum issue referenced in §3.2.

### 3.5 `StageSummary` — `models.py` lines 360–395

**Expected fields** (7 named fields + `disturbance_count`):
- `total_in_bed_time_milli` (int)
- `total_awake_time_milli` (int)
- `total_no_data_time_milli` (int)
- `total_light_sleep_time_milli` (int)
- `total_slow_wave_sleep_time_milli` (int)
- `total_rem_sleep_time_milli` (int)
- `sleep_cycle_count` (int)
- `disturbance_count` (int)

**SDK fields:**
| Field | Present | Type | Default | Verdict |
|---|---|---|---|---|
| `total_in_bed_time_milli` | ✅ line 369 | `int` | 0 | ✅ |
| `total_awake_time_milli` | ✅ line 370 | `int` | 0 | ✅ |
| `total_no_data_time_milli` | ✅ line 371 | `int` | 0 | ✅ |
| `total_light_sleep_time_milli` | ✅ line 372 | `int` | 0 | ✅ |
| `total_slow_wave_sleep_time_milli` | ✅ line 373 | `int` | 0 | ✅ |
| `total_rem_sleep_time_milli` | ✅ line 374 | `int` | 0 | ✅ |
| `sleep_cycle_count` | ✅ line 375 | `int` | 0 | ✅ |
| `disturbance_count` | ✅ line 376 | `int` | 0 | ✅ |

All 8 fields (7 duration fields + disturbance count) are present and correctly typed. Full coverage.

### 3.6 `SleepNeeded` — `models.py` lines 398–425

**Expected fields:**
- `baseline_milli` (int)
- `need_from_sleep_debt_milli` (int)
- `need_from_recent_strain_milli` (int)
- `need_from_recent_nap_milli` (int)

**SDK fields:**
| Field | Present | Type | Verdict |
|---|---|---|---|
| `baseline_milli` | ✅ line 407 | `int` | ✅ |
| `need_from_sleep_debt_milli` | ✅ line 408 | `int` | ✅ |
| `need_from_recent_strain_milli` | ✅ line 409 | `int` | ✅ |
| `need_from_recent_nap_milli` | ✅ line 410 | `int` | ✅ |

All 4 fields present. No gaps.

### 3.7 `SleepScore` — `models.py` lines 428–508

**Expected fields:**
- `stage_summary` (Optional[StageSummary])
- `sleep_needed` (Optional[SleepNeeded])
- `respiratory_rate` (Optional[float] — nullable)
- `sleep_performance_percentage` (Optional[float] — nullable)
- `sleep_consistency_percentage` (Optional[float] — nullable)
- `sleep_efficiency_percentage` (Optional[float] — nullable)

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `stage_summary` | ✅ line 443 | `Optional[StageSummary]` | none | ✅ |
| `sleep_needed` | ✅ line 447 | `Optional[SleepNeeded]` | none | ✅ |
| `respiratory_rate` | ✅ line 451 | `Optional[float]` | `gt=0` | ⚠️ See note |
| `sleep_performance_percentage` | ✅ line 456 | `Optional[float]` | `ge=0, le=100` | ✅ |
| `sleep_consistency_percentage` | ✅ line 462 | `Optional[float]` | `ge=0, le=100` | ✅ |
| `sleep_efficiency_percentage` | ✅ line 467 | `Optional[float]` | `ge=0, le=100` | ✅ |

> **[MEDIUM] `models.py` line 451–454:** `respiratory_rate` has constraint `gt=0`. The WHOOP API spec defines this as nullable (it can be absent), which the SDK correctly handles with `Optional`. However, if the API returns `respiratory_rate: 0` (e.g., data gap or calibration), Pydantic will reject it. Should be `ge=0` or left unconstrained.

All 6 fields present.

### 3.8 `Sleep` — `models.py` lines 511–575

**Expected fields:**
- `id` (str — UUID)
- `cycle_id` (int)
- `user_id` (int)
- `created_at` (datetime)
- `updated_at` (datetime)
- `start` (datetime)
- `end` (datetime — NOT nullable for sleep, always present)
- `timezone_offset` (str)
- `nap` (bool)
- `score_state` (str)
- `score` (Optional[SleepScore])

**SDK fields:**
| Field | Present | Type | Verdict |
|---|---|---|---|
| `id` | ✅ line 543 | `str` | ✅ |
| `cycle_id` | ✅ line 544 | `int` | ✅ |
| `user_id` | ✅ line 545 | `int` | ✅ |
| `created_at` | ✅ line 546 | `datetime` | ✅ |
| `updated_at` | ✅ line 547 | `datetime` | ✅ |
| `start` | ✅ line 548 | `datetime` | ✅ |
| `end` | ✅ line 549 | `datetime` | ✅ — non-nullable, correct |
| `timezone_offset` | ✅ line 550 | `str` | ✅ |
| `nap` | ✅ line 551 | `bool` | ✅ |
| `score_state` | ✅ line 552 | `str` | ⚠️ not enum |
| `score` | ✅ line 556 | `Optional[SleepScore]` | ✅ |

All 11 fields present. No structural gaps.

### 3.9 `WorkoutZoneDuration` — `models.py` lines 763–838

**Expected fields (6 zones, all nullable in v1 API):**
- `zone_zero_milli` (Optional[int])
- `zone_one_milli` (Optional[int])
- `zone_two_milli` (Optional[int])
- `zone_three_milli` (Optional[int])
- `zone_four_milli` (Optional[int])
- `zone_five_milli` (Optional[int])

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `zone_zero_milli` | ✅ line 793 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |
| `zone_one_milli` | ✅ line 794 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |
| `zone_two_milli` | ✅ line 795 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |
| `zone_three_milli` | ✅ line 796 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |
| `zone_four_milli` | ✅ line 797 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |
| `zone_five_milli` | ✅ line 798 | `int` | `ge=0`, required | ❌ Should be `Optional[int]` |

> **[HIGH] `models.py` lines 793–798:** All 6 zone duration fields are declared as required `int` with `ge=0`. The WHOOP API specifies all zone duration fields as nullable. When a workout has no HR data in a particular zone (common for short or low-intensity workouts), the API returns `null` for those zone fields. Pydantic will reject these responses because the fields are required and non-optional. All 6 fields must be `Optional[int] = Field(None, ...)`.

### 3.10 `WorkoutScore` — `models.py` lines 840–931

**Expected fields:**
- `strain` (float)
- `average_heart_rate` (int)
- `max_heart_rate` (int)
- `kilojoule` (float)
- `percent_recorded` (float)
- `distance_meter` (Optional[float] — nullable)
- `altitude_gain_meter` (Optional[float] — nullable)
- `altitude_change_meter` (Optional[float] — nullable)
- `zone_duration` (Optional[WorkoutZoneDuration] — nullable)

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `strain` | ✅ line 868 | `float` | `ge=0, le=21` | ✅ |
| `average_heart_rate` | ✅ line 874 | `int` | `gt=0` | ✅ |
| `max_heart_rate` | ✅ line 879 | `int` | `gt=0` | ✅ |
| `kilojoule` | ✅ line 884 | `float` | `ge=0` | ✅ |
| `percent_recorded` | ✅ line 889 | `float` | `ge=0, le=100` | ✅ |
| `distance_meter` | ✅ line 895 | `Optional[float]` | `ge=0` | ✅ |
| `altitude_gain_meter` | ✅ line 900 | `Optional[float]` | `ge=0` | ✅ |
| `altitude_change_meter` | ✅ line 905 | `Optional[float]` | none | ✅ |
| `zone_duration` | ✅ line 909 | `Optional[WorkoutZoneDuration]` | nullable | ✅ |

`WorkoutScore` fields are correctly modeled at the outer level. The zone_duration sub-model issue is documented in §3.9.

### 3.11 `Workout` — `models.py` lines 1040–1107

**Expected fields:**
- `id` (str — UUID in v1 API)
- `user_id` (int)
- `created_at` (datetime)
- `updated_at` (datetime)
- `start` (datetime)
- `end` (datetime)
- `timezone_offset` (str)
- `sport_id` (int — the primary sport identifier)
- `score_state` (str)
- `score` (Optional[WorkoutScore])

**SDK fields:**
| Field | Present | Type | Constraint | Verdict |
|---|---|---|---|---|
| `id` | ✅ line 1066 | `str` | required | ✅ |
| `user_id` | ✅ line 1067 | `int` | required | ✅ |
| `created_at` | ✅ line 1068 | `datetime` | required | ✅ |
| `updated_at` | ✅ line 1069 | `datetime` | required | ✅ |
| `start` | ✅ line 1070 | `datetime` | required | ✅ |
| `end` | ✅ line 1071 | `datetime` | required | ✅ |
| `timezone_offset` | ✅ line 1072 | `str` | required | ✅ |
| `sport_name` | ✅ line 1073 | `str` | required | ❌ See note |
| `sport_id` | ✅ line 1074 | `Optional[int]` | optional | ❌ See note |
| `score_state` | ✅ line 1075 | `str` | required | ⚠️ not enum |
| `score` | ✅ line 1079 | `Optional[WorkoutScore]` | nullable | ✅ |

> **[CRITICAL] `models.py` lines 1073–1074:** The WHOOP v1 API returns `sport_id` (int) as the primary sport identifier, **not** `sport_name`. The SDK makes `sport_name` a required `str` field (line 1073) and marks `sport_id` as `Optional[int]` with a "deprecated" comment (line 1074). This is inverted: `sport_name` does not exist as a direct field in the WHOOP API response. The API returns `sport_id` (required integer). Every `Workout` deserialization will fail with a Pydantic validation error because `sport_name` will be absent from the API response JSON.

> **[MEDIUM] `models.py` line 1074:** `sport_id` is marked `Optional[int]` with description `"Sport type identifier (deprecated)"`. The WHOOP v1 API returns `sport_id` as a required integer. This comment is incorrect. The `sport_id` lookup table `SPORT_NAMES` (lines 935–1037) is also present, which implies the author knew `sport_id` was the canonical field but implemented `sport_name` as primary anyway — contradicting the SPORT_NAMES lookup.

---

## 4. Pagination Audit

### 4.1 `next_token` following

All collection methods correctly follow `next_token` in both sync and async clients:

- `get_all_recovery()` / `get_all_sleep()` / `get_all_cycles()` / `get_all_workouts()` — each loops until `collection.next_token` is falsy. Correctly implemented. ✅
- `iter_recovery()` / `iter_sleep()` / `iter_cycles()` / `iter_workouts()` — generator variants, same loop logic. ✅

### 4.2 Auto-paginate helpers

Auto-pagination helpers exist and are functional (modulo the v1/v2 path bug):
- `get_all_*()` methods collect all pages into a list ✅
- `iter_*()` generator methods yield records page by page ✅
- Both accept `max_records` limits ✅
- Both accept `start` / `end` filters ✅

### 4.3 `limit` parameter and MAX_PAGE_LIMIT

**The WHOOP v1 API enforces a maximum `limit` of 25 records per request.**

> **[CRITICAL] `constants.py` line 136:** `MAX_PAGE_LIMIT` is set to `50`. The actual WHOOP API maximum page size is 25. The SDK's auto-pagination methods (`get_all_recovery`, etc.) always request `limit=MAX_PAGE_LIMIT` (50). The API will either reject these requests with a 400 error or silently truncate to 25. This means the SDK's auto-paginate will produce incomplete results if the API silently truncates, or fail outright if it rejects. Must be set to `25`.

Additionally, all docstrings for collection methods claim `limit` accepts `1-50` (e.g., `client.py` line 487: `"limit: Number of records per page (1-50). Defaults to 25."`), when the actual cap is 25.

> **[HIGH] `client.py` lines 487, 686, 857, 1016; `async_client.py` lines 427, 579, 710, 830:** All 8 collection method docstrings state the valid range is `"(1-50)"`. The actual WHOOP API maximum is 25. The docstrings are misleading and will cause callers to send requests that the API rejects.

### 4.4 `nextToken` query parameter name

The SDK sends pagination token as query parameter `nextToken` (camelCase), e.g., `client.py` line 530:
```python
params["nextToken"] = next_token
```

The WHOOP API documentation specifies the query parameter as `nextToken` (camelCase). This is correct. ✅

### 4.5 Collection response shape

All 4 collection models (`RecoveryCollection`, `SleepCollection`, `CycleCollection`, `WorkoutCollection`) define:
```python
records: List[...]
next_token: Optional[str]
```

This matches the documented API response shape `{"records": [...], "next_token": "string|null"}`. ✅

### 4.6 `start` and `end` parameter exposure

All 4 collection methods expose `start`, `end`, `limit`, and `next_token` in both sync and async clients. ✅

---

## 5. Authentication Flow Audit

### 5.1 Authorization code grant (`auth.py`)

- CSRF state generation: `secrets.token_urlsafe(32)` — ✅
- State verification in callback: ✅ (`_wait_for_callback` line 448)
- Local callback server (localhost:8080): ✅
- Token exchange: `POST` to `OAUTH_TOKEN_URL` with `grant_type=authorization_code` — ✅
- Token persistence: `save_tokens()` to JSON file — ✅ (with noted plaintext security caveat in source)

### 5.2 Token refresh (`auth.py` lines 529–617)

- `POST` to `OAUTH_TOKEN_URL` with `grant_type=refresh_token` — ✅
- Proactive refresh 60 seconds before expiry (`TOKEN_REFRESH_BUFFER_SECONDS = 60`) — ✅
- Re-saves refreshed token — ✅
- Falls back to old refresh token if new one not issued — ✅ (line 580)

### 5.3 Token revocation — already documented in §1.3 as [CRITICAL]

### 5.4 `offline` scope enforcement

The `OAuthHandler.__init__` (line 296) adds `"offline"` scope if missing, with a log warning. ✅

---

## 6. Additional Issues

### 6.1 `get_sleep()` ID type mismatch

`client.py` line 645 and `async_client.py` line 547:
```python
def get_sleep(self, sleep_id: int) -> Sleep:
    if sleep_id <= 0:
        raise ValueError(...)
```

The `Sleep` model defines `id` as `str` (UUID) at `models.py` line 543. The method signature accepts `int`, performs an integer validity check (`<= 0`), then passes it to the URL template. UUIDs cannot be meaningfully checked with `<= 0`.

> **[HIGH] `client.py` line 645, `async_client.py` line 547:** `get_sleep(sleep_id: int)` accepts `int` but the `Sleep.id` field is `str` (UUID). The method parameter type, the guard clause (`<= 0`), and the URL interpolation are all wrong for a UUID-based identifier. Should be `sleep_id: str` with a non-empty string check.

### 6.2 `get_workout()` ID type mismatch

`client.py` line 976 and `async_client.py` line 795:
```python
def get_workout(self, workout_id: int) -> Workout:
    if workout_id <= 0:
        raise ValueError(...)
```

The `Workout` model defines `id` as `str` (UUID) at `models.py` line 1066. Same issue as sleep.

> **[HIGH] `client.py` line 976, `async_client.py` line 795:** `get_workout(workout_id: int)` accepts `int` but `Workout.id` is `str` (UUID). Same pattern as §6.1.

### 6.3 `SleepStage` model — unused

`models.py` lines 322–357 define a `SleepStage` model with fields `stage_id`, `start_millis`, `end_millis`. This model is defined in the module but:
1. The WHOOP v1 API does not return a `stages` array of stage objects in the sleep response. The v1 API returns aggregated stage durations via `stage_summary` (which the SDK models correctly with `StageSummary`).
2. `SleepStage` is not referenced from any other model, not exported from `__init__.py`, and not used anywhere.

> **[LOW] `models.py` lines 322–357:** `SleepStage` is a dead model. The v1 API does not return individual sleep stages; it returns aggregated durations in `stage_summary`. This class is vestigial — likely from v1 API research — and should be removed to avoid confusion.

### 6.4 Plaintext token storage

`utils.py` line 62: tokens are saved as plaintext JSON with `json.dump`. The source comment on line 39 acknowledges this and suggests using `keyring`. This is a security risk in shared or multi-user environments.

> **[LOW] `utils.py` line 62:** Tokens stored in plaintext JSON at `.whoop_tokens.json`. Access token and refresh token are exposed to any process with filesystem read access. No severity escalation — this is documented in-source as a known limitation — but consumers should be warned in public documentation.

### 6.5 `ENDPOINTS` type annotation

`constants.py` line 34:
```python
ENDPOINTS: Final[dict[str, str]] = {...}
```

`dict[str, str]` uses the lowercase built-in `dict` which requires Python 3.9+. The use of `Final` from `typing` is already imported. For broader Python 3.8 compatibility this should be `Dict[str, str]` from `typing`. The `type_defs.py` correctly uses `from typing import ... Dict`. This is a minor inconsistency.

> **[LOW] `constants.py` line 34:** `dict[str, str]` syntax requires Python 3.9+. If Python 3.8 support is desired, use `Dict[str, str]` from `typing`. Same applies to `list[str]` on line 67.

---

## 7. Summary Table

| # | Severity | Location | Issue |
|---|---|---|---|
| 1 | [CRITICAL] | `constants.py` lines 36–55 | All 10 data endpoints use `/developer/v2/` — must be `/developer/v1/` |
| 2 | [CRITICAL] | `client.py` L1150, `async_client.py` L927, `constants.py` L38 | `revoke_access()` uses `DELETE /developer/v2/user/access` instead of `POST /oauth/oauth2/revoke` |
| 3 | [CRITICAL] | `constants.py` line 136 | `MAX_PAGE_LIMIT = 50` — WHOOP API max is 25; auto-paginate will break |
| 4 | [CRITICAL] | `models.py` lines 1073–1074 | `Workout.sport_name` is required but API returns `sport_id`; all workout deserialization will fail |
| 5 | [HIGH] | `models.py` line 189 | `RecoveryScore.resting_heart_rate` typed `int` but API returns `float` |
| 6 | [HIGH] | `models.py` line 194 | `RecoveryScore.hrv_rmssd_milli` has `gt=0` — API can return 0.0; should be `ge=0` |
| 7 | [HIGH] | `models.py` lines 793–798 | All 6 `WorkoutZoneDuration` zone fields required non-nullable; API returns null — all will fail validation |
| 8 | [HIGH] | `client.py` L645 / `async_client.py` L547 | `get_sleep(sleep_id: int)` but `Sleep.id` is UUID string |
| 9 | [HIGH] | `client.py` L976 / `async_client.py` L795 | `get_workout(workout_id: int)` but `Workout.id` is UUID string |
| 10 | [HIGH] | `client.py` L487 etc (8 locations) | Docstrings claim limit range is `1-50`; actual API max is 25 |
| 11 | [MEDIUM] | `models.py` line 451 | `SleepScore.respiratory_rate` has `gt=0` — API can return 0; should be `ge=0` |
| 12 | [MEDIUM] | `models.py` line 1074 | `sport_id` marked deprecated and optional, but is the primary API field |
| 13 | [MEDIUM] | `constants.py` line 47 | Orphaned `"sleep_for_cycle"` endpoint — not used, not a real API endpoint |
| 14 | [MEDIUM] | `models.py` lines 266, 552, 704, 1075 | `score_state` typed `str` — should be `Literal["SCORED","PENDING_SCORE","UNSCORABLE"]` |
| 15 | [LOW] | `models.py` lines 322–357 | `SleepStage` model is dead code — API does not return individual stage objects |
| 16 | [LOW] | `utils.py` line 62 | Tokens stored in plaintext JSON |
| 17 | [LOW] | `constants.py` line 34, 67 | `dict[str, str]` / `list[str]` require Python 3.9+ |

---

## 8. Files Audited

- `/home/frosty/whoopyy/src/constants.py`
- `/home/frosty/whoopyy/src/models.py`
- `/home/frosty/whoopyy/src/client.py`
- `/home/frosty/whoopyy/src/async_client.py`
- `/home/frosty/whoopyy/src/auth.py`
- `/home/frosty/whoopyy/src/type_defs.py`
- `/home/frosty/whoopyy/src/utils.py`
