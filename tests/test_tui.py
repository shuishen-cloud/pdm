# -*- coding: utf-8 -*-
"""TUI 的测试（用 textual 自带的 run_test 无头驱动）。

跳过条件：未安装 textual。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Input  # noqa: E402

from pdev import (  # noqa: E402
    Actor,
    CommitNote,
    Config,
    NoteKind,
    NoteStatus,
    NoteStore,
    Verification,
    VerificationKind,
)
from pdev.git import GitRepo  # noqa: E402
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


def make_app(store, cwd=None) -> PDMApp:
    """构造测试用 app。

    ``cwd`` 默认取 store 根目录所在处：那里通常不是 git 仓库，
    避免测试意外读到本仓库自身的 git 历史。
    """
    if cwd is None:
        cwd = str(Path(store.root).parent)
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
        await pilot.press("enter")
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
        await pilot.press("enter")
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
        await pilot.press("ctrl+l")
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
        await pilot.press("escape")
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
        await pilot.press("enter")
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


async def test_filter_q_types_into_input_not_close(store):
    """筛选弹窗里 q 是正常输入（因为焦点总在输入框），不会误关。"""
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


async def test_filter_esc_cancels(store):
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("slash")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, FilterScreen)


async def test_filter_esc_keeps_existing_filters(store):
    """Esc 取消不应清掉已有筛选。"""
    app = make_app(store)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        # 先应用一个筛选
        await pilot.press("slash")
        await pilot.pause()
        app.screen.query_one("#kind", Input).value = "bug"
        await pilot.press("enter")
        await pilot.pause()
        assert app._note_filters.get("kind") is NoteKind.BUG

        # 再打开并 Esc 取消
        await pilot.press("slash")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app._note_filters.get("kind") is NoteKind.BUG


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


# ---------------------------------------------------------------------------
# 语法高亮
# ---------------------------------------------------------------------------


def test_highlight_python_produces_colored_spans():
    from pdev.tui.panels import _highlight_python

    code = "def f():\n    x = 1\n    return x\n"
    text = _highlight_python(code)
    assert "def" in text.plain
    # 至少有若干带颜色的 span
    colored = [s for s in text.spans if s.style]
    assert len(colored) >= 3
    assert any("def" in text.plain[s.start:s.end] for s in text.spans)


def test_highlight_python_applies_indent():
    from pdev.tui.panels import _highlight_python

    text = _highlight_python("x = 1\ny = 2\n", indent="    │ ")
    for line in text.plain.splitlines():
        assert line.startswith("    │ ")


def test_highlight_python_handles_empty_and_bad_code():
    from pdev.tui.panels import _highlight_python

    assert _highlight_python("").plain == ""
    # 语法错误也不应抛异常
    out = _highlight_python("def broken(:\n    pass\n")
    assert "broken" in out.plain


# ---------------------------------------------------------------------------
# 验证过程弹窗
# ---------------------------------------------------------------------------


async def test_verify_screen_shows_results(tmp_path):
    from pdev import Verification, VerificationKind
    from pdev.tui.screens import VerifyScreen

    note = CommitNote(
        commit="c1", kind=NoteKind.BUG, title="t",
        verifications=[
            Verification(kind=VerificationKind.COMMAND, command="true",
                         method="总是通过"),
            Verification(kind=VerificationKind.COMMAND, command="false",
                         method="总是失败"),
        ],
    )
    s = NoteStore(tmp_path / "notes")
    s.add(note)
    app = make_app(s)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.push_screen(VerifyScreen(note, cwd=str(tmp_path)))
        await pilot.pause()
        assert isinstance(app.screen, VerifyScreen)

        # 等执行完成
        for _ in range(100):
            await pilot.pause()
            if app.screen._done:
                break
        assert app.screen._done
        body = app.screen.query_one("#verify-list").render()
        text = body.plain if hasattr(body, "plain") else str(body)
        assert "true" in text
        assert "false" in text
        assert "通过" in text and "失败" in text


async def test_verify_screen_esc_only_after_done(tmp_path):
    from pdev import Verification, VerificationKind
    from pdev.tui.screens import VerifyScreen

    note = CommitNote(
        commit="c1", kind=NoteKind.BUG, title="t",
        verifications=[Verification(kind=VerificationKind.COMMAND,
                                    command="true")],
    )
    s = NoteStore(tmp_path / "notes")
    s.add(note)
    app = make_app(s)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.push_screen(VerifyScreen(note, cwd=str(tmp_path)))
        for _ in range(100):
            await pilot.pause()
            if app.screen._done:
                break
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, VerifyScreen)


async def test_run_verify_opens_verify_screen(tmp_path):
    from pdev import Verification, VerificationKind

    s = NoteStore(tmp_path / "notes")
    s.add(CommitNote(
        commit="c1", kind=NoteKind.BUG, title="带验证",
        verifications=[Verification(kind=VerificationKind.COMMAND,
                                    command="true")],
    ))
    app = make_app(s)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.query_one(CommitList).focus()
        await pilot.press("r")
        await pilot.pause()
        from pdev.tui.screens import VerifyScreen
        assert isinstance(app.screen, VerifyScreen)


# ---------------------------------------------------------------------------
# 命令面板
# ---------------------------------------------------------------------------


async def test_command_palette_opens_with_p(store):
    from textual.command import CommandPalette

    app = make_app(store)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


async def test_pdm_commands_registered(store):
    from pdev.tui.commands import PDMCommands

    assert PDMCommands in PDMApp.COMMANDS


async def test_pdm_provider_lists_actions(store):
    from pdev.tui.commands import PDMCommands

    app = make_app(store)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        provider = next(
            (p for p in app.screen._providers if isinstance(p, PDMCommands)),
            None,
        )
        assert provider is not None
        names = [hit.text async for hit in provider.discover()]
        assert "提交面板" in names
        assert "跑验证" in names
        assert "退出" in names


async def test_pdm_provider_search(store):
    from pdev.tui.commands import PDMCommands

    app = make_app(store)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        provider = next(
            (p for p in app.screen._providers if isinstance(p, PDMCommands)),
            None,
        )
        hits = [hit.text async for hit in provider.search("验证")]
        assert "跑验证" in hits
        assert [hit.text async for hit in provider.search("zzz")] == []


# ---------------------------------------------------------------------------
# 接入 git：没有笔记的提交也要显示
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    """一个有两次提交、但没有任何笔记的仓库。"""
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "Tester")
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "first: 初始")
    (tmp_path / "b.txt").write_text("yo", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "second: 第二次")
    return tmp_path


async def test_git_only_commits_are_listed(git_repo, tmp_path):
    """仓库有提交但笔记为空时，提交列表仍展示 git 历史。"""
    s = NoteStore(tmp_path / "notes")
    app = make_app(s, cwd=str(git_repo))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        assert len(cl.children) == 2
        subjects = [c.info.subject for c in cl.children if c.info]
        assert "second: 第二次" in subjects
        assert "first: 初始" in subjects


async def test_git_only_commit_selects_empty_notes(git_repo, tmp_path):
    """选中无笔记的提交：笔记列表为空，详情提示无笔记。"""
    s = NoteStore(tmp_path / "notes")
    app = make_app(s, cwd=str(git_repo))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert len(app.query_one(NoteList).children) == 0
        pane = app.query_one(DetailPane)
        rendered = pane._build(pane.note, str(git_repo), pane.commit_info)
        assert "暂无笔记" in rendered.plain
        # 提交标题仍应展示
        assert "second: 第二次" in rendered.plain


async def test_git_and_notes_merged(git_repo, tmp_path):
    """有笔记的提交与纯 git 提交按 git 顺序合并展示。"""
    from pdev import Actor, NoteKind, NoteStatus

    s = NoteStore(tmp_path / "notes")
    # 取 git 里较老的那次提交挂一条笔记
    r = GitRepo(str(git_repo))
    oldest = r.log()[-1].hash
    s.add(CommitNote(commit=oldest, kind=NoteKind.PITFALL, title="坑",
                     author=Actor("human:lwy"), status=NoteStatus.NOTED))

    app = make_app(s, cwd=str(git_repo))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        # 两次提交都在，顺序为新→旧
        assert len(cl.children) == 2
        assert cl.children[0].commit == r.log()[0].hash
        assert cl.children[1].commit == oldest
        # 老提交带着 1 条笔记，新提交 0 条
        assert len(cl.children[1].notes) == 1
        assert len(cl.children[0].notes) == 0


async def test_fake_hash_without_git_still_shows(tmp_path):
    """非 git 仓库里，伪造 hash 的笔记照常显示（不受 git 接入影响）。"""
    s = NoteStore(tmp_path / "notes")
    s.add(CommitNote(commit="c0ffee1", kind=NoteKind.BUG, title="缺陷",
                     author=Actor("human:lwy")))
    app = make_app(s, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        cl = app.query_one(CommitList)
        assert len(cl.children) == 1
        assert cl.children[0].commit == "c0ffee1"
        assert len(cl.children[0].notes) == 1


# ---------------------------------------------------------------------------
# 提交条目：单行 + 截断
# ---------------------------------------------------------------------------


async def test_commit_item_is_single_line(tmp_path):
    from pdev.git import CommitInfo
    from pdev.tui.panels import CommitItem

    info = CommitInfo(hash="abcdef1234567890", subject="feat: 某功能",
                      author="T")
    text = CommitItem("abcdef12",
                      [CommitNote(commit="abcdef12", kind=NoteKind.BUG,
                                  title="x")], info).render()
    # 只有一行（不再有换行）
    assert "\n" not in text.plain
    assert "abcdef12" in text.plain
    assert "feat: 某功能" in text.plain


async def test_commit_item_ellipsize_helper():
    from pdev.tui.panels import _ellipsize

    assert _ellipsize("hello", 10) == "hello"
    assert _ellipsize("hello world", 6) == "hello…"
    # CJK 按 2 宽算：width=5 → 预算 4，可放两个汉字 + …
    assert _ellipsize("中文标题", 5) == "中文…"
    assert _ellipsize("中文标题", 3) == "中…"
    assert _ellipsize("x", 0) == ""


async def test_commit_item_truncates_long_subject_in_narrow_panel(tmp_path):
    from pdev.git import CommitInfo
    from pdev.tui.panels import CommitItem

    long_subject = "feat: " + "很长的提交说明" * 10
    info = CommitInfo(hash="abcdef1234567890", subject=long_subject,
                      author="T")
    s = NoteStore(tmp_path / "notes")
    app = make_app(s, cwd=str(tmp_path))
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        item = CommitItem("abcdef12", [], info)
        app.query_one(CommitList).mount(item)
        await pilot.pause()
        line = item.render().plain
        assert "\n" not in line
        assert "…" in line


async def test_commit_width_limit_from_config(tmp_path):
    from pdev.git import CommitInfo
    from pdev.tui.panels import CommitItem

    s = NoteStore(tmp_path / "notes")
    cfg = Config()
    cfg.ui.commit_width = 24
    app = PDMApp(s, cwd=str(tmp_path), config=cfg)
    async with app.run_test(size=(140, 30)) as pilot:
        await pilot.pause()
        info = CommitInfo(hash="abcdef1234567890",
                          subject="feat: 这是一个很长的提交标题用于测试截断",
                          author="T")
        item = CommitItem("abcdef12", [], info)
        app.query_one(CommitList).mount(item)
        await pilot.pause()
        line = item.render().plain
        # 受 commit_width 限制，总宽不超过 24
        from pdev.tui.panels import _display_width

        assert _display_width(line) <= 24


# ---------------------------------------------------------------------------
# 主题
# ---------------------------------------------------------------------------


async def test_theme_applied_from_config(store, tmp_path):
    cfg = Config()
    cfg.ui.theme = "nord"
    app = PDMApp(store, cwd=str(tmp_path), config=cfg)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        assert app.theme == "nord"


async def test_bad_theme_falls_back(store, tmp_path):
    cfg = Config()
    cfg.ui.theme = "no-such-theme"
    app = PDMApp(store, cwd=str(tmp_path), config=cfg)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        assert app.theme == "textual-dark"


async def test_cycle_theme_changes_and_persists(store, tmp_path):
    from pdev.config import load_config

    target = tmp_path / ".pdm.json"
    target.write_text("{}", encoding="utf-8")
    cfg = Config()
    app = PDMApp(store, cwd=str(tmp_path), config=cfg,
                 config_path=target)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        before = app.theme
        await pilot.press("t")
        await pilot.pause()
        assert app.theme != before
        # 写回文件并能重新加载
        cfg2 = load_config(project_config=target)
        assert cfg2.ui.theme == app.theme


async def test_pick_theme_screen(store, tmp_path):
    from pdev.tui.screens import ThemeScreen
    from textual.widgets import ListView

    target = tmp_path / ".pdm.json"
    target.write_text("{}", encoding="utf-8")
    app = PDMApp(store, cwd=str(tmp_path), config=Config(),
                 config_path=target)
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await pilot.press("T")
        await pilot.pause()
        assert isinstance(app.screen, ThemeScreen)
        view = app.screen.query_one("#theme-list", ListView)
        # 主题数与内置主题数一致
        assert len(view.children) == len(app.available_themes)


async def test_theme_screen_esc_cancels(store, tmp_path):
    from pdev.tui.screens import ThemeScreen

    app = PDMApp(store, cwd=str(tmp_path), config=Config())
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await pilot.press("T")
        await pilot.pause()
        assert isinstance(app.screen, ThemeScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ThemeScreen)


async def test_no_config_still_opens_theme_screen(store, tmp_path):
    """没传 config 时（默认），主题功能不应崩。"""
    from pdev.tui.screens import ThemeScreen

    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await pilot.press("T")
        await pilot.pause()
        assert isinstance(app.screen, ThemeScreen)


# ---------------------------------------------------------------------------
# Feat 面板
# ---------------------------------------------------------------------------


def _make_feats(tmp_path):
    from pdev.feat import Feat, FeatStore

    s = FeatStore(tmp_path / "feats")
    s.add(Feat(slug="a", title="A", doc="d.md", api=["f()"],
               fallbacks=["x"]))
    return s


async def test_feat_screen_opens(store, tmp_path):
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen

    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d.md", api=["f()"],
                fallbacks=["x"]))
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)


async def test_feat_binding_opens_screen(store, tmp_path):
    from pdev.tui.screens import FeatScreen

    _make_feats(tmp_path)
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)


async def test_feat_screen_lists_feats(store, tmp_path):
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen
    from textual.widgets import ListView

    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d", api=["f()"], fallbacks=["x"]))
    fs.add(Feat(slug="b", title="B", doc="d", api=["f()"], fallbacks=["x"]))
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        lv = app.screen.query_one("#feat-list", ListView)
        assert len(lv.children) == 2


async def test_feat_screen_check_reports_issues(store, tmp_path):
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen

    fs = FeatStore(tmp_path / "feats")
    # draft + commit → draft-has-commit warning
    f = Feat(slug="a", title="A", doc="d", api=["f()"], fallbacks=["x"])
    fs.add(f)
    fs.link_commit("a", "deadbeef")
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        codes = {i.code for i in app.screen._issues}
        assert "draft-has-commit" in codes


async def test_feat_screen_esc_closes(store, tmp_path):
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen

    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d", api=["f()"], fallbacks=["x"]))
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, FeatScreen)


async def test_feat_screen_empty_store(store, tmp_path):
    from pdev.feat import FeatStore
    from pdev.tui.screens import FeatScreen

    fs = FeatStore(tmp_path / "feats")
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)


async def test_feat_screen_q_closes_not_quits_app(store, tmp_path):
    """按 q 只关弹窗，不应退出整个应用（曾把 App 一起退掉）。"""
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen

    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d", api=["f()"], fallbacks=["x"]))
    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs))
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, FeatScreen)
        assert app.is_running          # 应用还活着


# ---------------------------------------------------------------------------
# 弹窗按键规范（见 docs/feat/modal-keys.md）
#
# 规范：关闭键必须在弹窗自己的 BINDINGS 里声明，不冒泡到 App；
#       有输入框的弹窗（FilterScreen）例外，q 是普通字符。
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["escape", "q"])
async def test_all_modals_close_without_quitting_app(store, tmp_path, key):
    """Esc / q 都应只关弹窗，App 保持存活。"""
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen, HelpScreen, ThemeScreen

    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d", api=["f()"], fallbacks=["x"]))

    screens = [
        lambda a: FeatScreen(fs),
        lambda a: HelpScreen(),
        lambda a: ThemeScreen(),
    ]
    for make in screens:
        app = make_app(store, cwd=str(tmp_path))
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            app.push_screen(make(app))
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            assert app.is_running, f"{make} 按 {key} 后退出了 App"


async def test_modal_close_leaves_app_screen(store, tmp_path):
    from pdev.tui.screens import HelpScreen

    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(HelpScreen())
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert app.is_running


async def test_filter_screen_q_is_character_not_close(store, tmp_path):
    """有输入框的弹窗：q 必须是字符输入，只有 Esc 关闭。"""
    from pdev.tui.screens import FilterScreen
    from textual.widgets import Input

    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FilterScreen())
        await pilot.pause()
        app.screen.query_one("#text", Input).focus()
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, FilterScreen)
        assert "q" in app.screen.query_one("#text", Input).value


def test_no_modal_uses_key_q_without_binding():
    """规范：非输入型弹窗不得用 key_q() 拦截（会冒泡退 App）。

    见 docs/feat/modal-keys.md 规则 2。FilterScreen 是唯一合法例外
    （它有输入框，q 必须是字符）。
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "pdev" / "tui" / "screens.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    allowed = {"FilterScreen"}       # 有输入框的例外
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef)
                and node.name.endswith("Screen")):
            continue
        has_key_q = any(isinstance(n, ast.FunctionDef) and n.name == "key_q"
                        for n in node.body)
        if has_key_q:
            assert node.name in allowed, (
                f"{node.name} 使用了 key_q()，应改为声明式 BINDINGS"
                f"（见 docs/feat/modal-keys.md）"
            )


