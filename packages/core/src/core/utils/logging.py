"""Logger factory writing to a library's organization.log."""

from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Return a module logger. If ``log_dir`` is given and no handler is attached yet, also
    log to ``<log_dir>/organization.log``."""

    logger = logging.getLogger(name)
    if log_dir is not None and not logger.handlers:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / "organization.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
