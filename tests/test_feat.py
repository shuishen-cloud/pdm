# -*- coding: utf-8 -*-
"""pdev.feat 的测试：Feat 数据结构与 FeatStore 存储。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from pdev.feat import (
    Feat,
    FeatError,
    FeatKind,
    FeatStatus,
    FeatStore,
    ReviewItem,
    valid_slug,
)
from tests.fixtures.feat_storage import (
    BAD_SLUGS,
    FULL_FEAT,
    LEGACY_FIELDS,
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
    assert got.doc == "docs/feat/demo.md"
    assert got.api == [
        "FeatStore.add(feat: Feat) -> None",
        "FeatStore.get(slug: str) -> Optional[Feat]",
    ]
    assert got.logs == ["创建时记录 slug 与标题", "状态推进时记录 from → to"]
    assert got.fallbacks == ["非法输入抛 FeatError"]
    assert got.commits == []


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


# ---------------------------------------------------------------------------
# 重构后：精简字段 + commit 串联
# ---------------------------------------------------------------------------


def test_legacy_doc_fields_are_ignored(tmp_path):
    """旧版塞进 Feat 的文档正文字段，读取时应被忽略而非报错。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    data = {
        "slug": "old", "title": "旧记录", "status": "draft",
        "design": "旧的设计正文",           # 应被忽略
        "data_model": "旧的",               # 应被忽略
        "fixtures": ["x"],                  # 应被忽略
        "touches": ["y"],                   # 应被忽略
        "follows": ["z"],                   # 应被忽略
        "debug": "w",                       # 应被忽略
        "api": ["FeatStore.add(feat: Feat) -> None"],
    }
    (d / "old.json").write_text(json.dumps(data), encoding="utf-8")

    store = FeatStore(root)
    feat = store.get("old")
    assert feat is not None
    assert feat.title == "旧记录"
    assert feat.api == ["FeatStore.add(feat: Feat) -> None"]
    for field in LEGACY_FIELDS:
        assert not hasattr(feat, field)


def test_api_and_logs_are_real_code_content():
    """api 是真实接口签名，logs 是日志内容（不是 usage / 格式串）。"""
    f = Feat(**FULL_FEAT)
    # api 里应是函数签名，含括号与箭头
    assert all("(" in a and ")" in a for a in f.api)
    # 不应是命令行 usage
    assert not any(a.strip().startswith("pdm ") for a in f.api)
    # logs 不应是 "event key=val" 这种格式串
    assert not any("=" in x for x in f.logs)


def test_by_commit_lookup(store):
    store.add(Feat(slug="a", title="A"))
    store.add(Feat(slug="b", title="B"))
    store.link_commit("a", "10a888c")
    assert store.by_commit("10a888c").slug == "a"
    # 支持短 hash 互查
    assert store.by_commit("10a888").slug == "a"
    assert store.by_commit("nonexist") is None


def test_unlink_commit(store):
    store.add(Feat(slug="a", title="A"))
    store.link_commit("a", "abc")
    store.link_commit("a", "def")
    feat = store.unlink_commit("a", "abc")
    assert feat.commits == ["def"]
    # 解除不存在的关联不报错
    store.unlink_commit("a", "zzz")
    assert store.get("a").commits == ["def"]


def test_link_multiple_commits_for_one_feat(store):
    """一个 feat 串联多个 commit。"""
    store.add(Feat(slug="feat-x", title="跨多个 commit 的功能"))
    for c in ("aaa111", "bbb222", "ccc333"):
        store.link_commit("feat-x", c)
    assert store.get("feat-x").commits == ["aaa111", "bbb222", "ccc333"]
    # 重载后仍在
    assert FeatStore(store.root).get("feat-x").commits == [
        "aaa111", "bbb222", "ccc333"]


def test_path_points_to_doc_not_content(store):
    """Feat 只存 doc 路径，不存正文。"""
    f = Feat(slug="a", title="A", doc="docs/feat/a.md")
    store.add(f)
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert data["doc"] == "docs/feat/a.md"
    # 没有正文类字段
    for field in LEGACY_FIELDS:
        assert field not in data


