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
    NoteKind.PROBLEM: "red",
    NoteKind.BUG: "red",
    NoteKind.PITFALL: "magenta",
    NoteKind.DIFFICULTY: "cyan",
    NoteKind.CONTROLLED_EXCEPTION: "green",
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


# ---------------------------------------------------------------------------
# 提交列表
# ---------------------------------------------------------------------------


class CommitItem(ListItem):
    """提交列表项。"""

    def __init__(self, commit: str, notes: List[CommitNote]) -> None:
        super().__init__()
        self.commit = commit
        self.notes = notes

    def render(self) -> Text:
        t = Text()
        t.append(self.commit[:8], style="bold yellow")
        t.append(f"  {len(self.notes)} notes\n", style="dim")
        # 类型缩写分布
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
        parts = [f"{short.get(k, '?')}:{c}"
                 for k, c in sorted(kinds.items(), key=lambda kv: kv[0].value)]
        t.append("  " + " ".join(parts), style="dim")
        return t


class CommitList(ListView):
    """左侧：有笔记的提交。"""

    class Selected(Message):
        def __init__(self, commit: str) -> None:
            self.commit = commit
            super().__init__()

    def load(self, commits: List[tuple]) -> None:
        self.clear()
        for commit, notes in commits:
            self.append(CommitItem(commit, notes))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, CommitItem):
            self.post_message(self.Selected(event.item.commit))

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

    class Selected(Message):
        def __init__(self, note: CommitNote) -> None:
            self.note = note
            super().__init__()

    def load(self, notes: List[CommitNote]) -> None:
        self.clear()
        for n in notes:
            self.append(NoteItem(n))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, NoteItem):
            self.post_message(self.Selected(event.item.note))

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
        self._body = Static(id="detail-body")

    def compose(self) -> ComposeResult:
        yield self._body

    def show_note(self, note: Optional[CommitNote], cwd: str = ".") -> None:
        self.note = note
        self._body.update(self._build(note, cwd))

    def _build(self, n: Optional[CommitNote], cwd: str) -> Text:
        if n is None:
            return Text("（无笔记）", style="dim")

        t = Text()
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

                # 脚本
                script = v.script or self._extract(v, cwd)
                if script:
                    t.append("    ┌" + "─" * 36 + "\n", style="dim")
                    for line in script.splitlines():
                        t.append("    │ " + line + "\n", style="bright_black")
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
