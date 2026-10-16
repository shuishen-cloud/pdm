# -*- coding: utf-8 -*-
"""Feat 面板的集成测试（**慢文件**）。

与 ``tests/tui_new_to_fix/test_smoke.py`` 的分工：

| 文件 | 内容 | 预算 |
|------|------|------|
| ``test_smoke.py`` | 启动 / 导航 / 键位 / 异常兜底 | < 1.5s |
| ``test_feat_ui.py``（本文件） | Feat 面板完整流程（勾选 / 单行 / 放大 / 评论） | < 3.5s |

拆开的理由：``run_test`` ≈ 0.13s、``pause`` ≈ 0.02s、``press`` ≈ 0.05s，
Feat 面板的流程用例天生需要多次按键与同步。拆开后**快速反馈**只需跑
``test_smoke.py``，改 Feat 界面时才跑本文件。

渲染细节（截断、多行、状态标记）一律由 ``test_feat_core.py`` 的
纯函数覆盖，本文件只验证“接线”。
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("textual")

from pdev.feat import Feat, FeatStore  # noqa: E402
from pdev.note import Actor, CommitNote, NoteKind  # noqa: E402
from pdev.store import NoteStore  # noqa: E402
from pdev.tui_new_to_fix import feat_core
from pdev.tui_new_to_fix.app import PDMApp  # noqa: E402

#: 本文件“自己的”耗时累加（不含 import、收集与其它测试）。
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
                   author=Actor("human:lwy")),
    ])
    return s


@pytest.fixture
def feat_root(tmp_path):
    """隔离的 feat 目录，内含一个 demo（api:0）。"""
    root = tmp_path / "feats"
    s = FeatStore(root)
    s.update(Feat(slug="demo", title="演示", api=["run() -> int"]))
    return root


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


def _reload_feat(root, slug="demo"):
    """从磁盘**重新**读一份 feat（模拟 CLI 复核，不听内存缓存）。"""
    return FeatStore(root).get(slug)


def _reload_store(root) -> FeatStore:
    return FeatStore(root)


def _detail_text(screen) -> str:
    """取 FeatScreen 右侧详情的纯文本。"""
    from textual.widgets import Static

    content = screen.query_one("#feat-detail-body", Static).content
    return getattr(content, "plain", str(content))


def _header_text(screen) -> str:
    """取 CommentScreen 顶部信息块的纯文本。"""
    from textual.widgets import Static

    content = screen.query_one("#comment-title", Static).content
    return getattr(content, "plain", str(content))


# ---------------------------------------------------------------------------
# 勾选：空格 / t（第一个写操作）
# ---------------------------------------------------------------------------


async def test_feat_panel_toggle_and_persist(store, feat_root):
    """``f`` 打开面板；``空格``/``t`` 能勾选并**真的落盘**。

    写盘一律用 :func:`_reload_feat` 复查（新建 store 从磁盘读，
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

        # --- 再按空格 = 取消；然后 t 勾 [测]（同批按键，只同步一次）---
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


# ---------------------------------------------------------------------------
# 列表：单行 / 放大 / 焦点
# ---------------------------------------------------------------------------


async def test_feat_list_single_line_zoom_and_focus(store, feat_root):
    """列表单行、``Enter`` 放大能看全、方向键切焦点。

    渲染细节由 ``test_feat_core.test_feat_line_*`` 覆盖，
    这里只验证“接线”：高度锁 1、enter 真的改变宽度、焦点真的换。
    """
    from pdev.tui_new_to_fix.screens import FeatScreen
    from textual.widgets import ListView

    long_slug = "tui-new-to-fix-and-feat-review-super-long-slug"
    _reload_store(feat_root).update(
        Feat(slug=long_slug, title="长", api=["x()", "y()"],
             design_note="为什么这么设计", impl_note="怎么落地的"))

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
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

        # --- 标签：默认 Review，d/n 切换，空格含义随标签变 ---
        screen = app.screen
        assert screen._tab == "review", "默认应在 Review（保持兼容）"

        await pilot.press("d")            # 切到 Design
        await pilot.pause()
        assert screen._tab == "design"
        body = _detail_text(screen)
        assert "设计思路" in body, "Design 页应展示设计条目"

        # Design 页：空格 = 展开/收起（不是勾审）
        before_folded = dict(screen._folded)
        await pilot.press("space")
        await pilot.pause()
        assert screen._folded != before_folded, "Design 页空格应切折叠"
        assert "▾" in _detail_text(screen), "展开后应有 ▾ 标记"

        # 回到 Review：空格又变回勾审（注意第一项可能是 design_note，
        # 因为整块文本字段已纳入可审项）
        await pilot.press("n")
        await pilot.pause()
        assert screen._tab == "review"
        first_key = screen._rows[screen._cursor][0]
        await pilot.press("space")
        await pilot.pause()
        assert _reload_feat(feat_root, long_slug).review_item(
            first_key).reviewed is True, f"Review 页空格应勾审 {first_key}"

        # --- Design 页：切过去自动把焦点给详情（否则 j/k 只会切 feat）---
        await pilot.press("d")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "feat-detail", \
            "切到 Design 后焦点应在详情，否则 j/k 移动无效"

        # --- 光标移动时，当前条目**必须在视口内**（曾滚到错误位置）---
        detail = screen._detail()
        for _ in range(4):
            await pilot.press("j")
            await pilot.pause()
            span = feat_core.design_cursor_span(
                screen._current_feat(), screen._folded,
                screen._design_cursor_section())
            top = detail.scroll_y
            bottom = top + detail.size.height - 1
            assert span[0] <= bottom, (
                f"光标条目 {screen._design_cursor_section()} 滚出视野："
                f"span={span} 可见=[{top},{bottom}]")

        # --- 光标**循环**：连按 len(filled) 次必回到同一位置 ---
        filled = screen._design_filled_keys(screen._current_feat())
        assert len(filled) >= 2, "本用例需要至少两个有条目的字段"
        before = screen._design_cursor
        for _ in range(len(filled)):
            await pilot.press("j")
            await pilot.pause()
        assert screen._design_cursor == before, "一圈之后应回到原位（循环）"


