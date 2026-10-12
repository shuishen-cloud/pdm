# -*- coding: utf-8 -*-
"""pdev.fingerprint 的测试。"""

from __future__ import annotations

import pytest

from pdev import Actor, Fingerprint, Generated


@pytest.mark.parametrize(
    "fp,expected",
    [
        # 全 AI 生成 + 未审 -> 风险
        (Fingerprint(generated_by=Generated.AI_FULL), True),
        # 全 AI 生成 + 已审 -> 安全
        (
            Fingerprint(generated_by=Generated.AI_FULL, reviewed_by=Actor("human:lwy")),
            False,
        ),
        # 人写 -> 安全
        (Fingerprint(generated_by=Generated.HUMAN), False),
        # 部分 AI + 未审 -> 安全（只有全 AI 才触发）
        (Fingerprint(generated_by=Generated.AI_PARTIAL), False),
        # 不可解释 -> 无论如何都风险
        (
            Fingerprint(
                generated_by=Generated.HUMAN,
                reviewed_by=Actor("human:lwy"),
                explainability="no",
            ),
            True,
        ),
        # AI 审查不算人工审查 -> 风险
        (
            Fingerprint(generated_by=Generated.AI_FULL, reviewed_by=Actor("ai:bot")),
            True,
        ),
    ],
)
def test_fingerprint_risky(fp, expected):
    assert fp.risky is expected


def test_fingerprint_predicates():
    ai = Fingerprint(generated_by=Generated.AI_FULL)
    assert ai.is_ai_generated and ai.fully_ai_generated

    part = Fingerprint(generated_by=Generated.AI_PARTIAL)
    assert part.is_ai_generated
    assert not part.fully_ai_generated

    human = Fingerprint(generated_by=Generated.HUMAN)
    assert not human.is_ai_generated
    assert human.explainable  # 空 explainability 视为可解释
    assert not human.reviewed

    assert Fingerprint(explainability="no").explainable is False
    assert Fingerprint(reviewed_by=Actor("human:lwy")).reviewed is True


def test_fingerprint_trailers():
    fp = Fingerprint(
        assisted_by="ai:claude-opus-4",
        generated_by=Generated.AI_FULL,
        reviewed_by=Actor("human:lwy"),
        explainability="yes",
        issue="0001",
    )
    assert fp.trailers == [
        ("Assisted-by", "ai:claude-opus-4"),
        ("Generated-by", "ai:100%"),
        ("Reviewed-by", "human:lwy"),
        ("Explainability", "yes"),
        ("Issue", "0001"),
    ]

    # 最小指纹：无 Assisted-by / Reviewed-by / Issue
    minimal = Fingerprint(generated_by=Generated.HUMAN)
    assert minimal.trailers == [
        ("Generated-by", "human"),
        ("Explainability", "yes"),
    ]


@pytest.mark.parametrize(
    "value,is_ai",
    [
        (Generated.AI_FULL, True),
        (Generated.AI_PARTIAL, True),
        (Generated.HUMAN, False),
    ],
)
def test_generated_is_ai(value, is_ai):
    assert value.is_ai is is_ai


def test_enum_values_are_strings():
    # str 混入让枚举可直接 JSON 序列化
    assert Generated.AI_FULL == "ai:100%"
