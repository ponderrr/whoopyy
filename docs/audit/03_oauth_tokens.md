# OAuth & Token Lifecycle Audit — whoopyy

**Generated:** 2026-03-14
**Auditor:** Agent 3 (OAuth/Token Lifecycle Audit)
**Branch:** master
**Working directory:** `/home/frosty/whoopyy`

---

## Scope

Files audited:

| File | Purpose |
|------|---------|
| `src/auth.py` | Core OAuth handler, callback server, token management |
| `src/client.py` | Sync API client — request dispatch, auth header injection |
| `src/async_client.py` | Async API client — same pattern as sync |
| `src/utils.py` | Token persistence helpers, expiry logic |
| `src/constants.py` | URLs, scopes, buffer constants |
| `src/exceptions.py` | Exception hierarchy |
| `src/type_defs.py` | `TokenData` TypedDict |
| `temp_web/app/api/whoop/auth/login/route.ts` | Next.js login route |
| `temp_web/app/api/whoop/auth/callback/route.ts` | Next.js OAuth callback |
| `temp_web/app/api/whoop/auth/refresh/route.ts` | Next.js token refresh |
| `temp_web/app/api/whoop/auth/logout/route.ts` | Next.js logout |
| `temp_web/lib/api/tokens.ts` | Cookie-based token storage |
| `temp_web/lib/auth/server.ts` | Server-side route protection |
| `.gitignore` | Token file exclusion check |
| `temp_web/.gitignore` | Web app exclusion check |

---

## 1. Auth URL Generation

### Python SDK (`src/auth.py` lines 383–401)

**`_build_authorization_url()`** constructs:

```
response_type=code   ✓  (line 394)
client_id            ✓  (line 395)
redirect_uri         ✓  (line 396)
scope                ✓  (line 397 — space-joined list)
state                ✓  (line 398)
```

All five required parameters are present.

**Scope list** (`src/constants.py` lines 67–75):

```python
SCOPES = [
    "offline",
    "read:profile",
    "read:body_measurement",
    "read:recovery",
    "read:sleep",
    "read:cycles",
    "read:workout",
]
```

The audit mandate specifies the scope string `read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement offline`. All seven required scopes are present. The scope name `read:cycles` matches the constant; the mandate used the alternate spelling `read:cycles` — this is consistent.

**State CSRF validation** (`src/auth.py` lines 448–452): State is compared in `_wait_for_callback()` immediately after the single-request callback server returns:

```python
if _CallbackHandler.auth_state != expected_state:
    raise WhoopAuthError(
        "State parameter mismatch - possible CSRF attack",
        status_code=400
    )
```

State is validated correctly. The `secrets.token_urlsafe(32)` call (line 353) produces 32 bytes of CSPRNG data, which is cryptographically adequate.

### Next.js (`temp_web/app/api/whoop/auth/login/route.ts` lines 17–33)

All required parameters are present: `client_id`, `redirect_uri`, `response_type`, `state`, and the full scope list (lines 25–33). State is generated with `crypto.randomUUID()` (line 17) — a UUID is 122 bits of random data, adequate for CSRF. The state is stored in an `httpOnly`, `secure`-in-production cookie with `sameSite: lax` and a 10-minute TTL (lines 39–45). Callback validates state against the cookie (callback lines 13–18).

**Finding — [LOW]** `temp_web/app/api/whoop/auth/login/route.ts` line 41: The `secure` attribute on the `oauth_state` cookie is only set in production (`process.env.NODE_ENV === 'production'`). In development the state cookie is transmitted over plain HTTP, making the CSRF state parameter interceptable in a development environment. While low severity for development, this is a developer-security hygiene issue.

---

## 2. Token Exchange

### Python SDK (`src/auth.py` lines 457–523)

**`_exchange_code_for_tokens()`** POST body:

```
grant_type=authorization_code   ✓  (line 473)
code                             ✓  (line 474)
client_id                        ✓  (line 475)
client_secret                    ✓  (line 476)
redirect_uri                     ✓  (line 477)
```

