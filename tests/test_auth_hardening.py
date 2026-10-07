"""
Hardening tests for the OAuth flow and the clients' 401 handling.

Covers the verified findings:

- C5: concurrent 401s must trigger exactly one refresh (WHOOP rotates
  refresh tokens, so a second refresh with the same token fails), and the
  async client must refresh without blocking the event loop.
- C20: the asyncio lock is created lazily per event loop.
- C6: a dead refresh token ends the authorization cleanly; authenticate()
  re-runs the browser flow; authenticate(force=True) and logout() exist.
- C16: the loopback callback server escapes reflected text, checks state
  before anything else, ignores stray paths and idle connections, and
  supports [::1].
- PKCE (opt-in) and the data clients honouring ``timeout=``.

The token endpoint is a fake that rotates refresh tokens on every refresh
and rejects a reused one with ``invalid_grant``, served through
httpx.MockTransport. Token files live in pytest's tmp_path. Nothing here
contacts WHOOP or sleeps with time.sleep.
"""

import asyncio
import base64
import hashlib
import re
import socket
import threading
import time
import urllib.parse
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from unittest.mock import patch

import httpx
import pytest

import whoopyy.auth as auth_module
from whoopyy.async_client import AsyncWhoopClient
from whoopyy.auth import AUTHORIZATION_ENDED_MESSAGE, OAuthHandler
from whoopyy.client import WhoopClient
from whoopyy.constants import API_BASE_URL
from whoopyy.exceptions import WhoopAuthError, WhoopTokenError
from whoopyy.utils import load_tokens, save_tokens


@pytest.fixture(autouse=True)
def _isolate_default_token_file(tmp_path, monkeypatch):
    """
    Redirect the default token file (~/.whoop_tokens.json) to a temp path.

    Every test below passes its own token_file; this is a safety net so a
    mistake can never read, lock or delete the developer's real tokens.
    """
    import os

    from whoopyy.constants import DEFAULT_TOKEN_FILE

    safe_path = str(tmp_path / "default_whoop_tokens.json")
    default_path = os.path.abspath(DEFAULT_TOKEN_FILE)

    def _safe(filepath):
        if os.path.abspath(os.fspath(filepath)) == default_path:
            return safe_path
        return filepath

    def _redirect_path_arg(func):
        def wrapper(filepath=DEFAULT_TOKEN_FILE, *args, **kwargs):
            return func(_safe(filepath), *args, **kwargs)
        return wrapper

    for name in (
        "load_tokens",
        "delete_tokens",
        "token_file_lock",
        "async_token_file_lock",
        "_check_token_file_writable",
        "_file_lock_held_by_current_thread",
    ):
        monkeypatch.setattr(auth_module, name, _redirect_path_arg(getattr(auth_module, name)))

    original_save = auth_module.save_tokens

    def _save(tokens, filepath=DEFAULT_TOKEN_FILE):
        return original_save(tokens, _safe(filepath))

    monkeypatch.setattr(auth_module, "save_tokens", _save)


# =============================================================================
# Fakes and helpers
# =============================================================================

PROFILE = {"user_id": 1, "email": "a@example.com", "first_name": "A", "last_name": "B"}
CLIENT_ID = "test_client_id"
CLIENT_SECRET = "test_client_secret"
WAIT = 10.0
"""Upper bound for event/barrier waits; only reached when a test fails."""


def _form(request: httpx.Request) -> Dict[str, str]:
    """Decode a form-encoded request body."""
    return dict(urllib.parse.parse_qsl(request.content.decode()))


def _bearer(request: httpx.Request) -> str:
    """Return the bearer token of a request."""
    return request.headers.get("Authorization", "").partition(" ")[2]


def _write_tokens(path: str, access_token: str, refresh_token: str, expires_in: float) -> None:
    """Save a token file whose access token expires ``expires_in`` seconds from now."""
    save_tokens(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
            "expires_at": time.time() + expires_in,
            "token_type": "bearer",
            "scope": "offline read:profile",
        },
        path,
    )


