"""Shared logging setup for persistent runtime error reporting."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from puzzle_dungeon import config


LOGGER_NAME = "puzzle_dungeon"


def configure_logging() -> logging.Logger:
    """Configure a persistent rotating error log once and return the app logger."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        config.ERROR_LOG_PATH,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Logging initialized at %s", config.ERROR_LOG_PATH)
    return logger


def install_exception_logging() -> logging.Logger:
    """Route uncaught Python and thread exceptions into the persistent log."""
    logger = configure_logging()

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: Any,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.exception(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        logger.exception(
            "Uncaught thread exception in %s",
            getattr(args.thread, "name", "<unknown>"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured child logger for the given module name."""
    root_logger = configure_logging()
    if not name:
        return root_logger
    return root_logger.getChild(name)