# ---------------------------------------------------------------------------
# 审查项：可审项展开（review_items）
# ---------------------------------------------------------------------------


def test_review_items_order_and_keys():
    """可审项顺序固定：doc → api → logs → fallbacks。"""
    f = Feat(
        slug="a", title="A", doc="feat/a.md",
        api=["f() -> int", "g() -> str"],
        logs=["创建时记录 slug"],
        fallbacks=["非法输入抛错"],
    )
    items = f.review_items()
    assert [r.key for r in items] == [
        "doc", "api:0", "api:1", "logs:0", "fallbacks:0",
    ]
    # label 是能直接显示的内容
    labels = {r.key: r.label for r in items}
    assert labels["doc"] == "feat/a.md"
    assert labels["api:0"] == "f() -> int"
    assert labels["logs:0"] == "创建时记录 slug"


def test_review_items_skip_empty_fields():
    """doc 为空 / 列表为空时不产生对应可审项。"""
    f = Feat(slug="a", title="A", api=["f()"], logs=[], fallbacks=[])
    assert [r.key for r in f.review_items()] == ["api:0"]
    assert Feat(slug="b", title="B").review_items() == []


def test_review_items_use_index_not_content():
    """key 由字段+序号构成，内容改动不改变 key。"""
    f = Feat(slug="a", title="A", api=["f() -> int"])
    assert [r.key for r in f.review_items()] == ["api:0"]
    f.api = ["f() -> str"]        # 内容变了，key 不变
    assert [r.key for r in f.review_items()] == ["api:0"]


# ---------------------------------------------------------------------------
# 审查项：双勾选位
# ---------------------------------------------------------------------------


def test_set_reviewed_records_by_and_time():
    f = Feat(slug="a", title="A", api=["f()"])
    item = f.set_reviewed("api:0", True, by="human:lwy")
    assert item.reviewed is True
    assert item.reviewed_by == "human:lwy"
    assert item.reviewed_at is not None
    # 互不蕴含：只审不测
    assert item.tested is False


def test_set_reviewed_false_clears():
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_reviewed("api:0", True, by="human:lwy")
    item = f.set_reviewed("api:0", False)
    assert item.reviewed is False


def test_set_tested_records_command_and_status():
    f = Feat(slug="a", title="A", api=["f()"])
    item = f.set_tested("api:0", True,
                        command="pytest tests/test_feat.py::test_x",
                        status="passed")
    assert item.tested is True
    assert item.test_command == "pytest tests/test_feat.py::test_x"
    assert item.test_status == "passed"
    assert item.tested_at is not None
    assert item.reviewed is False      # 只测未审


def test_set_tested_false_clears():
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_tested("api:0", True, command="x", status="passed")
    item = f.set_tested("api:0", False)
    assert item.tested is False


def test_set_reviewed_rejects_unknown_key():
    f = Feat(slug="a", title="A", api=["f()"])
    with pytest.raises(FeatError):
        f.set_reviewed("api:999")
    with pytest.raises(FeatError):
        f.set_tested("nope")
    # 非法 key 不应落盘
    assert f.reviews == {}


def test_review_item_lookup():
    f = Feat(slug="a", title="A", api=["f()"])
    assert f.review_item("api:0") is None
    f.set_reviewed("api:0")
    assert f.review_item("api:0").reviewed is True


# ---------------------------------------------------------------------------
# 审查项：统计（review_counts）
# ---------------------------------------------------------------------------


def test_review_counts():
    f = Feat(slug="a", title="A", doc="d.md",
             api=["f()", "g()"], logs=["l"], fallbacks=["fb"])
    _rc = f.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (5, 0, 0)      # doc + api:0/1 + logs:0 + fb:0
    f.set_reviewed("doc")
    f.set_reviewed("api:0")
    f.set_tested("api:0", status="passed")
    _rc = f.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (5, 2, 1)


def test_review_counts_ignore_orphans():
    """规格项被删除后，孤儿记录保留但不计入统计。"""
    f = Feat(slug="a", title="A", api=["f()", "g()"])
    f.set_reviewed("api:1")
    _rc = f.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (2, 1, 0)
    f.api = ["f()"]            # 删掉第二条，api:1 成孤儿
    assert "api:1" in f.reviews          # 记录保留
    _rc = f.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (1, 0, 0)  # 统计忽略


