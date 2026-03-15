"""
Targeted tests for whoopyy.auth to boost coverage.

Covers: _CallbackHandler HTML methods, _reset_callback_handler,
        OAuthHandler._build_authorization_url, log_message suppression,
        and OAuthHandler.__repr__.
"""

import io
from unittest.mock import MagicMock, patch

from whoopyy.auth import (
    OAuthHandler,
    _CallbackHandler,
    _reset_callback_handler,
)


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

    def test_do_get_with_code(self) -> None:
        _reset_callback_handler()
        handler = _CallbackHandler.__new__(_CallbackHandler)
        handler.path = "/callback?code=abc123&state=xyz"
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler.do_GET()
        assert _CallbackHandler.auth_code == "abc123"
        assert _CallbackHandler.auth_state == "xyz"
        assert _CallbackHandler.error is None

    def test_do_get_with_error(self) -> None:
        _reset_callback_handler()
        handler = _CallbackHandler.__new__(_CallbackHandler)
        handler.path = "/callback?error=access_denied"
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        handler.do_GET()
        assert _CallbackHandler.auth_code is None
        assert _CallbackHandler.error == "access_denied"


class TestResetCallbackHandler:
    """Cover _reset_callback_handler."""

    def test_reset_clears_state(self) -> None:
        _CallbackHandler.auth_code = "code"
        _CallbackHandler.auth_state = "state"
        _CallbackHandler.error = "err"
        _reset_callback_handler()
        assert _CallbackHandler.auth_code is None
        assert _CallbackHandler.auth_state is None
        assert _CallbackHandler.error is None


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