`redirect_uri` is sent and uses `self.redirect_uri`, the same value that was included in the authorization URL, satisfying the exact-match requirement.

All four response fields are extracted and stored (lines 490–497):

```
access_token    ✓  (line 491)
refresh_token   ✓  (line 492 — via .get(), may be None)
expires_in      ✓  (line 493)
token_type      ✓  (line 495 — defaults to "Bearer")
expires_at      ✓  (line 494 — computed via calculate_expiry())
```

**Finding — [MEDIUM]** `src/auth.py` line 492: `refresh_token` is extracted with `.get("refresh_token")`, meaning it is silently `None` if the server omits it. There is no assertion or warning if the server returns a token response without a `refresh_token` even though `offline` scope was requested. A missing refresh token will only surface later as `WhoopTokenError` when `_get_stored_refresh_token()` is called, making the failure mode non-obvious at exchange time.

### Next.js (`temp_web/app/api/whoop/auth/callback/route.ts`)

POST body fields:

```
grant_type=authorization_code   ✓  (line 31)
code                             ✓  (line 32)
client_id                        ✓  (line 33 — from env)
client_secret                    ✓  (line 34 — from env)
redirect_uri                     ✓  (line 35 — from env)
```

Fields extracted from response (lines 48–55): `access_token`, `refresh_token`, `expires_at` (computed). `token_type` is not stored — acceptable since it is always `"Bearer"` and the Next.js routes hard-code the `Bearer` prefix when constructing the `Authorization` header.

**Finding — [LOW]** `temp_web/app/api/whoop/auth/callback/route.ts` line 48: `expires_in` falls back to `|| 3600` if not present in the response. This is a reasonable defensive default but silently masks a malformed response.

---

## 3. Token Refresh

### 3.1 Proactive vs. Reactive Expiry Check

**Python SDK** — `src/utils.py` `is_token_expired()` (lines 164–207) performs a proactive timestamp comparison:

```python
is_expired = current_time >= (expires_at - buffer_seconds)
```

`TOKEN_REFRESH_BUFFER_SECONDS = 60` (`src/constants.py` line 105). This refreshes the token 60 seconds before it actually expires, which is proactive. Called from `get_valid_token()` (`src/auth.py` lines 685–690) before every API request.

**Next.js** — `temp_web/lib/api/tokens.ts` `isTokenExpired()` (lines 73–80) uses a 5-minute buffer:

```typescript
const fiveMinutesFromNow = Date.now() / 1000 + 300
return tokens.expires_at < fiveMinutesFromNow
```

Both implementations are proactive. **No reactive-only 401 catching.** This is the correct design.

### 3.2 Mutex / Lock Against Concurrent Refresh Race Conditions

**Finding — [CRITICAL] `src/auth.py` — no mutex/lock on `get_valid_token()` / `refresh_access_token()`**

The Python `OAuthHandler` is a plain object with no threading lock. `get_valid_token()` (lines 652–690) performs:

1. Check `is_token_expired()`
2. Call `refresh_access_token()`

If two threads call `get_valid_token()` simultaneously and both see an expired token at step 1, both will call `refresh_access_token()`. Both will send a refresh request to the server. Depending on whether Whoop uses one-time-use refresh tokens (rotation), the second refresh attempt will either succeed redundantly or fail with an invalid token error, leaving one thread with a dead token. There is no `threading.Lock`, no asyncio `asyncio.Lock`, and no flag that prevents this double-refresh.

This is especially dangerous for `AsyncWhoopClient` which exposes async API methods while sharing a single synchronous `OAuthHandler`. If callers use `asyncio.gather()` (as shown in docstring examples) multiple coroutines will simultaneously call the synchronous `_get_auth_headers()` → `get_valid_token()` path and race on the refresh.

**Finding — [CRITICAL] `src/async_client.py` lines 226–234 — `_get_auth_headers()` is synchronous inside async client**

