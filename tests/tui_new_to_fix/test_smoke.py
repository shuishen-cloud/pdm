# -*- coding: utf-8 -*-
"""新 TUI 的冒烟测试（无头驱动）。

**速度是硬指标**（见 ``doc/tui-new-to-fix.md``）：

- 一次 ``run_test`` ≈ 0.2s，因此全部会话加起来不得超过 6 次。
- 每个会话内按**代表性**键位（每次按键 ≈ 0.12s，不能穷举）。
- 结尾断言总耗时 < 2.5s，防止有人加回慢用例。

默认执行（不带 ``tui`` 标记）。
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("textual")

from pdev.note import (  # noqa: E402
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    Verification,
    VerificationKind,
)
from pdev.store import NoteStore  # noqa: E402
from pdev.tui_new_to_fix.app import PDMApp  # noqa: E402
from pdev.tui_new_to_fix.panels_check import (  # noqa: E402
    commit_rows,
    detail_text,
    note_rows,
)

#: 本文件“自己的”耗时累加（不含 import、不含 pytest 调度等外部开销）。
#: 不能用模块级 ``_T0``：全仓跑时它会把别的测试的耗时也算进去。
_ELAPSED = 0.0


@pytest.fixture(autouse=True)
def _measure():
    global _ELAPSED
    start = time.perf_counter()
    yield
    _ELAPSED += time.perf_counter() - start


@pytest.fixture
def store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="aaa1111", kind=NoteKind.PITFALL, title="竞态",
                   status=NoteStatus.OPEN, author=Actor("human:lwy")),
        CommitNote(commit="aaa1111", kind=NoteKind.BUG, title="缺陷",
                   status=NoteStatus.RESOLVED, author=Actor("ai:claude"),
                   verifications=[Verification(
                       kind=VerificationKind.COMMAND, command="true")]),
        CommitNote(commit="bbb2222", kind=NoteKind.DIFFICULTY, title="难点",
                   author=Actor("human:lwy")),
    ])
    return s


def make_app(store) -> PDMApp:
    """cwd 指向 store 的父目录：那里不是 git 仓库，避免读到真实历史。"""
    from pathlib import Path

    return PDMApp(store, cwd=str(Path(store.root).parent))


# --- 会话 1：启动 + 导航（一条会话覆盖全部渲染断言） -------------------------


async def test_boot_and_navigate(store):
    app = make_app(store)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.is_running
        # 伪造 hash 按倒序追加（cwd 不是 git 仓库）
        assert commit_rows(app) == ["bbb2222", "aaa1111"]
        # 第一条被选中 → 笔记栏显示它的笔记
        assert note_rows(app) == ["难点"]
        assert "难点" in detail_text(app)

        # j 下移到第二条提交，笔记栏与详情跟着变。
        # 注意：R（刷新）会把选中重置回第一条，所以必须**先断言 j 的效果**，
        # 不能把 j 与 R 批量放在一起（曾因此破坏语义）。
        await pilot.press("j")
        await pilot.pause()
        assert note_rows(app) == ["竞态", "缺陷"]
        assert "竞态" in detail_text(app)

        # 后几个键只验证“不炸”（R 刷新后选中回到第一条，不断言选中）
        await pilot.press("3", "tab", "2", "R")
        await pilot.pause()
        assert app.is_running
        assert app.errors == []
        assert len(commit_rows(app)) == 2

        # --- 条目必须单行（长 subject 不得折行）---
        from textual.widgets import ListView

        for panel in ("#commits", "#notes"):
            lv = app.query_one(panel, ListView)
            for child in lv.children:
                assert child.size.height == 1, f"{panel} 的条目折行了"

        # --- Enter 放大当前栏，再按还原 ---
        await pilot.press("1")                 # 焦点回提交栏
        await pilot.pause()
        commits = app.query_one("#commits", ListView)
        notes = app.query_one("#notes", ListView)
        wide_before = commits.size.width
        await pilot.press("enter")
        await pilot.pause()
        assert commits.size.width > wide_before, "enter 没有放大提交栏"
        assert notes.size.width == 0, "放大时其余栏应隐藏"
        assert app._zoomed == "commits"

        # 放大态互斥：切到笔记栏再按 enter，只留笔记栏
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert notes.size.width > 0
        assert commits.size.width == 0, "两栏不应同时可见（放大态必须互斥）"
        assert app._zoomed == "notes"

        # 再按还原
        await pilot.press("enter")
        await pilot.pause()
        assert app._zoomed is None, "再按 enter 应取消放大"
        assert commits.size.width > 0 and notes.size.width > 0
        assert commits.size.width == wide_before

        # --- 焦点不在三栏时，放大是静默 no-op ---
        app.set_focus(None)
        await pilot.pause()
        app.action_toggle_zoom()             # 同步 action，不 await
        await pilot.pause()
        assert app.zoom_target() is None
        assert app._zoomed is None
        assert app.errors == []


# --- 会话（异常兜底）：本 feat 的核心契约 ------------------------------------


async def test_exception_in_action_does_not_kill_app(store):
    """guard 注入故障 → app 继续跑（旧 TUI 会 panic 退出）。

    FeatScreen 内部的同类验证在 ``tests/tui_new_to_fix/test_feat_ui.py``
    的 ``test_feat_screen_exception_does_not_kill_app``（拆文件后
    两个文件各自更快）。
    """
    from pdev.tui_new_to_fix.guard import guard

    def boom() -> None:
        raise RuntimeError("intentional failure")

    app = make_app(store)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()

        # 用与 app 相同的方式包装，确保测的就是 guard 本身
        wrapped = guard(lambda self: boom())
        wrapped(app)                    # 不应抛出
        assert app.is_running, "guard 没兜住，app 退出了"
        assert len(app.errors) == 1, app.errors
        assert "intentional failure" in app.errors[0]

        # 出错后仍能正常操作（按键路径不受影响）
        await pilot.press("2")
        await pilot.pause()
        assert app.is_running


def test_all_actions_and_callbacks_are_guarded():
    """**每个界面类的 action / 回调**都必须被 guard 包住（防漏包）。

    这是本 feat 最重要的一条防回归：FeatScreen（ModalScreen）
    曾漏包，导致面板内任何异常都 panic 退出整个 TUI。

    纯函数式（不起 app），所以不必占 ``run_test`` 预算。
    不能查 ``dir(app)``：那会列出 Textual 框架自带的一堆 action
    （``action_add_class`` 等），它们不归我们管。
    """
    from pdev.tui_new_to_fix.app import PDMApp
    from pdev.tui_new_to_fix.screens import FeatScreen

    for cls in (PDMApp, FeatScreen):
        names = [n for n in vars(cls)
                 if n.startswith("action_") or n.startswith("on_")]
        assert names, f"{cls.__name__} 没定义任何 action/回调，断言无效"
        for name in names:
            fn = vars(cls)[name]
            # guard 用 functools.wraps，因此可从 __wrapped__ 反查
            assert hasattr(fn, "__wrapped__"), (
                f"{cls.__name__}.{name} 没被 guard 包住——"
                f"它抛异常会让整个 TUI 退出"
            )


async def test_exception_in_reload_does_not_kill_app(store):
    """数据层坏掉也不能带走 app（按 R 触发 _reload）。"""
    app = make_app(store)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()

        def boom():
            raise OSError("disk gone")

        app.store.all = boom
        await pilot.press("R")
        await pilot.pause()
        assert app.is_running, "数据层异常没被兜住"
        assert any("action_refresh" in e for e in app.errors), app.errors


# --- 会话 4：只有 q 退出 ----------------------------------------------------


async def test_q_quits(store):
    app = make_app(store)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not app.is_running


# --- 会话 5：启动即炸也不能退出 ---------------------------------------------


async def test_boot_failure_is_contained(tmp_path):
    """数据层在启动时就抛异常，app 仍必须起来（旧 TUI 会直接退出）。

    ``on_mount`` 曾经没包 guard；这是 “启动就挂” 的主要路径，
    因此单独盯住。
    """

    class ExplodingStore(NoteStore):
        def all(self):
            raise OSError("disk on fire at boot")

    app = PDMApp(ExplodingStore(tmp_path / "notes"), cwd=str(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.is_running, "启动即退出"
        assert any("on_mount" in e for e in app.errors), app.errors


# --- 时间预算 ---------------------------------------------------------------


def test_smoke_suite_is_fast():
    """本文件的 run_test 开销必须低于 2.5s（防回归）。

    Feat 面板的慢用例在 ``tests/tui_new_to_fix/test_feat_ui.py``，
    拆文件是为了保留“快速反馈”：改主界面只需跑本文件。

    单位成本（实测）：``run_test`` ≈ 0.13s、``pause`` ≈ 0.02s、
    ``press`` ≈ 0.05s。本文件 5 个用例各需一次 ``run_test``
    （硬成本 ≈ 0.65s），加断言所需的同步，约 1.6~2.0s。
    这里只统计用例自身耗时，不含 pytest 启动、收集、import。
    """
    assert _ELAPSED < 2.5, f"冒烟测试太慢：{_ELAPSED:.2f}s"
