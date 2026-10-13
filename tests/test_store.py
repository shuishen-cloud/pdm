# -*- coding: utf-8 -*-
"""pdev.store 的测试。"""

from __future__ import annotations

import json

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStatus, NoteStore, Priority
from tests.conftest import at


def note(**kw) -> CommitNote:
    base = dict(
        commit="abc123",
        kind=NoteKind.PITFALL,
        title="token 刷新有竞态",
        author=Actor("human:lwy"),
        created_at=at(0),
    )
    base.update(kw)
    return CommitNote(**base)


@pytest.fixture
def store(tmp_path) -> NoteStore:
    return NoteStore(tmp_path / "notes")


# ---------------------------------------------------------------------------
# 基本读写
# ---------------------------------------------------------------------------


def test_add_and_len(store):
    store.add(note())
    assert len(store) == 1


def test_add_rejects_invalid(store):
    with pytest.raises(ValueError):
        store.add(note(title=""))


def test_add_many(store):
    store.add_many([note(commit="a"), note(commit="a"), note(commit="b")])
    assert len(store) == 3


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def test_persists_across_instances(tmp_path):
    root = tmp_path / "notes"
    s1 = NoteStore(root)
    s1.add(note(issue_id="0001", files=["src/auth/token.py"], tags=["auth"]))

    s2 = NoteStore(root)
    assert len(s2) == 1
    n = next(s2.all())
    assert n.commit == "abc123"
    assert n.kind is NoteKind.PITFALL
    assert n.issue_id == "0001"
    assert n.files == ["src/auth/token.py"]
    assert n.tags == ["auth"]
    assert n.author == Actor("human:lwy")
    assert n.created_at == at(0)


def test_persists_severity_and_status(tmp_path):
    root = tmp_path / "notes"
    s1 = NoteStore(root)
    s1.add(note(severity=Priority.HIGH, status=NoteStatus.OPEN))

    n = next(NoteStore(root).all())
    assert n.severity is Priority.HIGH
    assert n.status is NoteStatus.OPEN


def test_persists_catches(tmp_path):
    root = tmp_path / "notes"
    s1 = NoteStore(root)
    s1.add(note(kind=NoteKind.CONTROLLED_EXCEPTION,
                catches=["TimeoutError", "ValueError"]))

    n = next(NoteStore(root).all())
    assert n.kind is NoteKind.CONTROLLED_EXCEPTION
    assert n.catches == ["TimeoutError", "ValueError"]


def test_persists_verifications(tmp_path):
    from pdev import Verification, VerificationKind, VerificationStatus

    root = tmp_path / "notes"
    v = Verification(kind=VerificationKind.TEST,
                     target="tests/x.py::test_y",
                     expected="passed")
    v.record(VerificationStatus.PASSED, at(9), "ok")
    s1 = NoteStore(root)
    s1.add(note(verifications=[v]))

    n = next(NoteStore(root).all())
    assert len(n.verifications) == 1
    got = n.verifications[0]
    assert got.kind is VerificationKind.TEST
    assert got.target == "tests/x.py::test_y"
    assert got.expected == "passed"
    assert got.last_status is VerificationStatus.PASSED
    assert got.last_run_at == at(9)
    assert got.last_output == "ok"


def test_verification_helpers(tmp_path):
    from pdev import Verification, VerificationKind

    s = NoteStore(tmp_path / "notes")
    s.add(note(commit="a",
               verifications=[Verification(kind=VerificationKind.COMMAND,
                                           command="true")]))
    s.add(note(commit="b", kind=NoteKind.BUG, title="no verify"))

    assert len(s.with_verifications()) == 1
    assert len(s.needing_verification()) == 1


def test_update_rewrites_note(tmp_path):
    from pdev import Verification, VerificationKind, VerificationStatus

    root = tmp_path / "notes"
    s = NoteStore(root)
    s.add(note(commit="a"))

    n = s.by_commit("a")[0]
    n.verifications.append(Verification(kind=VerificationKind.COMMAND,
                                        command="true"))
    n.verifications[0].record(VerificationStatus.PASSED, at(1), "ok")
    assert s.update(n)

    reloaded = NoteStore(root).by_commit("a")[0]
    assert reloaded.verifications[0].last_status is VerificationStatus.PASSED


