# -*- coding: utf-8 -*-
"""新 TUI 主应用。

设计目标（见 ``doc/tui-new-to-fix.md``）：

1. **不为异常退出**：所有 action 都被 :func:`pdev.tui_new_to_fix.guard.guard`
   包住，未知异常只提示、不 panic。
2. **小**：只做三栏浏览 + 刷新。

启动方式（与旧 TUI 并存，用 `--new` 切换）::

    pdm ui --new                     # 推荐
    python -m pdev.tui_new_to_fix    # 等价
    pdm ui                           # 旧 Textual TUI
"""

from __future__ import annotations

from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Header, ListItem, ListView, Static

from ..note import CommitNote
from . import core
from .guard import guard

__all__ = ["PDMApp", "run"]


class CommitItem(ListItem):
    """提交列表的一行。"""

    def __init__(self, commit: str, notes: List[CommitNote], info=None) -> None:
        super().__init__()
        self.commit = commit
        self.notes = notes
        self.info = info

    def render(self):
        from rich.text import Text

        width = self.size.width or 80
        hash_part, subject, tail, spans, _ = core.commit_line_parts(
            self.commit, self.info, self.notes, width
        )
        t = Text()
        t.append(hash_part, style="bold yellow")
        if subject:
            t.append("  ")
            t.append(subject, style="white")
        t.append("  ")
        for piece, style in spans:
            t.append(piece, style=style or None)
        return t


class NoteItem(ListItem):
    """笔记列表的一行。"""

    def __init__(self, note: CommitNote) -> None:
        super().__init__()
        self.note = note

    def render(self):
        from rich.text import Text

        width = self.size.width or 40
        mark, kind, title, suffix = core.note_line_parts(self.note, width)
        t = Text()
        t.append(mark + " ")
        t.append(kind, style=core.KIND_COLOR.get(self.note.kind, "white"))
        t.append(title)
        if suffix:
            t.append(suffix, style="dim")
        return t


class CommitList(ListView):
    """左侧提交列表。"""

    class Picked(Message):
        def __init__(self, commit: str) -> None:
            self.commit = commit
            super().__init__()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, CommitItem):
            self.post_message(self.Picked(event.item.commit))


class NoteList(ListView):
    """中间笔记列表。"""

    class Picked(Message):
        def __init__(self, note: CommitNote) -> None:
            self.note = note
            super().__init__()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, NoteItem):
            self.post_message(self.Picked(event.item.note))


class DetailPane(VerticalScroll):
    """右侧详情。"""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.note: Optional[CommitNote] = None
        self.commit_info = None
        self._body = Static(id="detail-body")

    def compose(self) -> ComposeResult:
        yield self._body

    def show_note(self, note, cwd: str = ".", commit_info=None) -> None:
        from rich.text import Text

        self.note = note
        self.commit_info = commit_info
        t = Text()
        if commit_info is not None and getattr(commit_info, "subject", ""):
            t.append("提交  ", style="dim")
            t.append(commit_info.subject + "\n", style="bold yellow")
            if getattr(commit_info, "author", ""):
                t.append("作者  ", style="dim")
                t.append(f"{commit_info.author}\n", style="dim")
            t.append("\n")
        if note is None:
            t.append("（该提交暂无笔记）", style="dim")
        else:
            t.append(f"[{note.kind.value}] ", style="bold")
            t.append(note.title + "\n", style="bold")
            if note.detail:
                t.append("\n" + note.detail + "\n")
            for i, v in enumerate(note.verifications, 1):
                t.append(f"\n验证 {i}: {v.kind.value}\n", style="bold cyan")
                if v.method:
                    t.append(f"  方法  {v.method}\n", style="dim")
                if getattr(v, "effective_command", None):
                    t.append(f"  $ {v.effective_command}\n", style="green")
        self._body.update(t)


