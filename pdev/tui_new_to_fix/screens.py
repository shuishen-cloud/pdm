# -*- coding: utf-8 -*-
"""Feat 面板（ModalScreen）：两栏浏览 + 审查勾选。

这是新 TUI 的**首个写操作**。约束见 ``doc/feat/tui-feat-review.md``：

- 写入只走 ``FeatStore.set_reviews()``（CLI 的同一条路径），不直接改 JSON。
- 只允许改 ``reviewed`` / ``tested`` 两个布尔位。
- ``by`` 由调用方（app）从 config 取，**不由界面/用户输入决定**。
- 校验与取反逻辑在 :mod:`pdev.tui_new_to_fix.feat_core`（纯函数，可单测）。
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from . import feat_core

__all__ = ["FeatScreen"]

_MARK = {True: "■", False: "□"}


def _feat_line(feat) -> Text:
    """左列：一条 feat。"""
    t = Text()
    status = getattr(getattr(feat, "status", None), "value", "?")
    t.append("● ", style="bold")
    t.append(getattr(feat, "slug", "?"), style="bold yellow")
    t.append(f"  {status}", style="dim")
    try:
        counts = feat.review_counts()
        t.append(f"  审 {counts.reviewed}/{counts.total}", style="cyan")
    except Exception:                            # noqa: BLE001
        pass
    return t


class FeatItem(ListItem):
    """左列的一项。"""

    def __init__(self, feat) -> None:
        super().__init__()
        self.feat = feat

    def render(self) -> Text:
        return _feat_line(self.feat)


class FeatScreen(ModalScreen):
    """两栏 feat 浏览 + 审查勾选。

    - ``↑``/``↓`` 或 ``j``/``k`` 选 feat
    - ``空格`` 切换 ``[审]``、``t`` 切换 ``[测]``（作用于**当前高亮可审项**）
    - ``Esc`` / ``q`` 关闭
    """

    CSS = """
    FeatScreen { align: center middle; background: $surface 90%; }
    #feat-box {
        width: 96%;
        height: 90%;
        padding: 0 1;
        border: thick $accent;
        background: $surface;
    }
    #feat-title { height: 1; color: $text-muted; }
    #feat-body { height: 1fr; }
    #feat-list { width: 34; height: 1fr; border: round $primary; }
    #feat-detail {
        width: 1fr; height: 1fr;
        border: round $primary; padding: 0 1;
    }
    #feat-hint { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("escape", "close", "关闭"),
        Binding("q", "close", "关闭"),
        Binding("j", "cursor_down", "下移", show=False),
        Binding("k", "cursor_up", "上移", show=False),
        Binding("space", "toggle_review", "勾选审查"),
        Binding("t", "toggle_test", "勾选测试"),
    ]

    def __init__(self, feat_store, by: str = "human") -> None:
        super().__init__()
        self.feat_store = feat_store
        self.by = by
        self._rows: List[tuple] = []      # 当前 feat 的可审项
        self._cursor = 0                  # 当前高亮的可审项下标

    # --- 布局 ---

    def compose(self) -> ComposeResult:
        with Vertical(id="feat-box"):
            yield Static("Feat（开发记录）· 空格 勾审 · t 勾测 · Esc 关闭",
                         id="feat-title")
            with Horizontal(id="feat-body"):
                yield ListView(id="feat-list")
                with VerticalScroll(id="feat-detail"):
                    yield Static("", id="feat-detail-body")
            yield Static("", id="feat-hint")

    def on_mount(self) -> None:
        self._load_list()
        self.query_one("#feat-list", ListView).focus()

    # --- 数据 ---

    def _feats(self) -> list:
        try:
            return list(self.feat_store.all())
        except Exception:                        # noqa: BLE001
            return []

    def _load_list(self) -> None:
        lv = self.query_one("#feat-list", ListView)
        lv.index = None
        lv.clear()
        feats = self._feats()
        for f in feats:
            lv.append(FeatItem(f))
        if feats:
            lv.index = 0
        self._refresh_detail()

    def _current_feat(self):
        lv = self.query_one("#feat-list", ListView)
        idx = lv.index
        feats = self._feats()
        if idx is None or idx < 0 or idx >= len(feats):
            return None
        return feats[idx]

    # --- 详情 ---

    def _refresh_detail(self) -> None:
        body = self.query_one("#feat-detail-body", Static)
        feat = self._current_feat()
        if feat is None:
            self._rows = []
            self._cursor = 0
            body.update(Text("（无 feat，用 pdm feat new 创建）", style="dim"))
            self._update_hint()
            return

        self._rows = feat_core.review_rows(feat)
        self._cursor = max(0, min(self._cursor, len(self._rows) - 1))

        t = Text()
        t.append(f"{getattr(feat, 'slug', '?')}\n", style="bold yellow")
        title = getattr(feat, "title", "")
        if title:
            t.append(f"{title}\n", style="bold")
        t.append("\n")

        if not self._rows:
            t.append("（无可审项）\n", style="dim")
        else:
            for i, (key, label, reviewed, tested) in enumerate(self._rows):
                if i == self._cursor:
                    t.append("▶ ", style="bold cyan")
                else:
                    t.append("  ")
                t.append(f"[{_MARK[reviewed]}][{_MARK[tested]}] ", style="green")
                t.append(f"{key:<12}", style="cyan")
                t.append(f"{label}\n", style="dim")

        self._show_comment_note(feat, t)
        body.update(t)
        self._update_hint()

    def _show_comment_note(self, feat, t: Text) -> None:
        """展示已有评论（只读；编辑是另一个 feat）。"""
        try:
            commented = list(feat.commented_items())
        except Exception:                        # noqa: BLE001
            return
        if not commented:
            return
        t.append("\n评论\n", style="bold")
        for ref in commented:
            t.append(f"  {ref.key}  ", style="cyan")
            t.append(f"{feat.comment(ref.key)}\n", style="dim")

    def _update_hint(self) -> None:
        if not self._rows:
            text = "无可审项   Esc 关闭"
        else:
            key, _label, reviewed, tested = self._rows[self._cursor]
            text = (f"{key}  [审]{_MARK[reviewed]} [测]{_MARK[tested]}   "
                    f"空格 勾审   t 勾测   ↑/↓ 选择   Esc 关闭")
        self.query_one("#feat-hint", Static).update(text)

    # --- actions ---

    def action_close(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self._move_cursor(1)

    def action_cursor_up(self) -> None:
        self._move_cursor(-1)

    def _move_cursor(self, delta: int) -> None:
        """上下移动：优先移动「可审项光标」，到头再切 feat。"""
        if self._rows:
            new = self._cursor + delta
            if 0 <= new < len(self._rows):
                self._cursor = new
                self._refresh_detail()
                return
        lv = self.query_one("#feat-list", ListView)
        idx = lv.index if lv.index is not None else -1
        feats = self._feats()
        new_idx = max(0, min(len(feats) - 1, idx + delta))
        if new_idx != idx:
            self._cursor = 0
            lv.index = new_idx
            self._refresh_detail()

    def action_toggle_review(self) -> None:
        self._toggle("review")

    def action_toggle_test(self) -> None:
        self._toggle("test")

    def _toggle(self, field: str) -> None:
        """切换一个勾选位并落盘（唯一写路径）。"""
        feat = self._current_feat()
        if feat is None or not self._rows:
            return
        key = self._rows[self._cursor][0]
        plan = feat_core.plan_toggle(feat, key, field)
        if plan is None:                         # 非法 key/field，不落盘
            return
        slug = getattr(feat, "slug", "")
        kwargs = dict(plan)
        if field == "review":
            kwargs["by"] = self.by                # 作者由调用方决定
        else:
            kwargs["status"] = "passed"
        try:
            self.feat_store.set_reviews(slug, [key], **kwargs)
        except Exception as e:                   # noqa: BLE001
            self.app.errors.append(f"feat review: {e}")   # type: ignore[attr-defined]
            self.notify(f"写入失败：{e}", severity="error")
            return
        self._refresh_detail()
        label = "审" if field == "review" else "测"
        self.notify(f"{key} [{label}] 已更新")

    def on_list_view_highlighted(self, event) -> None:
        if isinstance(event.item, FeatItem):
            self._cursor = 0
            self._refresh_detail()