def test_roundtrip_none_fields(tmp_path):
    root = tmp_path / "notes"
    s1 = NoteStore(root)
    s1.add(note(severity=None, created_at=None))

    n = next(NoteStore(root).all())
    assert n.severity is None
    assert n.created_at is None


def test_one_file_per_commit(store):
    store.add(note(commit="a"))
    store.add(note(commit="a", title="另一条"))
    store.add(note(commit="b"))

    d = store.root / "by-commit"
    assert (d / "a.json").exists()
    assert (d / "b.json").exists()

    data = json.loads((d / "a.json").read_text(encoding="utf-8"))
    assert data["commit"] == "a"
    assert len(data["notes"]) == 2


def test_index_is_written(store):
    store.add(note(issue_id="0001"))
    store.add(note(commit="b", kind=NoteKind.BUG))
    idx = json.loads((store.root / "index.json").read_text(encoding="utf-8"))
    assert idx["count"] == 2
    assert idx["by_kind"]["pitfall"] == 1
    assert idx["by_kind"]["bug"] == 1
    assert idx["by_issue"] == {"0001": 1}
    assert idx["commits"] == ["abc123", "b"]


def test_corrupt_file_is_skipped(tmp_path):
    root = tmp_path / "notes"
    s = NoteStore(root)
    s.add(note())
    (root / "by-commit" / "broken.json").write_text("{not json", encoding="utf-8")

    assert len(NoteStore(root)) == 1  # 坏文件被跳过，好数据仍可读


# ---------------------------------------------------------------------------
# 单条件查询
# ---------------------------------------------------------------------------


def test_queries(store):
    store.add(note(commit="a", kind=NoteKind.PROBLEM, tags=["auth"],
                   files=["src/auth/a.py"], issue_id="0001"))
    store.add(note(commit="b", kind=NoteKind.PITFALL, status=NoteStatus.OPEN,
                   tags=["db"], files=["src/db/b.py"]))
    store.add(note(commit="c", kind=NoteKind.PITFALL,
                   resolves=["0001"]))

    assert len(store.by_commit("a")) == 1
    assert len(store.by_kind(NoteKind.PITFALL)) == 2
    assert len(store.by_status(NoteStatus.OPEN)) == 1
    assert len(store.by_tag("auth")) == 1
    assert len(store.by_file("src/db/b.py")) == 1
    assert store.by_tag("nope") == []


def test_by_issue_covers_promote_and_resolve(store):
    store.add(note(commit="a", issue_id="0001"))       # 升级
    store.add(note(commit="b", resolves=["0001"]))     # 解决
    store.add(note(commit="c"))                        # 无关
    assert len(store.by_issue("0001")) == 2
    assert store.by_issue("9999") == []


def test_get_by_index(store):
    store.add(note(commit="a"))
    store.add(note(commit="b"))
    assert store.get(0).commit == "a"
    assert store.get(1).commit == "b"
    assert store.get(99) is None
    assert store.get(-1) is None


def test_empty_store(tmp_path):
    s = NoteStore(tmp_path / "n")
    assert len(s) == 0
    assert list(s.all()) == []
    s.rebuild_index()  # 空存储也能重建索引


def test_by_commit_prefix_match(store):
    """笔记存短 hash，调用方可能给 8/40 位——应前缀互匹配。"""
    store.add(CommitNote(commit="8d84a9b", kind=NoteKind.BUG, title="X"))
    assert len(store.by_commit("8d84a9b")) == 1
    assert len(store.by_commit("8d84a9ba")) == 1
    assert len(store.by_commit("8d84a9ba1234")) == 1
    assert len(store.by_commit("8d84a9c")) == 0     # 不匹配


def test_by_commit_short_string_no_false_match(store):
    """太短的前缀（<6 位）不应误匹配。"""
    store.add(CommitNote(commit="abcdef123456", kind=NoteKind.BUG, title="X"))
    assert store.by_commit("ab") == []
