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


class FeatOps:
    """Feat 面板的**写操作层**（见 doc/feat/tui-featscreen-split.md）。

    设计约束：**不依赖 Textual 运行时**——

    - 构造只接 ``feat_store`` 与 ``by``；
    - 方法返回 ``(ok, message)``，**不自己调 notify**；
    提示与错误记录由调用方（FeatScreen）负责。

    因此本类可脱离 ``run_test`` 单测（毫秒级，见
    ``tests/tui_new_to_fix/test_feat_ops.py``）。
    """

    def __init__(self, feat_store, by: str = "human") -> None:
        self.feat_store = feat_store
        self.by = by

    # --- 勾选 ---

    def toggle(self, feat, key, field: str):
        """切换一个勾选位并落盘。返回 ``(ok, message)``。

        非法 key/field → ``(False, 说明)``，**不落盘**。
        """
        plan = feat_core.plan_toggle(feat, key, field)
        if plan is None:
            return False, f"不能切换：{key}（{field}）"
        kwargs = dict(plan)
        if field == "review":
            kwargs["by"] = self.by            # 作者由调用方决定
        else:
            kwargs["status"] = "passed"
        slug = getattr(feat, "slug", "")
        try:
            self.feat_store.set_reviews(slug, [key], **kwargs)
        except Exception as e:                # noqa: BLE001
            return False, str(e) or "写入失败"
        label = "审" if field == "review" else "测"
        return True, f"{key} [{label}] 已更新"

    def toggle_review(self, feat, key):
        """切换 ``[审]``。"""
        return self.toggle(feat, key, "review")

    def toggle_test(self, feat, key):
        """切换 ``[测]``。"""
        return self.toggle(feat, key, "test")

    # --- 评论 ---

    def edit_comment(self, feat, key, text):
        """写评论（空串/纯空白 = 清除）。返回 ``(ok, message)``。"""
        normalized = feat_core.plan_comment(text)
        slug = getattr(feat, "slug", "")
        try:
            self.feat_store.set_comment(slug, key, normalized)
        except Exception as e:                # noqa: BLE001
            return False, str(e) or "写入失败"
        return True, f"{key} 评论已{'清除' if not normalized else '保存'}"


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
        Binding("space", "primary_action", "主操作"),
        Binding("t", "toggle_test", "勾选测试"),
        Binding("c", "edit_comment", "评论"),
        Binding("d", "tab_design", "Design", show=False),
        Binding("n", "tab_review", "Review", show=False),
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
        self.ops = FeatOps(feat_store, by=by)   # 写操作层（可独立单测）
        self._tab = "review"                # 当前标签（design|review）；默认 Review 保持兼容
        self._folded: dict = {}               # Design 条目的收起状态
        self._design_cursor = 0               # Design 页的条目光标
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
        """重绘详情。渲染选源**按当前标签分派**；
        两种行模型都是纯函数（见 ``feat_core.detail_lines`` / ``design_lines``）。
        """
        feat = self._current_feat()
        self._rows = feat_core.review_rows(feat) if feat is not None else []
        if self._rows:
            self._cursor = max(0, min(self._cursor, len(self._rows) - 1))
        else:
            self._cursor = 0

        if self._tab == "design":
            filled = self._design_filled_keys(feat)
            self._design_cursor = max(0, min(self._design_cursor,
                                              max(len(filled) - 1, 0)))
            model = feat_core.design_lines(feat, self._folded,
                                           cursor=filled[self._design_cursor]
                                           if filled else None)
        else:
            model = feat_core.detail_lines(feat, self._rows,
                                           self._cursor, _MARK)
        t = Text()
        for line in model:
            for value, style in line:
                t.append(value, style=style or None)
            t.append("\n")
        self.query_one("#feat-detail-body", Static).update(t)
        self._update_hint()

    def _design_filled_keys(self, feat) -> list:
        """有内容的 Design 条目 key（顺序与渲染一致）。

        顺序取自 ``feat_core.design_keys()``（单一真相），
        不在本类重复维护——两处定义漂移会让光标跳到错条目。
        """
        if feat is None:
            return []
        out = []
        for key in feat_core.design_keys():
            value = getattr(feat, key, None)
            if key == "importance":
                if value is not None:
                    out.append(key)
            elif value:
                out.append(key)
        return out

    def _design_cursor_section(self):
        """Design 页当前**可操作**的条目 key（跳过空条目）。

        只返回“有内容”的条目：空条目没有正文，展开/收起没有意义，
        让光标停在那里会让用户按空格却没反应。
        """
        feat = self._current_feat()
        if feat is None:
            return None
        filled = self._design_filled_keys(feat)
        if not filled:
            return None
        idx = max(0, min(self._design_cursor, len(filled) - 1))
        return filled[idx]

    def _update_hint(self) -> None:
        zoom = "[已放大] " if self._zoomed else ""
        if self._zoomed:
            tail = "Enter/z 还原   ↑/↓ 选 feat   Esc 关闭"
            self.query_one("#feat-hint", Static).update(zoom + tail)
            return
        tabs = "[DESIGN] Review" if self._tab == "design" else "DESIGN [Review]"
        if self._tab == "design":
            section = self._design_cursor_section() or ""
            folded = self._folded.get(section, True)
            text = (f"{tabs}   {section} {'收起' if folded else '展开'}   "
                    f"d/n 切标签   空格 展开/收起   ↑/↓ 选条目   Esc 关闭")
        elif not self._rows:
            text = f"{tabs}   无可审项   d/n 切标签   Enter 放大   Esc 关闭"
        else:
            key, _label, reviewed, tested = self._rows[self._cursor]
            text = (f"{tabs}   {key}  [审]{_MARK[reviewed]} [测]{_MARK[tested]}   "
                    f"空格 勾审   t 勾测   d/n 切标签   Enter 放大")
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

        # 焦点在详情：按当前标签分派（Design 移条目光标 / Review 移可审项）
        if self._tab == "design":
            filled = self._design_filled_keys(self._current_feat())
            if not filled:
                return
            # **循环**：到底回顶、到顶去底（与 lazygit 等一致）
            self._design_cursor = (self._design_cursor + delta) % len(filled)
            self._refresh_detail()
            self._scroll_design_cursor_into_view()
            return
        if not self._rows:
            self._detail().scroll_down()
            return
        # Review 页同样循环，与 Design 页保持一致
        self._cursor = (self._cursor + delta) % len(self._rows)
        self._refresh_detail()

    def _scroll_design_cursor_into_view(self) -> None:
        """把 Design 当前条目滚入视野（光标移动后调用）。

        行号由 :func:`feat_core.design_cursor_span` 算（与渲染同一
        份 sections 定义，不会漂移）。
        """
        span = feat_core.design_cursor_span(
            self._current_feat(), self._folded, self._design_cursor_section())
        if span is None:
            return
        start, end = span
        detail = self._detail()
        top = detail.scroll_y
        height = max(detail.size.height, 1)
        bottom = top + height - 1

        # 确保**起始行**落在视口内：上滚到下界、下滚到上界。
        # 注意不能拿 end 对齐顶部（那会把条目滚出视野）。
        if end > bottom:
            # 让条目末尾恰好露出：向上对齐 start，但不能超过条目长度
            target = min(start, max(end - height + 1, 0))
            detail.scroll_to(y=target, animate=False)
        elif start < top:
            detail.scroll_to(y=max(start - 1, 0), animate=False)

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
    def action_primary_action(self) -> None:
        """``空格``：**按当前标签分派**。

        - Review 页：勾选 ``[审]``（原有行为）
        - Design 页：展开/收起当前条目
        """
        if self._tab == "design":
            self._toggle_fold()
        else:
            self._toggle("review")

    @guard
    def action_tab_design(self) -> None:
        """``d``：切到 Design 标签。"""
        self._set_tab("design")

    @guard
    def action_tab_review(self) -> None:
        """``n``：切到 Review 标签。"""
        self._set_tab("review")

    def _set_tab(self, tab: str) -> None:
        if tab == self._tab:
            return
        self._tab = tab
        # Design 页的操作对象是条目（而非左列 feat）：切过去就把焦点
        # 交给详情，否则用户按 j/k 只会切 feat，以为“移动没反应”。
        if tab == "design":
            self._detail().focus()
        self._refresh_detail()

    def _toggle_fold(self) -> None:
        """展开/收起当前 Design 条目。"""
        key = self._design_cursor_section()
        if key is None:
            return
        self._folded[key] = not self._folded.get(key, True)
        self._refresh_detail()

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
        try:
            initial = feat.comment(key) or ""
        except Exception:                        # noqa: BLE001
            initial = ""

        def after(result) -> None:
            if result is None:                   # 取消，不落盘
                return
            ok, msg = self.ops.edit_comment(feat, key, result)
            if not ok:
                self._record_error(f"feat comment: {msg}")
                self.notify(f"写入失败：{msg}", severity="error")
                return
            self._refresh_detail()
            self.notify(msg)

        self.app.push_screen(
            CommentScreen(initial,
                          header=feat_core.comment_header(feat, key)),
            after)

    def _toggle(self, field: str) -> None:
        """切换一个勾选位（写盘委托给 :class:`FeatOps`）。"""
        feat = self._current_feat()
        if feat is None or not self._rows:
            return
        key = self._rows[self._cursor][0]
        ok, msg = self.ops.toggle(feat, key, field)
        if not ok:
            # plan_toggle 返回 None 时也只是“不能切”，不必报错刷屏
            if "不能切换" not in msg:
                self._record_error(f"feat {field}: {msg}")
                self.notify(f"写入失败：{msg}", severity="error")
            return
        self._refresh_detail()
        self.notify(msg)

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


