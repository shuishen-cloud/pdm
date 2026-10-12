# -*- coding: utf-8 -*-
"""pdev.note 的测试。"""

from __future__ import annotations

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStatus, Priority


def make_note(**kw) -> CommitNote:
    base = dict(commit="abc123", kind=NoteKind.PITFALL, title="token 刷新有竞态")
    base.update(kw)
    return CommitNote(**base)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


def test_note_kind_values():
    assert [k.value for k in NoteKind] == [
        "problem",
        "difficulty",
        "pitfall",
        "controlled-exception",
        "bug",
    ]
    assert NoteKind.PITFALL == "pitfall"  # str 混入，可直接序列化


def test_note_kind_asset_vs_debt():
    assert NoteKind.BUG.is_debt
    assert not NoteKind.BUG.is_asset
    for k in (NoteKind.PROBLEM, NoteKind.DIFFICULTY, NoteKind.PITFALL,
              NoteKind.CONTROLLED_EXCEPTION):
        assert k.is_asset
        assert not k.is_debt


def test_note_status_values():
    assert [s.value for s in NoteStatus] == ["open", "resolved", "noted"]


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def test_note_validate_ok():
    make_note().validate()


@pytest.mark.parametrize("kw", [{"commit": ""}, {"commit": "  "}, {"title": ""}])
def test_note_validate_rejects(kw):
    with pytest.raises(ValueError):
        make_note(**kw).validate()


# ---------------------------------------------------------------------------
# 派生属性
# ---------------------------------------------------------------------------


def test_note_default_status_is_noted():
    assert make_note().status is NoteStatus.NOTED
    assert not make_note().unresolved
    assert not make_note().risky


def test_note_issue_links():
    assert make_note(issue_id="0001").promotes_issue
    assert not make_note().promotes_issue

    assert make_note(resolves=["0001"]).resolves_issue
    assert not make_note().resolves_issue


def test_note_unresolved_and_risky():
    open_note = make_note(status=NoteStatus.OPEN)
    assert open_note.unresolved
    assert open_note.risky  # open 且未升级 -> 风险

    promoted = make_note(status=NoteStatus.OPEN, issue_id="0001")
    assert promoted.unresolved
    assert not promoted.risky  # 已升级，不算风险

    assert not make_note(status=NoteStatus.RESOLVED).unresolved


def test_note_written_by_ai():
    assert make_note(author=Actor("ai:claude")).written_by_ai
    assert not make_note(author=Actor("human:lwy")).written_by_ai


def test_note_is_bug_and_controlled_exception():
    assert make_note(kind=NoteKind.BUG).is_bug
    assert not make_note(kind=NoteKind.PITFALL).is_bug
    assert make_note(kind=NoteKind.CONTROLLED_EXCEPTION).is_controlled_exception
    assert not make_note(kind=NoteKind.BUG).is_controlled_exception


def test_bug_risky_until_resolved():
    # 缺陷是负债：未修复即风险，即使登记了 Issue
    assert make_note(kind=NoteKind.BUG, status=NoteStatus.OPEN).risky
    assert make_note(kind=NoteKind.BUG, status=NoteStatus.OPEN,
                     issue_id="0001").risky
    assert not make_note(kind=NoteKind.BUG,
                         status=NoteStatus.RESOLVED).risky


def test_non_bug_risky_only_when_open_and_unpromoted():
    assert make_note(kind=NoteKind.PITFALL, status=NoteStatus.OPEN).risky
    assert not make_note(kind=NoteKind.PITFALL, status=NoteStatus.OPEN,
                         issue_id="0001").risky
    assert not make_note(kind=NoteKind.CONTROLLED_EXCEPTION,
                         status=NoteStatus.NOTED).risky


def test_controlled_exception_catches():
    n = make_note(kind=NoteKind.CONTROLLED_EXCEPTION,
                  catches=["TimeoutError", "ConnectionError"])
    assert n.catches == ["TimeoutError", "ConnectionError"]
    assert make_note().catches == []  # 默认空


def test_note_fields_preserved():
    n = make_note(
        detail="详细说明",
        author=Actor("ai:claude"),
        files=["src/auth/token.py"],
        severity=Priority.HIGH,
        tags=["auth", "concurrency"],
    )
    assert n.detail == "详细说明"
    assert n.files == ["src/auth/token.py"]
    assert n.severity is Priority.HIGH
    assert n.tags == ["auth", "concurrency"]
