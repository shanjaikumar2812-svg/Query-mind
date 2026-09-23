"""Structured logging setup for services that run outside a request context."""

import logging
import os
import sys

_CONFIGURED_LOGGERS = set()


def get_logger(name: str, log_file: str = None, level: str = "INFO") -> logging.Logger:
    """Return a module-level logger.

    Falls back to a stream handler if no Flask app (and therefore no
    RotatingFileHandler from app.__init__) has attached handlers yet.
    """
    logger = logging.getLogger(name)

    if name in _CONFIGURED_LOGGERS:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(name)s: %(message)s"
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    logger.propagate = False
    _CONFIGURED_LOGGERS.add(name)
    return logger
