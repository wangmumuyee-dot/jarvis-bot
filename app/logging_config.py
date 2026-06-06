from __future__ import annotations

import logging
from pathlib import Path
from logging.config import dictConfig

from app.config import Settings


def configure_logging(settings: Settings) -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "filename": "logs/jarvis.log",
                    "maxBytes": 1_000_000,
                    "backupCount": 3,
                    "encoding": "utf-8",
                }
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console", "file"],
            },
        }
    )


logger = logging.getLogger("jarvis")
