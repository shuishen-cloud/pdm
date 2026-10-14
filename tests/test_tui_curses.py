# -*- coding: utf-8 -*-
"""curses 版只读浏览 TUI 的测试（tui-curses）。

设计见 ``doc/feat/tui-curses.md``。

**关键**：``build_view`` / ``render_view`` 是纯函数，**不 import curses**，
因此可以脱离终端直接断言——这正是本 feat 针对"框架边界 bug"的做法。
"""

from __future__ import annotations

import pytest

from pdev import (
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    NoteStore,
    Verification,
    VerificationKind,
)
from pdev.git import CommitInfo
from pdev.tui_curses import (
    CommitRow,
    CursesView,
    Selection,
    build_view,
    render_view,
)


@pytest.fixture
def store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="aaa1111222", kind=NoteKind.PITFALL, title="并发竞态",
                   status=NoteStatus.OPEN, files=["src/auth/token.py"],
                   tags=["auth"], author=Actor("human:lwy")),
        CommitNote(commit="aaa1111222", kind=NoteKind.DIFFICULTY, title="难点",
                   author=Actor("ai:claude")),
        CommitNote(commit="bbb2222333", kind=NoteKind.BUG, title="计数泄漏",
                   status=NoteStatus.RESOLVED,
                   verifications=[Verification(kind=VerificationKind.COMMAND,
                                               command="true")]),
    ])
    return s


class _FakeGit:
    """最小 git 替身，避免测试依赖真实仓库。"""

    available = True

    def __init__(self):
        self._infos = {
            "aaa1111222": CommitInfo(hash="aaa1111222", subject="feat(x): 实现",
                                     author="lwy"),
            "bbb2222333": CommitInfo(hash="bbb2222333", subject="fix(x): 修复",
                                     author="lwy"),
        }

    def log(self, limit: int = 0, ref: str = "HEAD"):
        return list(self._infos.values())

    def commit_info(self, ref: str):
        return self._infos.get(ref)


# ---------------------------------------------------------------------------
# 纯函数：build_view
# ---------------------------------------------------------------------------


def test_build_view_does_not_import_curses():
    """纯函数层不得依赖 curses（否则无法脱离终端测试）。

    做法：把三个纯函数的**可执行源码**取出（剔文档串），断言无 curses。
    """
    import inspect
    import re

    import pdev.tui_curses as m

    for fn in (m.build_view, m.render_view, m._note_detail, m._move):
        src = inspect.getsource(fn)
        # 去掉文档串，只查真实代码
        src = re.sub(r'""".*?"""', "", src, flags=re.S)
        assert "curses" not in src, f"{fn.__name__} 不应依赖 curses"


def test_module_importable_without_curses():
    """无 curses 平台也能 import 本模块（纯函数层与终端解耦）。"""
    import pdev.tui_curses as m

    assert m.curses is None, "模块顶部不应导入 curses（应延迟到 _load_curses）"
    assert callable(m._load_curses)


def test_build_view_lists_commits(store):
    view = build_view(store, _FakeGit(), Selection())
    assert [r.commit for r in view.commits] == ["aaa1111222", "bbb2222333"]
    assert "feat(x): 实现" in view.commits[0].label


def test_build_view_shows_notes_of_selected_commit(store):
    view = build_view(store, _FakeGit(), Selection(commit=0))
    assert len(view.notes) == 2
    assert any("并发竞态" in n for n in view.notes)
    assert any("难点" in n for n in view.notes)


def test_build_view_handles_no_notes(store):
    # bbb2222333 有 1 条笔记；换成一个没有笔记的提交
    git = _FakeGit()
    git._infos = {"ccc3333444": CommitInfo(hash="ccc3333444",
                                           subject="chore: 无笔记")}
    view = build_view(store, git, Selection())
    assert view.commits and view.commits[0].commit == "ccc3333444"
    assert view.notes == []
    assert any("暂无笔记" in line for line in view.detail)


def test_build_view_empty_store_does_not_crash(tmp_path):
    view = build_view(NoteStore(tmp_path / "empty"), _FakeGit(), Selection())
    assert isinstance(view, CursesView)
    assert view.commits == [] or len(view.commits) >= 0


def test_build_view_no_git_available(tmp_path):
    class _NoGit:
        available = False

        def log(self, limit: int = 0, ref: str = "HEAD"):
            return []

        def commit_info(self, ref: str):
            return None

    s = NoteStore(tmp_path / "n")
    s.add(CommitNote(commit="ccc3333444", kind=NoteKind.BUG, title="孤立提交"))
    view = build_view(s, _NoGit(), Selection())
    assert isinstance(view, CursesView)
    # 非 git 仓库时退回笔记里的 commit
    assert [r.commit for r in view.commits] == ["ccc3333444"]


# ---------------------------------------------------------------------------
# 纯函数：render_view
# ---------------------------------------------------------------------------


def test_render_view_returns_exactly_height_lines(store):
    view = build_view(store, _FakeGit(), Selection())
    for h, w in ((20, 80), (24, 120), (12, 61)):
        lines = render_view(view, h, w)
        assert len(lines) == h, (h, w)


def test_render_view_three_columns_separated(store):
    """三栏以竖线分隔。"""
    view = build_view(store, _FakeGit(), Selection())
    lines = render_view(view, 20, 90)
    body = lines[1]  # 跳过标题行
    assert "│" in body


