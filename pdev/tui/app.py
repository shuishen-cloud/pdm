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
        Binding("f", "show_feats", "Feat"),
        Binding("t", "cycle_theme", "主题", show=False),
        Binding("T", "pick_theme", "选主题", show=False),
        Binding("question_mark", "help", "帮助"),
    ]

    # 命令面板：Ctrl+P 或 p 唤起，可搜索本应用的动作
    COMMANDS = App.COMMANDS | {PDMCommands}

    def __init__(self, store: NoteStore, cwd: str = ".",
                 config=None, config_path=None) -> None:
        super().__init__()
        self.store = store
        self.cwd = cwd
        self.config = config
        self.config_path = config_path          # 写回时用；None 则自动找
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
        self._apply_theme(self._configured_theme())
        self._reload_commits()
        self.query_one(CommitList).focus()

    # --- 设置（主题等） ---

    def _configured_theme(self) -> str:
        """配置里指定的主题名（无效则回退默认）。"""
        name = getattr(getattr(self.config, "ui", None), "theme", None)
        if name and name in self.available_themes:
            return name
        return "catppuccin-macchiato"

    def _apply_theme(self, name: str) -> None:
        """切换主题（无效名静默忽略）。"""
        if name in self.available_themes:
            self.theme = name

    def action_cycle_theme(self) -> None:
        """循环切换内置主题并持久化。"""
        names = sorted(self.available_themes)
        if not names:
            return
        try:
            cur = names.index(self.theme)
        except ValueError:
            cur = -1
        nxt = names[(cur + 1) % len(names)]
        self.theme = nxt
        saved = self._persist_ui("theme", nxt)
        msg = f"主题：{nxt}"
        if saved:
            msg += f"  (已保存到 {saved})"
        self.notify(msg)

    def action_pick_theme(self) -> None:
        """弹出主题选择器（可搜索全部内置主题）。"""
        from .screens import ThemeScreen

        def apply(name: str | None) -> None:
            if not name:
                return
            self.theme = name
            saved = self._persist_ui("theme", name)
            msg = f"主题：{name}"
            if saved:
                msg += f"  (已保存)"
            self.notify(msg)

        self.push_screen(ThemeScreen(self.theme), apply)

    def _persist_ui(self, key: str, value) -> str | None:
        """把 UI 偏好写回**用户配置**（~/.config/pdm/config.json）。

    主题/列宽等是个人口味，不能写项目 ``.pdm.json``（会被 git 冲掉）。
    返回路径（失败返回 None）。
        """
        try:
            from ..config import save_user_config

            path = save_user_config({"ui": {key: value}})
        except Exception as e:            # 写不了不能影响使用
            self.notify(f"保存设置失败：{e}", severity="warning")
            return None
        if self.config is not None and hasattr(self.config, "ui"):
            setattr(self.config.ui, key, value)
        return str(path)

    # --- 数据加载 ---

    def _reload_commits(self) -> None:
        """重新加载提交列表。

        提交来源：

        - 有笔记的提交（笔记驱动的顺序，兼容非 git 仓库）
        - git 历史里的全部提交（即使没有笔记也显示，笔记为空）

        两者按 git 顺序合并；不在 git 里的伪造 hash 也会保留。
        """
        notes = list(self.store.all())
        notes = self._apply_filters(notes)

        # git 历史：新→旧，包含无笔记的提交
        git_infos = self.git.log() if self.git.available else []
        order = [info.hash for info in git_infos]
        info_by_hash = {info.hash: info for info in git_infos}

        # 笔记按 commit 归入对应的 git 提交（前缀互匹配：
        # 笔记常存 7 位短 hash，git 给 40 位）
        def _pick(commit: str) -> list:
            return [n for n in notes
                    if n.commit == commit
                    or (len(commit) >= 6 and n.commit.startswith(commit))
                    or (len(n.commit) >= 6 and commit.startswith(n.commit))]

        claimed: set = set()
        entries: list = []
        for h in order:
            ns = _pick(h)
            claimed.update(id(n) for n in ns)
            entries.append((h, ns, info_by_hash[h]))

        # 不在 git 历史里的（伪造 hash 或非 git 仓库）
        extra: dict = {}
        for n in notes:
            if id(n) not in claimed:
                extra.setdefault(n.commit, []).append(n)
        for c in sorted(extra, reverse=True):
            entries.append((c, extra[c], None))

        # 已筛选时只保留命中的提交；未筛选时展示全部 git 历史
        if self._note_filters:
            entries = [(c, ns, info) for c, ns, info in entries if ns]

        cl = self.query_one(CommitList)
        cl.load(entries)
        commits = [c for c, _, _ in entries]
        if commits:
            self._select_commit(commits[0])
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

    def action_show_feats(self) -> None:
        """打开 Feat 面板（开发记录 + 自约束校验）。"""
        from pathlib import Path

        from ..feat import FeatStore
        from .screens import FeatScreen

        root = ".pdm/feats"
        cfg = getattr(self.config, "feat", None)
        if cfg is not None:
            root = getattr(cfg, "store", ".pdm/feats") or ".pdm/feats"
        doc_dir = ".pdm/docs"
        dcfg = getattr(self.config, "doc", None)
        if dcfg is not None:
            doc_dir = getattr(dcfg, "dir", ".pdm/docs") or ".pdm/docs"
        path = Path(root)
        if not path.is_absolute():
            path = Path(self.cwd) / path
        view = getattr(cfg, "view", None) if cfg is not None else None
        self.push_screen(FeatScreen(FeatStore(path), self.git, self.store,
                                    doc_dir=doc_dir, view=view))