class ThemeScreen(ModalScreen):
    """主题选择器：列出全部主题，回车切换。

    ``dismiss`` 返回主题名（取消返回 ``None``）。

    注意：**不 import 旧包** ``pdev.tui.screens`` —— 旧 TUI 将来要删，
    新包必须自洽。
    """

    CSS = """
    ThemeScreen { align: center middle; background: $background 70%; }
    #theme-box {
        width: 48;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: thick $accent;
        background: $surface;
    }
    #theme-list { height: auto; max-height: 20; }
    ThemeItem { height: 1; padding: 0 1; }
    ThemeItem.--current { background: $accent 40%; }
    #theme-hint { height: 1; color: $text-muted; margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "取消"),
        Binding("q", "cancel", "取消"),
    ]

    def __init__(self, current: str = "") -> None:
        super().__init__()
        self.current = current
        self._names: List[str] = []

    def compose(self) -> ComposeResult:
        self._names = sorted(getattr(self.app, "available_themes", []) or [])
        with Vertical(id="theme-box"):
            items = []
            chosen = 0
            for i, name in enumerate(self._names):
                item = ThemeItem(name, current=(name == self.current))
                if name == self.current:
                    chosen = i
                items.append(item)
            view = ListView(*items, id="theme-list")
            if self._names:
                view.index = chosen
            yield view
            yield Static("Enter 选择   ·   Esc/q 取消", id="theme-hint")

    @guard
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """``ListView`` 的 Selected 事件；Enter 由这里接管。"""
        name = getattr(event.item, "theme_name", None)
        if name:
            self.dismiss(name)

    @guard
    def action_cancel(self) -> None:
        self.dismiss(None)


class ThemeItem(ListItem):
    """主题列表的一行（单行，``●`` 标出当前主题）。"""

    def __init__(self, name: str, current: bool = False) -> None:
        super().__init__()
        self.theme_name = name
        self.current = current
        if current:
            self.add_class("--current")

    def compose(self) -> ComposeResult:
        yield Static(("● " if self.current else "  ") + self.theme_name)
