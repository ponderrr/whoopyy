"""
Robustness tests for token refresh, token storage and the callback server.

Each test pins down a failure found by reviewing the auth hardening:

- Lock order: synchronous token code on an event loop thread, while a task
  of that loop holds the token file lock and another thread holds the
  handler's thread lock, raised nothing and deadlocked.
- Cancellation: a caller cancelled while its async refresh was in flight
  dropped the refresh token WHOOP had already rotated.
- Failed refreshes: callers queued behind a failing refresh repeated it one
  after another, and callers queued behind a rejected refresh token got
  "No tokens available" instead of "authorization has ended".
- Token storage: a symlinked or unwritable token file was noticed only
  after the refresh token had been spent; a read-only directory or a
  bind-mounted token file could not be saved at all; a token file that
  could not be deleted brought dead tokens back.
- Lock-free loads could cache tokens that logout() had just cleared.
- Callback server: a ``localhost`` redirect could be answered by another
  program listening on ::1, and handler threads outlived the flow.
- Gaps found by mutation testing (async cross-process lock, authenticate()
  cache clearing, authorize() storing under the lock, refresh timeout,
  callback socket timeout).

All network traffic goes to fakes (httpx.MockTransport or loopback
sockets); token files live in pytest's tmp_path.
"""

import asyncio
import contextlib
import errno
import os
import socket
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Set
from unittest.mock import patch

import httpx
import pytest
import whoopyy.auth as auth_module
import whoopyy.utils as utils_module
from whoopyy.async_client import AsyncWhoopClient
from whoopyy.auth import OAuthHandler
from whoopyy.client import WhoopClient
from whoopyy.exceptions import WhoopAuthError, WhoopTokenError
from whoopyy.utils import load_tokens, save_tokens

from tests.test_auth_hardening import (  # noqa: F401 - autouse fixture
    CLIENT_ID,
    CLIENT_SECRET,
    PROFILE,
    WAIT,
    CallbackFlow,
    RotatingTokenEndpoint,
    _bearer,
    _form,
    _free_port,
    _ipv6_loopback_available,
    _isolate_default_token_file,
    _make_async_client,
    _make_sync_client,
    _wire_auth,
    _write_tokens,
)

POSIX_PERMISSIONS = pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permission checks (not Windows, not root)",
)


def _run_threads(calls: List[Any]) -> List[str]:
    """Run each callable on its own thread; return "ok" or "Type: message"."""
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
    assert not any(t.is_alive() for t in threads), "a caller hung"
    return results


def _api_401_for(stale: str, endpoint: RotatingTokenEndpoint, parties: int):
    """API fake: ``parties`` requests with the stale token get 401 together."""
    barrier = threading.Barrier(parties)

    def api(request: httpx.Request) -> httpx.Response:
        token = _bearer(request)
        if token == stale:
            barrier.wait(timeout=WAIT)
            return httpx.Response(401, json={"error": "unauthorized"})
        if token in endpoint.valid_access_tokens:
            return httpx.Response(200, json=PROFILE)
        return httpx.Response(401, json={"error": "unauthorized"})

    return api


def _count_threads_entering_token_lock(handler: OAuthHandler) -> threading.Condition:
    """
    Wrap ``handler._token_lock`` to record which threads have asked for it.

    Returns:
        A Condition whose ``threads`` attribute is the set of thread idents
        that entered, notified on every entry.
    """
    cond = threading.Condition()
    entered: Set[int] = set()
    cond.threads = entered  # type: ignore[attr-defined]
    real_lock = handler._token_lock

    @contextlib.contextmanager
    def counting_lock() -> Iterator[None]:
        with cond:
            entered.add(threading.get_ident())
            cond.notify_all()
        with real_lock():
            yield

    handler._token_lock = counting_lock  # type: ignore[method-assign]
    return cond


# =============================================================================
# Lock order: sync token code on the event loop thread never deadlocks
# =============================================================================