class RotatingTokenEndpoint:
    """
    Fake WHOOP token endpoint with single-use, rotating refresh tokens.

    Each successful refresh issues ``at<N>``/``rt<N>`` and invalidates every
    earlier access token and refresh token, as WHOOP documents. Presenting
    any other refresh token gets 400 ``invalid_grant``.
    """

    def __init__(self, refresh_token: str = "rt0") -> None:
        self._lock = threading.Lock()
        self.valid_refresh_token = refresh_token
        self.valid_access_tokens: Set[str] = set()
        self.generation = 0
        self.refresh_calls: List[str] = []
        self.rejected: List[str] = []
        self.transports: List[str] = []
        self.exchanges: List[Dict[str, str]] = []
        self.before_refresh: Optional[Callable[[Dict[str, str]], None]] = None
        self.fail_next: List[httpx.Response] = []

    def issue(self) -> Dict[str, Any]:
        """Rotate: issue the next token pair and invalidate the previous ones."""
        self.generation += 1
        access_token = f"at{self.generation}"
        self.valid_refresh_token = f"rt{self.generation}"
        self.valid_access_tokens = {access_token}
        return {
            "access_token": access_token,
            "refresh_token": self.valid_refresh_token,
            "expires_in": 3600,
            "token_type": "bearer",
            "scope": "offline read:profile",
        }

    def respond(self, form: Dict[str, str], transport: str) -> httpx.Response:
        """Answer one token endpoint request."""
        hook = self.before_refresh
        if hook is not None and form.get("grant_type") == "refresh_token":
            self.before_refresh = None
            hook(form)
        with self._lock:
            self.transports.append(transport)
            if form.get("grant_type") == "authorization_code":
                self.exchanges.append(form)
                return httpx.Response(200, json=self.issue())
            refresh_token = form.get("refresh_token", "")
            self.refresh_calls.append(refresh_token)
            if self.fail_next:
                return self.fail_next.pop(0)
            if refresh_token != self.valid_refresh_token:
                self.rejected.append(refresh_token)
                return httpx.Response(
                    400,
                    json={
                        "error": "invalid_grant",
                        "error_description": "The refresh token was already used",
                    },
                )
            return httpx.Response(200, json=self.issue())

    def sync_transport(self) -> httpx.MockTransport:
        """Transport for the handler's sync httpx.Client."""
        return httpx.MockTransport(lambda request: self.respond(_form(request), "sync"))

    def async_transport(
        self, gate: Optional[Callable[[], Awaitable[None]]] = None
    ) -> httpx.MockTransport:
        """Transport for the async refresh; ``gate`` runs before answering."""

        async def handler(request: httpx.Request) -> httpx.Response:
            if gate is not None:
                await gate()
            return self.respond(_form(request), "async")

        return httpx.MockTransport(handler)


def _wire_auth(
    handler: OAuthHandler,
    endpoint: RotatingTokenEndpoint,
    gate: Optional[Callable[[], Awaitable[None]]] = None,
) -> None:
    """Point both of a handler's token endpoint clients at the fake endpoint."""
    handler._http_client.close()
    handler._http_client = httpx.Client(transport=endpoint.sync_transport())
    handler._make_async_http_client = (  # type: ignore[method-assign]
        lambda: httpx.AsyncClient(transport=endpoint.async_transport(gate))
    )


def _make_sync_client(path: str, endpoint: RotatingTokenEndpoint, api) -> WhoopClient:
    """WhoopClient on ``path`` whose API and token traffic go to fakes."""
    client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
    _wire_auth(client.auth, endpoint)
    client._http_client.close()
    client._http_client = httpx.Client(base_url=API_BASE_URL, transport=httpx.MockTransport(api))
    return client


async def _make_async_client(
    path: str,
    endpoint: RotatingTokenEndpoint,
    api,
    gate: Optional[Callable[[], Awaitable[None]]] = None,
) -> AsyncWhoopClient:
    """AsyncWhoopClient on ``path`` whose API and token traffic go to fakes."""
    client = AsyncWhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
    _wire_auth(client.auth, endpoint, gate)
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(
        base_url=API_BASE_URL, transport=httpx.MockTransport(api)
    )
    return client


# =============================================================================
# C5: one refresh for concurrent 401s (sync)
# =============================================================================