# ---------------------------------------------------------------------------
# Feat 界面：阶段闭环 + 关联笔记（见 docs/feat/feat-ui.md）
# ---------------------------------------------------------------------------


def test_stage_progress_all_done(tmp_path):
    """五个阶段齐全时全部为 True。"""
    from pdev.feat import Feat
    from pdev.tui.screens import stage_progress
    from pdev.git import GitRepo
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    for i, msg in enumerate(("doc(x): 规范", "test(x): 测试",
                             "feat(x): 实现", "fix(x): 修", "doc(x): 收尾")):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", msg)

    repo = GitRepo(str(tmp_path))
    feat = Feat(slug="a", title="A",
                commits=[i.hash for i in repo.log()])
    prog = stage_progress(feat, repo)
    assert dict(prog) == {"doc": True, "test": True, "feat": True,
                          "fix": True, "closing": True}


def test_stage_progress_partial(tmp_path):
    """只做了 doc + feat 时，test/fix 未完成。"""
    from pdev.feat import Feat
    from pdev.tui.screens import stage_progress
    from pdev.git import GitRepo
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    for i, msg in enumerate(("doc(x): 规范", "feat(x): 实现")):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", msg)

    repo = GitRepo(str(tmp_path))
    feat = Feat(slug="a", title="A", commits=[i.hash for i in repo.log()])
    d = dict(stage_progress(feat, repo))
    assert d["doc"] is True
    assert d["feat"] is True
    assert d["test"] is False
    assert d["fix"] is False


