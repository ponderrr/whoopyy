"""
Targeted tests for strapkit.auth to boost coverage.

Covers: _CallbackHandler HTML methods and request handling, the
        _CallbackServer result recording, OAuthHandler._build_authorization_url,
        log_message suppression, and OAuthHandler.__repr__.
"""

import io
import socket
from unittest.mock import MagicMock

import pytest

from strapkit.auth import (
    OAuthHandler,
    _CallbackHandler,
    _CallbackServer,
)


@pytest.fixture(autouse=True)
def _isolate_default_token_file(tmp_path, monkeypatch):
    """
    Redirect the default token file (~/.whoop_tokens.json) to a temp path.

    Refreshes re-read the token file and lock "<file>.lock" next to it, so a
    handler built with the default token_file would otherwise read, lock or
    delete the developer's real tokens.
    """
    import os

    import strapkit.auth as auth_module
    from strapkit.constants import DEFAULT_TOKEN_FILE

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


@pytest.fixture
def callback_server():
    """A bound (not serving) callback server expecting state 'xyz' on /callback."""
    server = _CallbackServer(
        ("127.0.0.1", 0),
        address_family=socket.AF_INET,
        expected_state="xyz",
        callback_path="/callback",
        socket_timeout=1.0,
    )
    yield server
    server.server_close()


def _make_handler(server, path):
    """Build a _CallbackHandler for ``path`` without a real connection."""
    handler = _CallbackHandler.__new__(_CallbackHandler)
    handler.server = server
    handler.path = path
    handler.wfile = io.BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler


class TestCallbackHandlerHtml:
    """Cover _success_html and _error_html methods."""

    def test_success_html_contains_success_text(self) -> None:
        handler = _CallbackHandler.__new__(_CallbackHandler)
        html = handler._success_html()
        assert "Authorization Successful" in html

    def test_error_html_contains_error_message(self) -> None:
        handler = _CallbackHandler.__new__(_CallbackHandler)
        html = handler._error_html("access_denied")
        assert "access_denied" in html

    def test_error_html_escapes_markup(self) -> None:
        handler = _CallbackHandler.__new__(_CallbackHandler)
        html = handler._error_html("<script>alert(1)</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_error_html_none_error(self) -> None:
        handler = _CallbackHandler.__new__(_CallbackHandler)
        html = handler._error_html(None)
        assert "Unknown error occurred" in html

    def test_log_message_suppressed(self) -> None:
        handler = _CallbackHandler.__new__(_CallbackHandler)
        # Should not raise
        handler.log_message("test %s", "arg")


class TestCallbackHandlerDoGet:
    """Cover do_GET method with simulated HTTP requests."""

    def test_do_get_with_code(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/callback?code=abc123&state=xyz")

        handler.do_GET()

        assert callback_server.result_ready.is_set()
        assert callback_server.auth_code == "abc123"
        assert callback_server.error is None
        handler.send_response.assert_called_once_with(200)
        assert b"Authorization Successful" in handler.wfile.getvalue()

    def test_do_get_with_error(self, callback_server) -> None:
        handler = _make_handler(
            callback_server,
            "/callback?error=access_denied&error_description=User+said+no&state=xyz",
        )

        handler.do_GET()

        assert callback_server.auth_code is None
        assert callback_server.error == "access_denied"
        assert callback_server.error_description == "User said no"
        assert b"access_denied" in handler.wfile.getvalue()

    def test_do_get_wrong_state_is_ignored(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/callback?error=access_denied&state=WRONG")

        handler.do_GET()

        assert not callback_server.result_ready.is_set()
        assert callback_server.error is None
        handler.send_response.assert_called_once_with(400)

    def test_do_get_missing_state_is_ignored(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/callback?code=abc123")

        handler.do_GET()

        assert not callback_server.result_ready.is_set()
        assert callback_server.auth_code is None

    def test_do_get_other_path_is_404_and_ignored(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/favicon.ico?code=abc123&state=xyz")

        handler.do_GET()

        assert not callback_server.result_ready.is_set()
        handler.send_response.assert_called_once_with(404)

    def test_do_get_without_code_or_error_ends_flow(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/callback?state=xyz")

        handler.do_GET()

        assert callback_server.result_ready.is_set()
        assert callback_server.auth_code is None
        assert callback_server.error is None

    def test_do_get_sets_defensive_headers(self, callback_server) -> None:
        handler = _make_handler(callback_server, "/callback?code=abc123&state=xyz")

        handler.do_GET()

        headers = {call.args[0]: call.args[1] for call in handler.send_header.call_args_list}
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Cache-Control"] == "no-store"

    def test_first_valid_callback_wins(self, callback_server) -> None:
        _make_handler(callback_server, "/callback?code=first&state=xyz").do_GET()
        _make_handler(callback_server, "/callback?code=second&state=xyz").do_GET()

        assert callback_server.auth_code == "first"


class TestOAuthHandlerBuildUrl:
    """Cover _build_authorization_url."""

    def test_build_url_contains_params(self) -> None:
        auth = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        )
        url = auth._build_authorization_url("test_state")
        assert "response_type=code" in url
        assert "client_id=test_id" in url
        assert "state=test_state" in url
        assert "code_challenge" not in url
        auth.close()

    def test_build_url_with_code_challenge(self) -> None:
        auth = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
        )
        url = auth._build_authorization_url("test_state", code_challenge="abc")
        assert "code_challenge=abc" in url
        assert "code_challenge_method=S256" in url
        auth.close()


class TestOAuthHandlerRepr:
    """Cover __repr__."""

    def test_repr_format(self) -> None:
        auth = OAuthHandler(
            client_id="test_id_long_enough",
            client_secret="test_secret",
        )
        r = repr(auth)
        assert "OAuthHandler" in r
        assert "test_id_" in r
        auth.close()


class TestOAuthHandlerScopeHandling:
    """Cover scope handling with missing offline scope."""

    def test_adds_offline_scope(self) -> None:
        auth = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            scope=["read:profile", "read:recovery"],
        )
        assert "offline" in auth.scope
        auth.close()

    def test_keeps_offline_scope(self) -> None:
        auth = OAuthHandler(
            client_id="test_id",
            client_secret="test_secret",
            scope=["offline", "read:profile"],
        )
        assert auth.scope == ["offline", "read:profile"]
        auth.close()
