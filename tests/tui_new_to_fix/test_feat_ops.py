# -*- coding: utf-8 -*-
"""FeatOps 的单测（**不起 app**，毫秒级）。

FeatOps 是拆分出的写操作层，设计约束是**不依赖 Textual 运行时**：
构造只接 store 与作者，方法返回 ``(ok, message)`` 由调用方提示。
本文件正是这条约束的验收——如果能顺利构造并断言，说明拆分成真。

见 ``doc/feat/tui-featscreen-split.md``。
"""

from __future__ import annotations

import time

import pytest

from pdev.feat import Feat, FeatImportance, FeatStore

#: 本文件“自己的”耗时累加（不含 import 与其它测试）。
#: 不能用模块级 ``_T0``——全仓跑时会把它人的耗时也算进来（已经踩过）。
_ELAPSED = 0.0


@pytest.fixture(autouse=True)
def _measure():
    global _ELAPSED
    start = time.perf_counter()
    yield
    _ELAPSED += time.perf_counter() - start


@pytest.fixture
def store(tmp_path) -> FeatStore:
    s = FeatStore(tmp_path / "feats")
    s.add(Feat(
        slug="demo", title="演示",
        api=["run() -> int"], logs=["启动"], fallbacks=["降级"],
        design_note="为什么", impl_note="怎么做",
        data_model=["D: dict"], samples=["{}"], changes=["pdev/a.py::B —— x"],
        test_note="pytest t.py", impact="无", importance=FeatImportance.HIGH,
    ))
    return s


@pytest.fixture
def ops(store):
    from pdev.tui_new_to_fix.screens import FeatOps

    return FeatOps(store, by="human:test")


def _reload(root, slug="demo"):
    """从磁盘重新读（不听内存缓存）。"""
    return FeatStore(root).get(slug)


# --- 构造约束：不依赖 Textual ----------------------------------------------


def test_feat_ops_constructs_without_textual_app(ops):
    """能独立构造 = 拆分成功的第一条证据。"""
    assert ops is not None


# --- toggle_review ----------------------------------------------------------


def test_toggle_review_persists(store, ops):
    feat = store.get("demo")
    ok, msg = ops.toggle_review(feat, "api:0")
    assert ok is True
    assert "api:0" in msg
    item = _reload(store.root).review_item("api:0")
    assert item.reviewed is True
    assert item.reviewed_by == "human:test"


def test_toggle_review_is_a_toggle(store, ops):
    """再切一次 → 取消（记录会被 _prune 删掉，读到 None 也算未勾选）。"""
    ops.toggle_review(store.get("demo"), "api:0")
    ok, _ = ops.toggle_review(store.get("demo"), "api:0")
    assert ok is True
    item = _reload(store.root).review_item("api:0")
    assert getattr(item, "reviewed", False) is False


def test_toggle_test_does_not_touch_review(store, ops):
    """切 [测] 不得顺带改 [审]。"""
    ops.toggle_test(store.get("demo"), "api:0")
    item = _reload(store.root).review_item("api:0")
    assert item.tested is True
    assert item.reviewed is False


def test_bad_key_returns_false(store, ops):
    """非法 key → (False, 说明)，不落盘、不抛异常。"""
    ok, msg = ops.toggle_review(store.get("demo"), "nope:9")
    assert ok is False
    assert msg
    assert _reload(store.root).review_item("nope:9") is None


def test_bad_field_returns_false(store, ops):
    ok, msg = ops.toggle(store.get("demo"), "api:0", "not-a-field")
    assert ok is False
    assert msg


# --- edit_comment -----------------------------------------------------------


def test_edit_comment_roundtrip(store, ops):
    ok, msg = ops.edit_comment(store.get("demo"), "api:0", "为何不泛化")
    assert ok is True
    assert "api:0" in msg
    assert _reload(store.root).comment("api:0") == "为何不泛化"


def test_edit_comment_empty_clears(store, ops):
    """空串（含纯空白）→ 清除评论。"""
    ops.edit_comment(store.get("demo"), "api:0", "先写一条")
    assert _reload(store.root).comment("api:0") == "先写一条"

    ok, msg = ops.edit_comment(store.get("demo"), "api:0", "   ")
    assert ok is True
    assert "清除" in msg
    assert _reload(store.root).comment("api:0") == ""


def test_edit_comment_bad_key(store, ops):
    ok, msg = ops.edit_comment(store.get("demo"), "nope:9", "x")
    assert ok is False
    assert msg


# --- 失败路径：返回 False 而不是抛异常 --------------------------------------


def test_write_failure_returns_false(store, ops):
    """store 抛异常 → (False, 原因)，不向上抛（由调用方提示）。"""

    def boom(*a, **k):
        raise OSError("disk full")

    store.set_reviews = boom
    ok, msg = ops.toggle_review(store.get("demo"), "api:0")
    assert ok is False
    assert "disk full" in msg


def test_comment_write_failure_returns_false(store, ops):
    def boom(*a, **k):
        raise OSError("readonly")

    store.set_comment = boom
    ok, msg = ops.edit_comment(store.get("demo"), "api:0", "x")
    assert ok is False
    assert "readonly" in msg


# --- 时间预算：FeatOps 单测不该起 app --------------------------------------


def test_ops_suite_is_fast():
    """本文件所有用例自身耗时之和必须远低于 1s。

    证明没有 ``run_test`` 被偷偷引入（FeatOps 的全部价值就在
    “不起 app 也能测”）。
    """
    assert _ELAPSED < 1.0, f"FeatOps 测试太慢：{_ELAPSED:.2f}s"
