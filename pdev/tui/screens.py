# -*- coding: utf-8 -*-
"""TUI 弹出屏：筛选与帮助。"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Grid, Vertical, VerticalScroll
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

    BINDINGS = [
        ("escape", "cancel", "取消"),
        ("ctrl+c", "cancel", "取消"),
    ]

    def __init__(self, current: Optional[dict] = None) -> None:
        super().__init__()
        self.current = current or {}

    def action_cancel(self) -> None:
        """Esc 关闭且不改变筛选。"""
        self.dismiss(None)

    def key_q(self) -> bool:
        """q 关闭：仅当焦点不在输入框时（否则 q 是正常输入）。"""
        from textual.widgets import Input

        if isinstance(self.focused, Input):
            return False
        self.dismiss(None)
        return True

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

  [cyan]1[/] / [cyan]2[/] / [cyan]3[/]        直接跳到 提交 / 笔记 / 详情 面板
  [cyan]Tab[/] / [cyan]Shift+Tab[/]     在面板间循环切换
  [cyan]h[/] / [cyan]l[/]             焦点左移 / 右移
  [cyan]j[/] / [cyan]k[/]             上下移动
  [cyan]Enter[/] / [cyan]z[/]         放大当前面板 / 再按还原
  [cyan]/[/]                 筛选（类型/状态/文件/全文）
  [cyan]r[/]                 执行当前笔记的验证
  [cyan]R[/]                 刷新数据
  [cyan]?[/]                 本帮助
  [cyan]q[/]                 退出

[bold]面板[/]

  [cyan]1[/] [bold]提交[/]    有笔记的 commit，显示提交标题与类型分布
  [cyan]2[/] [bold]笔记[/]    选中提交的全部笔记
  [cyan]3[/] [bold]详情[/]    笔记全文、验证方法与测试脚本

[bold]类型颜色[/]

  [red]bug[/] 缺陷    [bright_yellow]pit[/] 易错点   [green]exc[/] 可控异常
  [bright_red]pro[/] 问题    [cyan]dif[/] 难点

[bold]状态标记[/]

  笔记： [green]·[/] noted   [yellow]○[/] open   [green]●[/] resolved
  验证： [green]✓[/] 通过   [red]✗[/] 失败   [yellow]![/] 出错   [dim]-[/] 人工   [dim]·[/] 未跑

[dim]按 Esc / q / ? 关闭本窗口[/]
"""


class HelpScreen(ModalScreen):
    """帮助。按 Esc / q / ? 关闭。"""

    CSS = """
    HelpScreen {
        align: center middle;
        background: $background 70%;
    }
    #help-box {
        width: 74;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #help-text {
        width: auto;
        height: auto;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_help", "关闭"),
        ("q", "dismiss_help", "关闭"),
        ("enter", "dismiss_help", "关闭"),
        ("question_mark", "dismiss_help", "关闭"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(_HELP, id="help-text")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)
