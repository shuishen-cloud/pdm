# -*- coding: utf-8 -*-
"""从测试文件抽取脚本片段。

用途：``pdm verify show`` 直接展示验证对应的测试代码，无需切换窗口。

只做“读取 + 抽取”，不执行任何东西。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

__all__ = ["parse_target", "extract_script", "ScriptResult", "ParsedTarget"]


@dataclass(frozen=True)
class ParsedTarget:
    """一个测试目标的解析结果（替代裸 ``tuple``）。

    ``file`` 为 ``tests/x.py``，``nodes`` 为 ``["test_y"]``（可为空）。
    """

    file: str = ""
    nodes: List[str] = field(default_factory=list)

# target 形如 tests/x.py::test_y 或 tests/x.py::Class::test_y
_TARGET_RE = re.compile(
    r"^(?P<file>[^\s:]+\.py)(?:::?(?P<nodes>[\w.:]+))?$"
)


class ScriptResult:
    """脚本抽取结果。"""

    __slots__ = ("code", "source", "error")

    def __init__(
        self,
        code: str = "",
        source: str = "",
        error: str = "",
    ) -> None:
        self.code = code       # 抽到的代码
        self.source = source   # 来源文件路径
        self.error = error     # 抽不到时的原因

    @property
    def ok(self) -> bool:
        return bool(self.code)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ScriptResult(ok={self.ok}, source={self.source!r})"


def parse_target(target: str) -> ParsedTarget:
    """把 ``tests/x.py::test_y`` 拆成 :class:`ParsedTarget`。

    无 ``::`` 时节点列表为空。非 ``.py`` 目标返回空文件。
    """
    target = target.strip()
    if not target or "::" not in target and not target.endswith(".py"):
        return ParsedTarget(file="", nodes=[])
    m = _TARGET_RE.match(target)
    if not m:
        # 退而求其次：按 :: 手工切
        if "::" in target:
            file, _, rest = target.partition("::")
            return ParsedTarget(
                file=file, nodes=[n for n in rest.split("::") if n]
            )
        return ParsedTarget(file=target, nodes=[])
    file = m.group("file")
    nodes_raw = m.group("nodes") or ""
    nodes = [n for n in nodes_raw.split("::") if n]
    return ParsedTarget(file=file, nodes=nodes)


def extract_script(
    target: str,
    *,
    root: Optional[Path] = None,
    max_lines: int = 200,
) -> ScriptResult:
    """从 ``target`` 指向的测试文件抽取对应函数/类的源码。

    :param target: 如 ``tests/x.py::test_y``。
    :param root: 解析相对路径的起点，默认当前目录。
    :param max_lines: 最多抽取的行数（防止整个大文件）。
    """
    parsed = parse_target(target)
    file, nodes = parsed.file, parsed.nodes
    if not file:
        return ScriptResult(error="target 不是 Python 测试节点")

    base = Path(root) if root is not None else Path.cwd()
    path = Path(file)
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        return ScriptResult(error=f"文件不存在：{file}")

    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        return ScriptResult(error=f"无法读取：{e}")

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ScriptResult(error=f"语法错误：{e}")

    lines = source.splitlines()

    # 未指定节点：返回整个文件（截断）
    if not nodes:
        code = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            code += f"\n# …（省略 {len(lines) - max_lines} 行）"
        return ScriptResult(code=code, source=str(path))

    # 逐层定位：类 -> 方法
    node: Optional[ast.AST] = tree
    for name in nodes:
        node = _find_child(node, name)
        if node is None:
            return ScriptResult(
                error=f"未找到 {name}", source=str(path)
            )

    segment = ast.get_source_segment(source, node)
    if not segment:
        # 退化：用行号切片
        start = node.lineno - 1
        end = getattr(node, "end_lineno", start + 1)
        segment = "\n".join(lines[start:end])

    seg_lines = segment.splitlines()
    if len(seg_lines) > max_lines:
        segment = "\n".join(seg_lines[:max_lines])
        segment += f"\n    # …（省略 {len(seg_lines) - max_lines} 行）"

    return ScriptResult(code=segment, source=str(path))


def _find_child(node: ast.AST, name: str) -> Optional[ast.AST]:
    """在给定 AST 节点里找同名函数/类。"""
    body = getattr(node, "body", None)
    if body is None:
        return None
    for child in body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if child.name == name:
                return child
    return None
