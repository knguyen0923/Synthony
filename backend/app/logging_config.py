import logging
import os


def configure_logging() -> None:
    """Configure the root logger once at process startup. Level is
    overridable via the LOG_LEVEL env var (e.g. LOG_LEVEL=DEBUG) for local
    debugging. Uses force=True so calling this more than once (e.g. from a
    test that wants a fresh level) actually takes effect, instead of
    logging.basicConfig's normal "no-op after the first call" behavior."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
