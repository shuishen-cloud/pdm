# -*- coding: utf-8 -*-
"""TUI 命令面板（Ctrl+P / p）。

把常用动作注册为命令面板项，可以直接搜索并执行，无需记快捷键。
"""

from __future__ import annotations

from functools import partial
from typing import Iterable

from textual.command import DiscoveryHit, Hit, Hits, Provider

__all__ = ["PDMCommands"]


class PDMCommands(Provider):
    """ProjectDevelopManager 的命令。"""

    def _commands(self) -> list[tuple[str, str, str]]:
        """(显示名, 帮助, 动作名)。"""
        return [
            ("提交面板", "跳到提交列表", "focus_commits"),
            ("笔记面板", "跳到笔记列表", "focus_notes"),
            ("详情面板", "跳到详情", "focus_detail"),
            ("放大 / 还原", "当前面板撑满宽度", "toggle_zoom"),
            ("筛选", "按类型/状态/文件/全文筛选", "filter"),
            ("跑验证", "执行当前笔记的验证", "run_verify"),
            ("Feat 面板", "开发记录与自约束校验", "show_feats"),
            ("切换主题", "循环切换内置主题", "cycle_theme"),
            ("选择主题", "列出全部内置主题", "pick_theme"),
            ("刷新", "重新从磁盘加载", "refresh"),
            ("帮助", "快捷键说明", "help"),
            ("退出", "关闭应用", "quit"),
        ]

    async def discover(self) -> Hits:
        """未输入时展示的默认命令。"""
        for name, help_text, action in self._commands():
            yield DiscoveryHit(
                name,
                partial(self._run, action),
                text=name,
                help=help_text,
            )

    async def search(self, query: str) -> Hits:
        """按输入模糊匹配。"""
        matcher = self.matcher(query)
        for name, help_text, action in self._commands():
            score = matcher.match(name)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    partial(self._run, action),
                    text=name,
                    help=help_text,
                )

    def _run(self, action: str) -> None:
        """执行动作（由命令面板回调）。"""
        method = getattr(self.app, f"action_{action}", None)
        if method is not None:
            method()
