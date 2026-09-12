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


def test_configure_logging_writes_to_a_rotating_file_in_addition_to_stdout(tmp_path, monkeypatch):
    import app.logging_config as logging_config_module

    monkeypatch.setattr(logging_config_module, "LOG_DIR", tmp_path / "logs")

    configure_logging()
    logging.getLogger("test-logger").info("hello from the test")

    log_file = tmp_path / "logs" / "app.log"
    assert log_file.exists()
    assert "hello from the test" in log_file.read_text()


def test_configure_logging_file_handler_has_rotation_configured(tmp_path, monkeypatch):
    import logging.handlers
    import app.logging_config as logging_config_module

    monkeypatch.setattr(logging_config_module, "LOG_DIR", tmp_path / "logs")

    configure_logging()

    file_handlers = [
        h for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == 5 * 1024 * 1024
    assert file_handlers[0].backupCount == 3
