"""Logging setup for the CaggyID backup tool.

File logs go to the configured directory; console output uses a compact
prefix format that is safe for SSH sessions and cron capture.
OAuth tokens, credentials, and secrets are never logged.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .utils import ensure_dir

_LOG_FORMAT_FILE = "%(asctime)s [%(levelname)s] %(message)s"
_LOG_FORMAT_CONSOLE = "[%(levelname)s] %(message)s"
_SENSITIVE_KEYS = ("token", "credential", "password", "secret", "key")


def setup_logging(level: str = "INFO", directory: str | None = None, verbose: bool = False) -> logging.Logger:
    """Configure root package logging and return the package logger."""
    logger = logging.getLogger("caggy_backup")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console_level = "DEBUG" if verbose else (level if level != "DEBUG" else "INFO")
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(getattr(logging, console_level, logging.INFO))
    console.setFormatter(logging.Formatter(_LOG_FORMAT_CONSOLE))
    logger.addHandler(console)

    if directory:
        try:
            log_dir = ensure_dir(Path(os.path.expanduser(directory)))
            file_handler = RotatingFileHandler(
                Path(log_dir) / "caggy-backup.log",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(getattr(logging, level, logging.INFO))
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT_FILE))
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.debug("Could not open file log at %s: %s", directory, exc)

    return logger


def sanitize_message(message: str) -> str:
    """Best-effort redaction of accidental secrets inside log messages."""
    lowered = message.lower()
    for key in _SENSITIVE_KEYS:
        if key in lowered and ("=" in message or ": " in message):
            # Redact value portion after the sensitive key marker.
            for marker in (f"{key}=", f"{key}: ", f"{key}\""):
                idx = lowered.find(marker)
                if idx != -1:
                    start = idx + len(marker)
                    end = message.find(" ", start)
                    end = len(message) if end == -1 else end
                    message = message[:start] + "***" + message[end:]
                    lowered = message.lower()
    return message


class SensitiveFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.msg = sanitize_message(str(record.msg))
        return True
