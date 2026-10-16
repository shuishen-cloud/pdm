# -*- coding: utf-8 -*-
"""Feat 面板的纯函数内核。

**不 import textual**：全部是可单测的纯逻辑，测试毫秒级完成。

写操作在 **screens.py**（调 ``FeatStore.set_reviews``），这里只做
**取数与校验决策**——不落盘、不抛异常。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

__all__ = ["review_rows", "plan_toggle", "plan_comment",
           "comment_header", "detail_lines", "design_lines",
           "design_cursor_span",
           "feat_line", "feat_line_text", "REVIEW_FIELDS"]

#: 允许切换的字段（白名单，与 web-ui-review 一致）。
REVIEW_FIELDS = ("review", "test")


def review_rows(feat) -> List[Tuple[str, str, bool, bool]]:
    """把 feat 的可审项拆成 ``(key, label, reviewed, tested)``。

    供列表渲染与断言。无 ``review_items()``、或该 feat 没有可审项时
    返回 ``[]``，**不抛异常**（app 层可能传入各种对象）。
    """
    try:
        items = list(feat.review_items())
    except Exception:                            # noqa: BLE001
        return []
    out: List[Tuple[str, str, bool, bool]] = []
    for ref in items:
        key = getattr(ref, "key", "")
        if not key:
            continue
        rec = None
        try:
            rec = feat.review_item(key)
        except Exception:                        # noqa: BLE001
            rec = None
        out.append((
            key,
            getattr(ref, "label", "") or "",
            bool(getattr(rec, "reviewed", False)),
            bool(getattr(rec, "tested", False)),
        ))
    return out


def is_reviewable(feat, key) -> bool:
    """``key`` 是否是该 feat 的合法可审项。"""
    if not isinstance(key, str) or not key:
        return False
    return any(row[0] == key for row in review_rows(feat))


def plan_comment(text) -> str:
    """规范化评论文本，供 ``set_comment`` 使用。

    - ``None`` / 非 ``str`` / 全空白 → ``""``（表示**清除**该条评论）
    - 其余 → 去掉首尾空白（保留内部换行）

    纯函数：不落盘、不抛异常。与 CLI 的 ``--clear`` 语义一致：
    空串即删除，不会把空字符串写进 JSON。
    """
    if not isinstance(text, str):
        return ""
    stripped = text.strip()
    return stripped


def comment_header(feat, key: str) -> List[Tuple[str, str]]:
    """编辑框顶部要显示的条目详细信息：``[(字段名, 值), ...]``。

    包含：feat slug / 标题 / 条目 key / 条目内容(label) / 勾选状态。
    纯函数，不抛异常；缺什么就跳过什么。
    """
    out: List[Tuple[str, str]] = []

    slug = getattr(feat, "slug", "")
    if slug:
        out.append(("feat", slug))
    title = getattr(feat, "title", "")
    if title:
        out.append(("标题", title))
    if key:
        out.append(("条目", key))

    # 条目内容 + 勾选状态从可审项表里取
    label, reviewed, tested = "", False, False
    for row_key, row_label, row_reviewed, row_tested in review_rows(feat):
        if row_key == key:
            label, reviewed, tested = row_label, row_reviewed, row_tested
            break
    if label:
        out.append(("内容", label))
    if key:
        out.append(("状态",
                    f"[审]{'■' if reviewed else '□'} "
                    f"[测]{'■' if tested else '□'}"))
    return out


def detail_lines(feat, rows, cursor: int, mark) -> List[List[tuple]]:
    """组装右侧详情的**行模型**：``[[(text, style), ...], ...]``。

    外层是行，内层是该行的若干片段（一行可拼多种颜色），
    与界面的逐段 append 一一对应。

    纯函数（无 textual 依赖）：渲染细节可毫秒级单测。
    ``mark`` 是 ``{True: "■", False: "□"}``（由调用方传入，
    保持界面层的单一真相）。

    ``feat is None`` → 提示行；``rows`` 为空 → “无可审项”。
    """
    if feat is None:
        return [[("（无 feat，用 pdm feat new 创建）", "dim")]]

    lines: List[List[tuple]] = [
        [(str(getattr(feat, "slug", "?")), "bold yellow")],
    ]
    title = getattr(feat, "title", "")
    if title:
        lines.append([(str(title), "bold")])
    lines.append([("", "")])

    if not rows:
        lines.append([("（无可审项）", "dim")])
        return lines

    for i, (key, label, reviewed, tested) in enumerate(rows):
        on_cursor = i == cursor
        line: List[tuple] = []
        line.append(("▶ " if on_cursor else "  ",
                     "bold cyan" if on_cursor else ""))
        line.append((f"[{mark[reviewed]}][{mark[tested]}] ", "green"))
        line.append((f"{key:<12}", "cyan"))
        line.append((str(label), "dim"))
        lines.append(line)
        for cl in _comment_lines(feat, key):
            lines.append([cl])
    return lines


def _comment_lines(feat, key: str) -> List[tuple]:
    """评论缩进显示在自己条目下方（多行逐行）。"""
    try:
        text = feat.comment(key) or ""
    except Exception:                            # noqa: BLE001
        return []
    if not text:
        return []
    return [("      │ " + line, "dim") for line in (text.splitlines() or [""])]


def design_lines(feat, folded=None, cursor=None) -> List[List[tuple]]:
    """Design 标签页的行模型（**可折叠条目**）：``[[(text, style), ...]]``。

    每个条目：收起时只显示 ``▸ 标题  (N 行)``，展开时逐行显示正文。
    ``folded`` 是 ``{section_key: bool}``（None = 全部收起）；
    ``cursor`` 是当前高亮条目的 key（None = 不高亮任何条目）。

    纯函数：折叠/分组/行数统计可毫秒级单测。
    """
    if feat is None:
        return [[("（无 feat）", "dim")]]
    folded = folded or {}
    lines: List[List[tuple]] = []

    for key, title, value in _design_sections(feat):
        body = _section_body(value)
        on_cursor = key == cursor
        prefix = "▶ " if on_cursor else ""
        head_style = "bold cyan" if on_cursor else "bold"
        if not body:                     # 空条目：标题仍显示，标注未填
            lines.append([(f"{prefix}▸ {title}", head_style),
                          ("  （未填）", "dim")])
            continue
        is_folded = folded.get(key, True)      # 默认收起
        arrow = "▸" if is_folded else "▾"
        mark = f"  ({len(body)} 行)" if is_folded else ""
        lines.append([(f"{prefix}{arrow} {title}", head_style), (mark, "dim")])
        if not is_folded:
            for row in body:
                lines.append([(f"    {row}", "")])
    return lines


def _importance_text(feat) -> str:
    imp = getattr(feat, "importance", None)
    if imp is None:
        return ""
    label = getattr(imp, "label", "")
    value = getattr(imp, "value", imp)
    return f"{value}（{label}）" if label else str(value)


def design_cursor_span(feat, folded=None, cursor=None):
    """当前条目的**行范围** ``(start, end)``（0 起，含首尾）。

    用于移动光标后把该条目滚入视野。行号算法与
    :func:`design_lines` **共用同一份 sections 定义**（避免两处漂移）。

    找不到（无 feat / cursor 为空）返回 ``None``。
    """
    if feat is None or cursor is None:
        return None
    folded = folded or {}
    line = 0
    for key, title, value in _design_sections(feat):
        body = _section_body(value)
        if not body:
            height = 1                       # 空条目也占一行（“未填”）
        else:
            height = 1 if folded.get(key, True) else 1 + len(body)
        if key == cursor:
            return line, line + height - 1
        line += height
    return None


def _design_sections(feat):
    """Design 页的条目定义：``[(key, 标题, 值), ...]``。

    **单一真相**：``design_lines`` 与 ``design_cursor_span`` 都用它，
    保证“渲染出的行”与“算出的行号”不会漂移。
    """
    return [
        ("design_note", "设计思路", getattr(feat, "design_note", "")),
        ("impl_note", "实现方式", getattr(feat, "impl_note", "")),
        ("test_note", "测试方式", getattr(feat, "test_note", "")),
        ("debug_note", "调试方式", getattr(feat, "debug_note", "")),
        ("extend_note", "如何扩展", getattr(feat, "extend_note", "")),
        ("impact", "影响面", getattr(feat, "impact", "")),
        ("importance", "重要性", _importance_text(feat)),
        ("data_model", "数据结构", getattr(feat, "data_model", []) or []),
        ("samples", "样例值", getattr(feat, "samples", []) or []),
        ("api", "交付接口", getattr(feat, "api", []) or []),
        ("logs", "日志", getattr(feat, "logs", []) or []),
        ("fallbacks", "异常兜底", getattr(feat, "fallbacks", []) or []),
    ]


def _section_body(value) -> List[str]:
    """把字段值统一成“若干行文本”（空值 → ``[]``）。"""
    if not value:
        return []
    if isinstance(value, str):
        return value.splitlines() or []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def feat_line(feat, width: int = 0) -> tuple:
    """左列一条 feat 的 ``(marker, slug, tail)``（强制单行，超出截断）。

    ``width`` > 0 时按显示宽度截断（CJK 算 2 列），保证永不折行；
    0 表示不限。返回分段而不是拼好的字符串，避免调用方
    再“猜”如何拆回来。
    """
    from .core import display_width, ellipsize

    status = getattr(getattr(feat, "status", None), "value", "?")
    slug = getattr(feat, "slug", "?")
    tail = f"  {status}"
    try:
        counts = feat.review_counts()
        tail += f"  审 {counts.reviewed}/{counts.total}"
    except Exception:                            # noqa: BLE001
        pass

    marker = "● "
    if width > 0:
        avail = width - display_width(marker) - display_width(tail)
        slug = ellipsize(slug, max(avail, 1))
    return marker, slug, tail


def feat_line_text(feat, width: int = 0) -> str:
    """拼接后的纯文本形式（测试断言用）。"""
    return "".join(feat_line(feat, width))


def plan_toggle(feat, key, field) -> Optional[dict]:
    """校验并算出 ``FeatStore.set_reviews`` 的 kwargs；非法返回 ``None``。

    - ``field`` ∉ :data:`REVIEW_FIELDS` → ``None``
    - ``key`` 不在该 feat 的可审项中 → ``None``
    - 合法 → ``{"reviewed": bool}`` 或 ``{"tested": bool}``（**取反**当前值）

    纯函数：不落盘、不抛异常。只返回**一个**字段，不会顺带改另一位。
    """
    if field not in REVIEW_FIELDS:
        return None
    rows = review_rows(feat)
    for row_key, _label, reviewed, tested in rows:
        if row_key != key:
            continue
        if field == "review":
            return {"reviewed": not reviewed}
        return {"tested": not tested}
    return None
