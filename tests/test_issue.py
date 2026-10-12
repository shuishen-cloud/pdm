# -*- coding: utf-8 -*-
"""pdev.issue 的测试。"""

from __future__ import annotations

import pytest

from pdev import (
    Actor,
    Event,
    EventType,
    Generated,
    GitHubLink,
    Priority,
    Status,
    Sync,
    SyncState,
)
from tests.conftest import at


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,terminal",
    [
        (Status.OPEN, False),
        (Status.IN_PROGRESS, False),
        (Status.BLOCKED, False),
        (Status.RESOLVED, True),
        (Status.CLOSED, True),
    ],
)
def test_status_terminal(status, terminal):
    assert status.is_terminal is terminal


def test_issue_enum_values_are_strings():
    assert Status.OPEN == "open"
    assert Priority.HIGH == "high"
    assert EventType.NOTE == "note"
    assert SyncState.DIRTY == "dirty"


def test_priority_values():
    assert [p.value for p in Priority] == ["low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


def test_issue_validate_ok(make_issue):
    make_issue().validate()  # 不抛异常即通过


@pytest.mark.parametrize("kw", [{"id": ""}, {"id": "   "}, {"title": ""}, {"title": "  "}])
def test_issue_validate_rejects(make_issue, kw):
    with pytest.raises(ValueError):
        make_issue(**kw).validate()


def test_issue_derived_flags(make_issue):
    ai = make_issue(origin_fingerprint=Generated.AI_FULL, reporter=Actor("ai:claude"))
    assert ai.caused_by_ai
    assert ai.reported_by_ai

    human = make_issue(origin_fingerprint=Generated.HUMAN, reporter=Actor("human:lwy"))
    assert not human.caused_by_ai
    assert not human.reported_by_ai

    partial = make_issue(origin_fingerprint=Generated.AI_PARTIAL)
    assert partial.caused_by_ai  # 部分 AI 也算 AI 引起


@pytest.mark.parametrize(
    "status,expected",
    [
        (Status.OPEN, True),
        (Status.IN_PROGRESS, True),
        (Status.BLOCKED, True),
        (Status.RESOLVED, False),
        (Status.CLOSED, False),
    ],
)
def test_issue_open(make_issue, status, expected):
    assert make_issue(status=status).open is expected


def test_issue_add_event_advances_updated_at(make_issue):
    i = make_issue()
    i.add_event(
        Event(at=at(10), type=EventType.NOTE, actor=Actor("human:lwy"), text="复现")
    )
    assert i.updated_at == at(10)

    i.add_event(Event(at=at(30), type=EventType.NOTE, actor=Actor("human:lwy")))
    assert i.updated_at == at(30)

    # 更早的事件不回退时间（单调）
    i.add_event(Event(at=at(5), type=EventType.NOTE, actor=Actor("human:lwy")))
    assert i.updated_at == at(30)
    assert len(i.events) == 3


def test_issue_mark_dirty(make_issue):
    i = make_issue(sync=Sync(direction="push", state=SyncState.SYNCED, local_rev=3))
    i.mark_dirty()
    assert i.sync.state is SyncState.DIRTY
    assert i.sync.local_rev == 4


# ---------------------------------------------------------------------------
# GitHubLink
# ---------------------------------------------------------------------------


def test_github_link_url():
    assert (
        GitHubLink(repo="user/repo", number=42).url
        == "https://github.com/user/repo/issues/42"
    )
    assert GitHubLink().url == ""
    assert GitHubLink(repo="user/repo").url == ""  # 缺 number
