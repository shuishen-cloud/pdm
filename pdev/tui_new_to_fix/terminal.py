# -*- coding: utf-8 -*-
"""终端恢复（幂等、非 tty 安全）。

Ctrl+C / 异常退出时 Textual 的清理可能来不及，终端会留在备用屏 +
raw mode。这里作为无条件兜底，复用旧 TUI 已验证的序列。
"""

from __future__ import annotations

import sys

_SEQ = (
    "\x1b[?1000l"    # 关 VT200 鼠标
    "\x1b[?1003l"
    "\x1b[?1015l"
    "\x1b[?1006l"
    "\x1b[<u"        # 关 kitty 键盘协议
    "\x1b[?1049l"    # 退出备用屏
    "\x1b[?25h"      # 显示光标
    "\x1b[?1004l"
    "\x1b[?2004l"
)

__all__ = ["restore_terminal"]


def restore_terminal(stream=None) -> None:
    """把终端恢复到正常模式；非 tty 或写失败都静默跳过。"""
    out = stream if stream is not None else sys.stdout
    try:
        if not out.isatty():
            return
    except Exception:                            # noqa: BLE001
        return
    try:
        out.write(_SEQ)
        out.flush()
    except Exception:                            # noqa: BLE001
        pass
