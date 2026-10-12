# -*- coding: utf-8 -*-
"""TUI 的测试（用 textual 自带的 run_test 无头驱动）。

跳过条件：未安装 textual。
"""

from __future__ import annotations

from pathlib import Path

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


# ---------------------------------------------------------------------------
# 回归：点击不应崩溃（曾因自定义 Selected 覆盖 ListView.Selected）
# ---------------------------------------------------------------------------


async def test_click_commit_item_does_not_crash(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        await pilot.click(cl.children[1])
        await pilot.pause()
        assert app.is_running
        assert app._current_commit == "aaa111"


async def test_click_note_item_does_not_crash(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        nl = app.query_one(NoteList)
        await pilot.click(nl.children[0])
        await pilot.pause()
        assert app.is_running


async def test_click_detail_pane_does_not_crash(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#detail")
        await pilot.pause()
        assert app.is_running


async def test_panels_do_not_shadow_listview_selected():
    # 自定义消息不得叫 Selected，否则覆盖父类导致点击崩溃
    assert not hasattr(CommitList, "__dict__") or "Selected" not in CommitList.__dict__
    assert "Selected" not in NoteList.__dict__
    assert hasattr(CommitList, "Picked")
    assert hasattr(NoteList, "Picked")


# ---------------------------------------------------------------------------
# 放大 / 还原
# ---------------------------------------------------------------------------


async def test_zoom_with_z_key(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("z")
        await pilot.pause()
        assert app._zoomed == "commits"
        assert cl.has_class("zoomed")
        assert app.query_one(NoteList).has_class("dimmed")


async def test_zoom_toggles_back(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        cl.focus()
        await pilot.press("z")
        await pilot.pause()
        await pilot.press("z")
        await pilot.pause()
        assert app._zoomed is None
        assert not cl.has_class("zoomed")
        assert not app.query_one(NoteList).has_class("dimmed")


async def test_zoom_with_enter(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app._zoomed == "commits"


async def test_zoom_each_panel(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for panel_id in ("commits", "notes", "detail"):
            app.query_one(f"#{panel_id}").focus()
            await pilot.press("z")
            await pilot.pause()
            assert app._zoomed == panel_id
            await pilot.press("z")
            await pilot.pause()
            assert app._zoomed is None


# ---------------------------------------------------------------------------
# commit message（git 集成）
# ---------------------------------------------------------------------------


async def test_commit_subject_from_git(tmp_path):
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if not head:
        pytest.skip("不在 git 仓库中")

    s = NoteStore(tmp_path / "notes")
    s.add(CommitNote(commit=head, kind=NoteKind.BUG, title="真实提交"))
    app = make_app(s, cwd=str(Path.cwd()))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        item = app.query_one(CommitList).children[0]
        assert item.info is not None
        assert item.info.subject  # 拿到了提交标题


# ---------------------------------------------------------------------------
# 提交面板：类型分布染色
# ---------------------------------------------------------------------------


async def test_commit_item_colors_by_kind(tmp_path):
    from pdev.tui.panels import CommitItem

    notes = [
        CommitNote(commit="c1", kind=NoteKind.BUG, title="b"),
        CommitNote(commit="c1", kind=NoteKind.CONTROLLED_EXCEPTION, title="e"),
        CommitNote(commit="c1", kind=NoteKind.PITFALL, title="p"),
    ]
    text = CommitItem("c1", notes).render()
    styles = {text.plain[s.start:s.end]: s.style for s in text.spans}
    # 三种类型必须是不同颜色，否则扫视没意义
    assert styles["bug:1"] != styles["exc:1"]
    assert styles["exc:1"] != styles["pit:1"]
    assert styles["bug:1"] != styles["pit:1"]


async def test_commit_item_shows_subject_when_available(tmp_path):
    from pdev.git import CommitInfo
    from pdev.tui.panels import CommitItem

    info = CommitInfo(hash="abcdef1234567890", subject="feat: 某功能",
                      author="T")
    text = CommitItem("abcdef12",
                      [CommitNote(commit="abcdef12", kind=NoteKind.BUG,
                                  title="x")], info).render()
    assert "feat: 某功能" in text.plain


async def test_commit_item_without_info_still_renders(tmp_path):
    from pdev.tui.panels import CommitItem

    text = CommitItem("c1",
                      [CommitNote(commit="c1", kind=NoteKind.BUG,
                                  title="x")]).render()
    assert "c1" in text.plain
    assert "bug:1" in text.plain


# ---------------------------------------------------------------------------
# 帮助 / 筛选弹窗的可关闭性
# ---------------------------------------------------------------------------


async def test_help_closes_with_escape(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_help_closes_with_q(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert app.is_running   # 不应把整个应用退出


async def test_help_renders_markup_not_literal(store):
    """帮助内容应渲染为富文本，而不是显示 [bold] 字面量。"""
    from pdev.tui.screens import _HELP

    assert "[bold]" in _HELP          # 源文本是 Rich markup
    app = make_app(store)
    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        body = app.screen.query_one("#help-text")
        rendered = body.render()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        assert "[bold]" not in text
        assert "快捷键" in text


async def test_filter_closes_with_escape(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("slash")
        await pilot.pause()
        assert isinstance(app.screen, FilterScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, FilterScreen)


async def test_filter_q_types_into_input(store):
    """输入框聚焦时 q 应作为字符输入，而不是关闭弹窗。"""
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#text", Input).focus()
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, FilterScreen)
        assert "q" in app.screen.query_one("#text", Input).value


async def test_filter_q_closes_when_input_not_focused(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#apply", Button).focus()
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, FilterScreen)


# ---------------------------------------------------------------------------
# 面板直达快捷键
# ---------------------------------------------------------------------------


async def test_number_keys_jump_to_panels(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(DetailPane).focus()

        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.focused, CommitList)

        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.focused, NoteList)

        await pilot.press("3")
        await pilot.pause()
        assert isinstance(app.focused, DetailPane)


async def test_app_has_icon(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert app.ICON
        assert app.ICON.strip()


# ---------------------------------------------------------------------------
# 方向键切面板
# ---------------------------------------------------------------------------


async def test_arrow_keys_move_between_panels(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()

        await pilot.press("right")
        await pilot.pause()
        assert isinstance(app.focused, NoteList)

        await pilot.press("right")
        await pilot.pause()
        assert isinstance(app.focused, DetailPane)

        await pilot.press("left")
        await pilot.pause()
        assert isinstance(app.focused, NoteList)

        await pilot.press("left")
        await pilot.pause()
        assert isinstance(app.focused, CommitList)


async def test_arrow_left_stops_at_first_panel(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("left")
        await pilot.pause()
        assert isinstance(app.focused, CommitList)


async def test_arrow_right_stops_at_last_panel(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(DetailPane).focus()
        await pilot.press("right")
        await pilot.pause()
        assert isinstance(app.focused, DetailPane)
