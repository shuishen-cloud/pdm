# -*- coding: utf-8 -*-
"""pdev.featview 的测试：feat 视图内核（设计正文读取 + 笔记聚合）。"""

from __future__ import annotations

import pytest

from pdev import CommitNote, NoteKind, NoteStore
from pdev.feat import Feat


@pytest.fixture
def store(tmp_path) -> NoteStore:
    return NoteStore(tmp_path / "notes")


# ---------------------------------------------------------------------------
# read_doc_body
# ---------------------------------------------------------------------------


def test_read_doc_body_reads_file(tmp_path):
    from pdev.featview import read_doc_body

    (tmp_path / "feat").mkdir()
    (tmp_path / "feat" / "a.md").write_text("# 标题\n\n正文\n", encoding="utf-8")
    body = read_doc_body(str(tmp_path), "feat/a.md")
    assert "# 标题" in body and "正文" in body


def test_read_doc_body_missing_returns_marker(tmp_path):
    from pdev.featview import read_doc_body

    assert "不可读" in read_doc_body(str(tmp_path), "feat/nope.md")


def test_read_doc_body_empty_doc():
    from pdev.featview import read_doc_body

    assert read_doc_body(".pdm/docs", "") == ""


def test_read_doc_body_truncates(tmp_path):
    from pdev.featview import read_doc_body

    (tmp_path / "a.md").write_text("\n".join(f"行{i}" for i in range(100)),
                                   encoding="utf-8")
    body = read_doc_body(str(tmp_path), "a.md", max_lines=10)
    assert "行9" in body
    assert "行99" not in body
    assert "截断" in body


# ---------------------------------------------------------------------------
# notes_for_feat
# ---------------------------------------------------------------------------


def test_notes_for_feat(store):
    from pdev.featview import notes_for_feat

    store.add(CommitNote(commit="abc123", kind=NoteKind.BUG, title="缺陷"))
    feat = Feat(slug="a", title="A", commits=["abc123"])
    notes = notes_for_feat(feat, store)
    assert len(notes) == 1
    assert notes[0].title == "缺陷"


def test_notes_for_feat_empty(store):
    from pdev.featview import notes_for_feat

    feat = Feat(slug="a", title="A", commits=["nomatch"])
    assert notes_for_feat(feat, store) == []


def test_notes_for_feat_short_commit_no_false_match(store):
    """短 commit 串不应误匹配（Review 发现）。"""
    from pdev.featview import notes_for_feat

    store.add(CommitNote(commit="abcdef123456", kind=NoteKind.BUG, title="X"))
    feat = Feat(slug="a", title="A", commits=["ab"])   # 太短
    assert notes_for_feat(feat, store) == []
    # 够长的前缀可以匹配
    feat2 = Feat(slug="b", title="B", commits=["abcdef"])
    assert len(notes_for_feat(feat2, store)) == 1


# ---------------------------------------------------------------------------
# group_notes_by_kind
# ---------------------------------------------------------------------------


def test_group_notes_by_kind():
    from pdev.featview import group_notes_by_kind

    notes = [
        CommitNote(commit="a", kind=NoteKind.PITFALL, title="p1"),
        CommitNote(commit="a", kind=NoteKind.DIFFICULTY, title="d1"),
        CommitNote(commit="b", kind=NoteKind.PITFALL, title="p2"),
    ]
    groups = group_notes_by_kind(notes)
    assert [k for k, _ in groups] == ["pitfall", "difficulty"]
    assert len(groups[0][1]) == 2


def test_group_notes_by_kind_empty():
    from pdev.featview import group_notes_by_kind

    assert group_notes_by_kind([]) == []


# ---------------------------------------------------------------------------
# 零依赖：内核不 import textual
# ---------------------------------------------------------------------------


def test_featview_no_textual_dependency():
    import inspect

    import pdev.featview

    src = inspect.getsource(pdev.featview)
    # 不应 import textual（docstring 里提到词不算）
    assert "import textual" not in src
    assert "from textual" not in src