def test_review_counts_empty_feat():
    _rc = Feat(slug="a", title="A").review_counts()
    assert (_rc.total, _rc.reviewed, _rc.tested) == (0, 0, 0)


# ---------------------------------------------------------------------------
# 审查项：存储与序列化
# ---------------------------------------------------------------------------


def test_store_set_reviewed_persists(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.set_reviewed("a", "api:0", True, by="human:lwy")
    got = FeatStore(store.root).get("a")
    assert got.review_item("api:0").reviewed is True
    assert got.review_item("api:0").reviewed_by == "human:lwy"


def test_store_set_tested_persists(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.set_tested("a", "api:0", True, command="pytest x", status="passed")
    got = FeatStore(store.root).get("a")
    item = got.review_item("api:0")
    assert item.tested is True
    assert item.test_command == "pytest x"
    assert item.test_status == "passed"


def test_store_set_reviewed_missing_feat_raises(store):
    with pytest.raises(FeatError, match="找不到"):
        store.set_reviewed("nope", "api:0")
    with pytest.raises(FeatError, match="找不到"):
        store.set_tested("nope", "api:0")


def test_reviews_serialized_in_json(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.set_reviewed("a", "api:0", True, by="human:lwy")
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert "reviews" in data
    assert data["reviews"]["api:0"]["reviewed"] is True
    assert data["reviews"]["api:0"]["reviewed_by"] == "human:lwy"
    # 时间为 ISO 串，可被 fromisoformat 解析
    datetime.fromisoformat(data["reviews"]["api:0"]["reviewed_at"])


def test_untouched_keys_absent_from_json(store):
    """未操作的 key 不写入 JSON，保持文件精简。"""
    store.add(Feat(slug="a", title="A", api=["f()", "g()"]))
    store.set_reviewed("a", "api:0")
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert set(data["reviews"]) == {"api:0"}


def test_clearing_never_set_key_leaves_no_trace():
    """对一个从未勾选的项取消勾选，不应留下空记录。"""
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_reviewed("api:0", False)
    f.set_tested("api:0", False)
    assert f.reviews == {}


def test_clearing_both_bits_removes_record():
    """先审后测，再两个都取消 -> 记录从 dict 移除。"""
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_reviewed("api:0")
    f.set_tested("api:0", status="passed")
    f.set_reviewed("api:0", False)
    assert "api:0" in f.reviews          # 还有一个测试位
    f.set_tested("api:0", False)
    assert f.reviews == {}


def test_legacy_json_without_reviews(tmp_path):
    """旧 JSON 无 reviews 键 -> 空 dict，不报错。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧", "api": ["f()"],
    }), encoding="utf-8")
    feat = FeatStore(root).get("old")
    assert feat is not None
    assert feat.reviews == {}
    _rc = feat.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (1, 0, 0)


def test_corrupt_review_time_becomes_none(tmp_path):
    """时间字段非法 -> 静默置 None，不阻断加载。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps({
        "slug": "a", "title": "A", "api": ["f()"],
        "reviews": {"api:0": {
            "reviewed": True, "reviewed_at": "not-a-date",
            "tested": True, "tested_at": "also-bad",
        }},
    }), encoding="utf-8")
    feat = FeatStore(root).get("a")
    item = feat.review_item("api:0")
    assert item.reviewed is True
    assert item.reviewed_at is None
    assert item.tested_at is None


def test_reviews_non_dict_treated_as_empty(tmp_path):
    """reviews 值非 dict -> 视为空。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps({
        "slug": "a", "title": "A", "api": ["f()"],
        "reviews": ["not", "a", "dict"],
    }), encoding="utf-8")
    feat = FeatStore(root).get("a")
    assert feat.reviews == {}


def test_review_item_roundtrip_datetime():
    """ReviewItem 时间序列化后可无损还原。"""
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    item = ReviewItem(reviewed=True, reviewed_at=now, tested=True,
                      tested_at=now, test_status="passed")
    from pdev.feat import _review_to_dict, _review_from_dict

    back = _review_from_dict(_review_to_dict(item))
    assert back.reviewed_at == now
    assert back.tested_at == now
    assert back.test_status == "passed"


# ---------------------------------------------------------------------------
# 条目级评论（feat-comment）
# ---------------------------------------------------------------------------


def test_set_and_get_comment():
    f = Feat(slug="a", title="A", api=["f()"])
    assert f.comment("api:0") == ""
    f.set_comment("api:0", "这个签名保持最小")
    assert f.comment("api:0") == "这个签名保持最小"


def test_comment_empty_string_clears():
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_comment("api:0", "x")
    f.set_comment("api:0", "")
    assert f.comment("api:0") == ""
    assert "api:0" not in f.comments          # 未落盘


def test_comment_rejects_bad_key():
    f = Feat(slug="a", title="A", api=["f()"])
    with pytest.raises(FeatError):
        f.set_comment("api:99", "x")
    with pytest.raises(FeatError):
        f.set_comment("nope", "x")
    assert f.comments == {}


def test_comment_multiline_preserved():
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_comment("api:0", "第一行\n第二行")
    assert f.comment("api:0") == "第一行\n第二行"


def test_commented_items_only_nonempty_in_order():
    f = Feat(slug="a", title="A", doc="d.md",
             api=["f()", "g()"], logs=["l"])
    f.set_comment("api:1", "对第二条")
    f.set_comment("logs:0", "对日志")
    rows = f.commented_items()
    assert [r.key for r in rows] == ["api:1", "logs:0"]
    labels = {r.key: r.label for r in rows}
    assert labels["api:1"] == "g()"
    assert rows[0].comment == "对第二条"


def test_comment_independent_of_review():
    f = Feat(slug="a", title="A", api=["f()"])
    f.set_comment("api:0", "写了评论")
    _rc = f.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (1, 0, 0)     # 不影响勾选统计
    f.set_reviewed("api:0")
    assert f.comment("api:0") == "写了评论"    # 勾选不影响评论


def test_store_set_comment_persists(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.set_comment("a", "api:0", "持久化评论")
    got = FeatStore(store.root).get("a")
    assert got.comment("api:0") == "持久化评论"


def test_store_set_comment_missing_feat(store):
    with pytest.raises(FeatError, match="找不到"):
        store.set_comment("nope", "api:0", "x")


def test_comments_serialized(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.set_comment("a", "api:0", "评论内容")
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert data["comments"] == {"api:0": "评论内容"}


def test_legacy_json_without_comments(tmp_path):
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧", "api": ["f()"],
    }), encoding="utf-8")
    feat = FeatStore(root).get("old")
    assert feat.comments == {}


def test_comments_non_str_values_dropped(tmp_path):
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps({
        "slug": "a", "title": "A", "api": ["f()"],
        "comments": {"api:0": "好的", "api:x": 123, "api:y": ["not", "str"]},
    }), encoding="utf-8")
    feat = FeatStore(root).get("a")
    assert feat.comments == {"api:0": "好的"}


def test_orphan_comment_kept_but_not_listed():
    f = Feat(slug="a", title="A", api=["f()", "g()"])
    f.set_comment("api:1", "对第二条")
    f.api = ["f()"]                            # api:1 成孤儿
    assert "api:1" in f.comments               # JSON 保留
    assert f.commented_items() == []           # 不列出


# ---------------------------------------------------------------------------
# 批量勾选：resolve_keys / set_reviews（review-batch）
# ---------------------------------------------------------------------------


def _items_feat():
    return Feat(slug="a", title="A", doc="d.md",
                api=["f()", "g()"], logs=["l"], fallbacks=["fb"])


def test_resolve_keys_all(store):
    store.add(_items_feat())
    rows = store.resolve_keys("a", all_items=True)
    assert [r.key for r in rows] == ["doc", "api:0", "api:1", "logs:0",
                                    "fallbacks:0"]


def test_resolve_keys_prefix(store):
    store.add(_items_feat())
    rows = store.resolve_keys("a", item="api")
    assert [r.key for r in rows] == ["api:0", "api:1"]


def test_resolve_keys_exact(store):
    store.add(_items_feat())
    assert [r.key for r in store.resolve_keys("a", item="api:0")] == ["api:0"]
    assert [r.key for r in store.resolve_keys("a", item="doc")] == ["doc"]


def test_resolve_keys_no_match(store):
    store.add(_items_feat())
    with pytest.raises(FeatError):
        store.resolve_keys("a", item="nope")


def test_resolve_keys_all_on_empty_feat(store):
    store.add(Feat(slug="bare", title="B"))
    with pytest.raises(FeatError):
        store.resolve_keys("bare", all_items=True)


def test_set_reviews_batch_reviewed(store):
    store.add(_items_feat())
    keys = [r.key for r in store.resolve_keys("a", item="api")]
    store.set_reviews("a", keys, reviewed=True, by="human:lwy")
    got = FeatStore(store.root).get("a")
    _rc = got.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (5, 2, 0)
    assert got.review_item("api:0").reviewed_by == "human:lwy"


def test_set_reviews_batch_unreview(store):
    store.add(_items_feat())
    store.set_reviews("a", ["api:0", "api:1"], reviewed=True)
    store.set_reviews("a", ["api:0", "api:1"], reviewed=False)
    _rc = store.get("a").review_counts()
    assert (_rc.total, _rc.reviewed, _rc.tested) == (5, 0, 0)


def test_set_reviews_batch_tested(store):
    store.add(_items_feat())
    store.set_reviews("a", ["logs:0", "fallbacks:0"], tested=True,
                      command="pytest x", status="passed")
    got = store.get("a")
    _rc = got.review_counts(); assert (_rc.total, _rc.reviewed, _rc.tested) == (5, 0, 2)
    assert got.review_item("logs:0").test_command == "pytest x"


def test_set_reviews_writes_once(store, monkeypatch):
    """批量只落盘一次。"""
    store.add(_items_feat())
    calls = []
    orig = store._flush
    monkeypatch.setattr(store, "_flush",
                        lambda f: (calls.append(1), orig(f))[1])
    store.set_reviews("a", ["api:0", "api:1", "logs:0"], reviewed=True)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# 五项设计字段（feat-fields）
# ---------------------------------------------------------------------------


def _full_feat_kwargs():
    return dict(
        slug="a", title="A", doc="d.md",
        design_note="为什么这么设计", impl_note="怎么实现的",
        data_model=["Feat.x: int —— 计数"],
        samples=['{"k": 1}'],
        changes=["pdev/feat.py::Feat.x —— 新增字段"],
    )


def test_new_fields_default_empty():
    f = Feat(slug="a", title="A")
    assert f.design_note == ""
    assert f.impl_note == ""
    assert f.data_model == []
    assert f.samples == []
    assert f.changes == []


def test_new_fields_roundtrip_via_store(store):
    store.add(Feat(**_full_feat_kwargs()))
    got = FeatStore(store.root).get("a")
    assert got.design_note == "为什么这么设计"
    assert got.impl_note == "怎么实现的"
    assert got.data_model == ["Feat.x: int —— 计数"]
    assert got.samples == ['{"k": 1}']
    assert got.changes == ["pdev/feat.py::Feat.x —— 新增字段"]


def test_list_fields_are_reviewable():
    """data_model / samples / changes 并入可审项。"""
    f = Feat(**_full_feat_kwargs())
    keys = [r.key for r in f.review_items()]
    assert "data_model:0" in keys
    assert "samples:0" in keys
    assert "changes:0" in keys


def test_text_fields_not_reviewable():
    f = Feat(**_full_feat_kwargs())
    keys = [r.key for r in f.review_items()]
    assert not any(k.startswith("design_note") for k in keys)
    assert not any(k.startswith("impl_note") for k in keys)


def test_missing_required_fields_detects_all():
    f = Feat(slug="a", title="A")
    missing = f.missing_required_fields()
    assert len(missing) == 5
    assert any("设计思路" in m for m in missing)
    assert any("样例数据" in m for m in missing)
    assert any("改动" in m for m in missing)


def test_missing_required_fields_empty_when_complete():
    assert Feat(**_full_feat_kwargs()).missing_required_fields() == []


def test_missing_required_fields_partial():
    """只缺样例数据时只报一项。"""
    kw = _full_feat_kwargs()
    kw["samples"] = []
    missing = Feat(**kw).missing_required_fields()
    assert len(missing) == 1
    assert "样例数据" in missing[0]


def test_text_fields_keep_newlines(store):
    kw = _full_feat_kwargs()
    kw["design_note"] = "第一行\n第二行"
    store.add(Feat(**kw))
    assert FeatStore(store.root).get("a").design_note == "第一行\n第二行"


def test_legacy_json_without_new_fields(tmp_path):
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧", "api": ["f()"],
    }), encoding="utf-8")
    feat = FeatStore(root).get("old")
    assert feat.design_note == ""
    assert feat.samples == []
    assert feat.changes == []


def test_new_fields_in_json(store):
    store.add(Feat(**_full_feat_kwargs()))
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert data["design_note"] == "为什么这么设计"
    assert data["samples"] == ['{"k": 1}']
    assert data["changes"] == ["pdev/feat.py::Feat.x —— 新增字段"]


def test_legacy_feat_missing_new_fields_but_loadable(tmp_path):
    """历史 feat 缺新字段仍可加载，只是 missing 非空（check 层豁免）。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧", "api": ["f()"],
    }), encoding="utf-8")
    feat = FeatStore(root).get("old")
    assert len(feat.missing_required_fields()) == 5
    assert feat.review_items()                 # 旧字段仍可审


