# -*- coding: utf-8 -*-
"""pdev.review 的测试：审查覆盖率评分与低覆盖告警。

见 ``doc/feat/review-score.md``。
"""

from __future__ import annotations

import pytest

from pdev.feat import Feat
from pdev.review import (
    ReviewPolicy,
    ReviewScore,
    ReviewWarning,
    compute_review,
    format_score,
)


def _feat(slug: str, *, api=(), logs=(), fallbacks=(), doc="d.md") -> Feat:
    """构造一条带规格字段的 feat。"""
    return Feat(slug=slug, title=slug, doc=doc,
                api=list(api), logs=list(logs), fallbacks=list(fallbacks))


def _review_all(feat: Feat) -> Feat:
    for key, _ in feat.review_items():
        feat.set_reviewed(key, True, by="human:lwy")
    return feat


def _test_all(feat: Feat) -> Feat:
    for key, _ in feat.review_items():
        feat.set_tested(key, True, command="pytest x", status="passed")
    return feat


# ---------------------------------------------------------------------------
# 空输入与分母为 0
# ---------------------------------------------------------------------------


def test_empty_input():
    s = compute_review([])
    assert s.items == 0
    assert s.reviewed == 0
    assert s.tested == 0
    assert s.score == 0.0
    assert s.review_coverage == 0.0
    assert s.test_coverage == 0.0
    assert s.level == "none"
    assert s.warnings == []
    assert s.ok


def test_feat_without_reviewable_items():
    s = compute_review([Feat(slug="a", title="A")])   # 无 doc/api/logs/fb
    assert s.items == 0
    assert s.level == "none"
    assert s.warnings == []          # 没有可审内容，不告警


def test_no_division_by_zero():
    # 空仓库不应抛 ZeroDivisionError
    compute_review([])
    compute_review([Feat(slug="a", title="A")])


# ---------------------------------------------------------------------------
# 计数与覆盖率
# ---------------------------------------------------------------------------


def test_counts_and_coverage():
    f = _feat("a", api=["f()", "g()"], logs=["l"], fallbacks=["fb"])
    # doc + api:0/1 + logs:0 + fb:0 == 5 项
    f.set_reviewed("api:0")
    f.set_reviewed("api:1")
    s = compute_review([f])
    assert s.items == 5
    assert s.reviewed == 2
    assert s.tested == 0
    assert s.review_coverage == pytest.approx(2 / 5)
    assert s.test_coverage == 0.0
    assert s.feats == 1


def test_score_weighting():
    f = _feat("a", api=["f()"])
    _review_all(f)                   # 审查覆盖 1.0，测试 0.0
    s = compute_review([f])
    assert s.review_coverage == pytest.approx(1.0)
    assert s.test_coverage == pytest.approx(0.0)
    assert s.score == pytest.approx(0.6)   # 0.6*1 + 0.4*0


def test_score_full_coverage():
    f = _feat("a", api=["f()"], logs=["l"])
    _review_all(f)
    _test_all(f)
    s = compute_review([f])
    assert s.score == pytest.approx(1.0)
    assert s.level == "excellent"


def test_multiple_feats_aggregate():
    f1 = _feat("a", api=["f()"])           # 2 项
    f2 = _feat("b", api=["g()"], logs=["l"])   # 3 项
    _review_all(f1)
    s = compute_review([f1, f2])
    assert s.items == 5
    assert s.reviewed == 2
    assert s.feats == 2


def test_orphan_records_not_counted():
    """孤儿记录（规格项已删除）不计入分母。"""
    f = _feat("a", api=["f()", "g()"], doc="")
    f.set_reviewed("api:0")
    f.set_reviewed("api:1")
    f.api = ["f()"]                  # api:1 成孤儿
    s = compute_review([f])
    assert s.items == 1              # 只剩 api:0
    assert s.reviewed == 1


# ---------------------------------------------------------------------------
# 分档
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reviewed_ratio,tested_ratio,expected", [
    (0.0, 0.0, "poor"),
    (0.2, 0.0, "poor"),          # score=0.12
    (0.0, 0.75, "fair"),          # score=0.3
    (0.5, 0.0, "fair"),           # score=0.3
    (0.6, 0.6, "good"),           # score=0.6
    (0.8, 0.8, "good"),           # score=0.8
    (1.0, 0.75, "excellent"),     # score=0.9
    (1.0, 1.0, "excellent"),
])
def test_level_buckets(reviewed_ratio, tested_ratio, expected):
    n = 100
    f = _feat("a", api=[f"f{i}()" for i in range(n)], doc="")
    for i in range(round(reviewed_ratio * n)):
        f.set_reviewed(f"api:{i}")
    for i in range(round(tested_ratio * n)):
        f.set_tested(f"api:{i}", status="passed")
    s = compute_review([f])
    assert s.level == expected


# ---------------------------------------------------------------------------
# 告警：过低
# ---------------------------------------------------------------------------


