# -*- coding: utf-8 -*-
"""新 TUI（tui-new-to-fix）。

延迟导入 textual：未安装时 import 本包**不能**报错，
否则 CLI 其他命令会被拖累。
"""

from __future__ import annotations

__all__ = ["PDMApp", "run", "available"]


def available() -> bool:
    """textual 是否可用。"""
    try:
        import textual  # noqa: F401
    except Exception:                            # noqa: BLE001
        return False
    return True


def __getattr__(name):
    if name in ("PDMApp", "run"):
        from . import app

        return getattr(app, name)
    raise AttributeError(name)