# ---------------------------------------------------------------------------
# 评论（第二个写操作）
# ---------------------------------------------------------------------------


async def test_feat_comment_roundtrip(store, feat_root):
    """``c`` 编辑评论，``Ctrl+S`` 保存并落盘；``Esc`` 取消不落盘。

    多行/清除的细节由 ``test_feat_core.test_plan_comment_*`` 覆盖，
    这里只验证“接线”与“评论显示在自己条目下方”。
    """
    from textual.widgets import TextArea

    from pdev.tui_new_to_fix.screens import CommentScreen, FeatScreen

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    async with app.run_test(size=(100, 30)) as pilot:
        # 连续打开（f → c），只在需要断言弹窗内容时同步一次
        await pilot.press("f", "c")
        await pilot.pause()
        assert isinstance(app.screen, CommentScreen), "c 没打开评论弹窗"

        # 顶部应显示条目详细信息
        header = _header_text(app.screen)
        assert "demo" in header          # feat
        assert "api:0" in header         # 条目 key
        assert "run() -> int" in header  # 条目内容

        # 输入（直接写 TextArea，避开逐字按键）并 Ctrl+S 保存
        app.screen.query_one("#comment-text", TextArea).text = "为何不泛化"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen), "保存后应回到 FeatScreen"
        assert app.errors == []
        assert _reload_feat(feat_root).comment("api:0") == "为何不泛化"

        # 再次 c 应是“编辑已有评论”，Esc 取消不落盘
        await pilot.press("c")
        await pilot.pause()
        assert app.screen.query_one("#comment-text", TextArea).text == "为何不泛化"
        app.screen.query_one("#comment-text", TextArea).text = "改了"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, FeatScreen)
        assert _reload_feat(feat_root).comment("api:0") == "为何不泛化", \
            "Esc 取消不应落盘"

        # 写评论不等于勾选（两件事独立）
        item = _reload_feat(feat_root).review_item("api:0")
        assert getattr(item, "reviewed", False) is False

        # 评论必须紧跟在自己条目下方（不是堆在底部）
        detail = _detail_text(app.screen)
        lines = detail.splitlines()
        api_line = next(i for i, ln in enumerate(lines) if "api:0" in ln)
        assert "为何不泛化" in lines[api_line + 1], (
            f"评论没有紧跟在 api:0 下方：\n{detail}")


# ---------------------------------------------------------------------------
# FeatScreen 的异常兜底（曾因漏包 @guard 而闪退）
# ---------------------------------------------------------------------------


async def test_feat_screen_exception_does_not_kill_app(store, feat_root):
    """FeatScreen 内部抛异常 → app 继续跑。

    这是“用着用着直接退出”的确切根因：``ModalScreen`` 的方法漏包
    ``@guard``，异常冒到 Textual 的 ``_handle_exception()`` 就 panic。
    """
    from pdev.tui_new_to_fix import feat_core
    from pdev.tui_new_to_fix.screens import FeatScreen

    app = make_app(store)
    app.config = _config_with_feat(feat_root)
    original = feat_core.review_rows
    async with app.run_test(size=(100, 30)) as pilot:
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


# ---------------------------------------------------------------------------
# 时间预算（本文件自带，防止回归成慢测试）
# ---------------------------------------------------------------------------


def test_feat_ui_suite_is_fast():
    """本文件的 run_test 开销必须低于 3.5s（防回归）。

    基准（Textual 8.2.8，本机）：4 个集成会话 ≈ 2.5~3.0s。
    ``run_test`` ≈ 0.13s、``pause`` ≈ 0.02s、``press`` ≈ 0.05s，
    因此这个量级是“必要成本”，不是浪费；阈值留抖动余量。
    """
    assert _ELAPSED < 3.5, f"Feat 面板测试太慢：{_ELAPSED:.2f}s"