def test_no_review_warning():
    f = _feat("a", api=["f()"])
    s = compute_review([f])
    codes = [w.code for w in s.warnings]
    assert "no-review" in codes
    assert "low-review" in codes     # 0 < 0.6，也命中低覆盖
    assert not s.ok


def test_untested_warning():
    f = _feat("a", api=["f()"])
    _review_all(f)                   # 全审但没测
    s = compute_review([f])
    codes = [w.code for w in s.warnings]
    assert "untested" in codes
    assert "no-review" not in codes  # 已审查


def test_low_coverage_warning_with_custom_policy():
    f = _feat("a", api=[f"f{i}()" for i in range(10)], doc="")
    for i in range(5):               # 覆盖率 0.5
        f.set_reviewed(f"api:{i}")
    s = compute_review([f], ReviewPolicy(min_coverage=0.6))
    assert any(w.code == "low-review" for w in s.warnings)
    # 放宽阈值后不再告警
    s2 = compute_review([f], ReviewPolicy(min_coverage=0.5))
    assert not any(w.code == "low-review" for w in s2.warnings)


def test_no_warning_when_coverage_high():
    f = _feat("a", api=["f()", "g()", "h()"])
    _review_all(f)
    _test_all(f)
    s = compute_review([f])
    assert s.warnings == []
    assert s.ok


def test_policy_can_disable_warnings():
    f = _feat("a", api=["f()"])
    s = compute_review([f], ReviewPolicy(
        warn_no_review=False, warn_untested=False, min_coverage=0.0))
    assert s.warnings == []


def test_warning_has_level_warning():
    f = _feat("a", api=["f()"])
    s = compute_review([f])
    assert all(w.level == "warning" for w in s.warnings)
    assert all(isinstance(w, ReviewWarning) for w in s.warnings)


def test_threshold_out_of_range_does_not_raise():
    f = _feat("a", api=["f()"])
    _review_all(f)
    s = compute_review([f], ReviewPolicy(min_coverage=2.0))
    assert any(w.code == "low-review" for w in s.warnings)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def test_format_score_contains_key_numbers():
    f = _feat("a", api=["f()"])
    _review_all(f)
    _test_all(f)
    text = format_score(compute_review([f]))
    assert "100%" in text or "1.00" in text
    assert "excellent" in text


def test_format_score_empty():
    text = format_score(compute_review([]))
    assert "无可审内容" in text


def test_format_score_lists_warnings():
    f = _feat("a", api=["f()"])
    text = format_score(compute_review([f]))
    assert "no-review" in text or "完全不审查" in text


def test_score_is_plain_dataclass():
    s = ReviewScore()
    assert s.items == 0
    assert s.warnings == []


# ---------------------------------------------------------------------------
# 未审 / 未测清单（review-query）
# ---------------------------------------------------------------------------


def test_unreviewed_items_lists_unchecked():
    from pdev.review import unreviewed_items

    f = _feat("a", api=["f()", "g()"], doc="")
    f.set_reviewed("api:0")                  # 只审一项
    rows = unreviewed_items([f])
    keys = [(s, k) for s, k, _ in rows]
    assert ("a", "api:1") in keys
    assert ("a", "api:0") not in keys


def test_unreviewed_items_untested_only():
    from pdev.review import unreviewed_items

    f = _feat("a", api=["f()", "g()"], doc="")
    f.set_tested("api:0", status="passed")   # 只测一项
    rows = unreviewed_items([f], tested=True)
    keys = [(s, k) for s, k, _ in rows]
    assert ("a", "api:1") in keys
    assert ("a", "api:0") not in keys


def test_unreviewed_items_with_tested_flag_is_intersection():
    """tested=True 时取「既未审且未测」的交集。"""
    from pdev.review import unreviewed_items

    f = _feat("a", api=["f()", "g()", "h()"], doc="")
    f.set_reviewed("api:0")                  # 审了
    f.set_tested("api:1", status="passed")   # 测了
    # api:2 既未审也未测
    rows = unreviewed_items([f], tested=True)
    keys = [(s, k) for s, k, _ in rows]
    assert keys == [("a", "api:2")]


def test_unreviewed_items_multiple_feats_order():
    from pdev.review import unreviewed_items

    f1 = _feat("a", api=["f()"], doc="")
    f2 = _feat("b", api=["g()"], doc="")
    rows = unreviewed_items([f1, f2])
    assert [s for s, _, _ in rows] == ["a", "b"]


def test_unreviewed_items_empty():
    from pdev.review import unreviewed_items

    assert unreviewed_items([]) == []
    assert unreviewed_items([Feat(slug="a", title="A")]) == []


def test_unreviewed_items_all_reviewed():
    from pdev.review import unreviewed_items

    f = _feat("a", api=["f()"], doc="")
    _review_all(f)
    assert unreviewed_items([f]) == []
