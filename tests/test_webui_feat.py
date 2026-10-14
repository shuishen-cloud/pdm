# -*- coding: utf-8 -*-
"""Web UI 的 Feat 视图测试（web-ui-feat）。

设计见 ``doc/feat/web-ui-feat.md``。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStore
from pdev.feat import Feat, FeatKind, FeatStatus, FeatStore
from pdev.webui import (
    build_data,
    build_feat_detail,
    build_feats,
    make_handler,
)


class _FakeGit:
    available = False

    def log(self, limit: int = 0, ref: str = "HEAD"):
        return []

    def commit_info(self, ref: str):
        return None


@pytest.fixture
def note_store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="abc1234def", kind=NoteKind.PITFALL, title="并发竞态",
                   author=Actor("human:lwy")),
        CommitNote(commit="def5678abc", kind=NoteKind.BUG, title="计数泄漏",
                   author=Actor("ai:claude")),
    ])
    return s


@pytest.fixture
def feat_store(tmp_path) -> FeatStore:
    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(
        slug="alpha", title="功能甲", kind=FeatKind.FEAT,
        status=FeatStatus.CLOSED, stage="close",
        doc="feat/alpha.md",
        api=["Alpha.run(x) -> int"],
        logs=["运行时记录 x"],
        fallbacks=["异常降级为 0"],
        design_note="为了甲",
        impl_note="用 dict 实现",
        data_model=["Alpha: dict[str,int]"],
        samples=['{"a": 1}'],
        changes=["pdev/x.py::Alpha —— 新增"],
        commits=["abc1234def", "def5678abc"],
    ))
    fs.add(Feat(slug="beta", title="功能乙", stage=None))
    return fs


@pytest.fixture
def doc_dir(tmp_path):
    d = tmp_path / "doc" / "feat"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text("# 甲的设计\n\n## 规范\n\n正文内容\n",
                                encoding="utf-8")
    return str(tmp_path / "doc")


# ---------------------------------------------------------------------------
# 纯函数：build_feats
# ---------------------------------------------------------------------------


def test_build_feats_shape(feat_store, note_store):
    feats = build_feats(feat_store, note_store)
    assert len(feats) == 2
    by = {f["slug"]: f for f in feats}
    a = by["alpha"]
    for key in ("slug", "title", "kind", "status", "stage",
                "commit_count", "review", "missing_fields"):
        assert key in a, key
    assert a["stage"] == "close"
    assert a["commit_count"] == 2
    assert by["beta"]["stage"] is None


def test_build_feats_no_store_returns_empty():
    assert build_feats(None, None) == []


def test_build_feats_review_counts_shape(feat_store, note_store):
    feats = build_feats(feat_store, note_store)
    review = feats[0]["review"]
    assert isinstance(review, list) and len(review) == 2
    done, total = review
    assert 0 <= done <= total


def test_build_feats_missing_fields_reported(tmp_path, note_store):
    fs = FeatStore(tmp_path / "f2")
    fs.add(Feat(slug="bare", title="缺字段"))
    feats = build_feats(fs, note_store)
    assert feats[0]["missing_fields"], "缺字段的 feat 应报出 missing_fields"


# ---------------------------------------------------------------------------
# 纯函数：build_feat_detail
# ---------------------------------------------------------------------------


def test_build_feat_detail_includes_doc_body(feat_store, note_store, doc_dir):
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    assert d is not None
    assert d["slug"] == "alpha"
    for key in ("api", "logs", "fallbacks", "design_note", "impl_note",
                "data_model", "samples", "changes", "commits",
                "doc_body", "doc_missing", "notes", "stage_reviews"):
        assert key in d, key
    assert "甲的设计" in d["doc_body"]
    assert d["doc_missing"] is False


def test_build_feat_detail_unknown_slug_none(feat_store, note_store, doc_dir):
    assert build_feat_detail(feat_store, note_store, doc_dir, "nope") is None


def test_build_feat_detail_missing_doc(feat_store, note_store, tmp_path):
    empty_doc = tmp_path / "nodoc"
    empty_doc.mkdir()
    d = build_feat_detail(feat_store, note_store, str(empty_doc), "alpha")
    assert d is not None
    assert d["doc_body"] == ""
    assert d["doc_missing"] is True


def test_feat_notes_use_featview_matching(feat_store, note_store, doc_dir):
    """关联笔记必须走 featview.notes_for_feat（含前缀匹配），不自行实现。"""
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    titles = {n["title"] for n in d["notes"]}
    assert titles == {"并发竞态", "计数泄漏"}
    assert d["notes_by_kind"]


def test_build_feat_detail_is_json_serializable(feat_store, note_store,
                                               doc_dir):
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    assert json.loads(json.dumps(d, ensure_ascii=False))


def test_build_feats_source_does_not_reimplement_matching():
    """build_feats/build_feat_detail 不得自行写 startswith 匹配。"""
    import inspect

    from pdev import webui

    for fn in (webui.build_feats, webui.build_feat_detail):
        src = inspect.getsource(fn)
        assert "startswith" not in src, f"{fn.__name__} 不应自行匹配 hash"


# ---------------------------------------------------------------------------
# HTTP 路由
# ---------------------------------------------------------------------------


def _serve(data, feat_store=None, note_store=None, doc_dir="doc"):
    import socketserver

    handler = make_handler(data, feat_store=feat_store,
                           note_store=note_store, doc_dir=doc_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{port}", lambda: (httpd.shutdown(),
                                                httpd.server_close())


def test_api_data_includes_feats(feat_store, note_store):
    data = build_data(note_store, _FakeGit())
    data["feats"] = build_feats(feat_store, note_store)
    base, stop = _serve(data, feat_store, note_store)
    try:
        with urllib.request.urlopen(base + "/api/data", timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
        assert "feats" in payload
        assert {f["slug"] for f in payload["feats"]} == {"alpha", "beta"}
    finally:
        stop()


def test_api_feat_route_and_404(feat_store, note_store):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store)
    try:
        with urllib.request.urlopen(base + "/api/feat/alpha", timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        assert d["slug"] == "alpha"

        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/feat/nope", timeout=5)
        assert e.value.code == 404
    finally:
        stop()


def test_api_feat_route_absent_without_store(note_store):
    """未传 feat_store 时，/api/feat/<slug> 返回 404（不崩）。"""
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/feat/alpha", timeout=5)
        assert e.value.code == 404
    finally:
        stop()


# ---------------------------------------------------------------------------
# 前端契约
# ---------------------------------------------------------------------------


def test_page_has_feat_view():
    from pdev.webui import PAGE

    for token in ("Feat", "/api/feat/", "view-feat", "renderFeat",
                  "renderFeatDetail"):
        assert token in PAGE, token


def test_page_still_no_external_resources():
    import re

    from pdev.webui import PAGE

    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', PAGE)
    assert not [u for u in urls if u.startswith(("http", "//"))]