`AsyncWhoopClient._get_auth_headers()` calls `self.auth.get_valid_token()` synchronously. If the token is expired, `get_valid_token()` will call the synchronous `refresh_access_token()` which issues a blocking HTTP request via `httpx.Client` (not `httpx.AsyncClient`) on the async event loop thread. This blocks the event loop for the duration of the token refresh network request, degrading all concurrent coroutines and potentially causing timeouts.

**Next.js** — The Next.js refresh route (`temp_web/app/api/whoop/auth/refresh/route.ts`) has the same race condition: multiple concurrent requests could simultaneously detect expiry and POST to the refresh endpoint. No mutex or distributed lock is implemented. However, since cookies are server-set and Next.js runs on Node.js's single-threaded event loop, the practical impact is lower than in Python threads — but concurrent fetch calls within the same event loop tick can still produce duplicate refresh requests.

### 3.3 Handling Expired Refresh Token (Needs Full Re-Auth)

**Python SDK** — `src/auth.py` lines 598–617: When `refresh_access_token()` receives an HTTP error response (e.g., 401 from the token endpoint because the refresh token has expired), it raises `WhoopTokenError`:

```python
raise WhoopTokenError(
    f"Token refresh failed: {error_detail}",
    status_code=e.response.status_code
)
```

`WhoopTokenError` extends `WhoopAuthError`. The exception is catchable and semantically correct: the docstring in `exceptions.py` (line 104) says `WhoopTokenError` means re-authentication is required. This is correct behavior.

**Finding — [MEDIUM] `src/auth.py` lines 598–617**: The code does not distinguish between a 401 meaning "refresh token expired" (requires full re-auth) and a 5xx meaning "server error" (might be transient). Both are raised as `WhoopTokenError`, which is marked in the exception docs as fatal/non-retryable. A transient server error during token refresh will therefore force the user through the full browser OAuth flow unnecessarily.

**Next.js** — `temp_web/app/api/whoop/auth/refresh/route.ts` lines 31–34: On any `!response.ok`, it throws `AuthError('Failed to refresh token')`, returning a 401 to the client. Same issue: transient 5xx from the token endpoint is treated as fatal.

### 3.4 Auto-Retry of Original Failed Request After Successful Refresh

**Finding — [HIGH] No automatic retry after 401 in `src/client.py` and `src/async_client.py`**

`WhoopClient._request()` (`src/client.py` lines 316–321) handles 401 by immediately raising `WhoopAuthError`:

```python
if response.status_code == 401:
    logger.error("Authentication failed - token may be invalid")
    raise WhoopAuthError(
        "Authentication failed. Please re-authenticate.",
        status_code=401,
    )
```

There is no retry loop. If the token expires between when `get_valid_token()` returns and when the API request is actually dispatched (TOCTOU — the 60-second buffer reduces but does not eliminate this), the caller receives a `WhoopAuthError` and must handle the retry themselves. The proactive expiry check reduces this window, but a token could still expire in the sub-second gap between `get_valid_token()` and the HTTP dispatch.

More importantly: if `get_valid_token()` is called and the token appears valid (expires in 61 seconds), the token may expire in another thread/coroutine between the check and the HTTP call, resulting in a 401 that is never retried. The caller must catch `WhoopAuthError`, call `get_valid_token()` again, and reissue the request manually.

The same non-retry behavior exists in `AsyncWhoopClient._request()` (`src/async_client.py` lines 297–302).

**Next.js** — The individual API route handlers (e.g., `temp_web/app/api/whoop/recovery/route.ts`) would need to check `isTokenExpired()` and call the refresh route before making API calls. No automatic 401 retry is visible in the route handler layer audited.

### 3.5 Specific Catchable Exception on Refresh Failure

**Python SDK** — `WhoopTokenError` is raised on refresh failure (lines 608–617). It is a distinct, catchable exception subclassing `WhoopAuthError`. The exception hierarchy is:

```
WhoopError → WhoopAuthError → WhoopTokenError
```

This is correct. Callers can catch `WhoopTokenError` specifically to trigger re-auth.