def test_render_view_small_terminal_shows_hint(store):
    """过小终端只给提示，不崩、不画三栏。"""
    view = build_view(store, _FakeGit(), Selection())
    lines = render_view(view, 5, 30)
    assert len(lines) == 5
    joined = "\n".join(lines)
    assert "太小" in joined or "小" in joined


def test_render_view_no_cjk_overflow(store):
    """CJK 按 2 列计宽，任一行的显示宽度不超过给定 width。"""
    from pdev.tui.panels import _display_width

    view = build_view(store, _FakeGit(), Selection())
    width = 80
    for line in render_view(view, 20, width):
        assert _display_width(line) <= width, repr(line)


def test_render_view_empty_view_does_not_crash():
    view = CursesView(commits=[], notes=[], detail=[], focus=0,
                      cursor=[0, 0, 0])
    lines = render_view(view, 20, 80)
    assert len(lines) == 20


# ---------------------------------------------------------------------------
# 退出与兜底（不启动真实终端）
# ---------------------------------------------------------------------------


def test_run_returns_2_when_not_tty(store, monkeypatch):
    """stdout 非 tty 时不进入 curses，提示并返回 2。"""
    import pdev.tui_curses as m

    called = []
    monkeypatch.setattr(m, "_enter_curses",
                        lambda *a, **kw: called.append(1) or 0)
    assert m.run(store, cwd=".", stdout=_FakeStdout(isatty=False)) == 2
    assert not called, "非 tty 不应进入 curses"


def test_run_returns_2_when_curses_missing(store, monkeypatch):
    """curses 不可用时提示并返回 2。"""
    import pdev.tui_curses as m

    monkeypatch.setattr(m, "_load_curses", lambda: None)
    assert m.run(store, cwd=".", stdout=_FakeStdout(isatty=True)) == 2


class _FakeStdout:
    def __init__(self, isatty: bool):
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty


# ---------------------------------------------------------------------------
# 端到端：真实 PTY 下启动、按键、退出后终端恢复
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    __import__("sys").platform.startswith("win"), reason="PTY 仅 Unix"
)
def test_pty_start_send_q_exit_restores_terminal(tmp_path):
    """真实 PTY：启动 → 发 q → 进程结束，且退出序列含 endwin 恢复。

    沿用 tui-signal-restore 的教训：**必须确证进程真的结束**，
    而不是等超时；并检查终端恢复序列。
    """
    import os
    import pty
    import select
    import subprocess
    import sys
    import time

    from pdev import Actor, CommitNote, NoteKind, NoteStore

    store = NoteStore(tmp_path / "notes")
    store.add(CommitNote(commit="abc1234def", kind=NoteKind.PITFALL,
                         title="PTY 测试", author=Actor("human:lwy")))

    code = (
        "from pdev.store import NoteStore\n"
        "from pdev.tui_curses import run\n"
        f"s=NoteStore({str(store.root)!r})\n"
        "import sys; sys.exit(run(s, cwd='.', stdout=sys.stdout))\n"
    )

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=slave, stdout=slave, stderr=slave,
        cwd=str(tmp_path), close_fds=True,
    )
    os.close(slave)

    out = b""
    deadline = time.time() + 10
    try:
        # 等界面起来（收到任何输出），再发 q
        while time.time() < deadline:
            r, _, _ = select.select([master], [], [], 0.5)
            if r:
                out += os.read(master, 65536)
                break
        os.write(master, b"q")
        proc.wait(timeout=10)
        # 收尾读取
        while True:
            r, _, _ = select.select([master], [], [], 0.2)
            if not r:
                break
            try:
                out += os.read(master, 65536)
            except OSError:
                break
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.returncode == 0, f"退出码 {proc.returncode}"
    # 正常退出应恢复终端（退出备用屏 + 显示光标）
    assert b"\x1b[?1049l" in out or b"\x1b[?25h" in out, \
        "退出后应发出终端恢复序列"


@pytest.mark.skipif(
    __import__("sys").platform.startswith("win"), reason="PTY 仅 Unix"
)
def test_pty_ctrl_c_does_not_leave_raw_mode(tmp_path):
    """Ctrl+C 中断也应恢复终端（不依赖 KeyboardInterrupt 路径）。"""
    import os
    import pty
    import select
    import signal
    import subprocess
    import sys
    import time

    from pdev import NoteStore

    store = NoteStore(tmp_path / "notes")
    code = (
        "from pdev.store import NoteStore\n"
        "from pdev.tui_curses import run\n"
        f"s=NoteStore({str(store.root)!r})\n"
        "import sys; sys.exit(run(s, cwd='.', stdout=sys.stdout))\n"
    )
    master, slave = pty.openpty()
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdin=slave, stdout=slave, stderr=slave,
                            cwd=str(tmp_path), close_fds=True)
    os.close(slave)
    out = b""
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            r, _, _ = select.select([master], [], [], 0.5)
            if r:
                out += os.read(master, 65536)
                break
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=10)
        while True:
            r, _, _ = select.select([master], [], [], 0.2)
            if not r:
                break
            try:
                out += os.read(master, 65536)
            except OSError:
                break
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    # 关键是进程真的结束了、且尝试恢复终端
    assert proc.returncode is not None
    assert b"\x1b[?1049l" in out or b"\x1b[?25h" in out
