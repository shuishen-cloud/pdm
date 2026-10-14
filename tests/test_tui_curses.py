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
    """纯函数层不得依赖 curses（否则无法脱离终端测试）。"""
    import pdev.tui_curses as m
    import sys

    src = open(m.__file__, encoding="utf-8").read()
    # curses 只能出现在 run() 相关的 IO 层，用延迟导入
    assert "import curses" not in src.split("def run(")[0], \
        "curses 不应在模块顶部导入"


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

    view = build_view(NoteStore(tmp_path / "n"), _NoGit(), Selection())
    assert isinstance(view, CursesView)


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

    monkeypatch.setattr(m, "curses", None)
    assert m.run(store, cwd=".", stdout=_FakeStdout(isatty=True)) == 2


class _FakeStdout:
    def __init__(self, isatty: bool):
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty
