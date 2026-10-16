# -*- coding: utf-8 -*-
"""feat_core 的纯函数测试。

**不 import textual**，毫秒级完成，进默认 CI。
用真的 ``Feat`` 对象（纯数据类，不落盘），避免假对象与真对象行为不一致。
"""

from __future__ import annotations

import time

from pdev.feat import Feat  # noqa: E402
from pdev.tui_new_to_fix import feat_core  # noqa: E402

_T0 = time.perf_counter()


def _feat(api=("run() -> int",), logs=("启动日志",), slug="demo") -> Feat:
    """构造一个内存中的 Feat（不落盘）。"""
    return Feat(slug=slug, title="演示", api=list(api),
                logs=list(logs))


# --- review_rows ------------------------------------------------------------


def test_review_rows_shape():
    rows = feat_core.review_rows(_feat(api=("a()", "b()"), logs=()))
    assert len(rows) == 2
    key, label, reviewed, tested = rows[0]
    assert key == "api:0"
    assert label == "a()"
    assert reviewed is False and tested is False


def test_review_rows_includes_all_field_kinds():
    """api / logs 等各字段都成为可审项（顺序与 review_items 一致）。"""
    rows = feat_core.review_rows(_feat(api=("a()",), logs=("L",)))
    assert [r[0] for r in rows] == ["api:0", "logs:0"]


def test_review_rows_reflects_state():
    f = _feat()
    f.set_reviewed("api:0", True, by="human:lwy")
    f.set_tested("api:0", True, command="pytest -q", status="passed")
    _key, _label, reviewed, tested = feat_core.review_rows(f)[0]
    assert reviewed is True and tested is True


def test_review_rows_empty_feat():
    """没有任何规格字段的 feat → 空列表，不抛异常。"""
    assert feat_core.review_rows(Feat(slug="empty", title="空")) == []


def test_review_rows_survives_broken_feat():
    """对象没有 review_items() 时也不能抛（app 层会传各种东西）。"""

    class Broken:
        pass

    assert feat_core.review_rows(Broken()) == []


# --- plan_toggle ------------------------------------------------------------


def test_plan_toggle_review_field():
    """首次切换 = 置 True。"""
    plan = feat_core.plan_toggle(_feat(), "api:0", "review")
    assert plan == {"reviewed": True}


def test_plan_toggle_test_field():
    plan = feat_core.plan_toggle(_feat(), "api:0", "test")
    assert plan == {"tested": True}


def test_plan_toggle_is_a_toggle():
    """已勾选 → 再切一次变成 False。"""
    f = _feat()
    f.set_reviewed("api:0", True, by="human:lwy")
    assert feat_core.plan_toggle(f, "api:0", "review") == {"reviewed": False}


def test_plan_toggle_rejects_bad_field():
    for field in ("", "title", "REVIEW", None):
        assert feat_core.plan_toggle(_feat(), "api:0", field) is None


def test_plan_toggle_rejects_unknown_key():
    for key in ("", "api:99", "not-a-key", None):
        assert feat_core.plan_toggle(_feat(), key, "review") is None


def test_plan_toggle_only_touches_one_field():
    """切 [审] 不得顺带改 [测]。"""
    f = _feat()
    f.set_tested("api:0", True, command="x", status="passed")
    plan = feat_core.plan_toggle(f, "api:0", "review")
    assert plan == {"reviewed": True}
    assert "tested" not in plan


# --- 时间预算 ---------------------------------------------------------------


def test_core_suite_is_fast():
    start = time.perf_counter()
    for _ in range(200):
        f = _feat()
        feat_core.review_rows(f)
        feat_core.plan_toggle(f, "api:0", "review")
    assert time.perf_counter() - start < 0.5
