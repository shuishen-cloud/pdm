# -*- coding: utf-8 -*-
"""pdev.scripts 的测试：目标解析与 AST 抽取。"""

from __future__ import annotations

import pytest

from pdev.scripts import extract_script, parse_target


# ---------------------------------------------------------------------------
# parse_target
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,file,nodes",
    [
        ("tests/x.py::test_y", "tests/x.py", ["test_y"]),
        ("tests/x.py::TestC::test_y", "tests/x.py", ["TestC", "test_y"]),
        ("tests/x.py", "tests/x.py", []),
        ("tests/x.py::test_y::extra", "tests/x.py", ["test_y", "extra"]),
        ("", "", []),
        ("not a target", "", []),
    ],
)
def test_parse_target(target, file, nodes):
    f, n = parse_target(target)
    assert f == file
    assert n == nodes


# ---------------------------------------------------------------------------
# extract_script
# ---------------------------------------------------------------------------

SAMPLE = '''\
import pytest


def test_alpha():
    assert 1 == 1


def test_beta():
    x = 1
    assert x == 1


class TestGroup:
    def test_gamma(self):
        assert True
'''

OTHER = '''\
def unrelated():
    pass
'''


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "sample.py").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "tests" / "other.py").write_text(OTHER, encoding="utf-8")
    return tmp_path


def test_extract_function(proj):
    r = extract_script("tests/sample.py::test_alpha", root=proj)
    assert r.ok
    assert "def test_alpha():" in r.code
    assert "assert 1 == 1" in r.code
    assert "test_beta" not in r.code  # 只取目标函数


def test_extract_preserves_body_without_neighbors(proj):
    r = extract_script("tests/sample.py::test_beta", root=proj)
    assert "x = 1" in r.code
    assert "def test_alpha" not in r.code


def test_extract_class_method(proj):
    r = extract_script("tests/sample.py::TestGroup::test_gamma", root=proj)
    assert r.ok
    assert "def test_gamma" in r.code


def test_extract_whole_file(proj):
    r = extract_script("tests/sample.py", root=proj)
    assert r.ok
    assert "def test_alpha" in r.code
    assert "def test_beta" in r.code


def test_missing_file(proj):
    r = extract_script("tests/nope.py::test_x", root=proj)
    assert not r.ok
    assert "不存在" in r.error


def test_missing_node(proj):
    r = extract_script("tests/sample.py::test_missing", root=proj)
    assert not r.ok
    assert "未找到" in r.error


def test_non_python_target(proj):
    r = extract_script("make typecheck", root=proj)
    assert not r.ok


def test_syntax_error(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    r = extract_script("bad.py", root=tmp_path)
    assert not r.ok
    assert "语法错误" in r.error


def test_truncates_long_file(tmp_path):
    lines = ["def f%d():" % i + "\n    pass\n" for i in range(500)]
    (tmp_path / "big.py").write_text("".join(lines), encoding="utf-8")
    r = extract_script("big.py", root=tmp_path, max_lines=20)
    assert r.ok
    assert "省略" in r.code
    assert r.code.count("\n") < 40


def test_relative_path_uses_root(proj):
    r = extract_script("tests/sample.py::test_alpha", root=proj)
    assert r.ok
    assert str(proj) in r.source
