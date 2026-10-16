#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集 TUI 测试偶发崩溃的现场信息。

背景见 ``doc/feat/tui-test-exit-guard.md``：``pytest`` 跑 Textual
测试后曾以 139（SIGSEGV）退出，但**无法稳定复现**。本脚本把与
"退出阶段崩溃"相关的信息一次性收集起来，方便复发时直接贴进笔记。

设计约束：**采集本身绝不能崩**。任一字段取不到就写 ``unknown``。

用法::

    .venv/bin/python scripts/tui_crash_report.py
"""

from __future__ import annotations

import gc
import os
import platform
import sys
import threading
from pathlib import Path

__all__ = ["collect", "render", "main"]

_UNKNOWN = "unknown"


def _safe(fn, *args, **kwargs):
    """执行取值，任何异常都返回 ``unknown``。"""
    try:
        return fn(*args, **kwargs)
    except Exception:                            # noqa: BLE001
        return _UNKNOWN


def _version_of(modname: str) -> str:
    """取已安装包的版本（不 import，避免副作用）。"""
    try:
        from importlib.metadata import version

        return version(modname)
    except Exception:                            # noqa: BLE001
        return _UNKNOWN


def _fd_count() -> str:
    """当前进程打开的 fd 数（Linux）。"""
    try:
        return str(len(os.listdir("/proc/self/fd")))
    except Exception:                            # noqa: BLE001
        return _UNKNOWN


def _thread_names() -> str:
    try:
        names = [t.name for t in threading.enumerate()]
        return f"{len(names)}: {', '.join(names)}"
    except Exception:                            # noqa: BLE001
        return _UNKNOWN


def _gc_info() -> str:
    """GC 计数三元组与阈值（关闭期 GC 是重点怀疑对象）。"""
    try:
        counts = gc.get_count()
        thresh = gc.get_threshold()
        garbage = len(getattr(gc, "garbage", []) or [])
        return f"count={counts} threshold={thresh} garbage={garbage}"
    except Exception:                            # noqa: BLE001
        return _UNKNOWN


def collect() -> dict:
    """采集现场信息。任一字段失败写 ``unknown``，**不抛异常**。"""
    return {
        "python": _safe(lambda: sys.version.replace("\n", " ")),
        "executable": _safe(lambda: sys.executable),
        "platform": _safe(platform.platform),
        "flags": _safe(lambda: f"sys.flags.dev_mode={sys.flags.dev_mode} "
                               f"argv={sys.argv}"),
        "textual": _version_of("textual"),
        "pytest": _version_of("pytest"),
        "pytest_asyncio": _version_of("pytest-asyncio"),
        "gc_counts": _safe(_gc_info),
        "threads": _safe(_thread_names),
        "fds": _safe(_fd_count),
        "command": _safe(lambda: " ".join(
            [Path(sys.executable).name, "scripts/check_test_exit.py",
             "tests/tui_new_to_fix/", "--runs", "5"])),
    }


def render(info: dict) -> str:
    """dict -> 可直接粘贴的报告文本。缺字段写 ``unknown``。"""
    order = [
        ("python", "Python"),
        ("executable", "解释器"),
        ("platform", "平台"),
        ("flags", "sys.flags"),
        ("textual", "textual 版本"),
        ("pytest", "pytest 版本"),
        ("pytest_asyncio", "pytest-asyncio 版本"),
        ("gc_counts", "GC"),
        ("threads", "线程"),
        ("fds", "打开 fd 数"),
        ("command", "复现命令"),
    ]
    lines = ["=== TUI 测试崩溃现场 ==="]
    for key, label in order:
        value = info.get(key, _UNKNOWN)
        if value is None:
            value = _UNKNOWN
        lines.append(f"{label:18s}: {value}")
    lines.append("")
    lines.append("提示：退出阶段崩溃重点看 GC / 线程 / sys.flags.dev_mode；")
    lines.append("     曾观察到 -X dev 下不崩、普通模式下偶发。")
    return "\n".join(lines)


def main(argv=None) -> int:
    """打印报告。"""
    print(render(collect()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
