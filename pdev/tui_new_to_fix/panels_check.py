# -*- coding: utf-8 -*-
"""测试辅助：从正在运行的 app 里读出可断言的纯数据。

只被测试引用，不参与运行时。放在包内是为了让测试不必知道
widget 的层级（``#commits`` / ``#notes`` / ``#detail``）。
"""

from __future__ import annotations

from typing import List

from textual.widgets import ListView, Static

__all__ = ["commit_rows", "note_rows", "detail_text"]


def commit_rows(app) -> List[str]:
    """提交面板里每行的 commit。"""
    lv = app.query_one("#commits", ListView)
    return [item.commit for item in lv.children]


def note_rows(app) -> List[str]:
    """笔记面板里每行的标题。"""
    lv = app.query_one("#notes", ListView)
    return [item.note.title for item in lv.children]


def detail_text(app) -> str:
    """详情面板当前文本。

    Textual 8.x 把内容放在 ``Static.content``（``renderable`` 已移除），
    这里对旧属性做兼容。
    """
    static = app.query_one("#detail-body", Static)
    content = getattr(static, "content", None)
    if content is None:
        content = getattr(static, "renderable", None)
    if content is None:
        return ""
    plain = getattr(content, "plain", None)
    return plain if plain is not None else str(content)
