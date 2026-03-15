"""
Targeted tests for whoopyy.logger to reach high coverage.
"""

import logging

from whoopyy.logger import (
    _loggers,
    disable_logging,
    enable_logging,
    get_logger,
    set_log_level,
)


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_logger_instance(self) -> None:
        lgr = get_logger("whoopyy.test.coverage1")
        assert isinstance(lgr, logging.Logger)

    def test_caches_logger(self) -> None:
        lgr1 = get_logger("whoopyy.test.cache1")
        lgr2 = get_logger("whoopyy.test.cache1")
        assert lgr1 is lgr2

    def test_creates_handler_when_no_parent_handlers(self) -> None:
        # Use a unique name to avoid cache
        name = "whoopyy_handler_test_unique_abc123"
        _loggers.pop(name, None)
        raw_lgr = logging.getLogger(name)
        raw_lgr.handlers.clear()
        # Temporarily remove parent handlers to trigger handler-creation branch
        parent = raw_lgr.parent
        saved_handlers = list(parent.handlers) if parent else []
        if parent:
            parent.handlers.clear()
        try:
            result = get_logger(name)
            assert len(result.handlers) > 0
            assert result.handlers[0].formatter is not None
        finally:
            # Restore parent handlers
            if parent:
                parent.handlers.extend(saved_handlers)

    def test_explicit_level_parameter(self) -> None:
        name = "whoopyy.test.explicit_level"
        _loggers.pop(name, None)
        lgr = get_logger(name, level=logging.WARNING)
        assert lgr.level == logging.WARNING


class TestSetLogLevel:
    """Tests for set_log_level()."""

    def test_changes_all_cached_loggers(self) -> None:
        lgr = get_logger("whoopyy.test.setlevel1")
        set_log_level(logging.CRITICAL)
        assert lgr.level == logging.CRITICAL
        # Check handler levels too
        for h in lgr.handlers:
            assert h.level == logging.CRITICAL
        # Reset
        set_log_level(logging.INFO)


class TestDisableEnableLogging:
    """Tests for disable_logging() / enable_logging()."""

    def test_disable_then_enable(self) -> None:
        lgr = get_logger("whoopyy.test.disable1")
        disable_logging()
        assert lgr.disabled is True
        enable_logging()
        assert lgr.disabled is False
