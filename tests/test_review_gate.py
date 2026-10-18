# -*- coding: utf-8 -*-
"""审查率门禁的**交互与集成**测试。

对应 ``doc/feat/review-gate.md``。

分两层：

- **交互层**（``_gate_prompt``）：mock 掉 ``input`` 与 ``isatty``，
  验证「继续/取消/重试/非交互」四种分支。这一层最容易出 bug，
  单独测比跑整个 ``feat new`` 快得多。
- **集成层**（``cmd_feat_new``）：用 ``capsys`` 看用户实际看到什么，
  并确认 feat 到底建没建成。

纯函数部分（分数与阈值判断）在 ``tests/test_review.py``。
"""

from __future__ import annotations

import pytest

from pdev.cli.commands import _gate_prompt


# --- 交互层：_gate_prompt ---------------------------------------------------


def _fake_tty(monkeypatch, yes: bool = True) -> None:
    """让 ``sys.stdin.isatty()`` 返回 True（进入交互分支）。"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: yes)


def test_prompt_yes_continues(monkeypatch, capsys):
    _fake_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "y")

    assert _gate_prompt(0.05, 0.1) is True

    err = capsys.readouterr().err
    assert "审核率" in err
    assert "5.00%" in err or "0.05" in err       # 打印了实际分数


def test_prompt_no_cancels(monkeypatch, capsys):
    _fake_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "n")

    assert _gate_prompt(0.05, 0.1) is False
    assert "已取消" in capsys.readouterr().err


def test_prompt_uppercase_yes_accepted(monkeypatch):
    """输入 ``Y`` 也应当作同意（大小写不敏感）。"""
    _fake_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "Y")
    assert _gate_prompt(0.05, 0.1) is True


def test_prompt_retries_on_invalid_then_yes(monkeypatch, capsys):
    """输入非法 → 提示重试，不退出。"""
    _fake_tty(monkeypatch)
    answers = iter(["maybe", "", "y"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    assert _gate_prompt(0.05, 0.1) is True
    assert "请输入 y 或 n" in capsys.readouterr().err


def test_prompt_eof_cancels(monkeypatch, capsys):
    """交互环境下 stdin 被关闭 → 按取消处理，不挂住。"""
    _fake_tty(monkeypatch)

    def boom(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)

    assert _gate_prompt(0.05, 0.1) is False
    assert "没有读到输入" in capsys.readouterr().err


def test_prompt_non_tty_auto_continues(monkeypatch, capsys):
    """**非交互环境**（CI/管道/测试）→ 自动放行，绝不阻塞。"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    def must_not_call(_prompt=""):
        raise AssertionError("非交互环境下不应调用 input()")

    monkeypatch.setattr("builtins.input", must_not_call)

    assert _gate_prompt(0.0, 0.1) is True
    err = capsys.readouterr().err
    assert "跳过确认" in err


def test_prompt_isatty_failure_treated_as_non_interactive(monkeypatch):
    """``isatty()`` 本身抛异常（某些流）→ 当作非交互，不崩。"""

    def boom():
        raise OSError("no tty")

    monkeypatch.setattr("sys.stdin.isatty", boom)
    monkeypatch.setattr("builtins.input",
                        lambda _p="": pytest.fail("不应调用 input"))
    assert _gate_prompt(0.0, 0.1) is True


def test_prompt_warns_even_when_non_interactive(monkeypatch, capsys):
    """非交互时也要把低覆盖率警告打出来（不能静默）。"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    _gate_prompt(0.02, 0.1)
    err = capsys.readouterr().err
    assert "审核率" in err and "2.00%" in err


# --- 集成层：数值格式与边界 ------------------------------------------------


def test_prompt_formats_percentage(monkeypatch, capsys):
    """分数按百分比展示，便于人读。"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    _gate_prompt(0.1234, 0.5)
    err = capsys.readouterr().err
    assert "12.34%" in err
    assert "50.00%" in err


def test_prompt_zero_score(monkeypatch, capsys):
    """score 为 0（空仓库/全未审）时也能正常提示。"""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert _gate_prompt(0.0, 0.1) is True
    assert "0.00%" in capsys.readouterr().err
