# -*- coding: utf-8 -*-
"""退出门禁与现场采集的测试。

对应 ``doc/feat/tui-test-exit-guard.md``。两个脚本都只用标准库，
不依赖 textual，因此本文件可在任何环境跑。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"


def _load(name: str):
    """按路径加载 ``scripts/`` 下的脚本（它们不是包）。"""
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    return mod


exit_guard = _load("check_test_exit")
crash = _load("tui_crash_report")


# --- classify：退出码语义 ---------------------------------------------------


def test_classify_codes():
    """0 = 全过；1 = 有用例失败（**合法**）；其余 = 门禁失败。"""
    assert exit_guard.classify(0) == "ok"
    assert exit_guard.classify(1) == "tests-failed"
    for code in (2, 3, 5, 130, 139, 255):
        assert exit_guard.classify(code) == "exit-guard-failure", code


def test_classify_negative_means_signal():
    """被信号杀死时 subprocess 给负数（-11 = SIGSEGV），必须判为失败。"""
    assert exit_guard.classify(-11) == "exit-guard-failure"
    assert exit_guard.classify(-9) == "exit-guard-failure"


def test_classify_is_pure():
    """纯函数：多次调用结果一致，且不改动入参。"""
    assert exit_guard.classify(0) == exit_guard.classify(0) == "ok"


# --- 现场采集 ---------------------------------------------------------------


def test_collect_has_key_fields():
    """采集结果必须含排查所需的关键字段。"""
    info = crash.collect()
    for key in ("python", "flags", "textual", "pytest",
                "gc_counts", "threads", "fds", "command"):
        assert key in info, f"缺少字段：{key}"


def test_collect_never_raises():
    """采集脚本本身不能崩（这是它的存在意义）。"""
    info = crash.collect()
    assert isinstance(info, dict)


def test_render_mentions_all_fields():
    """报告文本要把字段都体现出来（便于直接粘贴）。"""
    info = crash.collect()
    text = crash.render(info)
    for key in ("python", "textual", "gc", "thread", "fd"):
        assert key in text.lower(), f"报告里没有 {key}"


def test_render_survives_missing_fields():
    """字段缺失时写 unknown，而不是抛 KeyError。"""
    text = crash.render({})
    assert "unknown" in text.lower()


def test_render_handles_weird_values():
    """值类型意外（如 None / 对象）也不能炸。"""
    text = crash.render({"python": None, "gc_counts": object(), "fds": "?"})
    assert isinstance(text, str) and text


# --- 门禁脚本的用法校验 -----------------------------------------------------


def test_exit_guard_rejects_bad_runs():
    """--runs 非法时以退出码 2 结束。

    非整数由 argparse 直接 `SystemExit(2)`；<=0 由我们返回 2。
    两者对调用方都是“用法错误”，退出码一致。
    """
    assert exit_guard.main(["tests/tui_new_to_fix/test_core.py",
                            "--runs", "0"]) == 2
    import pytest

    with pytest.raises(SystemExit) as exc:
        exit_guard.main(["tests/tui_new_to_fix/test_core.py", "--runs", "abc"])
    assert exc.value.code == 2


def test_exit_guard_rejects_missing_path():
    """目标路径不存在时返回 2。"""
    assert exit_guard.main(["tests/__no_such_file__.py"]) == 2