class PDMApp(App):
    """主应用。"""

    CSS = """
    #body { height: 1fr; }
    #commits { width: 36%; border: round $primary; }
    #notes   { width: 28%; border: round $primary; }
    #detail  { width: 1fr;  border: round $primary; padding: 0 1; }
    """

    TITLE = "PDM"
    ICON = "📓"

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("1", "focus_commits", "提交"),
        Binding("2", "focus_notes", "笔记"),
        Binding("3", "focus_detail", "详情"),
        Binding("tab", "focus_next", "下一个", show=False),
        Binding("j", "cursor_down", "下移", show=False),
        Binding("k", "cursor_up", "上移", show=False),
        Binding("R", "refresh", "刷新"),
    ]

    def __init__(self, store, cwd: str = ".", config=None) -> None:
        super().__init__()
        self.store = store
        self.cwd = cwd
        self.config = config
        self.errors: List[str] = []
        self._current: Optional[str] = None

    # --- 布局 ---

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False, icon=self.ICON)
        with Horizontal(id="body"):
            yield CommitList(id="commits")
            yield NoteList(id="notes")
            yield DetailPane(id="detail")
        yield Footer()

    @guard
    def on_mount(self) -> None:
        """启动即加载。

        必须包 guard：``on_mount`` 抛异常同样会被 Textual 判为
        panic 并退出——这正是旧 TUI “启动就挂” 的路径。
        """
        self._reload()
        self.query_one(CommitList).focus()

    # --- 数据 ---

    def _reload(self) -> None:
        """重新加载提交列表并选中第一条。

        注意：这里**故意不裹 guard**，改由调用方（action）负责，
        以便测试直接调用本方法验证异常路径。
        """
        notes = list(self.store.all())
        infos = _git_log(self.cwd)
        entries = core.commit_entries(notes, infos)
        cl = self.query_one(CommitList)
        cl.index = None
        cl.clear()
        for commit, ns, info in entries:
            cl.append(CommitItem(commit, ns, info))
        if entries:
            cl.index = 0
            self._select(entries[0][0])
        else:
            self._select(None)

    def _select(self, commit: Optional[str]) -> None:
        self._current = commit
        nl = self.query_one(NoteList)
        # 先复位 index 再 clear：否则 ListView 会在清空过程中发出
        # 携带旧 item 的 Highlighted 消息，用它把刚写好的详情覆盖掉
        # （曾导致"换提交后详情不更新"）。
        nl.index = None
        nl.clear()
        if commit is None:
            self.query_one(DetailPane).show_note(None, self.cwd)
            return
        notes = _safe_by_commit(self.store, commit)
        for n in notes:
            nl.append(NoteItem(n))
        # 先落详情，再设 index：即使随后收到 Highlighted，
        # 它携带的是同一个 note，结果是幂等的。
        self.query_one(DetailPane).show_note(
            notes[0] if notes else None, self.cwd
        )
        if notes:
            nl.index = 0

    # --- 消息 ---

    @guard
    def on_commit_list_picked(self, message: CommitList.Picked) -> None:
        self._select(message.commit)

    @guard
    def on_note_list_picked(self, message: NoteList.Picked) -> None:
        """笔记高亮变化 → 刷新详情。

        必须校验该 note 是否属于**当前**提交：``NoteList.clear()``
        会触发一个携带旧 item 的 ``Highlighted``，它排在我们写好的
        详情之后到达，不拦就会把详情刷回旧内容
        （曾导致“换提交后详情不更新”）。
        """
        if not _owns(self._current, message.note.commit):
            return
        self.query_one(DetailPane).show_note(message.note, self.cwd)

    # --- actions（全部走 guard） ---

    @guard
    def action_refresh(self) -> None:
        # 走公开 API（rebuild_index 会重新读盘），不碰私有 _load
        self.store.rebuild_index()
        self._reload()
        self.notify("已刷新")

    @guard
    def action_focus_commits(self) -> None:
        self.query_one(CommitList).focus()

    @guard
    def action_focus_notes(self) -> None:
        self.query_one(NoteList).focus()

    @guard
    def action_focus_detail(self) -> None:
        self.query_one(DetailPane).focus()

    @guard
    def action_cursor_down(self) -> None:
        w = self.focused
        if hasattr(w, "action_cursor_down"):
            w.action_cursor_down()

    @guard
    def action_cursor_up(self) -> None:
        w = self.focused
        if hasattr(w, "action_cursor_up"):
            w.action_cursor_up()


# ---------------------------------------------------------------------------
# 无 Textual 依赖的辅助
# ---------------------------------------------------------------------------


def _owns(current: Optional[str], commit: str) -> bool:
    """当前提交是否“拥有”这条笔记（允许 7 位短 hash 对 40 位长 hash）。"""
    if not current or not commit:
        return False
    if current == commit:
        return True
    return (len(current) >= 6 and commit.startswith(current)) or (
        len(commit) >= 6 and current.startswith(commit)
    )


def _git_log(cwd: str) -> list:
    """读 git 历史；失败就当空（非 git 仓库）。"""
    try:
        from ..git import GitRepo

        repo = GitRepo(cwd)
        return list(repo.log()) if repo.available else []
    except Exception:                            # noqa: BLE001
        return []


def _safe_by_commit(store, commit: str) -> list:
    try:
        return list(store.by_commit(commit))
    except Exception:                            # noqa: BLE001
        return [n for n in store.all() if n.commit == commit]


def run(store, cwd: str = ".", config=None) -> int:
    """启动新 TUI。"""
    from .terminal import restore_terminal

    try:
        PDMApp(store, cwd=cwd, config=config).run()
    except KeyboardInterrupt:
        return 130
    finally:
        restore_terminal()
    return 0
