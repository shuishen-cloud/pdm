# -*- coding: utf-8 -*-
"""pdev.query 的测试。"""

from __future__ import annotations

import pytest

from pdev import (
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    NoteStore,
    Query,
    search,
)
from tests.conftest import at


def note(**kw) -> CommitNote:
    base = dict(
        commit="abc123",
        kind=NoteKind.PITFALL,
        title="token 刷新有竞态",
        detail="",
        author=Actor("human:lwy"),
        created_at=at(0),
    )
    base.update(kw)
    return CommitNote(**base)


@pytest.fixture
def store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        note(commit="a", kind=NoteKind.PITFALL, status=NoteStatus.OPEN,
             title="刷新有竞态", detail="加锁解决",
             files=["src/auth/token.py"], tags=["auth"], created_at=at(10)),
        note(commit="b", kind=NoteKind.PROBLEM, status=NoteStatus.OPEN,
             title="登录超时", files=["src/auth/login.py"], tags=["auth"],
             issue_id="0001", created_at=at(20)),
        note(commit="c", kind=NoteKind.BUG, status=NoteStatus.RESOLVED,
             title="空指针", files=["src/db/conn.py"], tags=["db"],
             author=Actor("ai:claude"), created_at=at(30)),
        note(commit="d", kind=NoteKind.DIFFICULTY, status=NoteStatus.NOTED,
             title="异步上下文拿不到 config", files=["src/core/ctx.py"],
             created_at=None),
    ])
    return s


# ---------------------------------------------------------------------------
# 空查询 / 排序
# ---------------------------------------------------------------------------


def test_empty_query_returns_all(store):
    assert len(search(store, Query())) == 4


def test_sorted_newest_first(store):
    got = search(store, Query())
    # 有时间的按降序在前，无时间的排最后
    assert [n.commit for n in got] == ["c", "b", "a", "d"]


def test_limit(store):
    assert len(search(store, Query(limit=2))) == 2
    assert search(store, Query(limit=0)) == []
    assert len(search(store, Query(limit=None))) == 4


# ---------------------------------------------------------------------------
# 单维度
# ---------------------------------------------------------------------------


def test_by_kind(store):
    got = search(store, Query(kind=NoteKind.PITFALL))
    assert [n.commit for n in got] == ["a"]


def test_by_status(store):
    got = search(store, Query(status=NoteStatus.OPEN))
    assert [n.commit for n in got] == ["b", "a"]


def test_by_commit(store):
    assert [n.commit for n in search(store, Query(commit="c"))] == ["c"]


def test_by_tag(store):
    got = search(store, Query(tag="auth"))
    assert sorted(n.commit for n in got) == ["a", "b"]


def test_by_issue(store):
    got = search(store, Query(issue_id="0001"))
    assert [n.commit for n in got] == ["b"]


def test_by_author_kind(store):
    got = search(store, Query(author="ai"))
    assert [n.commit for n in got] == ["c"]


# ---------------------------------------------------------------------------
# 文件 glob
# ---------------------------------------------------------------------------


def test_file_glob(store):
    got = search(store, Query(file="src/auth/**"))
    assert sorted(n.commit for n in got) == ["a", "b"]


def test_file_glob_exact(store):
    got = search(store, Query(file="src/db/conn.py"))
    assert [n.commit for n in got] == ["c"]


def test_file_glob_no_match(store):
    assert search(store, Query(file="src/payment/**")) == []


# ---------------------------------------------------------------------------
# 全文
# ---------------------------------------------------------------------------


def test_text_matches_title(store):
    assert [n.commit for n in search(store, Query(text="竞态"))] == ["a"]


def test_text_matches_detail(store):
    assert [n.commit for n in search(store, Query(text="加锁"))] == ["a"]


def test_text_matches_tags(store):
    assert sorted(n.commit for n in search(store, Query(text="db"))) == ["c"]


def test_text_case_insensitive(store):
    s = NoteStore(store.root)
    s.add(note(commit="e", title="Config 丢失"))
    # 命中 e 与 d（d 的标题含 "config"），且不区分大小写
    got = search(s, Query(text="config"))
    assert {n.commit for n in got} == {"d", "e"}

    got = search(s, Query(text="CONFIG"))
    assert {n.commit for n in got} == {"d", "e"}


def test_text_no_match(store):
    assert search(store, Query(text="不存在的东西")) == []


# ---------------------------------------------------------------------------
# 时间范围
# ---------------------------------------------------------------------------


def test_since(store):
    got = search(store, Query(since=at(20)))
    assert [n.commit for n in got] == ["c", "b"]


def test_until(store):
    got = search(store, Query(until=at(20)))
    assert [n.commit for n in got] == ["b", "a"]


def test_since_excludes_undated(store):
    # 无 created_at 的笔记在时间筛选中被排除
    assert all(n.commit != "d" for n in search(store, Query(since=at(0))))


# ---------------------------------------------------------------------------
# 组合
# ---------------------------------------------------------------------------


def test_combined(store):
    got = search(store, Query(kind=NoteKind.PITFALL, file="src/auth/**",
                              status=NoteStatus.OPEN))
    assert [n.commit for n in got] == ["a"]

    assert search(store, Query(kind=NoteKind.PITFALL, tag="db")) == []
    assert search(store, Query(tag="auth", author="ai")) == []


def test_matches_method_is_public(store):
    q = Query(kind=NoteKind.PROBLEM)
    hit = note(kind=NoteKind.PROBLEM)
    miss = note(kind=NoteKind.PITFALL)
    assert q.matches(hit) is True
    assert q.matches(miss) is False
