# -*- coding: utf-8 -*-
"""ProjectDevelopManager 的 TUI（仿 lazygit 布局）。

三个面板：
- 左侧：提交列表（有笔记的 commit）
- 中左：选中提交的笔记列表
- 右侧：笔记详情（含验证方法与脚本）

底部为状态栏与快捷键提示。

启动::

    pdm ui
    python3 main.py ui --store demo-notes
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from ..store import NoteStore
from .commands import PDMCommands
from .panels import CommitList, DetailPane, NoteList
from .screens import FilterScreen, HelpScreen

__all__ = ["PDMApp", "run"]


class PDMApp(App):
    """主应用。"""

    CSS_PATH = "app.tcss"
    TITLE = "ProjectDevelopManager"
    # 左上角标志（Header 会以背景色高亮显示）
    ICON = "📓"

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("tab", "focus_next", "下一个面板", show=False),
        Binding("shift+tab", "focus_previous", "上一个面板", show=False),
        Binding("1", "focus_commits", "提交"),
        Binding("2", "focus_notes", "笔记"),
        Binding("3", "focus_detail", "详情"),
        Binding("h", "focus_left", "左移", show=False),
        Binding("l", "focus_right", "右移", show=False),
        Binding("left", "focus_left", "左移", show=False),
        Binding("right", "focus_right", "右移", show=False),
        Binding("j", "cursor_down", "下移", show=False),
        Binding("k", "cursor_up", "上移", show=False),
        Binding("enter", "toggle_zoom", "放大/还原"),
        Binding("z", "toggle_zoom", "放大/还原", show=False),
        Binding("slash", "filter", "筛选"),
        Binding("r", "run_verify", "跑验证"),
        Binding("R", "refresh", "刷新"),
        Binding("p", "command_palette", "命令"),
        Binding("question_mark", "help", "帮助"),
    ]

    # 命令面板：Ctrl+P 或 p 唤起，可搜索本应用的动作
    COMMANDS = App.COMMANDS | {PDMCommands}

    def __init__(self, store: NoteStore, cwd: str = ".") -> None:
        super().__init__()
        self.store = store
        self.cwd = cwd
        self._note_filters: dict = {}
        self._current_commit: str | None = None
        self._zoomed: str | None = None      # 被放大的面板 id
        from ..git import GitRepo

        self.git = GitRepo(cwd)

    # --- 布局 ---

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, icon=self.ICON)
        from textual.containers import Horizontal

        with Horizontal(id="main"):
            yield CommitList(id="commits")
            yield NoteList(id="notes")
            yield DetailPane(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"store: {self.store.root}"
        if not self.git.available:
            self.sub_title += "  (非 git 仓库)"
        self._reload_commits()
        self.query_one(CommitList).focus()

    # --- 数据加载 ---

    def _reload_commits(self) -> None:
        """重新加载提交列表（按笔记过滤条件）。"""
        notes = list(self.store.all())
        notes = self._apply_filters(notes)

        grouped: dict[str, list] = {}
        for n in notes:
            grouped.setdefault(n.commit, []).append(n)

        commits = sorted(grouped.items(), reverse=True)

        # 从 git 补齐 commit message
        infos = {}
        if self.git.available and commits:
            infos = self.git.commit_infos([c for c, _ in commits])

        cl = self.query_one(CommitList)
        cl.load([(c, ns, infos.get(c)) for c, ns in commits])
        if commits:
            self._select_commit(commits[0][0])
        else:
            self._select_commit(None)

    def _apply_filters(self, notes: list) -> list:
        """应用当前筛选条件。"""
        f = self._note_filters
        if not f:
            return notes
        from ..doc import match_glob

        out = []
        for n in notes:
            if f.get("kind") and n.kind is not f["kind"]:
                continue
            if f.get("status") and n.status is not f["status"]:
                continue
            if f.get("file") and not any(
                match_glob(f["file"], p) for p in n.files
            ):
                continue
            if f.get("text"):
                needle = f["text"].lower()
                hay = " ".join(
                    [n.title, n.detail, *n.tags, *n.catches]
                ).lower()
                if needle not in hay:
                    continue
            out.append(n)
        return out

    def _select_commit(self, commit: str | None) -> None:
        """选中某提交，刷新笔记列表与详情。"""
        self._current_commit = commit
        if commit is None:
            self.query_one(NoteList).load([])
            self.query_one(DetailPane).show_note(None, self.cwd)
            return
        notes = self.store.by_commit(commit)
        info = self.git.commit_info(commit) if self.git.available else None
        self.query_one(NoteList).load(notes)
        self.query_one(DetailPane).show_note(
            notes[0] if notes else None, self.cwd, commit_info=info
        )

    # --- 事件 ---

    def on_commit_list_picked(self, message: CommitList.Picked) -> None:
        self._select_commit(message.commit)

    def on_note_list_picked(self, message: NoteList.Picked) -> None:
        info = None
        if self.git.available and self._current_commit:
            info = self.git.commit_info(self._current_commit)
        self.query_one(DetailPane).show_note(message.note, self.cwd,
                                             commit_info=info)

    # --- 动作 ---

    def action_focus_left(self) -> None:
        self._shift_focus(-1)

    def action_focus_right(self) -> None:
        self._shift_focus(1)

    def action_focus_commits(self) -> None:
        """1：直接跳到提交面板（左上）。"""
        self.query_one(CommitList).focus()

    def action_focus_notes(self) -> None:
        """2：跳到笔记面板。"""
        self.query_one(NoteList).focus()

    def action_focus_detail(self) -> None:
        """3：跳到详情面板。"""
        self.query_one(DetailPane).focus()

    def _panel_widgets(self) -> list:
        return [
            self.query_one(CommitList),
            self.query_one(NoteList),
            self.query_one(DetailPane),
        ]

    def _shift_focus(self, delta: int) -> None:
        panels = self._panel_widgets()
        current = self.focused
        try:
            idx = panels.index(current)
        except ValueError:
            idx = 0
        new = max(0, min(len(panels) - 1, idx + delta))
        panels[new].focus()

    def action_cursor_down(self) -> None:
        w = self.focused
        if hasattr(w, "action_cursor_down"):
            w.action_cursor_down()

    def action_cursor_up(self) -> None:
        w = self.focused
        if hasattr(w, "action_cursor_up"):
            w.action_cursor_up()

    def action_refresh(self) -> None:
        self.store._load()
        self._reload_commits()
        self.notify("已刷新")

    def action_toggle_zoom(self) -> None:
        """把当前面板放大到整宽，再按一次还原。"""
        focused = self.focused
        if focused is None:
            return
        panel_id = focused.id
        if panel_id not in ("commits", "notes", "detail"):
            # 焦点在输入框等控件时，直接放大焦点所在面板
            for pid in ("commits", "notes", "detail"):
                if focused in self.query_one(f"#{pid}").ancestors:
                    panel_id = pid
                    break
            else:
                return

        for pid in ("commits", "notes", "detail"):
            widget = self.query_one(f"#{pid}")
            widget.remove_class("zoomed")
            widget.add_class("dimmed")

        if self._zoomed == panel_id:
            # 还原
            self._zoomed = None
            for pid in ("commits", "notes", "detail"):
                self.query_one(f"#{pid}").remove_class("dimmed")
            self.notify("已还原")
        else:
            self._zoomed = panel_id
            widget = self.query_one(f"#{panel_id}")
            widget.remove_class("dimmed")
            widget.add_class("zoomed")
            widget.focus()
            self.notify(f"已放大：{panel_id}")

    def action_filter(self) -> None:
        def apply(result: dict | None) -> None:
            # None = 取消（保持原状）；{} = 清除
            if result is None:
                return
            self._note_filters = result
            self._reload_commits()
            if result:
                self.notify(f"筛选：{self._describe_filters()}")
            else:
                self.notify("已清除筛选")

        self.push_screen(FilterScreen(self._note_filters), apply)

    def _describe_filters(self) -> str:
        return " ".join(f"{k}={v}" for k, v in self._note_filters.items())

    def action_run_verify(self) -> None:
        """弹出验证过程窗口并执行。"""
        from .screens import VerifyScreen

        note = self.query_one(DetailPane).note
        if note is None or not note.runnable_verifications:
            self.notify("当前笔记没有可执行的验证", severity="warning")
            return

        def after(_result) -> None:
            # 回写结果并刷新详情
            self.store.update(note)
            self.query_one(DetailPane).show_note(note, self.cwd)

        self.push_screen(VerifyScreen(note, cwd=self.cwd), after)

    def action_help(self) -> None:
        self.push_screen(HelpScreen())


def run(store: NoteStore, cwd: str = ".") -> int:
    """启动 TUI。"""
    PDMApp(store, cwd=cwd).run()
    return 0
