#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印 pdm 命令的**实际调用链**（谁调用了谁）。

原理：``sys.settrace`` 让解释器在每次函数进入/返回时回调我们，
用 ``frame.f_back`` 往上数出调用深度，从而画出树形调用链。
比手动单步高效：一次跑完，不用点几百次。

用法::

    # 默认目标：打印 pdm 帮助
    .venv/bin/python scripts/trace_calls.py

    # 跟踪一条命令（**调用链打到 stderr**，命令输出仍在 stdout）
    .venv/bin/python scripts/trace_calls.py feat show feat-edit-fields

    # 只保存调用链（丢弃命令自己的输出）
    .venv/bin/python scripts/trace_calls.py feat show x 2>calls.txt

    # --brief 隐藏高频小函数，输出更短
    .venv/bin/python scripts/trace_calls.py --brief feat new ...

    # 看某函数被调用时的局部变量（了解它拿到什么输入）
    .venv/bin/python scripts/trace_calls.py --locals cmd_feat_new feat new ...

    # 限定只跟踪某些模块（匹配的是**相对 root** 的路径）
    .venv/bin/python scripts/trace_calls.py --only cli feat show ...
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

#: 只跟踪这个目录下的文件（其余是标准库/textual/pytest 等噪声）
_DEFAULT_ROOT = "pdev"

#: --brief 时隐藏这些高频小函数（它们会淹没真正的结构）
_BRIEF_SKIP = {
    "_coerce", "_coerce_value", "_read_json", "_apply_segment",
    "__init__", "_is_tty", "getattr", "touch",
}


def _relpath(path: str, root: str) -> str:
    """把绝对路径压成相对 root 的短路径。"""
    try:
        abs_path = os.path.abspath(path)
        abs_root = os.path.abspath(root)
        if abs_path.startswith(abs_root + os.sep):
            return abs_path[len(abs_root) + 1:]
        return os.path.basename(path)
    except Exception:                            # noqa: BLE001
        return path


def _depth_of(frame, root: str) -> int:
    """frame 在**受跟踪目录内**的嵌套深度（0 = 最外层）。

    用 ``f_back`` 往上数，而不是自维护计数器——后者在
    call/return 不配对时会漂移，缩进就乱了。
    """
    abs_root = os.path.abspath(root)
    n, f = 0, frame
    while f is not None:
        try:
            if not os.path.abspath(f.f_code.co_filename).startswith(
                    abs_root + os.sep):
                break
        except Exception:                        # noqa: BLE001
            break
        n += 1
        f = f.f_back
    return max(0, n - 1)


class Tracer:
    """调用链追踪器。"""

    def __init__(self, root: str, brief: bool = False,
                 only: Optional[str] = None,
                 watch_locals: Optional[str] = None,
                 stream=None) -> None:
        self.root = root
        self.abs_root = os.path.abspath(root)
        self.brief = brief
        self.only = only
        self.watch_locals = watch_locals
        # 默认写 stderr：与命令自己的 stdout 分开，便于 `> calls.txt` 单独保存
        self.out = stream or sys.stderr
        self.enabled = False          # 等 import 完再开，过滤 import 噪声
        self.count = 0

    # --- 判定与输出 ---

    def _in_scope(self, frame) -> bool:
        try:
            path = os.path.abspath(frame.f_code.co_filename)
        except Exception:                        # noqa: BLE001
            return False
        if not path.startswith(self.abs_root + os.sep):
            return False
        if self.only:
            # 用**相对 root 的路径**匹配（如 pdev/cli），
            # 不是绝对路径——否则 --only pdev/cli 永远匹不上。
            rel = path[len(self.abs_root) + 1:].replace(os.sep, "/")
            return self.only.replace(os.sep, "/") in rel
        return True

    def _should_show(self, frame) -> bool:
        if not self._in_scope(frame):
            return False
        if self.brief and frame.f_code.co_name in _BRIEF_SKIP:
            return False
        return True

    def _emit(self, frame) -> None:
        depth = _depth_of(frame, self.root)
        name = frame.f_code.co_name
        rel = _relpath(frame.f_code.co_filename, self.root)
        n_args = frame.f_code.co_argcount
        args = ", ".join(frame.f_code.co_varnames[:n_args])
        self.out.write(f"{'  ' * depth}→ {rel}:{name}({args})\n")
        self.count += 1

        if self.watch_locals and name == self.watch_locals:
            for key, value in list(frame.f_locals.items())[:12]:
                text = repr(value)
                if len(text) > 200:
                    text = text[:200] + "…"
                self.out.write(f"{'  ' * (depth + 1)}· {key} = {text}\n")

    # --- settrace 回调 ---

    def __call__(self, frame, event, arg):
        if not self.enabled:
            return self
        if event == "call" and self._should_show(frame):
            self._emit(frame)
        return self


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trace_calls",
        description="打印 pdm 命令的实际调用链（sys.settrace 实现）",
    )
    p.add_argument("command", nargs="*",
                   help="要跟踪的 pdm 命令，如：feat show feat-edit-fields")
    p.add_argument("--root", default=_DEFAULT_ROOT,
                   help=f"只跟踪此目录下的调用（默认 {_DEFAULT_ROOT}）")
    p.add_argument("--only", default=None,
                   help="进一步限定路径片段（**相对 root**），如 cli")
    p.add_argument("--brief", action="store_true",
                   help="隐藏高频小函数，输出结构更清晰")
    p.add_argument("--locals", dest="watch", default=None,
                   metavar="FUNC",
                   help="打印该函数被调用时的局部变量")
    p.add_argument("--imports", action="store_true",
                   help="连 import 阶段的调用也记录（默认过滤）")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    cmd = args.command or ["--help"]

    # 先完成 import，再开始追踪，避免模块级代码刷屏
    from pdev.cli import main as cli_main

    tracer = Tracer(args.root, brief=args.brief, only=args.only,
                    watch_locals=args.watch)
    tracer.enabled = bool(args.imports)

    sys.settrace(tracer)
    tracer.enabled = True
    try:
        try:
            code = cli_main(cmd)
        except SystemExit as e:                  # argparse 的退出
            code = int(e.code or 0)
    finally:
        sys.settrace(None)
        tracer.out.write(f"\n（共记录 {tracer.count} 次函数调用）\n")
        try:
            tracer.out.flush()
        except Exception:                        # noqa: BLE001
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
