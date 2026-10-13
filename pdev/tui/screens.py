# -*- coding: utf-8 -*-
"""TUI 弹出屏：筛选、验证过程与帮助。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ..note import NoteKind, NoteStatus, VerificationStatus

__all__ = ["FilterScreen", "VerifyScreen", "HelpScreen", "ThemeScreen"]


class FilterScreen(ModalScreen):
    """筛选条件输入（紧凑单屏）。

    - ``Enter`` 应用
    - ``Esc`` / ``q`` 取消
    - ``Ctrl+L`` 清除
    返回 dict（空 dict 表示清除筛选），取消返回 None。
    """

    CSS = """
    FilterScreen { align: center middle; background: $background 60%; }
    #filter-box {
        width: 64;
        height: auto;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #filter-box .row { height: 3; }
    #filter-box .row Label {
        width: 12;
        height: 3;
        content-align: left middle;
        color: $text-muted;
    }
    #filter-box Input { width: 1fr; }
    #filter-hint { color: $text-muted; height: auto; margin-top: 1; }
    """

    BINDINGS = [
        ("escape", "cancel", "取消"),
        ("ctrl+l", "clear", "清除"),
        ("ctrl+c", "cancel", "取消"),
    ]

    def __init__(self, current: Optional[dict] = None) -> None:
        super().__init__()
        self.current = current or {}

    # --- 动作 ---

    def action_cancel(self) -> None:
        """Esc 关闭且不改变筛选。"""
        self.dismiss(None)

    def action_clear(self) -> None:
        """Ctrl+L 清除全部筛选。"""
        self.dismiss({})

    def key_q(self) -> bool:
        """q 关闭：仅当焦点不在输入框时（否则 q 是正常输入）。"""
        if isinstance(self.focused, Input):
            return False
        self.dismiss(None)
        return True

    def action_apply(self) -> None:
        """Enter：校验并应用。"""
        result = {}

        kind = self.query_one("#kind", Input).value.strip()
        if kind:
            try:
                result["kind"] = NoteKind(kind)
            except ValueError:
                self.notify(f"未知类型：{kind}", severity="error")
                self.query_one("#kind", Input).focus()
                return

        status = self.query_one("#status", Input).value.strip()
        if status:
            try:
                result["status"] = NoteStatus(status)
            except ValueError:
                self.notify(f"未知状态：{status}", severity="error")
                self.query_one("#status", Input).focus()
                return

        file = self.query_one("#file", Input).value.strip()
        if file:
            result["file"] = file
        text = self.query_one("#text", Input).value.strip()
        if text:
            result["text"] = text

        self.dismiss(result)

    # --- 布局 ---

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-box"):
            with Horizontal(classes="row"):
                yield Label("类型")
                yield Input(
                    value=(self.current.get("kind").value
                           if self.current.get("kind") else ""),
                    placeholder="problem / difficulty / pitfall / controlled-exception / bug",
                    id="kind",
                )
            with Horizontal(classes="row"):
                yield Label("状态")
                yield Input(
                    value=(self.current.get("status").value
                           if self.current.get("status") else ""),
                    placeholder="open / resolved / noted",
                    id="status",
                )
            with Horizontal(classes="row"):
                yield Label("文件")
                yield Input(
                    value=self.current.get("file", ""),
                    placeholder="src/auth/** （支持 glob）",
                    id="file",
                )
            with Horizontal(classes="row"):
                yield Label("全文")
                yield Input(
                    value=self.current.get("text", ""),
                    placeholder="关键字",
                    id="text",
                )
            yield Static(
                "[dim]Enter 应用   ·   Esc/q 取消   ·   Ctrl+L 清除[/]",
                id="filter-hint",
            )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_apply()


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
  [cyan]p[/] / [cyan]Ctrl+P[/]       命令面板（搜索并执行动作）
  [cyan]t[/]                 循环切换主题（自动保存）
  [cyan]T[/]                 弹出主题选择器
  [cyan]?[/]                 本帮助
  [cyan]q[/]                 退出

[bold]面板[/]

  [cyan]1[/] [bold]提交[/]    git 历史中的全部提交（单行显示，过长截断）
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


class VerifyScreen(ModalScreen):
    """验证执行过程与结果。

    打开后逐个跑验证，实时显示：命令、状态、输出（失败时）。
    全部完成后可 Esc/q 关闭。
    """

    CSS = """
    VerifyScreen {
        align: center middle;
        background: $background 60%;
    }
    #verify-box {
        width: 84;
        height: auto;
        max-height: 85%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #verify-title { text-style: bold; height: auto; }
    #verify-list { width: 1fr; height: auto; }
    #verify-footer { height: auto; margin-top: 1; }
    """

    BINDINGS = [
        ("escape", "close", "关闭"),
        ("q", "close", "关闭"),
        ("enter", "close", "关闭"),
    ]

    def __init__(self, note, cwd: str = ".", timeout: int = 600) -> None:
        super().__init__()
        self.note = note
        self.cwd = cwd
        self.timeout = timeout
        self._lines: list = []
        self._done = False

    def compose(self) -> ComposeResult:
        with Vertical(id="verify-box"):
            yield Static(id="verify-title")
            yield Static(id="verify-list")
            yield Static(id="verify-footer")

    def on_mount(self) -> None:
        self._render_lines()
        self.run_worker(self._run_all, exclusive=True)

    # --- 执行 ---

    async def _run_all(self) -> None:
        from ..verify import run_verification

        note = self.note
        self.query_one("#verify-title", Static).update(
            f"[bold]验证[/]  {note.commit[:8]}  {note.title}"
        )

        runnable = note.runnable_verifications
        if not runnable:
            self._lines.append(("dim", "（没有可执行的验证）"))
            self._render_lines()
            self._finish(0, 0)
            return

        passed = failed = 0
        for v in runnable:
            cmd = v.effective_command or "(空)"
            self._lines.append(("bold", f"$ {cmd}"))
            if v.method:
                self._lines.append(("italic", f"  方法  {v.method}"))
            self._render_lines()
            await self._pause(0.05)

            # 同步执行放进线程，避免阻塞 UI
            result = await asyncio.to_thread(
                run_verification, v, cwd=self.cwd, timeout=self.timeout
            )
            v.record(result.status, datetime.now().astimezone(), result.output)

            mark, color = {
                VerificationStatus.PASSED: ("✓ 通过", "green"),
                VerificationStatus.FAILED: ("✗ 失败", "red"),
                VerificationStatus.ERROR: ("! 出错", "yellow"),
                VerificationStatus.SKIPPED: ("- 跳过", "dim"),
            }.get(result.status, ("? 未知", "dim"))

            if result.status is VerificationStatus.PASSED:
                passed += 1
            elif result.status in (VerificationStatus.FAILED,
                                   VerificationStatus.ERROR):
                failed += 1

            self._lines.append((color, f"  → {mark}"))
            # 失败/出错时才展开输出，避免刷屏
            if result.status in (VerificationStatus.FAILED,
                                 VerificationStatus.ERROR) and result.output:
                for line in result.output.splitlines()[-15:]:
                    self._lines.append(("dim", f"    {line}"))
            self._lines.append(("", ""))
            self._render_lines()

        self._finish(passed, failed)

    async def _pause(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def _finish(self, passed: int, failed: int) -> None:
        self._done = True
        total = passed + failed
        color = "green" if failed == 0 else "red"
        self.query_one("#verify-footer", Static).update(
            f"[{color}]共 {total} 条：通过 {passed}，失败 {failed}[/]\n"
            "[dim]Esc / q 关闭[/]"
        )

    def _render_lines(self) -> None:
        text = Text()
        for style, line in self._lines:
            text.append(line + "\n", style=style)
        self.query_one("#verify-list", Static).update(text)

    def action_close(self) -> None:
        if not self._done:
            self.notify("验证进行中…", severity="warning")
            return
        self.dismiss(None)


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


class ThemeScreen(ModalScreen):
    """主题选择器：列出全部内置主题，回车切换。

    返回选中的主题名，取消返回 None。
    """

    CSS = """
    ThemeScreen {
        align: center middle;
        background: $background 70%;
    }
    #theme-box {
        width: 44;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #theme-list {
        height: auto;
        max-height: 24;
    }
    ThemeItem {
        padding: 0 1;
    }
    ThemeItem.--current {
        background: $accent 40%;
    }
    #theme-hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "取消"),
        ("q", "cancel", "取消"),
    ]

    class Picked(Message):
        """选中某个主题。"""

        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, current: str = "textual-dark") -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        from textual.widgets import ListItem, ListView

        names = sorted(self.app.available_themes)
        with Vertical(id="theme-box"):
            items = []
            for name in names:
                item = ListItem(Static(
                    ("● " if name == self.current else "  ") + name
                ))
                item.theme_name = name
                if name == self.current:
                    item.add_class("--current")
                items.append(item)
            view = ListView(*items, id="theme-list")
            if self.current in names:
                view.index = names.index(self.current)
            yield view
            yield Static("Enter 选择   ·   Esc/q 取消", id="theme-hint")

    def on_list_view_selected(self, event) -> None:
        item = event.item
        name = getattr(item, "theme_name", None)
        if name:
            self.dismiss(name)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_q(self) -> bool:
        """q 关闭（没有输入框，直接关）。"""
        self.dismiss(None)
        return True