**Next.js** — `AuthError` is raised (imported from `lib/api/errors.ts`) and is returned as HTTP 401 to the client. This is correct for a web context.

---

## 4. Token Storage

### Python SDK

**Storage mechanism:** Plaintext JSON file.

- Default path: `.whoop_tokens.json` (`src/constants.py` line 113)
- Written by `save_tokens()` (`src/utils.py` lines 31–74) using `json.dump()` with `indent=2`
- File is created in the current working directory at runtime — wherever the script is executed from

**Finding — [HIGH] `src/utils.py` line 62: No file permission restriction on token file**

`save_tokens()` opens the file with `open(filepath, "w")`. The file is created with the process's default umask. On most Linux systems the default umask is `022`, resulting in permissions `644` (world-readable). Any local user on the system can read the token file. No `os.chmod(filepath, 0o600)` call exists.

**gitignore coverage:** The root `.gitignore` (lines 56–58) includes:
```
.whoop_tokens.json
*_tokens.json
```
Both the default filename and the wildcard pattern are excluded. This is correct and sufficient.

**Missing/corrupted file handling:** `load_tokens()` (`src/utils.py` lines 77–120) returns `None` if the file is absent, and catches `OSError` and `json.JSONDecodeError`, returning `None` on corruption. This is handled gracefully — callers check for `None` and prompt re-authorization.

**File path is relative:** `DEFAULT_TOKEN_FILE = ".whoop_tokens.json"` is a relative path. The file location changes depending on the caller's working directory. If the working directory changes between `authorize()` and a subsequent `get_valid_token()` call, tokens will not be found. This is a minor but real usability hazard.

### Next.js

**Storage mechanism:** HTTP-only cookies.

- `whoop_access_token`: `httpOnly`, `sameSite: lax`, `maxAge: 3600` (1 hour)
- `whoop_refresh_token`: `httpOnly`, `sameSite: lax`, `maxAge: 604800` (7 days)
- `whoop_token_expires_at`: `httpOnly`, `sameSite: lax`, `maxAge: 604800` (7 days)

All three cookies use `secure: process.env.NODE_ENV === 'production'`.

**Finding — [MEDIUM] `temp_web/lib/api/tokens.ts` lines 41–63: Access token cookie `maxAge` is hardcoded to 3600 regardless of actual `expires_in`**

`setTokens()` always sets `maxAge: 60 * 60` for the access token cookie, ignoring the actual `expires_at` value passed in. If the server issues a token with a shorter or longer lifetime, the cookie will expire at the wrong time relative to the token. This is a mismatch between cookie TTL and token TTL.

**Finding — [LOW] `temp_web/lib/api/tokens.ts`: No token file involved; token data lives only in cookies**

The cookies are cleared by `clearTokens()` on logout. No persistent file storage means tokens are lost on browser data clear or cookie expiry, which is correct behavior for a web app. No gitignore concern.

---

## 5. Token Usage in Requests

### Python SDK

**Per-request injection (correct):**

`WhoopClient._get_auth_headers()` (`src/client.py` lines 236–249) calls `self.auth.get_valid_token()` on every request. The returned `Authorization: Bearer {token}` header is passed to `self._http_client.request(...)` as a per-call `headers=` argument (line 295). The `httpx.Client` base headers (lines 163–168) contain only `Accept` and `Content-Type` — the `Authorization` header is NOT set at init time and NOT stored on the client.

This is the correct pattern: if the token is refreshed, subsequent requests automatically use the new token because `get_valid_token()` is called fresh each time.

Same pattern applies in `AsyncWhoopClient._request()` (`src/async_client.py` lines 260–261).

### Next.js

Token injection happens within each individual API route handler (e.g., `temp_web/app/api/whoop/recovery/route.ts`) by calling `getAccessToken()` from `lib/api/tokens.ts`, which reads the cookie fresh on each request. This is per-request and correct.

**Finding — [MEDIUM] `temp_web/lib/auth/server.ts` lines 9–16: `requireAuth()` does not check token expiry**

