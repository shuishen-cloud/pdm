# -*- coding: utf-8 -*-
"""Feat 面板（ModalScreen）：两栏浏览 + 审查勾选 + 条目评论。

新 TUI 的两个写操作都在这里，约束见：

- ``doc/feat/tui-feat-review.md``：勾选
- ``doc/feat/tui-feat-comment.md``：评论

共同点：

- 写入只走 ``FeatStore.set_reviews()`` / ``set_comment()``
  （CLI 的同一条路径），不直接改 JSON。
- 校验与规范化逻辑在 :mod:`pdev.tui_new_to_fix.feat_core`（纯函数，可单测）。
- 所有 action / 回调必须包 ``@guard``（漏包会让整个 TUI 退出）。
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from . import core, feat_core
from .guard import guard

__all__ = ["FeatScreen", "CommentScreen"]

_MARK = {True: "■", False: "□"}


def _feat_line(feat, width: int = 0) -> Text:
    """左列：一条 feat（**强制单行**，超出截断）。

    渲染逻辑在 :func:`feat_core.feat_line`（纯函数，可毫秒级测）；
    这里只负责套上 rich 颜色。
    """
    t = Text()
    marker, slug, tail = feat_core.feat_line(feat, width)
    t.append(marker, style="bold")
    t.append(slug, style="bold yellow")
    t.append(tail, style="dim")
    return t


class FeatItem(ListItem):
    """左列的一项。"""

    def __init__(self, feat) -> None:
        super().__init__()
        self.feat = feat

    def render(self) -> Text:
        """按列表当前宽度截断，保证**单行**。"""
        width = self.size.width or 32
        return _feat_line(self.feat, width)


class FeatList(ListView):
    """左列 feat 列表。

    关键是拦截 ``Enter``：``ListView`` 会把它当“选中”吃掉，
    导致放大快捷键收不到（实测 ``action_toggle_zoom`` 触发 0 次）。
    """

    def key_enter(self) -> bool:
        """Enter 在被 ListView 消化前转给 FeatScreen 放大。"""
        screen = getattr(self, "screen", None)
        action = getattr(screen, "action_toggle_zoom", None)
        if action is not None:
            action()
            return True
        return False


class CommentScreen(ModalScreen):
    """条目评论编辑弹窗（**多行**，所以用 TextArea）。

    - 顶部显示**正在编辑的条目详细信息**（feat / 标题 / 条目 / 内容 / 状态）。
    - ``Ctrl+S`` 保存，``Esc`` 取消。
    - ``dismiss`` 返回 ``str``（保存，空串 = 清除）或 ``None``（取消）。
    - 独立弹窗的意义：文本框的字母/回车不会污染 FeatScreen 的
      ``j``/``k``/``空格``/``t``。
    """

    CSS = """
    CommentScreen { align: center middle; background: $surface 70%; }
    #comment-box {
        width: 80%;
        height: 70%;
        padding: 0 1;
        border: thick $accent;
        background: $surface;
    }
    #comment-title { height: auto; }
    #comment-text { height: 1fr; }
    #comment-hint { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "保存"),
        Binding("escape", "cancel", "取消"),
    ]

    def __init__(self, initial: str = "", header=None) -> None:
        """
        :param initial: 已有评论（空串表示新建）
        :param header: ``[(字段名, 值), ...]``，由 ``feat_core.comment_header`` 生成
        """
        super().__init__()
        self._initial = initial or ""
        self._header = list(header or [])

    def _header_text(self) -> Text:
        """顶部信息块（无 header 时退回一行提示）。"""
        t = Text()
        if not self._header:
            t.append("编辑评论", style="bold")
            return t
        for i, (name, value) in enumerate(self._header):
            if i:
                t.append("\n")
            t.append(f"{name}  ", style="dim")
            style = "bold yellow" if name in ("feat", "条目") else ""
            t.append(value, style=style)
        return t

    def compose(self) -> ComposeResult:
        from textual.widgets import TextArea

        with Vertical(id="comment-box"):
            yield Static(self._header_text(), id="comment-title")
            yield TextArea(self._initial, id="comment-text")
            yield Static("Ctrl+S 保存 · Esc 取消 · 留空=清除 · 回车换行",
                         id="comment-hint")

    @guard
    def on_mount(self) -> None:
        from textual.widgets import TextArea

        self.query_one("#comment-text", TextArea).focus()

    @guard
    def action_save(self) -> None:
        from textual.widgets import TextArea

        text = self.query_one("#comment-text", TextArea).text
        self.dismiss(text)

    @guard
    def action_cancel(self) -> None:
        self.dismiss(None)


