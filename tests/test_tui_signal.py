# -*- coding: utf-8 -*-
"""TUI 信号退出时恢复终端的测试（tui-signal-restore）。

见 ``.pdm/docs/feat/tui-signal-restore.md``。
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("textual")

from pdev.tui import app as app_mod  # noqa: E402


class _FakeTTY(io.StringIO):
    """伪装成 tty 的输出流。"""

    def isatty(self) -> bool:  # noqa: D102
        return True


RESTORE_MARKERS = ("\x1b[?1049l", "\x1b[?25h", "\x1b[?2004l")


def test_restore_writes_sequences_on_tty():
    out = _FakeTTY()
    app_mod._restore_terminal(out)
    text = out.getvalue()
    for marker in RESTORE_MARKERS:
        assert marker in text, marker


def test_restore_is_noop_on_non_tty():
    out = io.StringIO()          # isatty() 默认 False
    app_mod._restore_terminal(out)
    assert out.getvalue() == ""


def test_restore_swallows_errors():
    class Bad(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, s):  # noqa: D102
            raise OSError("write failed")

    # 不应抛出
    app_mod._restore_terminal(Bad())


def test_restore_idempotent():
    out = _FakeTTY()
    app_mod._restore_terminal(out)
    app_mod._restore_terminal(out)
    # 两次都应写入（幂等，可安全重复）
    assert out.getvalue().count("\x1b[?1049l") == 2


def test_run_restores_on_keyboard_interrupt(monkeypatch):
    """run() 在 app.run() 抛 KeyboardInterrupt 时恢复终端并返回 130。"""
    written = []

    def fake_restore(stream=None):
        written.append(True)

    monkeypatch.setattr(app_mod, "_restore_terminal", fake_restore)

    class BoomApp:
        def __init__(self, *a, **kw):
            pass

        def run(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(app_mod, "PDMApp", BoomApp)

    assert app_mod.run(store=None) == 130
    assert written, "run() 必须在 KeyboardInterrupt 时调用 _restore_terminal"


def test_run_restores_on_normal_exit(monkeypatch):
    written = []
    monkeypatch.setattr(app_mod, "_restore_terminal",
                        lambda stream=None: written.append(True))

    class OkApp:
        def __init__(self, *a, **kw):
            pass

        def run(self):
            return None

    monkeypatch.setattr(app_mod, "PDMApp", OkApp)
    app_mod.run(store=None)
    assert written
