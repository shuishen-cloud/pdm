# -*- coding: utf-8 -*-
"""pdm-workflow 技能的测试。

校验技能目录结构、frontmatter 合法性与被引用的参考文件存在——
避免技能因拼写或格式问题在 pi 中静默失效。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent / ".pi" / "skills" / "pdm-workflow"
SKILL_MD = SKILL_DIR / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict:
    """极简 frontmatter 解析（与 pi 的 parseFrontmatter 行为一致）。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[4:end]
    out = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line[0] not in (" ", "\t") and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            out[key] = val.strip()
        elif key:
            out[key] += " " + line.strip()
    return out


def test_skill_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_name(skill_text):
    fm = _frontmatter(skill_text)
    name = fm.get("name", "")
    assert name == "pdm-workflow"
    assert re.fullmatch(r"[a-z0-9-]+", name)
    assert not name.startswith("-") and not name.endswith("-")
    assert "--" not in name
    assert len(name) <= 64


def test_frontmatter_description(skill_text):
    fm = _frontmatter(skill_text)
    desc = fm.get("description", "")
    assert desc.strip(), "description 不能为空"
    assert len(desc) <= 1024
    # 应同时说明“做什么”与“何时用”的触发信息
    assert "pdm" in desc
    assert "feat commit" in desc or "commit" in desc


def test_references_exist():
    for name in ("commands.md", "design-doc.md", "data-model.md"):
        assert (SKILL_DIR / "references" / name).is_file(), name


@pytest.mark.parametrize("ref", ["commands.md", "design-doc.md", "data-model.md"])
def test_referenced_in_body(skill_text, ref):
    assert f"references/{ref}" in skill_text


def test_scripts_pdm_executable():
    script = SKILL_DIR / "scripts" / "pdm"
    assert script.is_file()
    assert script.stat().st_mode & 0o111, "scripts/pdm 应可执行"


def test_body_mentions_pipeline(skill_text):
    """核心指令必须写出阶段流水线。"""
    assert "doc → test → feat → fix → close" in skill_text


def test_body_warns_against_git_commit(skill_text):
    """必须明确禁止直接 git commit。"""
    assert "git commit" in skill_text