def _restore_terminal(stream=None) -> None:
    """把终端恢复到正常模式（幂等、非 tty 安全）。

    Textual 的 ``stop_application_mode()`` 会写这些序列，但当 ``asyncio.run``
    被 SIGINT 硬中断（KeyboardInterrupt）时，其 ``_shutdown`` 可能来不及完成，
    导致终端留在备用屏/raw mode，出现乱码。本函数作为**无条件的兜底**，
    在 ``run()`` 的 finally 中调用。

    :param stream: 输出流，默认 ``sys.stdout``。非 tty 时什么都不写。
    """
    import sys

    out = stream if stream is not None else sys.stdout
    try:
        if not out.isatty():
            return
    except Exception:  # noqa: BLE001
        return

    # 关鼠标 / kitty 键盘协议 / 退出备用屏 / 显示光标 / 关 FocusIn-Out、粘贴
    seq = (
        "\x1b[?1000l"    # 关 VT200 鼠标
        "\x1b[?1003l"    # 关 all-motion 鼠标
        "\x1b[?1015l"    # 关 urxvt 鼠标
        "\x1b[?1006l"    # 关 SGR 鼠标
        "\x1b[<u"        # 关 kitty 键盘协议
        "\x1b[?1049l"    # 退出备用屏
        "\x1b[?25h"      # 显示光标
        "\x1b[?1004l"    # 关 FocusIn/FocusOut
        "\x1b[?2004l"    # 关 bracketed paste
    )
    try:
        out.write(seq)
        out.flush()
    except Exception:  # noqa: BLE001
        pass

    # 深度兜底：stty sane（无 tty 或 stty 缺失则跳过）
    try:
        import subprocess

        subprocess.run(
            ["stty", "sane"],
            stdin=out,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except Exception:  # noqa: BLE001
        pass


def run(store: NoteStore, cwd: str = ".", config=None,
        config_path=None) -> int:
    """启动 TUI；保证任何退出路径都恢复终端。

    Ctrl+C（KeyboardInterrupt）视为正常退出，返回 130；
    其余异常照常传播（finally 仍会恢复终端）。
    """
    try:
        PDMApp(store, cwd=cwd, config=config,
               config_path=config_path).run()
    except KeyboardInterrupt:
        return 130
    finally:
        # 正常退出时 Textual 已恢复，这里重复写一次是无害的（幂等）；
        # Ctrl+C / 异常时这一句才是关键。
        _restore_terminal()
    return 0
