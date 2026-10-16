# -*- coding: utf-8 -*-
"""Feat 面板的纯函数内核。

**不 import textual**：全部是可单测的纯逻辑，测试毫秒级完成。

写操作在 **screens.py**（调 ``FeatStore.set_reviews``），这里只做
**取数与校验决策**——不落盘、不抛异常。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

__all__ = ["review_rows", "plan_toggle", "plan_comment", "comment_rows",
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


def comment_rows(feat) -> List[Tuple[str, str, str]]:
    """带非空评论的可审项：``(key, label, comment)``。

    按可审项顺序；无评论或 ``feat`` 不完整时返回 ``[]``（不抛异常）。
    """
    try:
        items = list(feat.commented_items())
    except Exception:                            # noqa: BLE001
        return []
    out: List[Tuple[str, str, str]] = []
    for ref in items:
        key = getattr(ref, "key", "")
        if not key:
            continue
        try:
            text = feat.comment(key)
        except Exception:                        # noqa: BLE001
            text = ""
        if text:
            out.append((key, getattr(ref, "label", "") or "", text))
    return out


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
