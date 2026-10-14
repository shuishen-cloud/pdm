# -*- coding: utf-8 -*-
"""文档一致性测试（docs-rewrite）。

确保使用说明里出现的命令与 CLI 真实帮助一致——文档漂移一次就报一次。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAIN_DOC = ROOT / "doc" / "使用方法以及效果.md"
CONFIG_DOC = ROOT / "doc" / "配置文件说明.md"

# 文档中出现的顶层命令必须都在帮助列表里
def _cli_subcommands() -> set:
    from pdev.cli import build_parser

    parser = build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and action.dest == "command":
            return set(action.choices)
    return set()


def test_doc_exists():
    assert MAIN_DOC.is_file()
    assert CONFIG_DOC.is_file()


def _mentioned_subcommands(text: str) -> set:
    return set(re.findall(r"\bpdm\s+([a-z][a-z-]*)", text))


def test_main_doc_commands_are_real():
    """文档里提到的顶层子命令都真实存在。"""
    known = _cli_subcommands()
    mentioned = _mentioned_subcommands(MAIN_DOC.read_text(encoding="utf-8"))
    unknown = {c for c in mentioned if c not in known}
    # 允许文档里出现 pdm 之外的东西（如 pdev 模块名），只查已知集合
    assert not unknown, f"文档提到不存在的子命令：{unknown}"


def test_main_doc_covers_feat_flow():
    """主文档必须覆盖 Feat 全流程与审查机制。"""
    text = MAIN_DOC.read_text(encoding="utf-8")
    for kw in ("feat new", "feat commit", "doc → test → feat → fix → close",
               "feat review", "feat comment", "pdm review",
               "--unreviewed", "掌握程度"):
        assert kw in text, f"主文档缺关键内容：{kw}"


def test_config_doc_covers_review_section():
    text = CONFIG_DOC.read_text(encoding="utf-8")
    assert "review" in text
    assert "min_coverage" in text


def test_doc_feat_examples_have_required_fields():
    """五分钟上手示例必须含五项必填参数。"""
    text = MAIN_DOC.read_text(encoding="utf-8")
    for flag in ("--design-note", "--impl-note", "--data-model",
                 "--sample", "--change"):
        assert flag in text, f"示例缺必填参数：{flag}"
