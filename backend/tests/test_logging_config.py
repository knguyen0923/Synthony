import logging

from app.logging_config import configure_logging


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_reads_log_level_env_var(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
