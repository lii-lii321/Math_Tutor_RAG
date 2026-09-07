"""结构化日志：统一格式，便于本地排查与日后接入日志平台。"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "mathmaster") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root = logging.getLogger("mathmaster")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
        _CONFIGURED = True
    return logging.getLogger(f"mathmaster.{name}") if name != "mathmaster" else logging.getLogger("mathmaster")
