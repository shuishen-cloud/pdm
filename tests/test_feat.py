# -*- coding: utf-8 -*-
"""pdev.feat 的测试：Feat 数据结构与 FeatStore 存储。"""

from __future__ import annotations

import json

import pytest

from pdev.feat import (
    Feat,
    FeatError,
    FeatKind,
    FeatStatus,
    FeatStore,
    valid_slug,
)
from tests.fixtures.feat_storage import (
    BAD_SLUGS,
    FULL_FEAT,
    MINIMAL_FEAT,
)


@pytest.fixture
def store(tmp_path) -> FeatStore:
    return FeatStore(tmp_path / "feats")


# ---------------------------------------------------------------------------
# slug 校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["feat-storage", "a", "x1-y2", "123"])
def test_valid_slug_accepts(slug):
    assert valid_slug(slug)


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_valid_slug_rejects(slug):
    assert not valid_slug(slug)


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_feat_rejects_bad_slug(slug):
    with pytest.raises(FeatError):
        Feat(slug=slug, title="x")


# ---------------------------------------------------------------------------
# 构造与校验
# ---------------------------------------------------------------------------


def test_minimal_feat_defaults():
    f = Feat(**MINIMAL_FEAT)
    assert f.kind is FeatKind.FEAT
    assert f.status is FeatStatus.DRAFT
    assert f.api == []
    assert f.commits == []
    assert f.created_at is not None
    assert f.updated_at == f.created_at


def test_full_feat_fields_roundtrip_via_store(store):
    f = Feat(**FULL_FEAT)
    store.add(f)
    got = store.get("demo-feat")
    assert got is not None
    assert got.title == "演示功能"
    assert got.api == ["pdm demo run"]
    assert got.fixtures == ["tests/fixtures/feat_storage.py"]
    assert got.touches == ["pdev/demo.py"]
    assert got.follows == ["JSON 分片存储"]
    assert got.logs == ["demo.created"]
    assert got.debug == "pdm demo --debug"


def test_validate_requires_title():
    with pytest.raises(FeatError):
        Feat(slug="ok", title="").validate()


# ---------------------------------------------------------------------------
# 状态机
# ---------------------------------------------------------------------------


def test_status_progression():
    f = Feat(slug="s", title="t")
    assert f.status is FeatStatus.DRAFT
    f.advance(FeatStatus.TESTING)
    assert f.status is FeatStatus.TESTING
    f.advance(FeatStatus.INTEGRATED)
    f.advance(FeatStatus.FIXING)
    f.advance(FeatStatus.CLOSED)
    assert f.status is FeatStatus.CLOSED


def test_status_cannot_go_backwards():
    f = Feat(slug="s", title="t")
    f.advance(FeatStatus.INTEGRATED)
    with pytest.raises(FeatError, match="倒退"):
        f.advance(FeatStatus.DRAFT)


def test_advance_same_status_is_ok():
    f = Feat(slug="s", title="t")
    f.advance(FeatStatus.DRAFT)      # 不算倒退
    assert f.status is FeatStatus.DRAFT


def test_next_step_per_status():
    f = Feat(slug="s", title="t")
    assert "测试" in f.next_step
    f.advance(FeatStatus.CLOSED)
    assert f.next_step is None


# ---------------------------------------------------------------------------
# FeatStore 读写
# ---------------------------------------------------------------------------


def test_add_and_get(store):
    store.add(Feat(slug="a", title="A"))
    assert len(store) == 1
    assert store.has("a")
    assert store.get("a").title == "A"
    assert store.get("nope") is None


def test_add_duplicate_raises(store):
    store.add(Feat(slug="a", title="A"))
    with pytest.raises(FeatError, match="已存在"):
        store.add(Feat(slug="a", title="A2"))


def test_persists_one_file_per_feat(store):
    store.add(Feat(slug="a", title="A"))
    store.add(Feat(slug="b", title="B"))
    files = sorted(p.name for p in (store.root / "by-id").glob("*.json"))
    assert files == ["a.json", "b.json"]


def test_reload_from_disk(tmp_path):
    s1 = FeatStore(tmp_path / "feats")
    s1.add(Feat(slug="a", title="A", api=["x"]))
    s2 = FeatStore(tmp_path / "feats")
    assert len(s2) == 1
    assert s2.get("a").api == ["x"]


def test_file_is_valid_strict_json(store):
    store.add(Feat(slug="a", title="A"))
    raw = (store.root / "by-id" / "a.json").read_text(encoding="utf-8")
    data = json.loads(raw)          # 严格 JSON
    assert data["slug"] == "a"
    assert data["status"] == "draft"


def test_skip_corrupt_file(tmp_path):
    root = tmp_path / "feats"
    (root / "by-id").mkdir(parents=True)
    (root / "by-id" / "bad.json").write_text("{ not json", encoding="utf-8")
    store = FeatStore(root)         # 不应抛异常
    assert len(store) == 0


def test_skip_invalid_record_but_keep_others(tmp_path):
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "good.json").write_text(
        json.dumps({"slug": "good", "title": "G"}), encoding="utf-8")
    (d / "evil.json").write_text(
        json.dumps({"slug": "Bad Slug", "title": "E"}), encoding="utf-8")
    store = FeatStore(root)
    assert len(store) == 1
    assert store.has("good")


# ---------------------------------------------------------------------------
# 关联：link / found
# ---------------------------------------------------------------------------


def test_link_commit(store):
    store.add(Feat(slug="a", title="A"))
    feat = store.link_commit("a", "4fd0fec")
    assert feat.commits == ["4fd0fec"]
    # 幂等：重复 link 不重复添加
    store.link_commit("a", "4fd0fec")
    assert store.get("a").commits == ["4fd0fec"]
    store.link_commit("a", "ba390f8")
    assert store.get("a").commits == ["4fd0fec", "ba390f8"]


def test_link_missing_feat_raises(store):
    with pytest.raises(FeatError, match="找不到"):
        store.link_commit("nope", "abc")


def test_add_discovered(store):
    store.add(Feat(slug="a", title="A"))
    store.add_discovered("a", "接入时列表高度多一行")
    store.add_discovered("a", "接入时列表高度多一行")   # 去重
    store.add_discovered("a", "主题名拼错未校验")
    assert len(store.get("a").discovered) == 2


def test_set_status_persists(store):
    store.add(Feat(slug="a", title="A"))
    store.set_status("a", FeatStatus.TESTING)
    assert FeatStore(store.root).get("a").status is FeatStatus.TESTING


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def test_by_status_and_kind(store):
    store.add(Feat(slug="a", title="A", kind=FeatKind.FEAT))
    store.add(Feat(slug="b", title="B", kind=FeatKind.FIX))
    store.set_status("a", FeatStatus.TESTING)
    assert [f.slug for f in store.by_status(FeatStatus.TESTING)] == ["a"]
    assert [f.slug for f in store.by_kind(FeatKind.FIX)] == ["b"]


def test_open_excludes_closed(store):
    store.add(Feat(slug="a", title="A"))
    store.add(Feat(slug="b", title="B"))
    for st in (FeatStatus.TESTING, FeatStatus.INTEGRATED,
               FeatStatus.FIXING, FeatStatus.CLOSED):
        store.set_status("b", st)
    slugs = [f.slug for f in store.open()]
    assert slugs == ["a"]


def test_all_sorted_newest_first(store):
    import time

    store.add(Feat(slug="a", title="A"))
    time.sleep(0.01)
    store.add(Feat(slug="b", title="B"))
    assert [f.slug for f in store.all()] == ["b", "a"]