class FeatScreen(ModalScreen):
    """两栏 feat 浏览 + 审查勾选。

    - ``↑``/``↓`` 或 ``j``/``k`` 选 feat／移动可审项
    - ``←``/``→`` 或 ``h``/``l`` / ``Tab`` 切焦点
    - ``空格`` 切换 ``[审]``、``t`` 切换 ``[测]``（作用于**当前高亮可审项**）
    - ``Enter`` / ``z`` 放大左侧 feat 列表（占满宽度，看全长 slug）
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
    /* 放大：列表占满，详情隐藏 */
    #feat-body.list-zoomed #feat-list { width: 1fr; }
    #feat-body.list-zoomed #feat-detail { display: none; }
    /* 关键：列表项必须单行（否则长 slug 会折成多行） */
    FeatItem { height: 1; padding: 0 1; }
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
        Binding("c", "edit_comment", "评论"),
        Binding("enter", "toggle_zoom", "放大列表"),
        Binding("z", "toggle_zoom", "放大列表", show=False),
        Binding("right", "focus_detail", "右移", show=False),
        Binding("l", "focus_detail", "右移", show=False),
        Binding("left", "focus_list", "左移", show=False),
        Binding("h", "focus_list", "左移", show=False),
        Binding("tab", "focus_toggle", "切焦点", show=False),
        Binding("pagedown", "detail_page_down", "翻页", show=False),
        Binding("pageup", "detail_page_up", "翻页", show=False),
    ]

    def __init__(self, feat_store, by: str = "human") -> None:
        super().__init__()
        self.feat_store = feat_store
        self.by = by
        self._rows: List[tuple] = []      # 当前 feat 的可审项
        self._cursor = 0                  # 当前高亮的可审项下标
        self._zoomed = False              # 左列是否已放大

    # --- 布局 ---

    def compose(self) -> ComposeResult:
        with Vertical(id="feat-box"):
            yield Static("Feat（开发记录）· 空格 勾审 · t 勾测 · Esc 关闭",
                         id="feat-title")
            with Horizontal(id="feat-body"):
                yield FeatList(id="feat-list")
                with VerticalScroll(id="feat-detail"):
                    yield Static("", id="feat-detail-body")
            yield Static("", id="feat-hint")

    @guard
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
                self._append_comment(t, feat, key)

        body.update(t)
        self._update_hint()

    def _append_comment(self, t: Text, feat, key: str) -> None:
        """把该条目的评论**缩进显示在自己的条目下方**（多行逐行）。"""
        try:
            text = feat.comment(key) or ""
        except Exception:                        # noqa: BLE001
            return
        if not text:
            return
        for line in text.splitlines() or [""]:
            t.append("      │ ", style="dim cyan")
            t.append(f"{line}\n", style="dim")

    def _update_hint(self) -> None:
        zoom = "[已放大] " if self._zoomed else ""
        if self._zoomed:
            tail = "Enter/z 还原   ↑/↓ 选 feat   Esc 关闭"
            self.query_one("#feat-hint", Static).update(zoom + tail)
            return
        if not self._rows:
            text = "无可审项   Enter 放大   Esc 关闭"
        else:
            key, _label, reviewed, tested = self._rows[self._cursor]
            text = (f"{key}  [审]{_MARK[reviewed]} [测]{_MARK[tested]}   "
                    f"空格 勾审   t 勾测   ←/→ 切焦点   Enter 放大")
        self.query_one("#feat-hint", Static).update(zoom + text)

    # --- actions ---

    @guard
    def action_close(self) -> None:
        self.dismiss(None)

    @guard
    def action_cursor_down(self) -> None:
        self._move_cursor(1)

    @guard
    def action_cursor_up(self) -> None:
        self._move_cursor(-1)

    def _is_list_focused(self) -> bool:
        return self.focused is self.query_one("#feat-list", ListView)

    def _detail(self):
        return self.query_one("#feat-detail", VerticalScroll)

    def _move_cursor(self, delta: int) -> None:
        """上下移动，**按焦点区分语义**（修复之前混在一起的问题）：

        - 焦点在左列：切换选中的 feat
        - 焦点在详情：移动可审项光标，并滚动详情让它可见
        """
        if self._is_list_focused():
            lv = self.query_one("#feat-list", ListView)
            idx = lv.index if lv.index is not None else -1
            feats = self._feats()
            new_idx = max(0, min(len(feats) - 1, idx + delta))
            if new_idx != idx:
                self._cursor = 0
                lv.index = new_idx
                self._refresh_detail()
            return

        # 焦点在详情：移动可审项光标
        if not self._rows:
            self._detail().scroll_down()
            return
        new = self._cursor + delta
        if 0 <= new < len(self._rows):
            self._cursor = new
            self._refresh_detail()

    @guard
    def action_toggle_zoom(self) -> None:
        """Enter / z：放大左列（占满宽度，看全长 slug），再按还原。"""
        body = self.query_one("#feat-body")
        self._zoomed = not self._zoomed
        if self._zoomed:
            body.add_class("list-zoomed")
            self._detail().blur()
            self.query_one("#feat-list", ListView).focus()
        else:
            body.remove_class("list-zoomed")
        self._update_hint()

    @guard
    def action_focus_list(self) -> None:
        """左移：焦点回左列。"""
        self.query_one("#feat-list", ListView).focus()

    @guard
    def action_focus_detail(self) -> None:
        """右移：焦点切到详情（可滚动）。"""
        self._detail().focus()

    @guard
    def action_focus_toggle(self) -> None:
        """Tab：在左列与详情之间切。"""
        if self._is_list_focused():
            self._detail().focus()
        else:
            self.action_focus_list()

    @guard
    def action_detail_page_down(self) -> None:
        self._detail().focus()
        self._detail().scroll_page_down()

    @guard
    def action_detail_page_up(self) -> None:
        self._detail().focus()
        self._detail().scroll_page_up()

    @guard
    def action_toggle_review(self) -> None:
        self._toggle("review")

    @guard
    def action_toggle_test(self) -> None:
        self._toggle("test")

    @guard
    def action_edit_comment(self) -> None:
        """``c``：编辑当前高亮可审项的评论（弹窗多行输入）。"""
        feat = self._current_feat()
        if feat is None or not self._rows:
            return
        key = self._rows[self._cursor][0]
        slug = getattr(feat, "slug", "")
        try:
            initial = feat.comment(key) or ""
        except Exception:                        # noqa: BLE001
            initial = ""

        def after(result) -> None:
            if result is None:                   # 取消，不落盘
                return
            text = feat_core.plan_comment(result)
            try:
                self.feat_store.set_comment(slug, key, text)
            except Exception as e:               # noqa: BLE001
                self._record_error(f"feat comment: {e}")
                self.notify(f"写入失败：{e}", severity="error")
                return
            self._refresh_detail()
            self.notify(f"{key} 评论已{'清除' if not text else '保存'}")

        self.app.push_screen(
            CommentScreen(initial,
                          header=feat_core.comment_header(feat, key)),
            after)

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
            self._record_error(f"feat review: {e}")
            self.notify(f"写入失败：{e}", severity="error")
            return
        self._refresh_detail()
        label = "审" if field == "review" else "测"
        self.notify(f"{key} [{label}] 已更新")

    def _record_error(self, msg: str) -> None:
        """记入 ``app.errors``（假如有）。**不得抛异常。**"""
        try:
            errors = getattr(self.app, "errors", None)
            if errors is not None:
                errors.append(msg)
        except Exception:                        # noqa: BLE001
            pass

    @guard
    def on_list_view_highlighted(self, event) -> None:
        if isinstance(event.item, FeatItem):
            self._cursor = 0
            self._refresh_detail()
