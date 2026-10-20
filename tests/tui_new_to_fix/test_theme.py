# -*- coding: utf-8 -*-
"""主题名归一化的纯函数测试。

**不 import textual**，毫秒级完成（见 ``doc/feat/tui-theme.md``）。
"""

from __future__ import annotations

import time

from pdev.tui_new_to_fix import theme

NAMES = [
    "catppuccin-latte",
    "catppuccin-macchiato",
    "catppuccin-mocha",
    "dracula",
    "nord",
]

_T0 = time.perf_counter()


# --- 默认值 -----------------------------------------------------------------


def test_default_is_macchiato():
    assert theme.DEFAULT_THEME == "catppuccin-macchiato"
    assert theme.DEFAULT_THEME in NAMES


# --- is_known ---------------------------------------------------------------


def test_is_known_exact():
    assert theme.is_known("nord", NAMES) is True


def test_is_known_normalizes_spaces_and_case():
    """``Catppuccin Macchiato`` 是用户最可能手敲的写法。"""
    assert theme.is_known("Catppuccin Macchiato", NAMES) is True


def test_is_known_normalizes_underscore():
    assert theme.is_known("catppuccin_macchiato", NAMES) is True


def test_is_known_rejects_unknown_and_empty():
    assert theme.is_known("no-such", NAMES) is False
    assert theme.is_known("", NAMES) is False
    assert theme.is_known(None, NAMES) is False


# --- normalize --------------------------------------------------------------


def test_normalize_returns_canonical_case():
    assert theme.normalize("NORD", NAMES) == "nord"
    assert theme.normalize("Catppuccin Macchiato", NAMES) == "catppuccin-macchiato"


def test_normalize_falls_back_for_unknown():
    assert theme.normalize("no-such", NAMES) == theme.DEFAULT_THEME
    assert theme.normalize("", NAMES) == theme.DEFAULT_THEME
    assert theme.normalize(None, NAMES) == theme.DEFAULT_THEME
    assert theme.normalize(42, NAMES) == theme.DEFAULT_THEME


def test_normalize_tolerates_empty_theme_list():
    """textual 没装 / 拿不到主题表时也不能抛。"""
    assert theme.normalize("nord", []) == theme.DEFAULT_THEME
    assert theme.is_known("nord", []) is False


def test_normalize_keeps_valid_config_theme():
    """配置里写的主题名原样生效（这是本 feat 的主诉求）。"""
    assert theme.normalize("nord", NAMES) == "nord"


# --- next_theme -------------------------------------------------------------


def test_next_theme_wraps():
    assert theme.next_theme("nord", ["dracula", "nord"]) == "dracula"


def test_next_theme_moves_forward():
    assert theme.next_theme("dracula", ["dracula", "nord"]) == "nord"


def test_next_theme_unknown_starts_from_default():
    assert theme.next_theme("bogus", NAMES) == theme.normalize(
        theme.DEFAULT_THEME, NAMES
    )


def test_next_theme_empty_list():
    assert theme.next_theme("nord", []) == theme.DEFAULT_THEME


def test_next_theme_is_total():
    """任何一个主题出发，循环 len(names) 次都回到自己。"""
    for name in NAMES:
        cur = name
        for _ in range(len(NAMES)):
            cur = theme.next_theme(cur, NAMES)
        assert cur == name, f"{name} 的循环没有闭合"


def test_budget():
    """本文件必须 < 0.2s（import 不算在内）。"""
    elapsed = time.perf_counter() - _T0
    assert elapsed < 0.2, f"纯函数测试太慢：{elapsed:.3f}s"
