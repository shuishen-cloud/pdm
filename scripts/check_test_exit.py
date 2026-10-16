#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试退出门禁：**以退出码为准**判定 pytest 结果。

背景见 ``doc/feat/tui-test-exit-guard.md``：曾出现
``5 passed`` 但进程以 139（SIGSEGV）退出的情况——崩溃发生在
解释器关闭阶段，输出文本全绿，**只有退出码暴露问题**。

用法::

    .venv/bin/python scripts/check_test_exit.py tests/tui_new_to_fix/
    .venv/bin/python scripts/check_test_exit.py tests/tui_new_to_fix/test_feat_ui.py --runs 5

退出码：0 = 门禁通过；1 = 门禁失败（出现异常退出）；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

__all__ = ["classify", "main"]

#: pytest 约定的退出码：0 = 全过，1 = 有用例失败。
_OK = 0
_TESTS_FAILED = 1

_HINT = (
    "  采集现场：.venv/bin/python scripts/tui_crash_report.py\n"
    "  然后带着输出与新笔记开一个 feat 排查。"
)


def classify(code: int) -> str:
    """退出码 -> 判定。

    - ``0`` → ``"ok"``
    - ``1`` → ``"tests-failed"``（pytest 约定，**合法**）
    - 其余（含负数的信号值）→ ``"exit-guard-failure"``

    纯函数，不抛异常。
    """
    if code == _OK:
        return "ok"
    if code == _TESTS_FAILED:
        return "tests-failed"
    return "exit-guard-failure"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check_test_exit",
        description="跑 pytest 并以退出码判定（抓退出阶段的偶发崩溃）",
    )
    p.add_argument("target", help="pytest 目标（文件或目录）")
    p.add_argument("--runs", type=int, default=1,
                   help="重复运行次数，用于捕捉间歇性崩溃（默认 1）")
    p.add_argument("--python", default=sys.executable,
                   help="用哪个解释器跑（默认当前解释器）")
    return p


def main(argv=None) -> int:
    """跑 pytest 并判定。返回 0=通过，1=门禁失败，2=用法错误。"""
    args = _build_parser().parse_args(argv)

    if args.runs < 1:
        print("错误：--runs 必须 >= 1", file=sys.stderr)
        return 2
    if not Path(args.target).exists():
        print(f"错误：目标不存在：{args.target}", file=sys.stderr)
        return 2

    cmd = [args.python, "-m", "pytest", args.target, "-q"]
    codes: list[int] = []
    for i in range(args.runs):
        proc = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent.parent))
        codes.append(proc.returncode)
        if args.runs > 1:
            print(f"  run {i + 1}/{args.runs}: 退出码 {proc.returncode}",
                  file=sys.stderr)

    verdicts = [classify(c) for c in codes]
    bad = [(i + 1, c) for i, (c, v) in enumerate(zip(codes, verdicts))
           if v == "exit-guard-failure"]

    if bad:
        print("", file=sys.stderr)
        print("退出门禁失败：出现异常退出码（既非 0 也非 1）", file=sys.stderr)
        for run_no, code in bad:
            signal_note = ""
            if code < 0:
                signal_note = f"（被信号 {-code} 杀死，如 -11 = SIGSEGV）"
            print(f"  第 {run_no} 次：退出码 {code}{signal_note}", file=sys.stderr)
        print(f"  复现命令：{' '.join(cmd)}", file=sys.stderr)
        print(_HINT, file=sys.stderr)
        return 1

    if "tests-failed" in verdicts:
        print("有测试失败（退出码 1，属合法结果，非门禁失败）", file=sys.stderr)
        return 0

    print(f"ok: {args.runs} 次运行退出码均为 0", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
