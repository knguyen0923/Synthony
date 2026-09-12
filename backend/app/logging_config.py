import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def configure_logging() -> None:
    """Configure the root logger once at process startup. Level is
    overridable via the LOG_LEVEL env var (e.g. LOG_LEVEL=DEBUG) for local
    debugging. Uses force=True so calling this more than once (e.g. from a
    test that wants a fresh level) actually takes effect, instead of
    logging.basicConfig's normal "no-op after the first call" behavior.

    Logs go to both stdout (as before) and a rotating file under
    backend/logs/, so there's a persisted trail to check after a crash if
    the server is ever run backgrounded rather than in a foreground
    terminal."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(), file_handler],
        force=True,
    )
