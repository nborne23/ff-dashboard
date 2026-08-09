"""File logging with rotation (task 11.3).

Console-only (today's dev behavior, unchanged) unless `GRIDIRON_LOG_DIR` is set, in
which case app + scheduler logs also go to a rotated file under that directory (5 MB x 5
backups) via stdlib `logging.handlers.RotatingFileHandler` — no new dependency (loguru
etc.) needed for this.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_FILENAME = "gridiron.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

# app.py logs through "uvicorn.error" (see main.py's comment on why); scheduler.py does
# too. Attaching the rotating handler to both covers every log line task 11.3 cares
# about without each module needing its own handler wiring.
_TARGET_LOGGERS = ("uvicorn.error", "uvicorn.access")

_added_handlers: list[logging.Handler] = []


def configure_logging(log_dir: str) -> None:
    """Idempotent: a no-op once already configured (or when `log_dir` is empty), so
    it's safe to call from `create_app()` even if that ever runs more than once in a
    process (e.g. multiple test clients)."""
    if not log_dir or _added_handlers:
        return

    directory = Path(log_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        directory / LOG_FILENAME, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    for logger_name in _TARGET_LOGGERS:
        logging.getLogger(logger_name).addHandler(handler)
    _added_handlers.append(handler)


def reset_for_tests() -> None:
    """Detach any handler `configure_logging` added and forget it, so tests can exercise
    `configure_logging` repeatedly without stacking duplicate handlers on the shared
    uvicorn loggers (mirrors the `reset_state()` pattern used across services)."""
    for handler in _added_handlers:
        for logger_name in _TARGET_LOGGERS:
            logging.getLogger(logger_name).removeHandler(handler)
        handler.close()
    _added_handlers.clear()