def test_stage_progress_no_git(tmp_path):
    from pdev.feat import Feat
    from pdev.tui.screens import stage_progress

    feat = Feat(slug="a", title="A")
    prog = stage_progress(feat, None)
    assert all(not done for _, done in prog)


def test_notes_for_feat(store, tmp_path):
    from pdev.feat import Feat
    from pdev.tui.screens import notes_for_feat

    store.add(CommitNote(commit="abc123", kind=NoteKind.BUG, title="缺陷"))
    feat = Feat(slug="a", title="A", commits=["abc123"])
    notes = notes_for_feat(feat, store)
    assert len(notes) == 1
    assert notes[0].title == "缺陷"


def test_notes_for_feat_empty(store, tmp_path):
    from pdev.feat import Feat
    from pdev.tui.screens import notes_for_feat

    feat = Feat(slug="a", title="A", commits=["nomatch"])
    assert notes_for_feat(feat, store) == []


async def test_feat_screen_shows_stages(store, tmp_path):
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import FeatScreen
    from pdev.git import GitRepo
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat(x): 实现")

    repo = GitRepo(str(tmp_path))
    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(slug="a", title="A", doc="d", api=["f()"],
                fallbacks=["x"], commits=[repo.log()[0].hash]))

    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        app.push_screen(FeatScreen(fs, repo, store))
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)