`requireAuth()` only checks that `getAccessToken()` returns a non-null value:

```typescript
const token = await getAccessToken()
if (!token) {
    redirect('/login')
}
return token
```

It does not check `isTokenExpired()`. A request with an expired access token (but whose cookie has not yet been deleted by the browser) will pass the auth check, receive an expired token, and fail at the Whoop API with a 401 — which is not caught or handled by `requireAuth()` itself. The route handler or API call must handle this separately.

---

## 6. Local Callback Server

**File:** `src/auth.py` lines 57–205 and 403–455.

### Port
Default port 8080 (`src/auth.py` line 418), parsed from `redirect_uri`. This is hardcoded as the fallback if `urlparse(self.redirect_uri).port` returns `None`. The default `redirect_uri` is `http://localhost:8080/callback`, so the parsed port is 8080. The port is only configurable by changing `redirect_uri`.

### Timeout

**Finding — [HIGH] `src/auth.py` lines 426–432: No timeout on the callback server**

```python
server = HTTPServer(("localhost", port), _CallbackHandler)
try:
    server.handle_request()
finally:
    server.server_close()
```

`HTTPServer.handle_request()` with no timeout argument blocks indefinitely. The default socket timeout for `HTTPServer` is `None` (no timeout). If the user never opens the browser, closes the tab, or the browser request never arrives, the process hangs forever. There is no `server.timeout` setting, no `threading.Timer`, and no `select`-based deadline anywhere in the authorization flow.

### Clean Shutdown
The `finally: server.server_close()` block (line 432) ensures the socket is released whether or not the request succeeded. This is correct.

### Single-Request Handling
`handle_request()` processes exactly one HTTP request, which is correct for an OAuth callback. The server does not continue listening after the callback is received.

### Class-Level State Pollution

**Finding — [MEDIUM] `src/auth.py` lines 72–74 and 200–204: `_CallbackHandler` uses class-level attributes**

```python
class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code: Optional[str] = None
    auth_state: Optional[str] = None
    error: Optional[str] = None
```

These are class attributes, not instance attributes. `_reset_callback_handler()` clears them before each authorization attempt, but if multiple `OAuthHandler` instances call `authorize()` concurrently (e.g., in a multi-user or test scenario), they share the same class-level state. The second instance's callback could overwrite the first's `auth_code` before the first reads it. For a single-user CLI tool this is acceptable, but it is a latent bug in any multi-threaded use case.

---

## 7. Summary of All Findings

| # | Severity | File | Line(s) | Description |
|---|----------|------|---------|-------------|
| F1 | **[CRITICAL]** | `src/auth.py` | 652–690, 529–617 | No mutex/lock protecting token refresh. Concurrent callers can trigger simultaneous refresh requests, potentially causing token invalidation if refresh tokens are rotated. |
| F2 | **[CRITICAL]** | `src/async_client.py` | 226–234 | `_get_auth_headers()` calls synchronous `get_valid_token()` which blocks the asyncio event loop during token refresh (uses `httpx.Client`, not `httpx.AsyncClient`). |
| F3 | **[HIGH]** | `src/client.py` | 315–322 | 401 responses from the API are not retried after an automatic token refresh. Caller must handle retry manually. Same issue in `src/async_client.py` lines 297–303. |
| F4 | **[HIGH]** | `src/utils.py` | 62 | Token file created without restricting permissions. Default umask produces world-readable `644` permissions. Tokens (access + refresh) readable by any local user. |
| F5 | **[HIGH]** | `src/auth.py` | 426–432 | Callback server `handle_request()` has no timeout. Process hangs indefinitely if user never completes OAuth flow. |
| F6 | **[MEDIUM]** | `src/auth.py` | 492 | No warning or assertion when `refresh_token` is absent from the token exchange response, even though `offline` scope was requested. |
| F7 | **[MEDIUM]** | `src/auth.py` | 598–617 | Transient 5xx errors during token refresh are raised as `WhoopTokenError` (fatal), forcing full re-auth unnecessarily. Same issue in `temp_web/app/api/whoop/auth/refresh/route.ts` lines 31–34. |
| F8 | **[MEDIUM]** | `temp_web/lib/api/tokens.ts` | 41–46 | Access token cookie `maxAge` is hardcoded to 3600 regardless of actual server-returned `expires_in`, causing TTL mismatch. |
| F9 | **[MEDIUM]** | `temp_web/lib/auth/server.ts` | 9–16 | `requireAuth()` does not check token expiry — an expired (but not yet browser-deleted) cookie passes the guard, resulting in a 401 at the Whoop API. |
| F10 | **[MEDIUM]** | `src/auth.py` | 72–74, 200–204 | `_CallbackHandler` uses class-level (shared) state. Multiple concurrent `OAuthHandler` instances share the same callback slot. |
| F11 | **[LOW]** | `temp_web/app/api/whoop/auth/login/route.ts` | 41 | `oauth_state` cookie `secure` flag only set in production; interceptable over plain HTTP in development. |
| F12 | **[LOW]** | `temp_web/app/api/whoop/auth/callback/route.ts` | 48 | `expires_in` silently defaults to `3600` if absent in token response. |
| F13 | **[LOW]** | `src/constants.py` | 113, `src/utils.py` 62 | Token file path is relative; location depends on caller's working directory, which can change between `authorize()` and subsequent calls. |

