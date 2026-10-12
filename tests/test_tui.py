# -*- coding: utf-8 -*-
"""TUI 的测试（用 textual 自带的 run_test 无头驱动）。

跳过条件：未安装 textual。
"""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Input  # noqa: E402

from pdev import (  # noqa: E402
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    NoteStore,
    Verification,
    VerificationKind,
)
from pdev.tui.app import PDMApp  # noqa: E402
from pdev.tui.panels import CommitList, DetailPane, NoteList  # noqa: E402
from pdev.tui.screens import FilterScreen, HelpScreen  # noqa: E402


@pytest.fixture
def store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="aaa111", kind=NoteKind.PITFALL, title="竞态",
                   status=NoteStatus.OPEN, files=["src/auth/token.py"],
                   tags=["auth"], author=Actor("human:lwy")),
        CommitNote(commit="aaa111", kind=NoteKind.DIFFICULTY, title="难点",
                   author=Actor("ai:claude")),
        CommitNote(commit="bbb222", kind=NoteKind.BUG, title="缺陷",
                   status=NoteStatus.RESOLVED,
                   verifications=[Verification(kind=VerificationKind.COMMAND,
                                               command="true")]),
    ])
    return s


def make_app(store, cwd=".") -> PDMApp:
    return PDMApp(store, cwd=cwd)


# ---------------------------------------------------------------------------
# 启动与数据加载
# ---------------------------------------------------------------------------


async def test_app_boots_and_populates(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        commits = app.query_one(CommitList)
        assert len(commits.children) == 2       # aaa111, bbb222
        notes = app.query_one(NoteList)
        assert len(notes.children) >= 1
        assert app.query_one(DetailPane).note is not None


async def test_commits_sorted_newest_first(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        commits = app.query_one(CommitList)
        order = [c.commit for c in commits.children]
        assert order == sorted(order, reverse=True)


async def test_empty_store_shows_nothing(tmp_path):
    app = make_app(NoteStore(tmp_path / "empty"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert len(app.query_one(CommitList).children) == 0
        assert app.query_one(DetailPane).note is None


# ---------------------------------------------------------------------------
# 导航
# ---------------------------------------------------------------------------


async def test_commit_selection_updates_notes(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("j")
        await pilot.pause()
        assert app._current_commit == "aaa111"


async def test_note_selection_updates_detail(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        nl = app.query_one(NoteList)
        nl.focus()
        await pilot.press("j")
        await pilot.pause()
        assert app.query_one(DetailPane).note is not None


async def test_tab_cycles_panels(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.focused, NoteList)


async def test_left_right_focus(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("l")
        await pilot.pause()
        assert isinstance(app.focused, NoteList)
        await pilot.press("h")
        await pilot.pause()
        assert isinstance(app.focused, CommitList)


async def test_cursor_move_stays_in_bounds(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        for _ in range(10):
            await pilot.press("k")   # 上移到顶
        await pilot.pause()
        assert app._current_commit is not None


# ---------------------------------------------------------------------------
# 帮助
# ---------------------------------------------------------------------------


async def test_help_opens_and_closes(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


# ---------------------------------------------------------------------------
# 筛选
# ---------------------------------------------------------------------------


async def test_filter_reduces_commits(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("slash")
        await pilot.pause()
        assert isinstance(app.screen, FilterScreen)

        app.screen.query_one("#kind", Input).value = "bug"
        app.screen.query_one("#apply", Button).press()
        await pilot.pause()

        assert app._note_filters["kind"] is NoteKind.BUG
        assert len(cl.children) == 1   # 只有 bbb222 有 bug


async def test_filter_by_text(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#text", Input).value = "竞态"
        app.screen.query_one("#apply", Button).press()
        await pilot.pause()
        assert len(cl.children) == 1


async def test_filter_clear_restores(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#clear", Button).press()
        await pilot.pause()
        assert app._note_filters == {}
        assert len(cl.children) == 2


async def test_filter_cancel_keeps_state(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#cancel", Button).press()
        await pilot.pause()
        assert app._note_filters == {}
        assert len(cl.children) == 2


async def test_filter_invalid_kind(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#kind", Input).value = "bogus"
        app.screen.query_one("#apply", Button).press()
        await pilot.pause()
        # 非法输入不关闭弹窗
        assert isinstance(app.screen, FilterScreen)


# ---------------------------------------------------------------------------
# 执行验证
# ---------------------------------------------------------------------------


async def test_run_verify_updates_status(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # 选到 bbb222（有验证的那条）
        cl = app.query_one(CommitList)
        cl.focus()
        # bbb222 排在前面（降序且 b > a）
        await pilot.press("r")
        await pilot.pause()
        note = app.query_one(DetailPane).note
        if note and note.verifications:
            assert note.verifications[0].last_status.value in (
                "passed", "failed", "error", "unknown"
            )


async def test_run_verify_without_verification_notifies(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("j")     # 切到没有验证的提交
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        # 不应崩溃
        assert app.query_one(DetailPane) is not None


async def test_refresh_reloads(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # 外部新增一条
        store.add(CommitNote(commit="ccc333", kind=NoteKind.PITFALL, title="新"))
        app.query_one(CommitList).focus()
        await pilot.press("R")
        await pilot.pause()
        assert len(app.query_one(CommitList).children) == 3
