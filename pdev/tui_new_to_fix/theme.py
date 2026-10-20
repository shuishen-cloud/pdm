# -*- coding: utf-8 -*-
"""主题名归一化与循环（**不 import textual**，可毫秒级测）。

见 ``doc/feat/tui-theme.md``。本模块只接字符串列表：

- :func:`normalize` 把配置里的主题名映射成 Textual 的规范名，
  匹配不到就回退 :data:`DEFAULT_THEME`（Catppuccin Macchiato）；
- :func:`next_theme` 供 ``t`` 键循环切换。

**为什么不写在 app.py**：``import textual`` 在纯函数测试层是被禁止的
（见 ``doc/tui-new-to-fix.md`` 的测试预算），归一化逻辑必须能单独测。
"""

from __future__ import annotations

from typing import Iterable, Optional

__all__ = ["DEFAULT_THEME", "normalize", "is_known", "next_theme"]

#: 未配置 / 名字无效时的主题。也是本项目推荐主题。
DEFAULT_THEME = "catppuccin-macchiato"

_SEPARATORS = ("_", " ", ".")


def _key(name: object) -> str:
    """比较用的键：小写，且把 ``_`` / 空格 / ``.`` 都当 ``-``。

    这样 ``Catppuccin Macchiato`` / ``catppuccin_macchiato`` 都能命中
    ``catppuccin-macchiato``——用户手敲配置时几乎必然会踩这个坑。
    """
    if not isinstance(name, str):
        return ""
    return _norm(str(name))


def _norm(text: str) -> str:
    for sep in _SEPARATORS:
        text = text.replace(sep, "-")
    return "-".join(part for part in text.lower().split("-") if part)


def _canonical(name: object, names: Iterable[str]) -> Optional[str]:
    """在 ``names`` 里找 ``name`` 的规范写法；找不到返回 ``None``。"""
    key = _key(name)
    if not key:
        return None
    for candidate in names:
        if _key(candidate) == key:
            return candidate
    return None


def is_known(name: object, names: Iterable[str]) -> bool:
    """``name`` 是否为 ``names`` 中的主题（大小写 / 分隔符不敏感）。"""
    return _canonical(name, names) is not None


def normalize(name: object, names: Iterable[str]) -> str:
    """把任意写法映射成规范主题名；无效则返回 :data:`DEFAULT_THEME`。

    ``names`` 为空（textual 未安装 / 取不到主题表）时**也**返回默认值，
    不抛异常。
    """
    names = list(names or [])
    found = _canonical(name, names)
    if found:
        return found
    found = _canonical(DEFAULT_THEME, names)
    return found or DEFAULT_THEME


def next_theme(current: object, names: Iterable[str]) -> str:
    """``current`` 的下一个主题（列表末尾回绕）。

    - 列表为空 → 默认主题；
    - ``current`` 不在列表里 → **默认主题**本身（不静默 no-op，
      否则用户按 ``t`` 会“没反应”）；默认主题也不在列表里 → 列表首项。
    """
    names = sorted(names or [])
    if not names:
        return DEFAULT_THEME
    cur = _canonical(current, names)
    if cur is None:
        return _canonical(DEFAULT_THEME, names) or names[0]
    return names[(names.index(cur) + 1) % len(names)]