def test_notes_for_feat_short_commit_no_false_match(store):
    """短 commit 串不应误匹配（Review 发现）。"""
    from pdev.feat import Feat
    from pdev.tui.screens import notes_for_feat

    store.add(CommitNote(commit="abcdef123456", kind=NoteKind.BUG, title="X"))
    feat = Feat(slug="a", title="A", commits=["ab"])   # 太短
    assert notes_for_feat(feat, store) == []
    # 够长的前缀可以匹配
    feat2 = Feat(slug="b", title="B", commits=["abcdef"])
    assert len(notes_for_feat(feat2, store)) == 1


# ---------------------------------------------------------------------------
# TUI 显示 commit message（见 docs/feat/note-commit-msg.md）
# ---------------------------------------------------------------------------


async def test_detail_shows_commit_message(store, tmp_path):
    """详情面板顶部应显示 commit message。"""
    from pdev.git import CommitInfo
    from pdev.tui.panels import DetailPane

    app = make_app(store, cwd=str(tmp_path))
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        note = next(iter(store.all()))
        info = CommitInfo(hash="aaa111", subject="feat(x): 某功能",
                          author="T")
        pane = app.query_one(DetailPane)
        pane.show_note(note, str(tmp_path), commit_info=info)
        await pilot.pause()
        rendered = pane._build(note, str(tmp_path), info)
        assert "feat(x): 某功能" in rendered.plain


async def test_feat_screen_notes_show_commit_hash(store, tmp_path):
    """FeatScreen 的关联笔记应带 commit 短 hash。"""
    from pdev.feat import Feat, FeatStore
    from pdev.tui.screens import _feat_detail

    store.add(CommitNote(commit="abc1234def", kind=NoteKind.BUG,
                         title="缺陷"))
    fs = FeatStore(tmp_path / "feats")
    feat = Feat(slug="a", title="A", doc="d", api=["f()"],
                fallbacks=["x"], commits=["abc1234def"])
    fs.add(feat)
    text = _feat_detail(feat, [], git=None, note_store=store)
    assert "关联笔记" in text.plain
    assert "缺陷" in text.plain
    assert "abc1234d" in text.plain