class TestConcurrent401Sync:
    """Concurrent 401s in threads refresh exactly once."""

    def _api_with_barrier(self, endpoint: RotatingTokenEndpoint, parties: int):
        """API fake: all requests with the stale token get 401 at the same moment."""
        barrier = threading.Barrier(parties)

        def api(request: httpx.Request) -> httpx.Response:
            token = _bearer(request)
            if token == "stale":
                barrier.wait(timeout=WAIT)
                return httpx.Response(401, json={"error": "unauthorized"})
            if token in endpoint.valid_access_tokens:
                return httpx.Response(200, json=PROFILE)
            return httpx.Response(401, json={"error": "unauthorized"})

        return api

    def _run_threads(self, calls: List[Callable[[], Any]]) -> List[str]:
        results: List[str] = [""] * len(calls)

        def run(index: int) -> None:
            try:
                calls[index]()
                results[index] = "ok"
            except Exception as e:  # noqa: BLE001 - reported in the assertion
                results[index] = f"{type(e).__name__}: {e}"

        threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(WAIT)
        return results

    def test_six_threads_with_401_refresh_once(self, tmp_path) -> None:
        """6 threads all get 401: one refresh, no invalid_grant, all succeed on retry."""
        path = str(tmp_path / "tokens.json")
        # Valid by timestamp, but the server has invalidated it
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        client = _make_sync_client(path, endpoint, self._api_with_barrier(endpoint, 6))
        try:
            results = self._run_threads([client.get_profile_basic] * 6)
        finally:
            client.close()

        assert results == ["ok"] * 6
        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []
        saved = load_tokens(path)
        assert saved is not None
        assert saved["refresh_token"] == "rt1"
        assert saved["access_token"] == "at1"

    def test_two_handlers_sharing_a_token_file_refresh_once(self, tmp_path) -> None:
        """Two clients on one token file (like two processes): one refresh in total."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        api = self._api_with_barrier(endpoint, 6)
        first = _make_sync_client(path, endpoint, api)
        second = _make_sync_client(path, endpoint, api)
        try:
            results = self._run_threads(
                [first.get_profile_basic] * 3 + [second.get_profile_basic] * 3
            )
        finally:
            first.close()
            second.close()

        assert results == ["ok"] * 6
        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []

    def test_refresh_if_stale_reuses_token_rotated_elsewhere(self, tmp_path) -> None:
        """If the token file already holds a newer token, no refresh is made."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.get_valid_token() == "at0"
            # Another process refreshed and saved the result
            _write_tokens(path, "at-other", "rt-other", expires_in=3600)

            assert handler.refresh_if_stale("at0") == "at-other"
        finally:
            handler.close()

        assert endpoint.refresh_calls == []

    def test_refresh_if_stale_refreshes_the_rejected_token(self, tmp_path) -> None:
        """If the current token is the rejected one, it is refreshed once."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.refresh_if_stale("at0") == "at1"
            # The rejected token is already replaced: no second refresh
            assert handler.refresh_if_stale("at0") == "at1"
        finally:
            handler.close()

        assert endpoint.refresh_calls == ["rt0"]

    def test_refresh_if_stale_with_unknown_token_keeps_valid_token(self, tmp_path) -> None:
        """seen_access_token=None returns a current unexpired token without refreshing."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.refresh_if_stale(None) == "at0"
        finally:
            handler.close()

        assert endpoint.refresh_calls == []

    def test_expired_token_in_second_handler_is_reloaded_not_refreshed(self, tmp_path) -> None:
        """A handler with stale memory picks up a rotation saved by another handler."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        first = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        second = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(first, endpoint)
        _wire_auth(second, endpoint)
        try:
            assert second.has_valid_tokens() is True  # loads expired at0/rt0
            assert first.get_valid_token() == "at1"  # rotates rt0 -> rt1
            assert second.get_valid_token() == "at1"  # reloads instead of reusing rt0
        finally:
            first.close()
            second.close()

        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []


# =============================================================================
# C5: one refresh for concurrent 401s (async), without blocking the loop
# =============================================================================

class TestConcurrent401Async:
    """Concurrent 401s in coroutines refresh exactly once, off the blocking path."""

    async def test_gather_six_401s_refresh_once_without_blocking_loop(
        self, tmp_path, monkeypatch
    ) -> None:
        """asyncio.gather of 6 requests that all get 401: one async refresh.

        The fake token endpoint only answers after a ticker coroutine has
        run several times while the refresh is in flight, so the test can
        only pass if the event loop keeps running during the refresh.
        """
        loop_thread = threading.get_ident()
        sleeps_on_loop: List[float] = []
        real_sleep = time.sleep

        def spy_sleep(seconds: float) -> None:
            if threading.get_ident() == loop_thread:
                sleeps_on_loop.append(seconds)
            real_sleep(seconds)

        monkeypatch.setattr(time, "sleep", spy_sleep)

        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")

        refresh_in_flight = asyncio.Event()
        ticker_done = asyncio.Event()
        ticks = {"during_refresh": 0}

        async def gate() -> None:
            refresh_in_flight.set()
            await asyncio.wait_for(ticker_done.wait(), WAIT)

        async def ticker() -> None:
            await refresh_in_flight.wait()
            for _ in range(5):
                await asyncio.sleep(0)
                ticks["during_refresh"] += 1
            ticker_done.set()

        arrived = {"n": 0}
        all_arrived = asyncio.Event()

        async def api(request: httpx.Request) -> httpx.Response:
            token = _bearer(request)
            if token == "stale":
                arrived["n"] += 1
                if arrived["n"] == 6:
                    all_arrived.set()
                await asyncio.wait_for(all_arrived.wait(), WAIT)
                return httpx.Response(401, json={"error": "unauthorized"})
            if token in endpoint.valid_access_tokens:
                return httpx.Response(200, json=PROFILE)
            return httpx.Response(401, json={"error": "unauthorized"})

        client = await _make_async_client(path, endpoint, api, gate)
        ticker_task = asyncio.ensure_future(ticker())
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(client.get_profile_basic() for _ in range(6)), return_exceptions=True
                ),
                WAIT,
            )
        finally:
            ticker_task.cancel()
            await client.close()

        assert [type(r).__name__ for r in results] == ["UserProfileBasic"] * 6
        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []
        # Only the async token client was used, never the blocking sync one
        assert endpoint.transports == ["async"]
        assert ticks["during_refresh"] == 5
        assert sleeps_on_loop == []

    async def test_async_refresh_retry_never_calls_time_sleep(
        self, tmp_path, monkeypatch
    ) -> None:
        """5xx backoff on the async path uses asyncio.sleep, not time.sleep."""
        monkeypatch.setattr(auth_module, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
        loop_thread = threading.get_ident()
        sleeps_on_loop: List[float] = []
        real_sleep = time.sleep

        def spy_sleep(seconds: float) -> None:
            if threading.get_ident() == loop_thread:
                sleeps_on_loop.append(seconds)
            real_sleep(seconds)

        monkeypatch.setattr(time, "sleep", spy_sleep)

        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(503, text="unavailable")]
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert await handler.async_get_valid_token() == "at1"
        finally:
            handler.close()

        assert endpoint.refresh_calls == ["rt0", "rt0"]
        assert endpoint.transports == ["async", "async"]
        assert sleeps_on_loop == []

    async def test_async_refresh_if_stale_reuses_token_rotated_elsewhere(self, tmp_path) -> None:
        """Async twin: a newer token in the file is reused without a refresh."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert await handler.async_get_valid_token() == "at0"
            # Another process rotated rt0 -> rt-other at WHOOP and saved the result
            endpoint.valid_refresh_token = "rt-other"
            _write_tokens(path, "at-other", "rt-other", expires_in=3600)

            assert await handler.async_refresh_if_stale("at0") == "at-other"
            # Now the newer token is rejected too: refresh with the newer refresh token
            assert await handler.async_refresh_if_stale("at-other") == "at1"
        finally:
            handler.close()

        assert endpoint.refresh_calls == ["rt-other"]
        assert endpoint.rejected == []