---

## 8. Detailed Remediation Notes

### F1 — Concurrent Refresh Race (CRITICAL)

Add a `threading.Lock` on `OAuthHandler`:

```python
import threading
self._refresh_lock = threading.Lock()

def get_valid_token(self) -> str:
    with self._refresh_lock:
        if is_token_expired(self._tokens):
            self._tokens = self.refresh_access_token()
    return self._tokens["access_token"]
```

For the async client, add an `asyncio.Lock` on the async path or move token refresh to an async method.

### F2 — Blocking Event Loop (CRITICAL)

`AsyncWhoopClient` should use an `httpx.AsyncClient` for token refresh, or delegate refresh to a dedicated async method. At minimum, `get_valid_token()` should not perform network I/O synchronously in an async context.

### F3 — No Retry After 401 (HIGH)

Implement a single-retry loop in `_request()`: on receiving 401, call `get_valid_token()` explicitly (forcing a refresh by invalidating the cached token), then retry the original request once.

### F4 — Token File Permissions (HIGH)

After writing the token file, call:

```python
import os, stat
os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
```

### F5 — Callback Server Timeout (HIGH)

Set `server.timeout` before calling `handle_request()`:

```python
server = HTTPServer(("localhost", port), _CallbackHandler)
server.timeout = 120  # 2-minute timeout
server.handle_request()
if not _CallbackHandler.auth_code and not _CallbackHandler.error:
    raise WhoopAuthError("OAuth callback timed out after 120 seconds")
```

---

## 9. What Works Correctly

The following areas are **well-implemented** and present no findings:

- Auth URL includes all required OAuth 2.0 parameters and all required scopes.
- State parameter is generated with CSPRNG and validated on callback in both Python and Next.js.
- `grant_type=authorization_code` and `redirect_uri` are correctly sent in token exchange.
- All four token response fields (`access_token`, `refresh_token`, `expires_in`, `token_type`) are extracted and stored.
- Token expiry is checked **proactively** with a 60-second buffer (Python) / 5-minute buffer (Next.js), not only on 401.
- `Authorization: Bearer {token}` is injected **per-request**, not once at client init — header stays current after refresh.
- `WhoopTokenError` / `AuthError` are raised as specific catchable exceptions on refresh failure.
- Token file (`.whoop_tokens.json`) is excluded from git via `.gitignore`.
- Corrupted or missing token files are handled gracefully (return `None`, not crash).
- Callback server shuts down cleanly via `finally: server.server_close()`.
- Next.js tokens stored in `httpOnly` cookies — not accessible to client-side JavaScript.
- Exception hierarchy is well-structured and semantically meaningful.
