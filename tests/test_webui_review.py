# -*- coding: utf-8 -*-
"""Web UI 的 Review 勾选测试（web-ui-review）。

设计见 ``doc/feat/web-ui-review.md``。**首个写操作**，因此用例重点在
**拒绝非法输入**与**作者由服务端决定**。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from pdev import NoteStore
from pdev.feat import Feat, FeatKind, FeatStore
from pdev.webui import (
    apply_review,
    build_data,
    build_feat_detail,
    build_review_items,
    make_handler,
)


class _FakeGit:
    available = False

    def log(self, limit: int = 0, ref: str = "HEAD"):
        return []

    def commit_info(self, ref: str):
        return None


@pytest.fixture
def feat_store(tmp_path) -> FeatStore:
    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(
        slug="alpha", title="功能甲", kind=FeatKind.FEAT,
        doc="feat/alpha.md",
        api=["Alpha.run(x) -> int", "Alpha.stop() -> None"],
        logs=["运行日志"],
        fallbacks=["降级为 0"],
    ))
    return fs


@pytest.fixture
def note_store(tmp_path) -> NoteStore:
    return NoteStore(tmp_path / "notes")


@pytest.fixture
def doc_dir(tmp_path):
    d = tmp_path / "doc" / "feat"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text("# 甲\n", encoding="utf-8")
    return str(tmp_path / "doc")


# ---------------------------------------------------------------------------
# 纯函数：build_review_items
# ---------------------------------------------------------------------------


def test_build_review_items_shape(feat_store):
    feat = feat_store.get("alpha")
    items = build_review_items(feat)
    assert items, "应有可审项"
    keys = {it["key"] for it in items}
    # doc + api:0/1 + logs:0 + fallbacks:0
    assert keys == {"doc", "api:0", "api:1", "logs:0", "fallbacks:0"}
    for it in items:
        for f in ("key", "label", "reviewed", "tested", "comment"):
            assert f in it, f


def test_build_review_items_reflects_state(feat_store):
    feat_store.set_reviews("alpha", ["api:0"], reviewed=True,
                           by="human:lwy")
    items = build_review_items(feat_store.get("alpha"))
    by_key = {it["key"]: it for it in items}
    assert by_key["api:0"]["reviewed"] is True
    assert by_key["api:1"]["reviewed"] is False


def test_build_feat_detail_includes_review_items(feat_store, note_store,
                                                doc_dir):
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    assert "review_items" in d
    assert isinstance(d["review_items"], list)
    assert d["review_items"]


# ---------------------------------------------------------------------------
# 纯函数：apply_review（校验 + 写入）
# ---------------------------------------------------------------------------


def test_apply_review_sets_reviewed(feat_store):
    r = apply_review(feat_store, {"slug": "alpha", "key": "api:0",
                                  "field": "review", "value": True},
                     by="human:lwy")
    assert r["ok"] is True
    assert r["reviewed"] == 1
    feat = feat_store.get("alpha")
    assert feat.review_item("api:0").reviewed is True


def test_apply_review_sets_tested(feat_store):
    r = apply_review(feat_store, {"slug": "alpha", "key": "api:0",
                                  "field": "test", "value": True},
                     by="human:lwy")
    assert r["ok"] is True
    assert feat_store.get("alpha").review_item("api:0").tested is True


def test_apply_review_can_uncheck(feat_store):
    apply_review(feat_store, {"slug": "alpha", "key": "api:0",
                              "field": "review", "value": True},
                 by="human:lwy")
    r = apply_review(feat_store, {"slug": "alpha", "key": "api:0",
                                  "field": "review", "value": False},
                     by="human:lwy")
    assert r["ok"] is True
    assert r["reviewed"] == 0


def test_apply_review_by_comes_from_server(feat_store):
    """作者由服务端参数决定，payload 里塞的 by 必须被忽略。"""
    apply_review(feat_store,
                 {"slug": "alpha", "key": "api:0", "field": "review",
                  "value": True, "by": "ai:evil"},
                 by="human:lwy")
    item = feat_store.get("alpha").review_item("api:0")
    assert item.reviewed_by == "human:lwy"


@pytest.mark.parametrize("payload,status", [
    ({"slug": "alpha", "key": "api:0", "field": "title", "value": True}, 400),
    ({"slug": "alpha", "key": "api:0", "field": "review", "value": "yes"}, 400),
    ({"slug": "alpha", "key": "api:0", "field": "review"}, 400),
    ({"slug": "alpha", "key": "nope:9", "field": "review", "value": True}, 400),
    ({"key": "api:0", "field": "review", "value": True}, 400),
])
def test_apply_review_rejects_bad_input(feat_store, payload, status):
    r = apply_review(feat_store, payload, by="human:lwy")
    assert r["ok"] is False
    assert r["_status"] == status


def test_apply_review_unknown_slug_404(feat_store):
    r = apply_review(feat_store, {"slug": "nope", "key": "api:0",
                                  "field": "review", "value": True})
    assert r["ok"] is False and r["_status"] == 404


def test_apply_review_without_store_403():
    r = apply_review(None, {"slug": "alpha", "key": "api:0",
                            "field": "review", "value": True})
    assert r["ok"] is False and r["_status"] == 403


def test_apply_review_no_path_traversal(feat_store):
    """slug 含路径分隔符不应越界，只做查表 → 404。"""
    r = apply_review(feat_store, {"slug": "../../etc/passwd", "key": "api:0",
                                  "field": "review", "value": True})
    assert r["ok"] is False
    assert r["_status"] == 404


def test_apply_review_response_has_items(feat_store):
    r = apply_review(feat_store, {"slug": "alpha", "key": "doc",
                                  "field": "review", "value": True},
                     by="human:lwy")
    assert "items" in r and r["items"]
    assert all("key" in it for it in r["items"])
    assert "total" in r


# ---------------------------------------------------------------------------
# HTTP 路由
# ---------------------------------------------------------------------------


def _serve(data, feat_store=None, note_store=None, doc_dir="doc",
           by="human:lwy"):
    import socketserver

    handler = make_handler(data, feat_store=feat_store,
                           note_store=note_store, doc_dir=doc_dir, by=by)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{port}", lambda: (httpd.shutdown(),
                                                httpd.server_close())


def _post(url, payload):
    req = urllib.request.Request(
        url, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5)


def test_post_review_route_writes(feat_store, note_store, doc_dir):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store, doc_dir)
    try:
        with _post(base + "/api/review",
                   {"slug": "alpha", "key": "api:0",
                    "field": "review", "value": True}) as r:
            assert r.status == 200
            body = json.loads(r.read().decode("utf-8"))
        assert body["ok"] is True
        assert body["reviewed"] == 1
        # 再查详情应已持久
        with urllib.request.urlopen(base + "/api/feat/alpha", timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        by_key = {it["key"]: it for it in d["review_items"]}
        assert by_key["api:0"]["reviewed"] is True
    finally:
        stop()


def test_other_post_still_405(feat_store, note_store, doc_dir):
    """写面不得扩大：只有 /api/review 可写。"""
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store, doc_dir)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(base + "/api/data", {"x": 1})
        assert e.value.code == 405
    finally:
        stop()


def test_post_review_bad_json_400(feat_store, note_store, doc_dir):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store, doc_dir)
    try:
        req = urllib.request.Request(
            base + "/api/review", method="POST", data=b"{not json",
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 400
    finally:
        stop()


def test_post_review_unknown_slug_404_http(feat_store, note_store, doc_dir):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store, doc_dir)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(base + "/api/review",
                  {"slug": "nope", "key": "api:0",
                   "field": "review", "value": True})
        assert e.value.code == 404
    finally:
        stop()


def test_error_body_does_not_leak_path(feat_store, note_store, doc_dir):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store, doc_dir)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(base + "/api/review",
                  {"slug": "nope", "key": "api:0",
                   "field": "review", "value": True})
        body = e.value.read().decode("utf-8")
        assert "Traceback" not in body
        assert "/tmp" not in body
    finally:
        stop()


# ---------------------------------------------------------------------------
# 前端契约
# ---------------------------------------------------------------------------


def test_page_has_checkboxes_and_post():
    from pdev.webui import PAGE

    for token in ("/api/review", "toggleReview", "method: \"POST\"",
                  "data-key"):
        assert token in PAGE, token


def test_page_still_no_external_resources():
    import re

    from pdev.webui import PAGE

    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', PAGE)
    assert not [u for u in urls if u.startswith(("http", "//"))]