# =============================================================================
# C20: asyncio lock bound lazily to the running loop
# =============================================================================

class TestAsyncLockEventLoops:
    """OAuthHandler works across event loops and without one at construction."""

    def test_handler_built_outside_loop_survives_two_asyncio_runs(self, tmp_path) -> None:
        """Constructed with no loop, used in two asyncio.run() calls with contention."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")

        async def yield_a_few_times() -> None:
            # Let the other coroutines queue on the lock while this refresh waits
            for _ in range(3):
                await asyncio.sleep(0)

        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint, gate=yield_a_few_times)
        assert handler._async_lock is None  # nothing bound at construction

        async def contended():
            tokens = await asyncio.gather(*(handler.async_get_valid_token() for _ in range(4)))
            return (
                tokens,
                handler._async_lock,
                handler._async_lock_loop,
                asyncio.get_running_loop(),
            )

        try:
            tokens1, lock1, bound1, loop1 = asyncio.run(contended())
            # Expire the token so the second loop has to refresh under contention too
            _write_tokens(path, "at1", "rt1", expires_in=-10)
            handler._tokens = None
            tokens2, lock2, bound2, loop2 = asyncio.run(contended())
        finally:
            handler.close()

        assert tokens1 == ["at1"] * 4
        assert tokens2 == ["at2"] * 4
        assert bound1 is loop1
        assert bound2 is loop2
        assert lock2 is not lock1  # no lock left bound to the closed first loop
        assert endpoint.refresh_calls == ["rt0", "rt1"]
        assert endpoint.rejected == []

    def test_handler_constructed_in_thread_without_event_loop(self, tmp_path) -> None:
        """Python 3.9 raised 'There is no current event loop' here."""
        errors: List[BaseException] = []

        def build() -> None:
            try:
                OAuthHandler(
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    token_file=str(tmp_path / "tokens.json"),
                ).close()
            except BaseException as e:  # noqa: BLE001 - asserted below
                errors.append(e)

        thread = threading.Thread(target=build)
        thread.start()
        thread.join(WAIT)

        assert errors == []

    def test_sync_client_constructed_after_asyncio_run(self, tmp_path) -> None:
        """A sync client can be built in the main thread after asyncio.run()."""
        asyncio.run(asyncio.sleep(0))
        client = WhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
        )
        client.close()


# =============================================================================
# C6: dead refresh token, authenticate(force=True), logout()
# =============================================================================

class TestDeadRefreshToken:
    """A rejected refresh token ends the authorization and allows re-auth."""

    def test_dead_refresh_token_clears_tokens_and_file(self, tmp_path) -> None:
        """invalid_grant: tokens cleared, file deleted, clear 'authorization ended' error."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "dead", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(client.auth, endpoint)
        try:
            with pytest.raises(WhoopTokenError) as exc_info:
                client.auth.get_valid_token()

            assert AUTHORIZATION_ENDED_MESSAGE in str(exc_info.value)
            assert "authorization has ended" in str(exc_info.value)
            assert "authenticate()" in str(exc_info.value)
            assert exc_info.value.status_code == 400
            assert client.auth._tokens is None
            assert not (tmp_path / "tokens.json").exists()
            assert client.auth.has_valid_tokens() is False
            assert client.is_authenticated() is False

            # The documented recovery now works: authenticate() runs the browser flow
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate(auto_open_browser=False)
            mock_authorize.assert_called_once_with(auto_open_browser=False)
        finally:
            client.close()

        assert endpoint.refresh_calls == ["dead"]

    def test_dead_refresh_token_via_api_401(self, tmp_path) -> None:
        """A 401 whose refresh is rejected surfaces the 'authorization ended' error."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "revoked", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        client = _make_sync_client(
            path, endpoint, lambda request: httpx.Response(401, json={"error": "unauthorized"})
        )
        try:
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                client.get_profile_basic()
        finally:
            client.close()

        assert not (tmp_path / "tokens.json").exists()

    async def test_dead_refresh_token_async(self, tmp_path) -> None:
        """Async client: same outcome through the non-blocking refresh."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "revoked", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")

        async def api(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        client = await _make_async_client(path, endpoint, api)
        try:
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                await client.get_profile_basic()
            assert client.auth._tokens is None
            assert not (tmp_path / "tokens.json").exists()
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_called_once_with(auto_open_browser=True)
        finally:
            await client.close()

        assert endpoint.transports == ["async"]

    def test_is_authenticated_turns_false_after_dead_token(self, tmp_path) -> None:
        """authenticate() succeeded earlier; a dead refresh token makes is_authenticated() False."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "revoked", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        client = _make_sync_client(
            path, endpoint, lambda request: httpx.Response(401, json={"error": "unauthorized"})
        )
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_not_called()
            assert client.is_authenticated() is True

            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                client.get_profile_basic()

            assert client.is_authenticated() is False
        finally:
            client.close()

    async def test_is_authenticated_turns_false_after_dead_token_async(self, tmp_path) -> None:
        """Async twin: is_authenticated() follows the cleared tokens, not the old flag."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "revoked", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")

        async def api(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        client = await _make_async_client(path, endpoint, api)
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_not_called()
            assert client.is_authenticated() is True

            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                await client.get_profile_basic()

            assert client.is_authenticated() is False
        finally:
            await client.close()

    def test_token_inactive_is_also_treated_as_dead(self, tmp_path) -> None:
        """Hydra answers 401 token_inactive for a reused refresh token."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(401, json={"error": "token_inactive"})]
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="authorization has ended") as exc_info:
                handler.refresh_access_token()
        finally:
            handler.close()

        assert exc_info.value.status_code == 401
        assert not (tmp_path / "tokens.json").exists()

    def test_client_authentication_error_keeps_tokens(self, tmp_path) -> None:
        """invalid_client is a credentials problem: the tokens are not deleted."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(401, json={"error": "invalid_client"})]
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError) as exc_info:
                handler.get_valid_token()
            assert "authorization has ended" not in str(exc_info.value)
            assert handler._tokens is not None
        finally:
            handler.close()

        saved = load_tokens(path)
        assert saved is not None
        assert saved["refresh_token"] == "rt0"

    def test_rotation_by_another_process_is_picked_up(self, tmp_path) -> None:
        """invalid_grant because another process just rotated: use its newer tokens."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")

        def other_process_refreshes_first(form: Dict[str, str]) -> None:
            # A process that does not share our lock (e.g. an older whoopyy)
            # spends rt0 and saves its result just before our request lands.
            issued = endpoint.issue()
            _write_tokens(path, issued["access_token"], issued["refresh_token"], 3600)

        endpoint.before_refresh = other_process_refreshes_first
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.get_valid_token() == "at1"
        finally:
            handler.close()

        assert endpoint.rejected == ["rt0"]  # our request lost the race...
        saved = load_tokens(path)  # ...but the rotated tokens were kept
        assert saved is not None
        assert saved["refresh_token"] == "rt1"

    def test_expired_rotation_by_another_process_is_refreshed_once(self, tmp_path) -> None:
        """If the other process's tokens are expired too, refresh once with its token."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")

        def other_process_refreshes_first(form: Dict[str, str]) -> None:
            issued = endpoint.issue()
            _write_tokens(path, issued["access_token"], issued["refresh_token"], -10)

        endpoint.before_refresh = other_process_refreshes_first
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.get_valid_token() == "at2"
        finally:
            handler.close()

        assert endpoint.refresh_calls == ["rt0", "rt1"]
        assert endpoint.rejected == ["rt0"]

    async def test_rotation_by_another_process_is_picked_up_async(self, tmp_path) -> None:
        """Async twin of the rotation race."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")

        def other_process_refreshes_first(form: Dict[str, str]) -> None:
            issued = endpoint.issue()
            _write_tokens(path, issued["access_token"], issued["refresh_token"], 3600)

        endpoint.before_refresh = other_process_refreshes_first
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert await handler.async_get_valid_token() == "at1"
        finally:
            handler.close()

        assert endpoint.rejected == ["rt0"]
        assert endpoint.transports == ["async"]
        saved = load_tokens(path)
        assert saved is not None
        assert saved["refresh_token"] == "rt1"

    def test_authenticate_runs_browser_flow_without_usable_refresh_token(self, tmp_path) -> None:
        """An expired access token with an empty refresh token is not usable."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "", expires_in=-10)
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_called_once_with(auto_open_browser=True)
        finally:
            client.close()

    def test_authenticate_skips_browser_with_valid_tokens(self, tmp_path) -> None:
        """Without force, stored usable tokens skip the browser flow."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_not_called()
        finally:
            client.close()

    def test_authenticate_force_runs_browser_flow(self, tmp_path) -> None:
        """authenticate(force=True) runs the flow even with valid tokens."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        client._cache_set("profile_basic", object(), ttl=300)
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate(auto_open_browser=False, force=True)
            mock_authorize.assert_called_once_with(auto_open_browser=False)
            assert client._authenticated is True
            assert client._cache == {}
        finally:
            client.close()

    async def test_async_authenticate_force_runs_browser_flow(self, tmp_path) -> None:
        """AsyncWhoopClient.authenticate(force=True) runs the flow too."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = AsyncWhoopClient(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path
        )
        try:
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
                mock_authorize.assert_not_called()
                client.authenticate(force=True)
            mock_authorize.assert_called_once_with(auto_open_browser=True)
        finally:
            await client.close()

    def test_logout_clears_tokens_file_and_cache_without_network(self, tmp_path) -> None:
        """logout() forgets everything locally and never calls WHOOP."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        requests: List[str] = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(500)

        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        client.auth._http_client.close()
        client.auth._http_client = httpx.Client(transport=httpx.MockTransport(record))
        client._http_client.close()
        client._http_client = httpx.Client(
            base_url=API_BASE_URL, transport=httpx.MockTransport(record)
        )
        try:
            client.authenticate()
            client._cache_set("profile_basic", object(), ttl=300)

            client.logout()

            assert client.auth._tokens is None
            assert not (tmp_path / "tokens.json").exists()
            assert client._cache == {}
            assert client.is_authenticated() is False
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_called_once()
        finally:
            client.close()

        assert requests == []

    async def test_async_logout_clears_tokens_file_and_cache_without_network(
        self, tmp_path
    ) -> None:
        """Async logout() forgets everything locally and never calls WHOOP."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        requests: List[str] = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(500)

        client = AsyncWhoopClient(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path
        )
        client.auth._http_client.close()
        client.auth._http_client = httpx.Client(transport=httpx.MockTransport(record))
        client.auth._make_async_http_client = (  # type: ignore[method-assign]
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(record))
        )
        await client._http_client.aclose()
        client._http_client = httpx.AsyncClient(
            base_url=API_BASE_URL, transport=httpx.MockTransport(record)
        )
        try:
            client.authenticate()
            client._cache_set("profile_basic", object(), ttl=300)

            await client.logout()

            assert client.auth._tokens is None
            assert not (tmp_path / "tokens.json").exists()
            assert client._cache == {}
            assert client.is_authenticated() is False
        finally:
            await client.close()

        assert requests == []


class _TokensClearedBetweenReads(OAuthHandler):
    """
    Handler whose ``_tokens`` reads replay ``script``, then return None.

    Simulates another thread clearing the tokens (logout, or a rejected
    refresh token) between two reads of the lock-free fast paths.
    """

    def __init__(self, script: List[Optional[Dict[str, Any]]], **kwargs: Any) -> None:
        self.script = list(script)
        super().__init__(**kwargs)

    @property  # type: ignore[override]
    def _tokens(self) -> Optional[Dict[str, Any]]:
        return self.script.pop(0) if self.script else None

    @_tokens.setter
    def _tokens(self, value: Optional[Dict[str, Any]]) -> None:
        pass


class TestTokensClearedConcurrently:
    """The lock-free fast paths read the in-memory tokens exactly once."""

    @staticmethod
    def _handler(tmp_path) -> _TokensClearedBetweenReads:
        tokens = {
            "access_token": "at0",
            "refresh_token": "rt0",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
        }
        return _TokensClearedBetweenReads(
            [tokens, tokens],
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
        )

    def test_get_valid_token_survives_tokens_cleared_mid_call(self, tmp_path) -> None:
        handler = self._handler(tmp_path)
        try:
            assert handler.get_valid_token() == "at0"
        finally:
            handler.close()

    async def test_async_get_valid_token_survives_tokens_cleared_mid_call(
        self, tmp_path
    ) -> None:
        handler = self._handler(tmp_path)
        try:
            assert await handler.async_get_valid_token() == "at0"
        finally:
            handler.close()

    def test_has_valid_tokens_survives_tokens_cleared_mid_call(self, tmp_path) -> None:
        handler = self._handler(tmp_path)
        try:
            assert handler.has_valid_tokens() is True
        finally:
            handler.close()


# =============================================================================
# C16: loopback callback server
# =============================================================================

def _free_port(family: int = socket.AF_INET, host: str = "127.0.0.1") -> int:
    """Find a free TCP port on a loopback address."""
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def _ipv6_loopback_available() -> bool:
    """Tell whether this machine can bind the IPv6 loopback address."""
    if not socket.has_ipv6:
        return False
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        probe.bind(("::1", 0))
        return True
    except OSError:
        return False
    finally:
        probe.close()


class CallbackFlow:
    """Run OAuthHandler._wait_for_callback on a background thread."""

    def __init__(self, tmp_path, host: str = "localhost", state: str = "expected-state") -> None:
        family = socket.AF_INET6 if host == "[::1]" else socket.AF_INET
        bind_host = "::1" if host == "[::1]" else "127.0.0.1"
        self.port = _free_port(family, bind_host)
        self.base = f"http://{host}:{self.port}"
        self.state = state
        self.handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=f"{self.base}/callback",
            token_file=str(tmp_path / "tokens.json"),
        )
        # Bound and listening before the thread starts: requests queue up
        self.server = self.handler._create_callback_server(state)
        self.code: Optional[str] = None
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.http = httpx.Client(trust_env=False, timeout=WAIT)

    def _run(self) -> None:
        try:
            self.code = self.handler._wait_for_callback(self.state, server=self.server)
        except BaseException as e:  # noqa: BLE001 - inspected by the tests
            self.error = e

    def get(self, path_and_query: str) -> httpx.Response:
        return self.http.get(self.base + path_and_query)

    def finish(self) -> None:
        self.thread.join(WAIT)
        assert not self.thread.is_alive(), "callback flow did not finish"
        self.http.close()
        self.handler.close()


@pytest.fixture
def fast_callback(monkeypatch):
    """Short socket timeout; a deadline long enough to never be hit by accident."""
    monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)


class TestCallbackServer:
    """The OAuth callback server cannot be confused, hung or used for XSS."""

    def test_correct_state_and_code_returns_code(self, tmp_path, fast_callback) -> None:
        flow = CallbackFlow(tmp_path)
        response = flow.get("/callback?code=the-code&state=expected-state")
        flow.finish()

        assert response.status_code == 200
        assert "Authorization Successful" in response.text
        assert flow.code == "the-code"
        assert flow.error is None

    def test_reflected_error_is_html_escaped(self, tmp_path, fast_callback) -> None:
        flow = CallbackFlow(tmp_path)
        response = flow.get(
            "/callback?state=expected-state&error=%3Cscript%3Ealert(1)%3C%2Fscript%3E"
        )
        flow.finish()

        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert isinstance(flow.error, WhoopAuthError)
        assert "Authorization denied" in str(flow.error)

    def test_forged_error_with_wrong_state_is_rejected(self, tmp_path, fast_callback) -> None:
        """A forged error (or code) without the right state does not end the flow."""
        flow = CallbackFlow(tmp_path)
        forged_error = flow.get("/callback?error=access_denied&state=WRONG")
        forged_code = flow.get("/callback?code=attacker-code&state=WRONG")
        no_state = flow.get("/callback?error=access_denied")

        assert forged_error.status_code == 400
        assert forged_code.status_code == 400
        assert no_state.status_code == 400
        assert not flow.server.result_ready.is_set()
        assert flow.thread.is_alive()

        real = flow.get("/callback?code=real-code&state=expected-state")
        flow.finish()

        assert real.status_code == 200
        assert flow.code == "real-code"
        assert flow.error is None

    def test_stray_request_to_other_path_is_ignored(self, tmp_path, fast_callback) -> None:
        flow = CallbackFlow(tmp_path)
        favicon = flow.get("/favicon.ico")
        other = flow.get("/totally/other?code=abc&state=expected-state")

        assert favicon.status_code == 404
        assert other.status_code == 404
        assert not flow.server.result_ready.is_set()

        flow.get("/callback?code=real-code&state=expected-state")
        flow.finish()

        assert flow.code == "real-code"

    def test_idle_connection_does_not_delay_real_callback(self, tmp_path, monkeypatch) -> None:
        """An idle pre-connect does not hold up a callback on another connection."""
        monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", WAIT)
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)
        flow = CallbackFlow(tmp_path)
        idle = socket.create_connection(("127.0.0.1", flow.port))
        try:
            idle.sendall(b"GET /callback?co")  # incomplete request line
            started = time.monotonic()
            response = flow.get("/callback?code=real-code&state=expected-state")
            flow.finish()
            elapsed = time.monotonic() - started
        finally:
            idle.close()

        assert response.status_code == 200
        assert flow.code == "real-code"
        # Far below the idle connection's 10s read timeout
        assert elapsed < WAIT / 2

    def test_idle_connection_does_not_hang_past_deadline(self, tmp_path, monkeypatch) -> None:
        """With only an idle connection, the flow still ends at the deadline."""
        monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", WAIT)
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", 0.3)
        started = time.monotonic()
        flow = CallbackFlow(tmp_path)
        idle = socket.create_connection(("127.0.0.1", flow.port))
        try:
            idle.sendall(b"GET /callback?co")
            flow.finish()
        finally:
            idle.close()
        elapsed = time.monotonic() - started

        assert isinstance(flow.error, WhoopAuthError)
        assert "timed out after 0.3 seconds" in str(flow.error)
        assert elapsed < WAIT / 2

    @pytest.mark.skipif(not _ipv6_loopback_available(), reason="no IPv6 loopback")
    def test_ipv6_loopback_redirect(self, tmp_path, fast_callback) -> None:
        flow = CallbackFlow(tmp_path, host="[::1]")
        response = flow.get("/callback?code=v6-code&state=expected-state")
        flow.finish()

        assert response.status_code == 200
        assert flow.code == "v6-code"

    def test_busy_port_fails_before_browser_opens(self, tmp_path) -> None:
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=f"http://localhost:{port}/callback",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            with patch.object(auth_module.webbrowser, "open") as mock_open:
                with pytest.raises(WhoopAuthError, match="callback server"):
                    handler.authorize()
            mock_open.assert_not_called()
        finally:
            busy.close()
            handler.close()

    def test_non_loopback_redirect_rejected_before_browser_opens(self, tmp_path) -> None:
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri="http://example.com/callback",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            with patch.object(auth_module.webbrowser, "open") as mock_open:
                with pytest.raises(WhoopAuthError, match="localhost"):
                    handler.authorize()
            mock_open.assert_not_called()
        finally:
            handler.close()


# =============================================================================
# PKCE (opt-in)
# =============================================================================

def _run_authorize(tmp_path, monkeypatch, use_pkce: bool):
    """
    Run the real authorize() flow against a fake browser and token endpoint.

    The fake browser follows the authorization URL like WHOOP would: it
    redirects to the callback with a code and the URL's state.

    Returns:
        Tuple of (authorization URL query dict, exchange form, tokens, handler token file).
    """
    monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)
    port = _free_port()
    path = str(tmp_path / "tokens.json")
    endpoint = RotatingTokenEndpoint()
    handler = OAuthHandler(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=f"http://localhost:{port}/callback",
        token_file=path,
        use_pkce=use_pkce,
    )
    _wire_auth(handler, endpoint)
    opened: List[str] = []

    def fake_browser(url: str) -> bool:
        opened.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        redirect = (
            f"{query['redirect_uri'][0]}?code=auth-code&state="
            f"{urllib.parse.quote(query['state'][0])}"
        )

        def follow() -> None:
            with httpx.Client(trust_env=False, timeout=WAIT) as browser:
                browser.get(redirect)

        threading.Thread(target=follow, daemon=True).start()
        return True

    monkeypatch.setattr(auth_module.webbrowser, "open", fake_browser)
    try:
        tokens = handler.authorize()
    finally:
        handler.close()

    assert len(opened) == 1
    assert len(endpoint.exchanges) == 1
    query = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)
    return query, endpoint.exchanges[0], tokens, path


class TestPKCE:
    """PKCE is sent only when use_pkce=True, and the pair matches."""

    def test_use_pkce_sends_s256_challenge_and_matching_verifier(
        self, tmp_path, monkeypatch
    ) -> None:
        query, exchange, tokens, path = _run_authorize(tmp_path, monkeypatch, use_pkce=True)

        assert query["code_challenge_method"] == ["S256"]
        challenge = query["code_challenge"][0]
        verifier = exchange["code_verifier"]
        assert 43 <= len(verifier) <= 128
        assert re.fullmatch(r"[A-Za-z0-9\-._~]+", verifier)
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == expected
        assert "=" not in challenge
        # The confidential-client secret is still sent alongside the verifier
        assert exchange["client_secret"] == CLIENT_SECRET
        assert exchange["code"] == "auth-code"
        assert tokens["access_token"] == "at1"
        assert load_tokens(path) is not None

    def test_default_sends_neither_challenge_nor_verifier(self, tmp_path, monkeypatch) -> None:
        query, exchange, tokens, path = _run_authorize(tmp_path, monkeypatch, use_pkce=False)

        assert "code_challenge" not in query
        assert "code_challenge_method" not in query
        assert "code_verifier" not in exchange
        assert exchange["code"] == "auth-code"
        saved = load_tokens(path)
        assert saved is not None
        assert saved["access_token"] == tokens["access_token"]

    def test_each_flow_uses_a_fresh_verifier(self) -> None:
        first = auth_module._generate_pkce_pair()
        second = auth_module._generate_pkce_pair()
        assert first != second

    def test_clients_pass_use_pkce_through(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        default = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        enabled = WhoopClient(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path, use_pkce=True
        )
        try:
            assert default.auth.use_pkce is False
            assert enabled.auth.use_pkce is True
        finally:
            default.close()
            enabled.close()

    async def test_async_client_passes_use_pkce_through(self, tmp_path) -> None:
        client = AsyncWhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            use_pkce=True,
        )
        try:
            assert client.auth.use_pkce is True
        finally:
            await client.close()


# =============================================================================
# timeout= is honoured by the data clients
# =============================================================================

class TestClientTimeout:
    """The constructor timeout reaches the API HTTP client."""

    def test_sync_client_uses_constructor_timeout(self, tmp_path) -> None:
        client = WhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=5,
        )
        try:
            timeout = client._http_client.timeout
            assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5, 5, 5, 5)
        finally:
            client.close()

    def test_sync_client_caps_connect_timeout(self, tmp_path) -> None:
        short = WhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=2,
        )
        long = WhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=90,
        )
        try:
            assert short._http_client.timeout.connect == 2
            assert short._http_client.timeout.read == 2
            assert long._http_client.timeout.connect == 5.0
            assert long._http_client.timeout.read == 90
        finally:
            short.close()
            long.close()

    def test_timeout_none_still_accepted(self, tmp_path) -> None:
        """timeout=None was accepted before; it now means no read timeout."""
        client = WhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=None,  # type: ignore[arg-type]
        )
        try:
            assert client._http_client.timeout.read is None
            assert client._http_client.timeout.connect == 5.0
        finally:
            client.close()

    async def test_async_client_uses_constructor_timeout(self, tmp_path) -> None:
        client = AsyncWhoopClient(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=5,
        )
        try:
            timeout = client._http_client.timeout
            assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5, 5, 5, 5)
            # The async token refresh uses it as well
            refresh_client = client.auth._make_async_http_client()
            assert refresh_client.timeout.read == 5
            await refresh_client.aclose()
        finally:
            await client.close()
