# -*- coding: utf-8 -*-
"""pdev.common 的测试。"""

from __future__ import annotations

import pytest

from pdev import Actor


@pytest.mark.parametrize(
    "raw,kind,name,is_ai,is_human",
    [
        ("human:lwy", "human", "lwy", False, True),
        ("ai:claude-opus-4", "ai", "claude-opus-4", True, False),
        ("ci", "ci", "", False, False),
        ("tool", "tool", "", False, False),
        ("github:alice", "github", "alice", False, False),
        ("", "", "", False, False),
        ("ai:a:b", "ai", "a:b", True, False),  # 只切第一个冒号
    ],
)
def test_actor(raw, kind, name, is_ai, is_human):
    a = Actor(raw)
    assert a.kind == kind
    assert a.name == name
    assert a.is_ai is is_ai
    assert a.is_human is is_human
    assert str(a) == raw


def test_actor_is_hashable():
    # frozen dataclass 可哈希，可用于 set/dict
    assert {Actor("human:lwy"), Actor("human:lwy")} == {Actor("human:lwy")}


def test_utcnow_is_timezone_aware():
    from pdev import utcnow

    assert utcnow().tzinfo is not None
