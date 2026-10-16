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

        # 3 跳到详情面板；再跑几个代表性键，确认不炸（每次约 0.1s，不穷举）
        for key in ["3", "tab", "2"]:
            await pilot.press(key)
            await pilot.pause()
            assert app.is_running, f"{key} 让 app 退出了"
            assert app.errors == [], f"{key} 产生了异常：{app.errors}"
        # R 刷新后数据仍在
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


def _reload_store(root):
    """从磁盘重新读一个 FeatStore。"""
    from pdev.feat import FeatStore

    return FeatStore(root)


def _header_text(screen) -> str:
    """取 CommentScreen 顶部信息块的纯文本（用于断言）。"""
    from textual.widgets import Static

    content = screen.query_one("#comment-title", Static).content
    return getattr(content, "plain", str(content))


def _detail_text(screen) -> str:
    """取 FeatScreen 右侧详情的纯文本。"""
    from textual.widgets import Static

    content = screen.query_one("#feat-detail-body", Static).content
    return getattr(content, "plain", str(content))


async def test_feat_panel_toggle_and_persist(store, feat_root):
    """``f`` 打开面板；``空格``/``t`` 能勾选并**真的落盘**。

    写盘一律用 ``_reload_feat`` 复查（新建 store 从磁盘读，
    不听内存缓存），与 ``web-ui-review`` 的「CLI 复核」同一思路。
    """
    from pdev.tui_new_to_fix.screens import FeatScreen
    from textual.widgets import ListView

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()

        # --- f 打开面板 + 空格勾 [审] ---
        await pilot.press("f", "space")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, FeatScreen)
        assert len(screen.query_one("#feat-list", ListView).children) == 1
        assert app.errors == []

        # 勾选必须真的落盘（从磁盘复查）
        item = _reload_feat(feat_root).review_item("api:0")
        assert item.reviewed is True
        assert item.reviewed_by == "human:test-author"   # by 来自 config

        # --- 再按空格 = 取消；然后 t 勾 [测] 且不动 [审] ---
        # 注：两位都清空时记录会被 _prune 掉，review_item 返回 None，
        # 同样表示“未勾选”，因此用 getattr 读。
        await pilot.press("space", "t")
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


# --- 会话 3：Feat 列表的单行/放大/焦点（与勾选解耦） -------------------------


async def test_feat_list_single_line_zoom_and_focus(store, feat_root):
    """列表单行、Enter 放大能看全、（左右） 方向键切焦点。

    渲染细节（截断宽度、省略号）由 ``test_feat_core`` 的纯函数测覆盖，
    这里只验证“接线”：高度锁 1、enter 真的改变宽度、焦点真的换。
    """
    from pdev.feat import Feat
    from pdev.tui_new_to_fix.screens import FeatScreen
    from textual.widgets import ListView

    long_slug = "tui-new-to-fix-and-feat-review-super-long-slug"
    _reload_store(feat_root).update(
        Feat(slug=long_slug, title="长", api=["x()"]))

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)
        lv = app.screen.query_one("#feat-list", ListView)
        item = next(i for i in lv.children if i.feat.slug == long_slug)
        assert item.size.height == 1, "列表项折行了"

        # --- Enter 放大：不得被 ListView 吞 ---
        width_before = lv.size.width
        await pilot.press("enter")
        await pilot.pause()
        assert lv.size.width > width_before, "enter 没有放大列表（被 ListView 吞了？）"
        assert long_slug in item.render().plain, "放大后应能看到完整 slug"
        await pilot.press("enter")
        await pilot.pause()
        assert lv.size.width == width_before

        # --- 方向键切焦点 ---
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "feat-detail"
        await pilot.press("h")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "feat-list"


# --- 会话：评论编辑（第二个写操作） ------------------------------------------


async def test_feat_comment_roundtrip(store, feat_root):
    """``c`` 打开评论弹窗，输入后 Ctrl+S 保存并**真的落盘**；Esc 不落盘。

    多行输入的细节（换行保留、留空=清除）由 ``test_feat_core``
    的纯函数测覆盖，这里只验证“接线”。
    """
    from textual.widgets import TextArea

    from pdev.tui_new_to_fix.screens import CommentScreen, FeatScreen

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)

        # --- c 打开评论弹窗，顶部应显示条目详细信息 ---
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, CommentScreen), "c 没打开评论弹窗"
        header = _header_text(app.screen)
        assert "demo" in header          # feat
        assert "api:0" in header         # 条目 key
        assert "run() -> int" in header  # 条目内容（详细信息）

        # --- 输入（直接写 TextArea，避开逐字按键的开销）并 Ctrl+S 保存 ---
        app.screen.query_one("#comment-text", TextArea).text = "为何不泛化"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen), "保存后应回到 FeatScreen"
        assert app.errors == []
        assert _reload_feat(feat_root).comment("api:0") == "为何不泛化"

        # --- 再次 c 应是“编辑已有评论”，Esc 取消不落盘 ---
        await pilot.press("c")
        await pilot.pause()
        assert app.screen.query_one("#comment-text", TextArea).text == "为何不泛化"
        app.screen.query_one("#comment-text", TextArea).text = "改了"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)
        assert _reload_feat(feat_root).comment("api:0") == "为何不泛化", \
            "Esc 取消不应落盘"

        # --- 两件事仍互不干扰（写评论不等于勾选）---
        item = _reload_feat(feat_root).review_item("api:0")
        assert getattr(item, "reviewed", False) is False

        # --- 评论必须紧跟在自己条目下方（不是堆在底部）---
        detail = _detail_text(app.screen)
        lines = detail.splitlines()
        api_line = next(i for i, ln in enumerate(lines) if "api:0" in ln)
        assert "为何不泛化" in lines[api_line + 1], (
            f"评论没有紧跟在 api:0 下方：\n{detail}")


# --- 会话：FeatScreen 内部的异常兜底 ----------------------------------------


async def test_feat_screen_exception_does_not_kill_app(store, feat_root):
    """FeatScreen 内部抛异常 → app 继续跑（曾因漏包 @guard 而闪退）。"""
    from pdev.tui_new_to_fix import feat_core
    from pdev.tui_new_to_fix.screens import FeatScreen

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    original = feat_core.review_rows
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)
        feat_core.review_rows = lambda f: (_ for _ in ()).throw(
            RuntimeError("corrupt feat json")
        )
        try:
            await pilot.press("space")
            await pilot.pause()
            assert app.is_running, "FeatScreen 抛异常把 app 带走了"
            assert any("corrupt feat json" in e for e in app.errors), app.errors
        finally:
            feat_core.review_rows = original


# --- 会话（异常兜底）：本 feat 的核心契约 ------------------------------------


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
    """本文件所有用例的**自身**耗时之和必须低于 2.5s（防回归）。

    只统计用例执行时间（autouse fixture 累加），不含 pytest 启动、
    收集、import —— 否则全仓跑时会被其它测试的耗时污染。

    基准（Textual 8.2.8，本机）：约 1.6~1.9s。
    """
    assert _ELAPSED < 2.5, f"冒烟测试太慢：{_ELAPSED:.2f}s"