class TestSharedHandlerLockOrder:
    """One handler shared by sync code and an event loop thread."""

    def _scenario(self, tmp_path, step3) -> Dict[str, Any]:
        """
        Drive the deadlock sequence on a dedicated event loop thread.

        1. Task T on the loop thread refreshes asynchronously and holds the
           token file lock while the token endpoint is held back.
        2. Worker thread S calls refresh_if_stale(): it takes the handler's
           thread lock and waits for the token file lock.
        3. ``step3(handler)`` runs synchronously on the loop thread.

        Returns:
            What each step produced; ``finished`` is False if the loop
            thread hung.
        """
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        out: Dict[str, Any] = {"finished": False}

        async def main() -> None:
            release = asyncio.Event()

            async def gate() -> None:
                await release.wait()

            _wire_auth(handler, endpoint, gate)
            task = asyncio.ensure_future(handler.async_refresh_if_stale("stale"))
            for _ in range(int(WAIT / 0.01)):
                await asyncio.sleep(0.01)
                if utils_module._file_lock_held_by_current_thread(path):
                    break
            out["task_holds_file_lock"] = utils_module._file_lock_held_by_current_thread(path)

            worker_result: Dict[str, str] = {}

            def worker() -> None:
                try:
                    worker_result["token"] = handler.refresh_if_stale("stale")
                except Exception as e:  # noqa: BLE001 - asserted below
                    worker_result["token"] = f"{type(e).__name__}: {e}"

            worker_thread = threading.Thread(target=worker, daemon=True)
            worker_thread.start()
            # Wait (blocking the loop on purpose) until S holds the thread lock
            worker_holds = False
            deadline = time.monotonic() + WAIT
            while not worker_holds and time.monotonic() < deadline:
                if handler._refresh_lock.acquire(blocking=False):
                    handler._refresh_lock.release()
                    time.sleep(0.01)
                else:
                    worker_holds = True
            out["worker_holds_thread_lock"] = worker_holds

            try:
                step3(handler)
                out["step3"] = "returned"
            except BaseException as e:  # noqa: BLE001 - asserted by the tests
                out["step3"] = e

            release.set()
            out["task"] = await asyncio.wait_for(task, WAIT)
            worker_thread.join(WAIT)
            out["worker"] = worker_result.get("token")

        def loop_thread() -> None:
            asyncio.run(main())
            out["finished"] = True

        thread = threading.Thread(target=loop_thread, daemon=True)
        thread.start()
        thread.join(WAIT * 2)
        out["refresh_calls"] = list(endpoint.refresh_calls)
        out["exchanges"] = list(endpoint.exchanges)
        out["handler"] = handler
        return out

    def test_sync_logout_on_loop_thread_raises_instead_of_deadlocking(self, tmp_path) -> None:
        out = self._scenario(tmp_path, lambda handler: handler.clear_tokens())
        out["handler"].close()

        assert out["finished"], "the event loop thread deadlocked"
        assert out["task_holds_file_lock"] is True
        assert out["worker_holds_thread_lock"] is True
        assert isinstance(out["step3"], RuntimeError)
        assert "deadlock" in str(out["step3"])
        # Both refreshers then finish normally, with a single refresh
        assert out["task"] == "at1"
        assert out["worker"] == "at1"
        assert out["refresh_calls"] == ["rt0"]

    def test_authenticate_on_loop_thread_fails_before_the_browser_opens(
        self, tmp_path
    ) -> None:
        """authorize() refuses up front instead of losing a completed sign-in."""
        browser: List[str] = []
        exchanged: List[str] = []

        def step3(handler: OAuthHandler) -> None:
            with patch.object(auth_module.webbrowser, "open", side_effect=browser.append), \
                 patch.object(handler, "_exchange_code_for_tokens",
                              side_effect=lambda code, **kw: exchanged.append(code)):
                handler.authorize()

        out = self._scenario(tmp_path, step3)
        out["handler"].close()

        assert out["finished"], "the event loop thread deadlocked"
        assert isinstance(out["step3"], WhoopAuthError)
        assert "async token refresh" in str(out["step3"])
        assert browser == []
        assert exchanged == []
        assert out["task"] == "at1"
        assert out["worker"] == "at1"


# =============================================================================
# Cancellation: a cancelled caller never loses the rotated refresh token
# =============================================================================

class TestCancelledAsyncRefresh:
    """The async refresh survives the cancellation of the caller that started it."""

    @staticmethod
    def _slow_endpoint(endpoint: RotatingTokenEndpoint, release: asyncio.Event):
        """Async transport that rotates at once, then answers when released."""

        async def handler(request: httpx.Request) -> httpx.Response:
            response = endpoint.respond(_form(request), "async")
            await release.wait()
            return response

        return httpx.MockTransport(handler)

    @pytest.mark.parametrize("trigger", ["401", "expiry"])
    async def test_cancelled_caller_keeps_rotated_token(self, tmp_path, trigger) -> None:
        path = str(tmp_path / "tokens.json")
        if trigger == "401":
            _write_tokens(path, "stale", "rt0", expires_in=3600)
        else:
            _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        release = asyncio.Event()

        async def api(request: httpx.Request) -> httpx.Response:
            if _bearer(request) in endpoint.valid_access_tokens:
                return httpx.Response(200, json=PROFILE)
            return httpx.Response(401, json={"error": "unauthorized"})

        client = await _make_async_client(path, endpoint, api)
        client.auth._make_async_http_client = (  # type: ignore[method-assign]
            lambda: httpx.AsyncClient(transport=self._slow_endpoint(endpoint, release))
        )
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(client.get_profile_basic(), 0.3)
            # WHOOP has rotated rt0 -> rt1, and the caller is gone
            assert endpoint.valid_refresh_token == "rt1"

            release.set()
            saved: Optional[str] = None
            for _ in range(int(WAIT / 0.01)):
                await asyncio.sleep(0.01)
                tokens = load_tokens(path)
                saved = tokens.get("refresh_token") if tokens else None
                if saved == "rt1":
                    break
            assert saved == "rt1"

            profile = await client.get_profile_basic()
        finally:
            await client.close()

        assert profile.user_id == 1
        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []


