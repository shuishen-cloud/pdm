# -*- coding: utf-8 -*-
"""TUI 层（仿 lazygit 布局）。

与 CLI 平级，均依赖内核（``pdev.*``）。

- :class:`~pdev.tui.app.PDMApp` 主应用
- 面板：提交 / 笔记 / 详情
"""

from __future__ import annotations

__all__ = ["PDMApp", "run", "available"]


def available() -> bool:
    """textual 是否可用。"""
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


def __getattr__(name: str):
    # 延迟导入，避免无 textual 时导入本包即失败
    if name in ("PDMApp", "run"):
        from . import app

        return getattr(app, name)
    raise AttributeError(name)
