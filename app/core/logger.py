from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.models import Settings


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOGGER_NAME = "telegram_user_group_sender_gui"
DEFAULT_LOG_FILE = "logs/app.log"
DEFAULT_LOG_LEVEL = logging.INFO
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logger(settings: Settings) -> logging.Logger:
    logger_name = _logger_name(settings)
    logger = logging.getLogger(logger_name)

    logger.setLevel(_log_level(settings))
    logger.propagate = False

    _reset_handlers(logger)

    formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(_log_level(settings))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = _build_file_handler(settings)
    file_handler.setLevel(_log_level(settings))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def _logger_name(settings: Settings) -> str:
    app_name = str(getattr(settings, "app_name", "") or "").strip()

    if app_name:
        return app_name

    return DEFAULT_LOGGER_NAME


def _log_level(settings: Settings) -> int:
    level_name = str(getattr(settings, "log_level", "") or "").strip().upper()

    if not level_name:
        return DEFAULT_LOG_LEVEL

    level = getattr(logging, level_name, DEFAULT_LOG_LEVEL)

    if isinstance(level, int):
        return level

    return DEFAULT_LOG_LEVEL


def _log_file(settings: Settings) -> Path:
    log_file = str(getattr(settings, "log_file", "") or "").strip()

    if not log_file:
        log_file = DEFAULT_LOG_FILE

    path = Path(log_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    return path


def _build_file_handler(settings: Settings) -> RotatingFileHandler:
    return RotatingFileHandler(
        filename=str(_log_file(settings)),
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )


def _reset_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

        try:
            handler.close()
        except Exception:
            pass