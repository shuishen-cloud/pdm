# -*- coding: utf-8 -*-
"""``scripts/trace_calls.py`` 的测试。

追踪脚本本身不参与生产逻辑，但它依赖几个纯函数（路径压缩、
深度计算、过滤判定），这些值得测——否则改坏了只会"输出变难看"，
不易发现。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "trace_calls.py"


def _load():
    spec = importlib.util.spec_from_file_location("trace_calls", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["trace_calls"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load()


# --- _relpath -----------------------------------------------------------------


def test_relpath_strips_root():
    got = mod._relpath("/repo/pdev/cli/commands.py", "/repo/pdev")
    assert got == "cli/commands.py"


def test_relpath_outside_root_falls_back_to_basename():
    got = mod._relpath("/other/lib/x.py", "/repo/pdev")
    assert got == "x.py"


def test_relpath_survives_garbage():
    """任何异常都不能让追踪脚本崩掉。"""
    assert isinstance(mod._relpath(None, "/x"), (str, type(None)))


# --- Tracer._in_scope / _should_show ------------------------------------------


def _fake_frame(path: str, name: str = "f"):
    """构造一个最小 frame 替身。"""
    code = type("C", (), {
        "co_filename": path,
        "co_name": name,
        "co_argcount": 0,
        "co_varnames": (),
    })()
    return type("F", (), {"f_code": code, "f_back": None,
                          "f_locals": {}})()


def test_in_scope_accepts_files_under_root(tmp_path):
    t = mod.Tracer(str(tmp_path))
    inside = tmp_path / "cli" / "x.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("", encoding="utf-8")
    assert t._in_scope(_fake_frame(str(inside))) is True


def test_in_scope_rejects_outside(tmp_path):
    t = mod.Tracer(str(tmp_path))
    assert t._in_scope(_fake_frame("/usr/lib/python3/os.py")) is False


def test_only_narrows_scope(tmp_path):
    """``--only`` 匹配的是**相对 root** 的路径（不含 root 自身）。

    例如 ``--root pdev --only cli`` → 匹配 ``pdev/cli/...``。
    """
    t = mod.Tracer(str(tmp_path), only="cli")
    a = tmp_path / "cli" / "a.py"
    b = tmp_path / "core" / "b.py"
    for p in (a, b):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    assert t._in_scope(_fake_frame(str(a))) is True
    assert t._in_scope(_fake_frame(str(b))) is False


def test_brief_hides_noisy_functions(tmp_path):
    t = mod.Tracer(str(tmp_path), brief=True)
    f = tmp_path / "x.py"
    f.write_text("", encoding="utf-8")
    assert t._should_show(_fake_frame(str(f), "_coerce")) is False
    assert t._should_show(_fake_frame(str(f), "real_function")) is True


def test_non_brief_shows_everything(tmp_path):
    t = mod.Tracer(str(tmp_path), brief=False)
    f = tmp_path / "x.py"
    f.write_text("", encoding="utf-8")
    assert t._should_show(_fake_frame(str(f), "_coerce")) is True


# --- 输出默认走 stderr --------------------------------------------------------


def test_default_stream_is_stderr(tmp_path):
    """调用链默认写 stderr，好与命令的 stdout 分开（可 2>calls.txt）。"""
    t = mod.Tracer(str(tmp_path))
    assert t.out is sys.stderr


def test_emit_reports_count(tmp_path):
    import io

    buf = io.StringIO()
    t = mod.Tracer(str(tmp_path), stream=buf)
    assert t.count == 0
    t._emit(_fake_frame(str(tmp_path / "x.py"), "f"))
    assert t.count == 1
    assert "f" in buf.getvalue()


def test_watch_locals_prints_values(tmp_path):
    import io

    buf = io.StringIO()
    t = mod.Tracer(str(tmp_path), watch_locals="target", stream=buf)

    code = type("C", (), {
        "co_filename": str(tmp_path / "x.py"),
        "co_name": "target",
        "co_argcount": 0,
        "co_varnames": (),
    })()
    frame = type("F", (), {"f_code": code, "f_back": None,
                          "f_locals": {"answer": 42}})()
    t._emit(frame)
    out = buf.getvalue()
    assert "answer = 42" in out


def test_depth_of_counts_only_in_scope(tmp_path):
    """深度按'仍在受跟踪目录内'计，遇到外部帧即停。"""
    f1 = _fake_frame(str(tmp_path / "a.py"), "outer")
    f2 = _fake_frame(str(tmp_path / "b.py"), "inner")
    out = _fake_frame("/usr/lib/outside.py", "lib")
    f2.f_back = f1
    f1.f_back = out
    assert mod._depth_of(f2, str(tmp_path)) == 1
    assert mod._depth_of(f1, str(tmp_path)) == 0
