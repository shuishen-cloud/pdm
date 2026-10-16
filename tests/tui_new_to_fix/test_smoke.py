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


def _config_with_feat(feat_root):
    """造一个最小 config：只带 feat.store 与 default_author。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        feat=SimpleNamespace(store=str(feat_root)),
        default_author="human:test-author",
    )


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

        # j 下移到第二条提交，笔记栏与详情跟着变
        await pilot.press("j")
        await pilot.pause()
        assert note_rows(app) == ["竞态", "缺陷"]
        assert "竞态" in detail_text(app)

        # 3 跳到详情面板
        await pilot.press("3")
        await pilot.pause()
        assert app.is_running
        # R 刷新后数据仍在（放在这里，与导航共用一个会话）
        await pilot.press("R")
        await pilot.pause()
        assert len(commit_rows(app)) == 2
        assert app.errors == []


# --- 会话 2：代表性键位不炸 + Feat 面板（同一个 app） ---------------------------


@pytest.fixture
def feat_root(tmp_path):
    """隔离的 feat 目录，内含一个 demo。避免碰到仓库里的真 feat。"""
    from pdev.feat import Feat, FeatStore

    root = tmp_path / "feats"
    s = FeatStore(root)
    s.update(Feat(slug="demo", title="演示", api=["run() -> int"]))
    return root


def _reload_feat(root, slug="demo"):
    """从磁盘**重新**读一份 feat（模拟 CLI 复核，不听内存缓存）。"""
    from pdev.feat import FeatStore

    return FeatStore(root).get(slug)


async def test_keys_keep_app_alive_and_feat_panel(store, feat_root):
    """纯导航键不炸；且 ``f`` 能打开 Feat 面板、``空格`` 能勾审查并落盘。

    两件事共用一个 app 会话：``run_test`` 很贵，能合并就合并。
    写盘一律用 ``_reload_feat`` 复查（新建 store 从磁盘读），
    与 ``web-ui-review`` 的「CLI 复核」同一思路。
    """
    from pdev.tui_new_to_fix.screens import FeatScreen
    from textual.widgets import ListView

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        for key in ["2", "3", "tab"]:
            await pilot.press(key)
            await pilot.pause()
            assert app.is_running, f"{key} 让 app 退出了"
            assert app.errors == [], f"{key} 产生了异常：{app.errors}"

        # --- f 打开面板，能看到列表 ---
        await pilot.press("f")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FeatScreen)
        assert len(screen.query_one("#feat-list", ListView).children) == 1

        # --- 空格勾 [审]，必须真的落盘（从磁盘复查） ---
        await pilot.press("space")
        await pilot.pause()
        assert app.errors == []
        item = _reload_feat(feat_root).review_item("api:0")
        assert item.reviewed is True
        assert item.reviewed_by == "human:test-author"   # by 来自 config

        # 再按一次 = 取消（两个位都清空时记录会被 _prune 掉，
        # 因此 review_item 返回 None——同样表示“未勾选”）
        await pilot.press("space")
        await pilot.pause()
        item = _reload_feat(feat_root).review_item("api:0")
        assert getattr(item, "reviewed", False) is False

        # --- t 勾 [测]，且不得顺带改 [审] ---
        await pilot.press("t")
        await pilot.pause()
        assert app.errors == []
        item = _reload_feat(feat_root).review_item("api:0")
        assert item.tested is True
        assert item.reviewed is False

        # --- Esc 关闭后 app 仍在跑 ---
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running
        assert not isinstance(app.screen, FeatScreen)


# --- 会话 3：异常兜底（本 feat 的核心契约） ---------------------------------


async def test_exception_in_action_does_not_kill_app(store):
    """action 抛异常 → app 继续跑（旧 TUI 会 panic 退出）。

    用 monkeypatch 注入故障，而不是在 app 里留一个“自毁键”。
    直接调 action 而不是按键：这是单元级验证，不必经过输入栈。
    """
    app = make_app(store)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()

        def boom() -> None:
            raise RuntimeError("intentional failure")

        # 用与 app 相同的方式包装，确保测的就是 guard 本身
        from pdev.tui_new_to_fix.guard import guard

        wrapped = guard(lambda self: boom())
        wrapped(app)                    # 不应抛出

        assert app.is_running, "guard 没兜住，app 退出了"
        assert len(app.errors) == 1, app.errors
        assert "intentional failure" in app.errors[0]
        # 出错后仍能正常操作（按键路径不受影响）
        await pilot.press("2")
        await pilot.pause()
        assert app.is_running


async def test_bound_action_is_guarded(store):
    """**本类自己定义**的 action 必须都被 guard 包住（防漏包）。

    不能查 ``dir(app)``：那会列出 Textual 框架自带的一堆 action
    （``action_add_class`` 等），它们不归我们管。
    """
    app = make_app(store)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        own = [n for n in vars(type(app)) if n.startswith("action_")]
        assert own, "本类没定义任何 action，断言无效"
        for name in own:
            fn = getattr(app, name)
            # guard 用 functools.wraps，因此可从 __wrapped__ 反查
            assert hasattr(fn, "__wrapped__"), f"{name} 没被 guard 包住"


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
    """本文件所有用例的**自身**耗时之和必须低于 2.5s（防回归）。

    只统计用例执行时间（autouse fixture 累加），不含 pytest 启动、
    收集、import —— 否则全仓跑时会被其它测试的耗时污染。

    基准（Textual 8.2.8，本机）：约 1.6~1.9s。
    """
    assert _ELAPSED < 2.5, f"冒烟测试太慢：{_ELAPSED:.2f}s"
