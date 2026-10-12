# -*- coding: utf-8 -*-
"""TUI 弹出屏：筛选与帮助。"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from ..note import NoteKind, NoteStatus

__all__ = ["FilterScreen", "HelpScreen"]


class FilterScreen(ModalScreen):
    """筛选条件输入。返回 dict（空 dict 表示清除筛选）。"""

    CSS = """
    FilterScreen { align: center middle; }
    #filter-box { width: 60; height: auto; padding: 1 2;
                  border: thick $accent; background: $surface; }
    #filter-box Label { margin-top: 1; }
    #buttons { margin-top: 1; height: auto; }
    """

    def __init__(self, current: Optional[dict] = None) -> None:
        super().__init__()
        self.current = current or {}

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-box"):
            yield Label("筛选（留空表示不限制）", id="title")
            yield Label("类型 problem/difficulty/pitfall/controlled-exception/bug")
            yield Input(
                value=(self.current.get("kind").value
                       if self.current.get("kind") else ""),
                placeholder="kind", id="kind",
            )
            yield Label("状态 open/resolved/noted")
            yield Input(
                value=(self.current.get("status").value
                       if self.current.get("status") else ""),
                placeholder="status", id="status",
            )
            yield Label("文件（支持 glob，如 src/auth/**）")
            yield Input(
                value=self.current.get("file", ""),
                placeholder="file", id="file",
            )
            yield Label("全文关键字")
            yield Input(
                value=self.current.get("text", ""),
                placeholder="text", id="text",
            )
            with Grid(id="buttons"):
                yield Button("应用", variant="primary", id="apply")
                yield Button("清除", id="clear")
                yield Button("取消", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "clear":
            self.dismiss({})
            return

        result = {}
        kind = self.query_one("#kind", Input).value.strip()
        status = self.query_one("#status", Input).value.strip()
        file = self.query_one("#file", Input).value.strip()
        text = self.query_one("#text", Input).value.strip()

        if kind:
            try:
                result["kind"] = NoteKind(kind)
            except ValueError:
                self.notify(f"未知类型：{kind}", severity="error")
                return
        if status:
            try:
                result["status"] = NoteStatus(status)
            except ValueError:
                self.notify(f"未知状态：{status}", severity="error")
                return
        if file:
            result["file"] = file
        if text:
            result["text"] = text

        self.dismiss(result)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#apply", Button).press()


_HELP = """\
[bold]快捷键[/]

  [yellow]Tab / Shift+Tab[/]   在面板间切换
  [yellow]h / l[/]             左移 / 右移面板
  [yellow]j / k[/]             上下移动
  [yellow]/[/]                 筛选（类型/状态/文件/全文）
  [yellow]r[/]                 执行当前笔记的验证
  [yellow]R[/]                 刷新数据
  [yellow]q[/]                 退出

[bold]面板[/]

  1. [bold]提交[/]    有笔记的 commit，显示笔记数量与类型分布
  2. [bold]笔记[/]    选中提交的全部笔记
  3. [bold]详情[/]    笔记全文、验证方法与脚本

[bold]状态标记[/]

  笔记： [green]·[/] noted  [yellow]○[/] open  [green]●[/] resolved
  验证： [green]✓[/] 通过  [red]✗[/] 失败  [yellow]![/] 出错  [dim]-[/] 人工  ? 未跑
"""


class HelpScreen(ModalScreen):
    """帮助。按任意键关闭。"""

    CSS = """
    HelpScreen { align: center middle; }
    #help-box { width: 68; height: auto; max-height: 90%;
                padding: 1 2; border: thick $accent;
                background: $surface; }
    """

    BINDINGS = [
        ("escape", "dismiss", "关闭"),
        ("q", "dismiss", "关闭"),
        ("enter", "dismiss", "关闭"),
        ("question_mark", "dismiss", "关闭"),
    ]

    def compose(self) -> ComposeResult:
        from textual.widgets import Markdown

        with Vertical(id="help-box"):
            yield Markdown(_HELP)

    def action_dismiss(self) -> None:
        self.dismiss(None)
