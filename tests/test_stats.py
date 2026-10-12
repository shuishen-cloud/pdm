# -*- coding: utf-8 -*-
"""pdev.stats 的测试（Issue 与 Note 两部分）。"""

from __future__ import annotations

from pdev import (
    Actor,
    CommitNote,
    Generated,
    NoteKind,
    NoteStatus,
    NoteStore,
    Status,
    compute_note_stats,
    compute_stats,
)


# ---------------------------------------------------------------------------
# Issue 统计
# ---------------------------------------------------------------------------


def test_compute_stats(make_issue):
    issues = [
        make_issue(
            id="1",
            status=Status.OPEN,
            origin_fingerprint=Generated.AI_FULL,
            reporter=Actor("ai:claude"),
        ),
        make_issue(
            id="2",
            status=Status.CLOSED,
            origin_fingerprint=Generated.AI_FULL,
            reporter=Actor("human:lwy"),
            fix_commit="abc",
        ),
        make_issue(
            id="3",
            status=Status.IN_PROGRESS,
            origin_fingerprint=Generated.HUMAN,
            reporter=Actor("human:lwy"),
            fix_commit="def",
        ),
        make_issue(
            id="4",
            status=Status.CLOSED,
            origin_fingerprint=Generated.HUMAN,
            reporter=Actor("ci"),
            fix_commit="ghi",
        ),
    ]
    s = compute_stats(issues)
    assert s.total == 4
    assert s.open == 2
    assert s.ai_caused == 2
    assert s.ai_reported == 1
    assert s.fixed == 3
    assert s.ai_cause_rate == 0.5


def test_compute_stats_empty():
    s = compute_stats([])
    assert s.total == 0
    assert s.ai_cause_rate == 0.0


def test_compute_stats_accepts_generator(make_issue):
    gen = (make_issue(id=str(n)) for n in range(3))
    assert compute_stats(gen).total == 3


# ---------------------------------------------------------------------------
# Note 统计
# ---------------------------------------------------------------------------


def test_compute_note_stats(tmp_path):
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="a", kind=NoteKind.PITFALL, title="t1",
                   status=NoteStatus.OPEN, files=["x.py"]),
        CommitNote(commit="a", kind=NoteKind.PITFALL, title="t2",
                   status=NoteStatus.OPEN, issue_id="0001", files=["y.py"]),
        CommitNote(commit="b", kind=NoteKind.BUG, title="t3",
                   status=NoteStatus.RESOLVED, author=Actor("ai:claude")),
        CommitNote(commit="c", kind=NoteKind.DIFFICULTY, title="t4",
                   status=NoteStatus.NOTED),
    ])
    st = compute_note_stats(s)
    assert st.total == 4
    assert st.by_kind == {"pitfall": 2, "bug": 1, "difficulty": 1}
    assert st.open == 2
    assert st.promoted == 1
    assert st.resolved == 1
    assert st.written_by_ai == 1
    assert st.risky == 1          # t1: open 且未升级
    assert st.commits == 3        # a, b, c
    assert st.files == 2          # x.py, y.py


def test_compute_note_stats_empty(tmp_path):
    st = compute_note_stats(NoteStore(tmp_path / "n"))
    assert st.total == 0
    assert st.by_kind == {}
    assert st.commits == 0
    assert st.bugs == 0
    assert st.caught_types == 0


def test_note_stats_bugs_and_exceptions(tmp_path):
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="a", kind=NoteKind.BUG, title="未修缺陷",
                   status=NoteStatus.OPEN),
        CommitNote(commit="b", kind=NoteKind.BUG, title="已修缺陷",
                   status=NoteStatus.RESOLVED),
        CommitNote(commit="c", kind=NoteKind.CONTROLLED_EXCEPTION,
                   title="缓存超时降级", catches=["TimeoutError"]),
        CommitNote(commit="c", kind=NoteKind.CONTROLLED_EXCEPTION,
                   title="连接失败重试",
                   catches=["ConnectionError", "TimeoutError"]),
    ])
    st = compute_note_stats(s)
    assert st.bugs == 2
    assert st.bugs_open == 1
    assert st.controlled_exceptions == 2
    assert st.caught_types == 2   # TimeoutError, ConnectionError 去重
    assert st.risky == 1          # 只有未修缺陷
