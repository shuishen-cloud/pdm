# -*- coding: utf-8 -*-
"""TUI 的三个面板。"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static

from ..note import CommitNote, NoteKind, NoteStatus, VerificationStatus

__all__ = ["CommitList", "NoteList", "DetailPane"]

_KIND_COLOR = {
    NoteKind.PROBLEM: "bright_red",
    NoteKind.BUG: "red",
    NoteKind.PITFALL: "yellow",
    NoteKind.DIFFICULTY: "cyan",
    NoteKind.CONTROLLED_EXCEPTION: "green",
}

# 提交面板里类型缩写的颜色（比详情更饱和，便于扫视）
_KIND_COLOR_LIST = {
    NoteKind.PROBLEM: "bright_red",
    NoteKind.BUG: "red",
    NoteKind.PITFALL: "bright_yellow",
    NoteKind.DIFFICULTY: "bright_cyan",
    NoteKind.CONTROLLED_EXCEPTION: "bright_green",
}

_STATUS_MARK = {
    NoteStatus.OPEN: "○",
    NoteStatus.RESOLVED: "●",
    NoteStatus.NOTED: "·",
}

_VERIFY_MARK = {
    VerificationStatus.PASSED: "✓",
    VerificationStatus.FAILED: "✗",
    VerificationStatus.ERROR: "!",
    VerificationStatus.SKIPPED: "-",
    VerificationStatus.UNKNOWN: "·",
}


def _ellipsize(text: str, width: int) -> str:
    """按显示宽度截断，超出部分用 …… 代替。"""
    if width <= 0:
        return ""
    if _display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    # 逐字累加，避免在宽字符中间切断
    out = []
    used = 0
    budget = width - 1          # 留一个位置给 …
    for ch in text:
        w = _display_width(ch)
        if used + w > budget:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def _display_width(text: str) -> int:
    """近似显示宽度（CJK 算 2）。"""
    import unicodedata

    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _commit_width_limit(item) -> int:
    """配置的提交条目宽度上限（0 = 不限）。

    脱离 app（如单元测试直接调 ``render()``）时安全返回 0。
    """
    try:
        app = item.app
    except Exception:
        return 0
    cfg = getattr(app, "config", None)
    ui = getattr(cfg, "ui", None)
    return int(getattr(ui, "commit_width", 0) or 0)


# ---------------------------------------------------------------------------
# 提交列表
# ---------------------------------------------------------------------------


class CommitItem(ListItem):
    """提交列表项。"""

    def __init__(self, commit: str, notes: List[CommitNote],
                 info=None) -> None:
        super().__init__()
        self.commit = commit
        self.notes = notes
        self.info = info              # CommitInfo | None

    def render(self) -> Text:
        """单行渲染：``hash  标题  ·  类型分布``。

        超过可用宽度就截断（面板可放大看全）。
        """
        short = {
            NoteKind.PROBLEM: "pro",
            NoteKind.BUG: "bug",
            NoteKind.PITFALL: "pit",
            NoteKind.DIFFICULTY: "dif",
            NoteKind.CONTROLLED_EXCEPTION: "exc",
        }
        kinds: dict = {}
        for n in self.notes:
            kinds[n.kind] = kinds.get(n.kind, 0) + 1

        # 右缀：类型分布（有笔记才显示）
        tail = Text()
        if kinds:
            for i, (k, c) in enumerate(
                sorted(kinds.items(), key=lambda kv: kv[0].value)
            ):
                if i:
                    tail.append(" ")
                tail.append(f"{short.get(k, '?')}:{c}",
                            style=_KIND_COLOR_LIST.get(k, "white"))
        else:
            tail.append("无笔记", style="dim italic")

        hash_part = Text(self.commit[:8], style="bold yellow")
        subject = self.info.subject if (self.info and self.info.subject) else ""

        # 可用宽度：优先面板宽度，其次配置的 commit_width
        width = self.size.width
        if not width:
            width = 80                     # 脱离 app 渲染时的估值
        limit = _commit_width_limit(self)
        if limit > 0:
            width = min(width, limit)

        # hash(8) + 2 空格 + tail；剩余给标题
        gap = 2
        avail = width - len(hash_part.plain) - gap - tail.cell_len - gap

        t = Text()
        t.append_text(hash_part)
        t.append("  ")
        if subject:
            t.append(_ellipsize(subject, max(avail, 4)), style="white")
        t.append("  ")
        t.append_text(tail)
        return t


class CommitList(ListView):
    """左侧：有笔记的提交。"""

    class Picked(Message):
        """用户选中某个提交。

        不能叫 ``Selected``：那会覆盖 ``ListView.Selected``，
        而 Textual 点击 item 时正是发父类的 ``Selected``（叁数不同）会报错。
        """

        def __init__(self, commit: str) -> None:
            self.commit = commit
            super().__init__()

    def load(self, commits: List[tuple]) -> None:
        """commits: [(commit, notes, info|None), ...]"""
        self.clear()
        for entry in commits:
            commit, notes = entry[0], entry[1]
            info = entry[2] if len(entry) > 2 else None
            self.append(CommitItem(commit, notes, info))
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, CommitItem):
            self.post_message(self.Picked(event.item.commit))

    def key_enter(self) -> bool:
        """Enter 在被 ListView 消化前转给 App 放大。"""
        self.app.action_toggle_zoom()
        return True

    def action_cursor_down(self) -> None:
        self.action_cursor_down_impl()

    def action_cursor_down_impl(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, delta: int) -> None:
        if not self.children:
            return
        idx = self.index if self.index is not None else 0
        new = max(0, min(len(self.children) - 1, idx + delta))
        self.index = new


# ---------------------------------------------------------------------------
# 笔记列表
# ---------------------------------------------------------------------------


class NoteItem(ListItem):
    """笔记列表项。"""

    def __init__(self, note: CommitNote) -> None:
        super().__init__()
        self.note = note

    def render(self) -> Text:
        n = self.note
        t = Text()
        t.append(_STATUS_MARK.get(n.status, "·") + " ")
        t.append(f"[{n.kind.value}] ", style=_KIND_COLOR.get(n.kind, "white"))
        t.append(n.title)
        if n.verifications:
            # 只显示聚合结果，不逐条堆叠符号
            marks = "".join(
                _VERIFY_MARK.get(v.last_status, "?") for v in n.verifications
            )
            t.append(f"  {marks}", style="dim")
        if n.severity:
            t.append(f"  {n.severity.value}", style="dim red")
        return t


class NoteList(ListView):
    """中左：选中提交的笔记。"""

    class Picked(Message):
        """用户选中某条笔记（不叫 Selected，原因见 CommitList.Picked）。"""

        def __init__(self, note: CommitNote) -> None:
            self.note = note
            super().__init__()

    def load(self, notes: List[CommitNote]) -> None:
        self.clear()
        for n in notes:
            self.append(NoteItem(n))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, NoteItem):
            self.post_message(self.Picked(event.item.note))

    def key_enter(self) -> bool:
        self.app.action_toggle_zoom()
        return True

    def action_cursor_down(self) -> None:
        self._move(1)

    def action_cursor_up(self) -> None:
        self._move(-1)

    def _move(self, delta: int) -> None:
        if not self.children:
            return
        idx = self.index if self.index is not None else 0
        new = max(0, min(len(self.children) - 1, idx + delta))
        self.index = new


# ---------------------------------------------------------------------------
# 详情面板
# ---------------------------------------------------------------------------


class DetailPane(VerticalScroll):
    """右侧：笔记详情。"""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.note: Optional[CommitNote] = None
        self.commit_info = None
        self._body = Static(id="detail-body")

    def compose(self) -> ComposeResult:
        yield self._body

    def show_note(self, note: Optional[CommitNote], cwd: str = ".",
                  commit_info=None) -> None:
        self.note = note
        self.commit_info = commit_info
        self._body.update(self._build(note, cwd, commit_info))

    def _build(self, n: Optional[CommitNote], cwd: str,
               commit_info=None) -> Text:
        t = Text()
        # 提交标题放在最上方，一眼看到这次提交干了什么
        has_header = commit_info is not None and commit_info.subject
        if has_header:
            t.append("提交  ", style="dim")
            t.append(commit_info.subject + "\n", style="bold yellow")
            if commit_info.author:
                t.append("作者  ", style="dim")
                when = (commit_info.date.strftime("%Y-%m-%d %H:%M")
                        if commit_info.date else "")
                t.append(f"{commit_info.author}", style="dim")
                if when:
                    t.append(f"  {when}", style="dim")
                t.append("\n")
            if commit_info.hash:
                t.append("提交号 ", style="dim")
                t.append(commit_info.hash + "\n", style="dim")
            t.append("─" * 40 + "\n", style="dim")

        # 没有笔记：只展示提交信息（这是一个尚未记录的提交）
        if n is None:
            if has_header:
                t.append("（该提交暂无笔记）", style="dim italic")
            else:
                t.append("（无笔记）", style="dim")
            return t

        t.append(f"[{n.kind.value}] ", style=f"bold {_KIND_COLOR.get(n.kind, 'white')}")
        t.append(n.title + "\n", style="bold")
        t.append("─" * 40 + "\n", style="dim")

        rows = [
            ("commit", n.commit),
            ("author", str(n.author)),
            ("status", n.status.value),
        ]
        if n.severity:
            rows.append(("severity", n.severity.value))
        if n.files:
            rows.append(("files", ", ".join(n.files)))
        if n.tags:
            rows.append(("tags", " ".join("#" + x for x in n.tags)))
        if n.catches:
            rows.append(("catches", ", ".join(n.catches)))
        if n.issue_id:
            rows.append(("issue", n.issue_id))
        if n.resolves:
            rows.append(("resolves", ", ".join(n.resolves)))
        if n.created_at:
            rows.append(("created", n.created_at.strftime("%Y-%m-%d %H:%M")))

        for k, v in rows:
            t.append(f"{k:<10}", style="dim")
            t.append(f"{v}\n")

        if n.detail:
            t.append("\n")
            t.append(n.detail + "\n")

        # 验证
        t.append("\n")
        if not n.verifications:
            t.append("（未登记验证方法）\n", style="dim")
        else:
            t.append("验证\n", style="bold")
            t.append("─" * 40 + "\n", style="dim")
            for i, v in enumerate(n.verifications, 1):
                mark = _VERIFY_MARK.get(v.last_status, "?")
                color = {
                    VerificationStatus.PASSED: "green",
                    VerificationStatus.FAILED: "red",
                    VerificationStatus.ERROR: "yellow",
                }.get(v.last_status, "dim")
                t.append(f"{mark} ", style=color)
                t.append(f"[{v.kind.value}] ", style="bold")
                t.append((v.effective_command or v.note or "(人工)") + "\n")
                if v.method:
                    t.append(f"    方法  {v.method}\n", style="italic")
                if v.expected:
                    t.append(f"    期望  {v.expected}\n", style="dim")

                # 脚本（语法高亮）
                script = v.script or self._extract(v, cwd)
                if script:
                    t.append("    ┌" + "─" * 36 + "\n", style="dim")
                    t.append_text(_highlight_python(script, indent="    │ "))
                    t.append("    └" + "─" * 36 + "\n", style="dim")
        return t

    def _extract(self, v, cwd: str) -> str:
        """尝试从测试文件抽取脚本。"""
        if v.kind.value != "test" or not v.target:
            return ""
        from pathlib import Path

        from ..scripts import extract_script

        r = extract_script(v.target, root=Path(cwd))
        return r.code if r.ok else ""


def _highlight_python(code: str, indent: str = "") -> Text:
    """用 Pygments 给 Python 代码上色，返回带样式的 Text。

    Pygments 是 Textual 的依赖，总是可用；出错时回退为纯文本。
    """
    out = Text()
    if not code:
        return out
    try:
        from pygments import lex
        from pygments.lexers import PythonLexer
        from pygments.styles import get_style_by_name
    except Exception:
        for line in code.splitlines():
            out.append(indent + line + "\n")
        return out

    # 把 Pygments 调色板映射到终端可用颜色
    try:
        style = get_style_by_name("monokai")
    except Exception:
        style = None

    def color_for(token_type) -> str | None:
        if style is None:
            return None
        try:
            st = style.style_for_token(token_type)
        except Exception:
            return None
        if st.get("color"):
            return "#" + st["color"]
        return None

    line_start = True
    line_text = Text()
    for token_type, value in lex(code, PythonLexer()):
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                out.append_text(line_text)
                out.append("\n")
                line_text = Text()
                line_start = True
            if part:
                if line_start:
                    line_text.append(indent)
                    line_start = False
                color = color_for(token_type)
                line_text.append(part, style=color or "")
    if line_text.plain:
        out.append_text(line_text)
    return out