# =============================================================================
# Callers queued behind a failed refresh share its outcome
# =============================================================================

class TestQueuedCallersShareFailure:
    """A failing refresh is not repeated by every caller that waited for it."""

    def test_sync_waiters_share_a_5xx_failure(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(auth_module, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(503, text="unavailable") for _ in range(20)]
        client = _make_sync_client(path, endpoint, _api_401_for("stale", endpoint, 3))
        entered = _count_threads_entering_token_lock(client.auth)

        def hold_first_refresh(form: Dict[str, str]) -> None:
            # Answer only once all three callers are waiting for the lock
            with entered:
                assert entered.wait_for(
                    lambda: len(entered.threads) == 3, WAIT  # type: ignore[attr-defined]
                )

        endpoint.before_refresh = hold_first_refresh
        try:
            results = _run_threads([client.get_profile_basic] * 3)
        finally:
            client.close()

        expected = "WhoopTokenError: Token refresh failed with status 503"
        assert all(r.startswith(expected) for r in results), results
        # One attempt: the first request plus MAX_RETRIES retries, not three attempts
        assert len(endpoint.refresh_calls) == auth_module.MAX_RETRIES + 1
        saved = load_tokens(path)
        assert saved is not None and saved["refresh_token"] == "rt0"

    async def test_async_waiters_share_a_5xx_failure(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(auth_module, "RETRY_BACKOFF_BASE_SECONDS", 0.0)
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(503, text="unavailable") for _ in range(20)]

        waiting: Set[int] = set()
        all_waiting = asyncio.Event()
        arrived = {"n": 0}
        all_arrived = asyncio.Event()

        async def api(request: httpx.Request) -> httpx.Response:
            if _bearer(request) == "stale":
                arrived["n"] += 1
                if arrived["n"] == 3:
                    all_arrived.set()
                await asyncio.wait_for(all_arrived.wait(), WAIT)
            return httpx.Response(401, json={"error": "unauthorized"})

        async def gate() -> None:
            await asyncio.wait_for(all_waiting.wait(), WAIT)

        client = await _make_async_client(path, endpoint, api, gate)
        real_lock = client.auth._async_token_lock

        @contextlib.asynccontextmanager
        async def counting_lock():
            task = asyncio.current_task()
            waiting.add(id(task))
            if len(waiting) == 3:
                all_waiting.set()
            async with real_lock():
                yield

        client.auth._async_token_lock = counting_lock  # type: ignore[method-assign]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*(client.get_profile_basic() for _ in range(3)),
                               return_exceptions=True),
                WAIT,
            )
        finally:
            await client.close()

        assert [type(r) for r in results] == [WhoopTokenError] * 3
        assert all(r.status_code == 503 for r in results)  # type: ignore[union-attr]
        assert len(endpoint.refresh_calls) == auth_module.MAX_RETRIES + 1

    def test_expired_token_waiters_share_a_network_failure(self, tmp_path) -> None:
        """get_valid_token(): callers queued behind a refresh that timed out don't repeat it."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        entered = _count_threads_entering_token_lock(handler)
        posts: List[str] = []

        def token_endpoint(request: httpx.Request) -> httpx.Response:
            posts.append(_form(request)["refresh_token"])
            with entered:
                entered.wait_for(lambda: len(entered.threads) == 3, WAIT)  # type: ignore[attr-defined]
            raise httpx.ReadTimeout("timed out", request=request)

        handler._http_client.close()
        handler._http_client = httpx.Client(transport=httpx.MockTransport(token_endpoint))
        try:
            results = _run_threads([handler.get_valid_token] * 3)
        finally:
            handler.close()

        assert results == ["ReadTimeout: timed out"] * 3
        assert posts == ["rt0"]

    def test_a_later_caller_retries_after_a_failure(self, tmp_path) -> None:
        """Only callers that waited share the failure; the next call tries again."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        endpoint.fail_next = [httpx.Response(400, json={"error": "invalid_request"})]
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="status 400"):
                handler.get_valid_token()
            assert handler.get_valid_token() == "at1"
        finally:
            handler.close()

        assert endpoint.refresh_calls == ["rt0", "rt0"]