# ---------------------------------------------------------------------------
# 阶段级审核（stage-review）
# ---------------------------------------------------------------------------


def test_review_stage_roundtrip(store):
    store.add(Feat(slug="a", title="A", api=["f()"]))
    store.review_stage("a", "doc", "human:lwy")
    got = FeatStore(store.root).get("a")
    assert got.stage_reviewed("doc")
    assert got.stage_reviews["doc"].by == "human:lwy"
    assert got.stage_reviews["doc"].at is not None


def test_unreview_stage(store):
    store.add(Feat(slug="a", title="A"))
    store.review_stage("a", "doc", "human:lwy")
    store.unreview_stage("a", "doc")
    assert not store.get("a").stage_reviewed("doc")
    assert "doc" not in store.get("a").stage_reviews


def test_review_stage_rejects_bad_stage(store):
    store.add(Feat(slug="a", title="A"))
    with pytest.raises(FeatError):
        store.review_stage("a", "nope", "human:lwy")


def test_review_stage_overwrites():
    f = Feat(slug="a", title="A")
    f.review_stage("doc", "human:lwy")
    f.review_stage("doc", "human:bob", note="再审一次")
    assert f.stage_reviews["doc"].by == "human:bob"
    assert f.stage_reviews["doc"].note == "再审一次"


def test_pending_stage_review():
    f = Feat(slug="a", title="A")
    assert f.pending_stage_review("doc") is None      # 首阶段无需前序
    assert f.pending_stage_review("test") == "doc"
    f.review_stage("doc", "human:lwy")
    assert f.pending_stage_review("test") is None
    assert f.pending_stage_review("feat") == "test"


def test_stage_reviews_serialized(store):
    store.add(Feat(slug="a", title="A"))
    store.review_stage("a", "doc", "human:lwy")
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert data["stage_reviews"]["doc"]["by"] == "human:lwy"
    assert data["stage_reviews"]["doc"]["at"]


def test_legacy_json_without_stage_reviews(tmp_path):
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧", "api": ["f()"],
    }), encoding="utf-8")
    assert FeatStore(root).get("old").stage_reviews == {}


def test_untouched_stages_absent_from_json(store):
    store.add(Feat(slug="a", title="A"))
    store.review_stage("a", "doc", "human:lwy")
    data = json.loads((store.root / "by-id" / "a.json").read_text("utf-8"))
    assert set(data["stage_reviews"]) == {"doc"}
