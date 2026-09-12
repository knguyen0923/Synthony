import logging

import pytest

from app.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_root_logger_state():
    """configure_logging() calls logging.basicConfig(force=True), which
    permanently replaces the root logger's level and handlers for the rest
    of the pytest session — this file's tests run alphabetically before
    many other test modules, so without restoring afterward they'd leak
    into unrelated tests and make them unexpectedly noisy or quiet."""
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    yield
    root.level = original_level
    root.handlers = original_handlers


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_reads_log_level_env_var(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
