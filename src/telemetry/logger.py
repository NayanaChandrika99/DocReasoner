"""
Minimal structured logging helper so each CLI command can emit consistent
records without pulling in the full observability stack.
"""

from __future__ import annotations

import logging
from logging import Logger
from typing import Any, Dict


def get_logger(name: str = "reasoning-service") -> Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_event(logger: Logger, event: str, **payload: Any) -> None:
    structured: Dict[str, Any] = {"event": event, **payload}
    logger.info(structured)
