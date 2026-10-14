# -*- coding: utf-8 -*-
"""pdm-workflow skill 与代码的一致性测试（skill-sync）。

skill 是人与 AI 的操作入口，漂移一次就会照着旧文档操作而失败。
本测试把它钉在代码上——改代码忘了同步 skill，这里就红。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / ".pi" / "skills" / "pdm-workflow"
SKILL = SKILL_DIR / "SKILL.md"
COMMANDS = SKILL_DIR / "references" / "commands.md"
DATA_MODEL = SKILL_DIR / "references" / "data-model.md"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _commands_text() -> str:
    return COMMANDS.read_text(encoding="utf-8")


def _top_level_subcommands() -> set:
    from pdev.cli import build_parser

    parser = build_parser()
    for action in parser._actions:
        if getattr(action, "choices", None) and action.dest == "command":
            return set(action.choices)
    return set()


def _feat_subcommands() -> set:
    from pdev.cli import build_parser

    parser = build_parser()
    for action in parser._actions:
        if action.dest == "command":
            for sub in action.choices.values():
                for a in sub._actions:
                    if a.dest == "feat_command":
                        return set(a.choices)
    return set()


def test_skill_files_exist():
    assert SKILL.is_file()
    assert COMMANDS.is_file()
    assert DATA_MODEL.is_file()


def test_skill_mentions_only_real_top_level_commands():
    """SKILL.md 里写的 pdm 子命令都真实存在。"""
    known = _top_level_subcommands()
    mentioned = set(re.findall(r"\bpdm\s+([a-z][a-z-]*)", _skill_text()))
    unknown = {c for c in mentioned if c not in known}
    assert not unknown, f"skill 提到不存在的子命令：{unknown}"


def test_commands_ref_covers_all_feat_subcommands():
    """commands.md 必须覆盖 feat 的全部子命令。"""
    text = _commands_text()
    missing = {c for c in _feat_subcommands() if c not in text}
    assert not missing, f"commands.md 缺 feat 子命令：{missing}"


def test_skill_stage_sequence_matches_code():
    """流水线序列与 ``stage.STAGE_SEQUENCE`` 完全一致。"""
    from pdev.stage import STAGE_SEQUENCE

    seq = "→".join(STAGE_SEQUENCE)
    assert seq in _skill_text().replace(" ", ""), f"SKILL.md 缺流水线 {seq}"
    assert seq in _commands_text().replace(" ", ""), f"commands.md 缺流水线 {seq}"


def test_skill_documents_script_optional():
    """script 的可选语义必须写明（可跳过直达 feat）。"""
    text = _commands_text()
    assert "script" in text, "commands.md 未提及 script 阶段"
    assert "可选" in text, "commands.md 未说明 script 可选"


def test_commands_ref_lists_all_check_codes():
    """check 规则表必须覆盖 ``check.CODES`` 全部代号。"""
    from pdev.check import CODES

    text = _commands_text()
    missing = [c for c in CODES if c not in text]
    assert not missing, f"commands.md 缺 check 规则：{missing}"


def test_skill_documents_feat_new_required_fields():
    """五项必填字段必须写明。"""
    text = _commands_text()
    for flag in ("--design-note", "--impl-note", "--data-model",
                 "--sample", "--change"):
        assert flag in text, f"commands.md 缺必填参数：{flag}"


def test_data_model_stage_includes_script():
    """data-model.md 的 stage 取值要含 script。"""
    text = DATA_MODEL.read_text(encoding="utf-8")
    assert "script" in text, "data-model.md 的 stage 未含 script"
