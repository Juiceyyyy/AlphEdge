"""Rotating file logger setup."""
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_INITIALIZED = False


def setup_logging(log_dir: str | Path = "logs", name: str = "alpha_strategy",
                  level: int = logging.INFO) -> logging.Logger:
    global _INITIALIZED
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("alpha_strategy")
    logger.setLevel(level)

    if _INITIALIZED:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = Path(log_dir) / f"{name}.log"
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024,
                             backupCount=10, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _INITIALIZED = True
    return logger


def get_logger(name: str = "alpha_strategy") -> logging.Logger:
    return logging.getLogger(name if name == "alpha_strategy" else f"alpha_strategy.{name}")