class TestAuthorizationEndedForEveryCaller:
    """Every caller learns that the authorization has ended, not just the first."""

    def test_sync_waiters_and_later_calls_get_authorization_ended(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        client = _make_sync_client(path, endpoint, _api_401_for("stale", endpoint, 3))
        entered = _count_threads_entering_token_lock(client.auth)

        def hold_first_refresh(form: Dict[str, str]) -> None:
            with entered:
                entered.wait_for(lambda: len(entered.threads) == 3, WAIT)  # type: ignore[attr-defined]

        endpoint.before_refresh = hold_first_refresh
        try:
            results = _run_threads([client.get_profile_basic] * 3)
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                client.auth.get_valid_token()
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                client.auth.refresh_if_stale("stale")

            # An explicit logout replaces it with the plain message
            client.logout()
            with pytest.raises(WhoopTokenError) as exc_info:
                client.auth.get_valid_token()
        finally:
            client.close()

        assert all("authorization has ended" in r for r in results), results
        assert endpoint.refresh_calls == ["dead"]
        assert "No tokens available" in str(exc_info.value)
        assert "authenticate()" in str(exc_info.value)

    async def test_async_waiters_get_authorization_ended(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "dead", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt-unknown")

        async def api(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0)
            return httpx.Response(401, json={"error": "unauthorized"})

        client = await _make_async_client(path, endpoint, api)
        try:
            results = await asyncio.gather(
                *(client.get_profile_basic() for _ in range(4)), return_exceptions=True
            )
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                await client.auth.async_get_valid_token()
        finally:
            await client.close()

        assert [type(r) for r in results] == [WhoopTokenError] * 4
        assert all("authorization has ended" in str(r) for r in results), results
        assert endpoint.refresh_calls == ["dead"]

    def test_new_tokens_end_the_authorization_ended_state(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "dead", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                handler.get_valid_token()
            # Signing in again (here: another process saved new tokens)
            _write_tokens(path, "fresh", "rt-fresh", expires_in=3600)
            assert handler.get_valid_token() == "fresh"
        finally:
            handler.close()


# =============================================================================
# Token storage problems are found before a refresh token is spent
# =============================================================================

def _symlinked_token_file(tmp_path, expires_in: float) -> str:
    """Create real/tokens.json (rt0) and a symlink link.json pointing to it."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real = str(real_dir / "tokens.json")
    _write_tokens(real, "at0", "rt0", expires_in=expires_in)
    link = str(tmp_path / "link.json")
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"cannot create symlinks here: {e}")
    return link


class TestTokenFileCheckedBeforeRefresh:
    """A token file that cannot be saved never costs the refresh token."""

    def test_symlinked_token_file_refuses_before_refreshing(self, tmp_path) -> None:
        link = _symlinked_token_file(tmp_path, expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=link)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="symbolic link") as exc_info:
                handler.get_valid_token()
            # A second process finds everything as it was
            with pytest.raises(WhoopTokenError, match="symbolic link"):
                handler.refresh_access_token()
        finally:
            handler.close()

        assert "was not sent" in str(exc_info.value)
        assert endpoint.refresh_calls == []
        assert os.path.islink(link)
        saved = load_tokens(link)
        assert saved is not None and saved["refresh_token"] == "rt0"

    def test_symlinked_token_file_on_401_path(self, tmp_path) -> None:
        link = _symlinked_token_file(tmp_path, expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        client = _make_sync_client(
            link, endpoint, lambda request: httpx.Response(401, json={"error": "unauthorized"})
        )
        try:
            with pytest.raises(WhoopTokenError, match="symbolic link"):
                client.get_profile_basic()
        finally:
            client.close()

        assert endpoint.refresh_calls == []
        assert os.path.islink(link)

    async def test_symlinked_token_file_async(self, tmp_path) -> None:
        link = _symlinked_token_file(tmp_path, expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=link)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="symbolic link"):
                await handler.async_get_valid_token()
        finally:
            handler.close()

        assert endpoint.transports == []
        assert os.path.islink(link)

    def test_authorize_with_symlinked_token_file_does_not_open_browser(
        self, tmp_path, monkeypatch
    ) -> None:
        # Fail fast instead of waiting for the full flow if the check is missed
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", 0.5)
        link = _symlinked_token_file(tmp_path, expires_in=3600)
        port = _free_port()
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=f"http://127.0.0.1:{port}/callback",
            token_file=link,
        )
        try:
            with patch.object(auth_module.webbrowser, "open") as mock_open, \
                 patch.object(handler, "_exchange_code_for_tokens") as mock_exchange:
                with pytest.raises(WhoopAuthError, match="symbolic link") as exc_info:
                    handler.authorize()
            mock_open.assert_not_called()
            mock_exchange.assert_not_called()
        finally:
            handler.close()

        assert "browser was not opened" in str(exc_info.value)

    @POSIX_PERMISSIONS
    def test_unwritable_token_file_refuses_before_refreshing(self, tmp_path) -> None:
        locked = tmp_path / "locked"
        locked.mkdir()
        path = str(locked / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        os.chmod(path, 0o400)
        os.chmod(locked, 0o500)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            with pytest.raises(WhoopTokenError, match="nor the token file is writable"):
                handler.get_valid_token()
        finally:
            handler.close()
            os.chmod(locked, 0o700)
            os.chmod(path, 0o600)

        assert endpoint.refresh_calls == []

    def test_save_failure_after_refresh_raises_whoop_token_error(
        self, tmp_path, monkeypatch
    ) -> None:
        """A save that fails anyway raises WhoopTokenError; the tokens stay in memory."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)

        def full_disk(tokens, filepath=None):
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(auth_module, "save_tokens", full_disk)
        try:
            with pytest.raises(WhoopTokenError, match="could not be saved") as exc_info:
                handler.get_valid_token()
            # The rotated tokens are kept in memory, so this handler keeps working
            assert handler.get_valid_token() == "at1"
        finally:
            handler.close()

        assert isinstance(exc_info.value.__cause__, OSError)
        assert endpoint.refresh_calls == ["rt0"]


class TestTokenFileFallbacks:
    """Set-ups that cannot use temp-file-and-rename still save tokens."""

    @POSIX_PERMISSIONS
    def test_read_only_directory_rewrites_writable_file_in_place(self, tmp_path) -> None:
        locked = tmp_path / "locked"
        locked.mkdir()
        path = str(locked / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=-10)
        os.chmod(locked, 0o500)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        try:
            assert handler.get_valid_token() == "at1"
            saved = load_tokens(path)
            mode = os.stat(path).st_mode & 0o777
            leftovers = sorted(os.listdir(locked))
        finally:
            handler.close()
            os.chmod(locked, 0o700)

        assert saved is not None and saved["refresh_token"] == "rt1"
        assert mode == 0o600
        assert leftovers == ["tokens.json"]

    def test_mount_point_token_file_rewritten_in_place(self, tmp_path, monkeypatch) -> None:
        """os.replace onto a bind-mounted file fails with EBUSY on Linux."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        if hasattr(os, "chmod"):
            os.chmod(path, 0o644)

        def busy_replace(src, dst):
            raise OSError(errno.EBUSY, "Device or resource busy")

        monkeypatch.setattr(utils_module.os, "replace", busy_replace)
        new_tokens = {
            "access_token": "short",
            "refresh_token": "r",
            "expires_in": 1,
            "expires_at": 1.0,
        }
        save_tokens(new_tokens, path)  # type: ignore[arg-type]

        assert load_tokens(path) == new_tokens
        assert sorted(os.listdir(tmp_path)) == ["tokens.json"]
        if os.name != "nt":
            assert os.stat(path).st_mode & 0o777 == 0o600

    def test_other_replace_errors_still_raise(self, tmp_path, monkeypatch) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        with open(path, "rb") as f:
            before = f.read()

        def failing_replace(src, dst):
            raise OSError(errno.EIO, "I/O error")

        monkeypatch.setattr(utils_module.os, "replace", failing_replace)
        with pytest.raises(OSError):
            save_tokens({"access_token": "x"}, path)  # type: ignore[typeddict-item]

        with open(path, "rb") as f:
            assert f.read() == before


class TestUndeletableTokenFile:
    """Cleared tokens never come back from a token file that could not be deleted."""

    @staticmethod
    def _undeletable(monkeypatch) -> List[str]:
        attempts: List[str] = []

        def failing_delete(filepath=None):
            attempts.append(filepath)
            return False

        monkeypatch.setattr(auth_module, "delete_tokens", failing_delete)
        return attempts

    def test_dead_refresh_token_with_undeletable_file(self, tmp_path, monkeypatch) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "dead", expires_in=-10)
        endpoint = RotatingTokenEndpoint("rt-unknown")
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(client.auth, endpoint)
        attempts = self._undeletable(monkeypatch)
        try:
            with pytest.raises(WhoopTokenError, match="could not be deleted") as exc_info:
                client.auth.get_valid_token()
            assert os.path.exists(path)
            assert client.auth.has_valid_tokens() is False
            assert client.is_authenticated() is False
            with pytest.raises(WhoopTokenError, match="authorization has ended"):
                client.auth.get_valid_token()
            with patch.object(client.auth, "authorize") as mock_authorize:
                client.authenticate()
            mock_authorize.assert_called_once()
        finally:
            client.close()

        assert attempts == [path]
        assert "authenticate(force=True)" in str(exc_info.value)
        assert endpoint.refresh_calls == ["dead"]

    def test_logout_with_undeletable_file(self, tmp_path, monkeypatch) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        self._undeletable(monkeypatch)
        try:
            assert client.is_authenticated() is True
            client.logout()
            assert client.is_authenticated() is False
            with pytest.raises(WhoopTokenError, match="No tokens available"):
                client.auth.get_valid_token()
            # New tokens written to the file are picked up again
            _write_tokens(path, "at-new", "rt-new", expires_in=3600)
            assert client.auth.get_valid_token() == "at-new"
        finally:
            client.close()


# =============================================================================
# Lock-free loads never resurrect cleared tokens
# =============================================================================

class TestUnlockedLoadRace:
    """A first load that races logout() is not cached."""

    def test_load_racing_logout_is_not_cached(self, tmp_path, monkeypatch) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = WhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        real_load = auth_module.load_tokens
        loaded = threading.Event()
        resume = threading.Event()

        def gated_load(filepath=None):
            data = real_load(filepath)
            if threading.current_thread().name == "reader":
                loaded.set()
                resume.wait(WAIT)
            return data

        monkeypatch.setattr(auth_module, "load_tokens", gated_load)
        result: Dict[str, str] = {}
        reader = threading.Thread(
            target=lambda: result.setdefault("token", client.auth.get_valid_token()),
            name="reader",
        )
        try:
            reader.start()
            assert loaded.wait(WAIT)
            client.logout()
            resume.set()
            reader.join(WAIT)

            assert result["token"] == "at0"  # read before the logout
            assert client.auth._tokens is None
            assert client.is_authenticated() is False
            with pytest.raises(WhoopTokenError):
                client.auth.get_valid_token()
        finally:
            resume.set()
            client.close()

    def test_load_racing_refresh_does_not_overwrite_new_tokens(
        self, tmp_path, monkeypatch
    ) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(handler, endpoint)
        real_load = auth_module.load_tokens
        loaded = threading.Event()
        resume = threading.Event()

        def gated_load(filepath=None):
            data = real_load(filepath)
            if threading.current_thread().name == "reader":
                loaded.set()
                resume.wait(WAIT)
            return data

        monkeypatch.setattr(auth_module, "load_tokens", gated_load)
        reader = threading.Thread(target=handler.has_valid_tokens, name="reader")
        try:
            reader.start()
            assert loaded.wait(WAIT)
            assert handler.refresh_if_stale("at0") == "at1"
            resume.set()
            reader.join(WAIT)
            tokens = handler._tokens
        finally:
            resume.set()
            handler.close()

        assert tokens is not None and tokens["access_token"] == "at1"


# =============================================================================
# Callback server: both loopback addresses, no squatters, no leftover threads
# =============================================================================

def _listen(family: int, address: str, port: int, v6only: Optional[bool] = None) -> socket.socket:
    """Open a listening socket that plays another program on the port."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    if v6only is not None:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1 if v6only else 0)
    sock.bind((address, port))
    sock.listen(5)
    return sock


def _closed_by_peer(sock: socket.socket, within: float) -> bool:
    """Tell whether the server closes ``sock`` within ``within`` seconds."""
    sock.settimeout(within)
    try:
        while True:
            if sock.recv(4096) == b"":
                return True
    except socket.timeout:
        return False
    except OSError:
        return True


@pytest.fixture
def fast_callback(monkeypatch):
    """Short socket timeout; a flow deadline long enough to never be hit by accident."""
    monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)


needs_ipv6 = pytest.mark.skipif(not _ipv6_loopback_available(), reason="no IPv6 loopback")


class TestCallbackServerAddresses:
    """A localhost redirect is served on 127.0.0.1 and ::1, and squatters are refused."""

    @needs_ipv6
    def test_localhost_redirect_is_served_on_ipv6_too(self, tmp_path, fast_callback) -> None:
        flow = CallbackFlow(tmp_path, host="localhost")
        try:
            with httpx.Client(trust_env=False, timeout=WAIT) as browser:
                response = browser.get(
                    f"http://[::1]:{flow.port}/callback?code=v6-code&state=expected-state"
                )
        finally:
            flow.finish()

        assert response.status_code == 200
        assert flow.code == "v6-code"

    @needs_ipv6
    @pytest.mark.parametrize(
        "squatter",
        [
            pytest.param(("::1", True), id="ipv6-loopback"),
            pytest.param(("::", False), id="dual-stack-wildcard"),
        ],
    )
    def test_localhost_redirect_refuses_port_taken_on_ipv6(
        self, tmp_path, squatter, monkeypatch
    ) -> None:
        # Fail fast instead of waiting for the full flow if the squatter is missed
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", 0.5)
        address, v6only = squatter
        port = _free_port()
        try:
            other = _listen(socket.AF_INET6, address, port, v6only=v6only)
        except OSError as e:
            pytest.skip(f"cannot listen on [{address}]:{port}: {e}")
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=f"http://localhost:{port}/callback",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            with patch.object(auth_module.webbrowser, "open") as mock_open:
                with pytest.raises(WhoopAuthError, match="already listening"):
                    handler.authorize()
            mock_open.assert_not_called()
        finally:
            other.close()
            handler.close()

    def test_explicit_ipv4_redirect_refuses_port_taken_on_ipv4(self, tmp_path) -> None:
        port = _free_port()
        other = _listen(socket.AF_INET, "127.0.0.1", port)
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=f"http://127.0.0.1:{port}/callback",
            token_file=str(tmp_path / "tokens.json"),
        )
        try:
            with pytest.raises(WhoopAuthError, match="already listening on 127.0.0.1"):
                handler._create_callback_server("state")
        finally:
            other.close()
            handler.close()

    def test_localhost_without_ipv6_listens_on_ipv4(
        self, tmp_path, fast_callback, monkeypatch
    ) -> None:
        real_init = auth_module._CallbackServer.__init__

        def no_ipv6(self, server_address, address_family, *args, **kwargs):
            if address_family == socket.AF_INET6:
                raise OSError(errno.EADDRNOTAVAIL, "Cannot assign requested address")
            real_init(self, server_address, address_family, *args, **kwargs)

        monkeypatch.setattr(auth_module._CallbackServer, "__init__", no_ipv6)
        flow = CallbackFlow(tmp_path, host="localhost")
        try:
            assert flow.server.siblings == []
            response = flow.get("/callback?code=v4-code&state=expected-state")
        finally:
            flow.finish()

        assert response.status_code == 200
        assert flow.code == "v4-code"


class TestCallbackConnections:
    """Connections to the callback server never outlive their welcome."""

    def test_connections_are_closed_when_the_flow_ends(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", WAIT)
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)
        flow = CallbackFlow(tmp_path)
        idle = socket.create_connection(("127.0.0.1", flow.port))
        try:
            idle.sendall(b"GET /callback?co")
            flow.get("/callback?code=real-code&state=expected-state")
            flow.finish()
            # Without the cleanup this would stay open for the 10s read timeout
            assert _closed_by_peer(idle, within=WAIT / 4)
        finally:
            idle.close()

        assert flow.code == "real-code"

    def test_trickling_connection_is_closed_after_the_socket_timeout(
        self, tmp_path, fast_callback
    ) -> None:
        """A byte every 0.1s defeats a per-read timeout, but not the age limit."""
        flow = CallbackFlow(tmp_path)
        slow = socket.create_connection(("127.0.0.1", flow.port))
        stop = threading.Event()

        def trickle() -> None:
            try:
                slow.sendall(b"GET /c")
                while not stop.wait(0.1):
                    slow.sendall(b"a")
            except OSError:
                pass

        trickler = threading.Thread(target=trickle, daemon=True)
        try:
            trickler.start()
            started = time.monotonic()
            closed = _closed_by_peer(slow, within=WAIT / 2)
            elapsed = time.monotonic() - started
            flow_still_waiting = flow.thread.is_alive()
            flow.get("/callback?code=real-code&state=expected-state")
            flow.finish()
        finally:
            stop.set()
            slow.close()
            trickler.join(WAIT)

        assert closed
        assert elapsed < WAIT / 2
        assert flow_still_waiting
        assert flow.code == "real-code"

    def test_too_many_connections_close_the_oldest(
        self, tmp_path, fast_callback, monkeypatch
    ) -> None:
        monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", WAIT)
        monkeypatch.setattr(auth_module, "_CALLBACK_MAX_CONNECTIONS", 2)
        flow = CallbackFlow(tmp_path)
        idle = [socket.create_connection(("127.0.0.1", flow.port)) for _ in range(3)]
        try:
            for sock in idle:
                sock.sendall(b"GET /callback?co")
            oldest_closed = _closed_by_peer(idle[0], within=WAIT / 4)
            # The real callback still gets through, closing another idle connection
            response = flow.get("/callback?code=real-code&state=expected-state")
            flow.finish()
        finally:
            for sock in idle:
                sock.close()

        assert flow.server.max_connections == 2
        assert oldest_closed
        assert response.status_code == 200
        assert flow.code == "real-code"

    def test_each_connection_gets_the_socket_timeout(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(auth_module, "CALLBACK_SOCKET_TIMEOUT_SECONDS", 7.5)
        monkeypatch.setattr(auth_module, "CALLBACK_TIMEOUT_SECONDS", WAIT)
        flow = CallbackFlow(tmp_path)
        idle = socket.create_connection(("127.0.0.1", flow.port))
        timeouts: List[Optional[float]] = []
        try:
            deadline = time.monotonic() + WAIT
            while time.monotonic() < deadline:
                with flow.server._connections_lock:
                    timeouts = [s.gettimeout() for s in flow.server._connections]
                if timeouts and timeouts[0] is not None:
                    break
                time.sleep(0.01)
            flow.get("/callback?code=real-code&state=expected-state")
            flow.finish()
        finally:
            idle.close()

        assert timeouts == [7.5]


# =============================================================================
# Gaps found by mutation testing
# =============================================================================

class TestMutationGaps:
    """Behaviour whose removal no earlier test noticed."""

    async def test_two_async_handlers_sharing_a_token_file_refresh_once(self, tmp_path) -> None:
        """Like two processes: only the token file lock keeps them apart."""
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "stale", "rt0", expires_in=3600)
        endpoint = RotatingTokenEndpoint("rt0")
        in_flight = {"n": 0}
        second_arrived = asyncio.Event()

        async def gate() -> None:
            # Hold the first refresh until a second one arrives (only
            # possible without the file lock) or 0.3s pass.
            in_flight["n"] += 1
            if in_flight["n"] >= 2:
                second_arrived.set()
                return
            try:
                await asyncio.wait_for(second_arrived.wait(), 0.3)
            except asyncio.TimeoutError:
                pass

        first = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        second = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        _wire_auth(first, endpoint, gate)
        _wire_auth(second, endpoint, gate)
        try:
            tokens = await asyncio.wait_for(
                asyncio.gather(
                    *(handler.async_refresh_if_stale("stale")
                      for handler in (first, second, first, second))
                ),
                WAIT,
            )
        finally:
            first.close()
            second.close()

        assert tokens == ["at1"] * 4
        assert endpoint.refresh_calls == ["rt0"]
        assert endpoint.rejected == []

    async def test_async_authenticate_force_clears_cache(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        _write_tokens(path, "at0", "rt0", expires_in=3600)
        client = AsyncWhoopClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        client._cache_set("profile_basic", object(), ttl=300)
        try:
            with patch.object(client.auth, "authorize"):
                client.authenticate(force=True)
            assert client._cache == {}
        finally:
            await client.close()

    def test_authorize_stores_tokens_under_the_token_lock(self, tmp_path, monkeypatch) -> None:
        path = str(tmp_path / "tokens.json")
        handler = OAuthHandler(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, token_file=path)
        held: List[bool] = []
        real_save = auth_module.save_tokens

        def checking_save(tokens, filepath=None):
            held.append(utils_module._file_lock_held_by_current_thread(path))
            return real_save(tokens, filepath)

        monkeypatch.setattr(auth_module, "save_tokens", checking_save)
        tokens = {
            "access_token": "at-new",
            "refresh_token": "rt-new",
            "expires_in": 3600,
            "expires_at": time.time() + 3600,
            "token_type": "bearer",
            "scope": "offline",
        }
        try:
            with patch.object(handler, "_create_callback_server"), \
                 patch.object(handler, "_wait_for_callback", return_value="code"), \
                 patch.object(handler, "_exchange_code_for_tokens", return_value=tokens), \
                 patch.object(auth_module.webbrowser, "open"):
                handler.authorize()
        finally:
            handler.close()

        assert held == [True]
        saved = load_tokens(path)
        assert saved is not None and saved["refresh_token"] == "rt-new"

    async def test_async_refresh_client_uses_the_handler_timeout(self, tmp_path) -> None:
        handler = OAuthHandler(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            token_file=str(tmp_path / "tokens.json"),
            timeout=17.0,
        )
        refresh_client = handler._make_async_http_client()
        try:
            timeout = refresh_client.timeout
            assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
                17.0, 17.0, 17.0, 17.0
            )
        finally:
            await refresh_client.aclose()
            handler.close()


# =============================================================================
# utils: lock holder lookup and messages
# =============================================================================

class TestLockHolderLookup:
    """_file_lock_held_by_current_thread and the re-entry error message."""

    def test_held_by_current_thread_only(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        seen_from_other_thread: List[bool] = []
        assert utils_module._file_lock_held_by_current_thread(path) is False
        with utils_module.token_file_lock(path):
            assert utils_module._file_lock_held_by_current_thread(path) is True
            other = threading.Thread(
                target=lambda: seen_from_other_thread.append(
                    utils_module._file_lock_held_by_current_thread(path)
                )
            )
            other.start()
            other.join(WAIT)
        assert seen_from_other_thread == [False]
        assert utils_module._file_lock_held_by_current_thread(path) is False

    @pytest.mark.skipif(
        utils_module._fcntl is None and utils_module._msvcrt is None,
        reason="no file locking on this platform",
    )
    async def test_sync_lock_under_suspended_task_names_the_task(self, tmp_path) -> None:
        path = str(tmp_path / "tokens.json")
        holding = asyncio.Event()
        release = asyncio.Event()

        async def holder() -> None:
            async with utils_module.async_token_file_lock(path):
                holding.set()
                await release.wait()

        task = asyncio.ensure_future(holder())
        await asyncio.wait_for(holding.wait(), WAIT)
        try:
            with pytest.raises(RuntimeError, match="not re-entrant") as exc_info:
                with utils_module.token_file_lock(path):
                    pass
        finally:
            release.set()
            await asyncio.wait_for(task, WAIT)

        assert "asyncio task suspended" in str(exc_info.value)
        assert "this thread already" not in str(exc_info.value)

