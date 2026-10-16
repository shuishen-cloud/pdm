# -*- coding: utf-8 -*-
"""异常兜底：让任何一个 action 出错都不会带走整个 TUI。

Textual 的 ``App._handle_exception()`` 会 panic 整个 app
（``return_code=1`` 并退出）。我们不允许"未知异常 = 退出"，
因此在所有 action / 回调外面套一层 :func:`guard`。

设计约束（见 ``doc/tui-new-to-fix.md``）：

- 只捕 ``Exception``，**不捕** ``BaseException``：Ctrl+C
  （``KeyboardInterrupt``）仍走正常退出路径。
- 吞掉的异常记录进 ``app.errors``，便于测试断言与事后排查。
- 出错后 action 静默返回，app 继续运行。
"""

from __future__ import annotations

import functools
import traceback

__all__ = ["guard"]


def guard(fn):
    """把 ``fn`` 包成不抛异常的版本。

    用于 ``App`` 的 action 与消息回调。异常会被转成
    ``self.notify(...)`` + ``self.errors.append(...)``。
    """

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:                # noqa: BLE001 - 兜底本意
            _record(self, exc, fn.__name__)
            return None

    return wrapper


def _record(app, exc: Exception, where: str) -> None:
    """记录并提示；记录本身失败也不能再抛。"""
    detail = "".join(
        traceback.format_exception_only(type(exc), exc)
    ).strip()
    entry = f"{where}: {detail}"
    try:
        errors = getattr(app, "errors", None)
        if errors is not None:
            errors.append(entry)
    except Exception:                            # noqa: BLE001
        pass
    try:
        app.notify(f"{where} 出错：{detail}", severity="error")
    except Exception:                            # noqa: BLE001
        pass
