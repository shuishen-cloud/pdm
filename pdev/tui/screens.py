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

__all__ = ["FilterScreen", "VerifyScreen", "HelpScreen",
           "ThemeScreen", "FeatScreen"]


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
  [cyan]f[/]                 Feat 面板（开发记录 + 自约束校验）
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


class FeatScreen(ModalScreen):
    """Feat 与自约束校验：左列 feat，右侧详情 + check 结果。

    - `j` / `k` 或上下键移动
    - `c` 对当前 feat 跑校验
    - `Esc` / `q` 关闭
    """

    CSS = """
    FeatScreen { align: center middle; background: $background 70%; }
    #feat-box {
        width: 96;
        height: 80%;
        padding: 0 1;
        border: thick $accent;
        background: $surface;
    }
    #feat-title { height: 1; color: $text-muted; margin-bottom: 1; }
    #feat-body { height: 1fr; }
    #feat-list { width: 40; height: 1fr; border: round $primary; }
    #feat-detail {
        width: 1fr;
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    FeatItem { padding: 0 1; height: 1; }
    #feat-hint { height: 1; color: $text-muted; margin-top: 1; }
    """

    BINDINGS = [
        ("escape", "close", "关闭"),
        ("q", "close", "关闭"),
        ("c", "check", "校验"),
        ("r", "reload", "刷新"),
    ]

    def __init__(self, store, git=None, note_store=None) -> None:
        super().__init__()
        self.feat_store = store
        self.git = git
        self.note_store = note_store
        self._issues: list = []

    def compose(self) -> ComposeResult:
        from textual.widgets import ListItem, ListView

        feats = list(self.feat_store.all())
        items = [ListItem(Static(_feat_line(f)), id=f"feat-{f.slug}")
                 for f in feats]
        for item, f in zip(items, feats):
            item.feat_slug = f.slug

        with Vertical(id="feat-box"):
            yield Static("Feat（开发记录）·  c 校验  ·  Esc 关闭",
                         id="feat-title")
            with Horizontal(id="feat-body"):
                view = ListView(*items, id="feat-list")
                if feats:
                    view.index = 0
                yield view
                yield Static("", id="feat-detail")
            yield Static("j/k 移动   ·   c 跑校验   ·   r 刷新   ·   Esc 关闭",
                         id="feat-hint")

    def on_mount(self) -> None:
        self._refresh_detail()

    def on_list_view_highlighted(self, event) -> None:
        self._refresh_detail()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_reload(self) -> None:
        self._issues = []
        self.refresh(recompose=True)
        self.call_after_refresh(self._refresh_detail)

    def action_check(self) -> None:
        """对当前 feat 跑自约束校验。"""
        from ..check import check_one, summarize

        slug = self._current_slug()
        if slug is None:
            return
        try:
            self._issues = check_one(self.feat_store, slug, self.git)
        except KeyError:
            self._issues = []
        if not self._issues:
            self._issues = []
        self._refresh_detail()
        stats = summarize(self._issues)
        if stats["total"]:
            self.notify(
                f"{slug}：{stats['errors']} 错误，{stats['warnings']} 警告",
                severity="error" if stats["errors"] else "warning",
            )
        else:
            self.notify(f"{slug}：通过校验")

    def _current_slug(self):
        from textual.widgets import ListView

        view = self.query_one("#feat-list", ListView)
        idx = view.index
        feats = list(self.feat_store.all())
        if idx is None or idx >= len(feats):
            return None
        return feats[idx].slug

    def _refresh_detail(self) -> None:
        from textual.widgets import Static

        slug = self._current_slug()
        body = self.query_one("#feat-detail", Static)
        if slug is None:
            body.update(Text("（无 feat，用 pdm feat new 创建）", style="dim"))
            return
        feat = self.feat_store.get(slug)
        body.update(_feat_detail(feat, self._issues,
                                 git=self.git, note_store=self.note_store))


def _feat_line(feat) -> Text:
    """feat 列表的一行。"""
    t = Text()
    mark = {
        "draft": "○", "testing": "◐", "integrated": "◑",
        "fixing": "◒", "closed": "●",
    }.get(feat.status.value, "·")
    t.append(f"{mark} ", style="bold")
    t.append(f"{feat.slug}", style="bold yellow")
    t.append(f"  {feat.status.value}", style="dim")
    if feat.commits:
        t.append(f"  ×{len(feat.commits)}", style="dim green")
    return t


