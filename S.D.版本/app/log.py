"""操作日志（G-09）：链路关键事件落盘，供管理后台查看与排障。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("sd_finance")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        log_dir = get_settings().log_dir
        handler = RotatingFileHandler(
            log_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    _logger = logger
    return logger


def read_recent_logs(lines: int = 100) -> list[str]:
    log_file = get_settings().log_dir / "app.log"
    if not log_file.exists():
        return []
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]
