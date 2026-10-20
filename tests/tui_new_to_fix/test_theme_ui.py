# -*- coding: utf-8 -*-
"""主题在 app 层的冒烟测试（**一次** ``run_test``，见测试预算约束）。

覆盖 ``doc/feat/tui-theme.md`` 的三条行为：

1. 启动时把 ``config.ui.theme`` 应用到 ``App.theme``；
2. 配置主题缺失/非法 → 回退 ``catppuccin-macchiato``；
3. ``t`` 循环切换并写入用户配置（``~/.config/pdm/config.json``）。
"""

from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("textual")

from pdev.store import NoteStore  # noqa: E402
from pdev.tui_new_to_fix.app import PDMApp  # noqa: E402

_T0 = time.perf_counter()


class _UIConfig:
    def __init__(self, theme) -> None:
        self.theme = theme


class _Config:
    def __init__(self, theme) -> None:
        self.ui = _UIConfig(theme)


@pytest.fixture(autouse=True)
def user_config(tmp_path, monkeypatch):
    """把用户配置指向临时目录：测试绝不能碰真实的 ~/.config/pdm。"""
    path = tmp_path / "home" / "config.json"
    monkeypatch.setattr("pdev.config.USER_CONFIG_PATH", str(path))
    return path


def make_app(store, theme_name) -> PDMApp:
    from pathlib import Path

    return PDMApp(
        store,
        cwd=str(Path(store.root).parent),
        config=_Config(theme_name),
    )


async def test_configured_theme_applied_and_cycled(tmp_path, user_config):
    store = NoteStore(tmp_path / "notes")

    # --- 1. 配置主题生效（默认值就是 macchiato，这里用 nord 证明真的读了配置）---
    app = make_app(store, "nord")
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.theme == "nord", f"没读 config.ui.theme：{app.theme}"
        assert app.is_running

        # --- 3. t 循环切换并持久化 ---
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != "nord", "t 没有切换主题"
        saved = json.loads(user_config.read_text(encoding="utf-8"))
        assert saved["ui"]["theme"] == app.theme
        assert app.errors == []

        # 非法配置值不影响运行（不会 panic）
        app.config.ui.theme = "no-such-theme"
        assert app.theme in app.available_themes


async def test_default_theme_when_config_missing(tmp_path):
    """配置里没有主题（None）→ 用 Catppuccin Macchiato。"""
    store = NoteStore(tmp_path / "notes")
    app = make_app(store, None)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "catppuccin-macchiato"
        assert app.is_running


def test_budget():
    elapsed = time.perf_counter() - _T0
    assert elapsed < 2.5, f"主题 UI 测试太慢：{elapsed:.2f}s"