def _feat_detail(feat, issues, git=None, note_store=None) -> Text:
    """右侧详情：阶段闭环 + 字段 + 笔记 + 校验。"""
    t = Text()
    t.append(f"{feat.slug}\n", style="bold yellow")
    t.append(f"{feat.title}\n", style="bold")
    t.append("─" * 36 + "\n", style="dim")

    # 阶段闭环
    t.append("阶段  ", style="dim")
    for key, done in stage_progress(feat, git):
        label = dict(_FEAT_STAGES).get(key, key)
        mark = "●" if done else "○"
        style = "green" if done else "dim"
        t.append(f"{mark}{label} ", style=style)
    t.append("\n")
    t.append("─" * 36 + "\n", style="dim")

    if feat.doc:
        t.append("设计文档  ", style="dim")
        t.append(f"{feat.doc}\n", style="white")
    t.append("状态      ", style="dim")
    t.append(f"{feat.kind.value} / {feat.status.value}\n", style="white")

    if feat.api:
        t.append("\n交付接口\n", style="bold cyan")
        for a in feat.api:
            t.append(f"  · {a}\n")
    if feat.logs:
        t.append("\n会打的日志\n", style="bold cyan")
        for x in feat.logs:
            t.append(f"  · {x}\n")
    if feat.fallbacks:
        t.append("\n异常兜底\n", style="bold cyan")
        for x in feat.fallbacks:
            t.append(f"  · {x}\n")
    if feat.commits:
        t.append("\n关联 commit\n", style="bold cyan")
        for c in feat.commits:
            t.append(f"  · {c[:8]}\n", style="green")
    if feat.discovered:
        t.append("\n发现的异常\n", style="bold red")
        for x in feat.discovered:
            t.append(f"  · {x}\n")

    # 关联笔记
    notes = notes_for_feat(feat, note_store)
    t.append("\n关联笔记\n", style="bold cyan")
    if not notes:
        t.append("  （该 feat 暂无笔记）\n", style="dim")
    else:
        for n in notes:
            t.append(f"  {n.kind.value} ", style="cyan")
            t.append(f"{n.title}\n")

    t.append("\n校验\n", style="bold cyan")
    if not issues:
        t.append("  （按 c 运行校验）\n", style="dim")
    else:
        from ..check import format_issue

        for i in issues:
            style = "red" if i.level == "error" else "yellow"
            t.append(f"  {i.mark} {i.code}\n", style=style)
            t.append(f"      {i.message}\n", style="dim")
    return t


# ---------------------------------------------------------------------------
# Feat 界面辅助（见 docs/feat/feat-ui.md）
# ---------------------------------------------------------------------------

# 五阶段：显示名 → classify_stage 能识别的键
_FEAT_STAGES = [
    ("doc", "① 设计"), ("test", "② 测试"), ("feat", "③ 实现"),
    ("fix", "④ 修复"), ("closing", "⑤ 收尾"),
]


def stage_progress(feat, git) -> list:
    """推导 doc→test→feat→fix→doc 五阶段的完成情况。

    返回 ``[(键, 是否完成), ...]``；git 不可用时全部为 False。

    阶段由 ``feat.commits`` 的提交信息前缀判定（复用 classify_stage）。
    ``doc`` 前缀可同时算①设计与⑤收尾。
    """
    done = {"doc": False, "test": False, "feat": False,
            "fix": False, "closing": False}
    if git is None or not getattr(git, "available", False):
        return [(k, False) for k, _ in _FEAT_STAGES]

    from ..check import classify_stage

    doc_seen = 0
    for c in feat.commits:
        info = git.commit_info(c)
        if info is None:
            continue
        stage = classify_stage(info.subject)
        if stage == "doc":
            doc_seen += 1
            done["doc"] = True
            if doc_seen >= 2:
                done["closing"] = True
        elif stage in done:
            done[stage] = True

    return [(k, done[k]) for k, _ in _FEAT_STAGES]


def notes_for_feat(feat, note_store) -> list:
    """该 feat 关联 commit 上的全部笔记。

    匹配规则：完全相等，或一方是另一方的 hash 前缀（至少 6 位），
    避免短串误匹配。
    """
    if note_store is None:
        return []
    wanted = [c for c in feat.commits if c]
    out = []
    for n in note_store.all():
        nc = n.commit or ""
        if not nc:
            continue
        for c in wanted:
            if nc == c:
                out.append(n)
                break
            if len(c) >= 6 and nc.startswith(c):
                out.append(n)
                break
            if len(nc) >= 6 and c.startswith(nc):
                out.append(n)
                break
    return out
