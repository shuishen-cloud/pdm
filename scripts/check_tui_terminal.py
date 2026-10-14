#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 TUI 退出后终端是否恢复（tui-signal-restore 的回归工具）。

用 PTY 启动 ``pdm ui``，发送退出按键，检查进程退出后终端输出里是否包含
Textual 的恢复序列（退出备用屏 / 显示光标 / 关 bracketed paste）。

背景：Ctrl+C / 信号退出时，``asyncio.run`` 硬中断事件循环可能跳过
``stop_application_mode()``，导致终端留在备用屏 + raw mode（乱码）。

用法::

    python scripts/check_tui_terminal.py            # 测 q 退出
    python scripts/check_tui_terminal.py --keys ctrlq   # 测 Ctrl+C → Ctrl+Q

退出码：0 = 恢复序列齐全；1 = 缺失（终端可能乱码）。
"""

from __future__ import annotations

import argparse
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

# 退出后终端应恢复：退备用屏 + 显示光标 + 关 bracketed paste
REQUIRED = (b"\x1b[?1049l", b"\x1b[?25h", b"\x1b[?2004l")

ROOT = Path(__file__).resolve().parent.parent


def _pdm() -> str:
    """优先用项目自带 pdm，其次 .venv/bin/python -m pdev.cli。"""
    cand = ROOT / ".venv" / "bin" / "pdm"
    if cand.exists():
        return str(cand)
    return f"{sys.executable} -m pdev.cli"


def run_case(keys: bytes, wait: float = 3.0, settle: float = 2.0) -> bytes:
    """在 PTY 里跑 pdm ui，发 keys，返回全部终端输出。"""
    cmd = f"{_pdm()} ui"
    pid, fd = pty.fork()
    if pid == 0:                       # 子进程
        os.execvp("bash", ["bash", "-lc", cmd])
        os._exit(127)

    chunks: list[bytes] = []

    def drain(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.2)
            if fd in r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    return
                if not data:
                    return
                chunks.append(data)

    drain(wait)                        # 等界面渲染
    os.write(fd, keys)                 # 发退出按键
    drain(settle)

    # 若仍存活，兜底 kill
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    drain(0.5)
    return b"".join(chunks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="验证 TUI 退出后终端恢复")
    ap.add_argument("--keys", choices=["q", "ctrlq", "ctrlc-ctrlq"],
                    default="q", help="退出按键序列")
    args = ap.parse_args(argv)

    keys = {
        "q": b"q",
        "ctrlq": b"\x11",
        "ctrlc-ctrlq": b"\x03\x11",      # Ctrl+C 弹确认 → Ctrl+Q 确认
    }[args.keys]

    out = run_case(keys)
    missing = [m for m in REQUIRED if m not in out]
    if missing:
        print("✗ 终端恢复序列缺失（退出后可能乱码）：")
        for m in missing:
            print(f"    missing {m!r}")
        return 1
    print(f"✓ 恢复序列齐全（keys={args.keys}）："
          + ", ".join(m.decode("latin1") for m in REQUIRED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
