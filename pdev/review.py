# -*- coding: utf-8 -*-
"""审查覆盖率评分与低覆盖告警。

基于每条 Feat 的双勾选位（见 ``doc/feat/review-model.md``），跨全部
Feat 汇总出「项目代码掌握程度」，并对**人工审核覆盖率过低**的仓库告警。

设计见 ``doc/feat/review-score.md``。

纯函数，无 IO、无日志、不依赖 textual。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

__all__ = [
    "ReviewPolicy",
    "ReviewWarning",
    "ReviewScore",
    "compute_review",
    "format_score",
    "LEVELS",
]

# 分档下界：(level, score 下界)，从高到低匹配
LEVELS = (
    ("excellent", 0.9),
    ("good", 0.6),
    ("fair", 0.3),
    ("poor", 0.0),
)

# 综合评分权重：人工审核更重要（没被人看过的测试通过不算掌握）
REVIEW_WEIGHT = 0.6
TEST_WEIGHT = 0.4


@dataclass
class ReviewPolicy:
    """告警阈值与开关。"""

    min_coverage: float = 0.6     # 人工审核覆盖率下限
    warn_no_review: bool = True   # 是否报 no-review
    warn_untested: bool = True    # 是否报 untested


@dataclass
class ReviewWarning:
    """一条告警。"""

    code: str        # no-review | low-review | untested
    level: str       # warning
    message: str


@dataclass
class ReviewScore:
    """跨 Feat 汇总结果。"""

    items: int = 0
    reviewed: int = 0
    tested: int = 0
    feats: int = 0                # 贡献了可审项的 feat 数
    review_coverage: float = 0.0
    test_coverage: float = 0.0
    score: float = 0.0
    level: str = "none"
    warnings: List[ReviewWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """无告警即 ok。"""
        return not self.warnings


def _level_of(score: float, items: int) -> str:
    if items == 0:
        return "none"
    for name, low in LEVELS:
        if score >= low:
            return name
    return "poor"


def compute_review(feats: Optional[Iterable] = None,
                   policy: Optional[ReviewPolicy] = None) -> ReviewScore:
    """汇总一批 Feat 的审查覆盖率、评分与告警。

    :param feats: 任意可迭代的 :class:`pdev.feat.Feat`；``None`` 视为空。
    :param policy: 阈值；``None`` 时用默认。
    """
    policy = policy or ReviewPolicy()
    feats = list(feats) if feats else []

    s = ReviewScore()
    for f in feats:
        try:
            items, reviewed, tested = f.review_counts()
        except AttributeError:
            continue
        if items == 0:
            continue
        s.feats += 1
        s.items += items
        s.reviewed += reviewed
        s.tested += tested

    if s.items:
        s.review_coverage = s.reviewed / s.items
        s.test_coverage = s.tested / s.items
        s.score = (REVIEW_WEIGHT * s.review_coverage
                   + TEST_WEIGHT * s.test_coverage)
    s.level = _level_of(s.score, s.items)

    s.warnings = _warnings(s, policy)
    return s


def _warnings(s: ReviewScore, policy: ReviewPolicy) -> List[ReviewWarning]:
    """按「过低」规则生成告警；空仓库不告警。"""
    out: List[ReviewWarning] = []
    if s.items == 0:
        return out

    if policy.warn_no_review and s.reviewed == 0:
        out.append(ReviewWarning(
            "no-review", "warning",
            f"完全不审查：{s.items} 个可审项无一项被人工确认",
        ))
    if s.review_coverage < policy.min_coverage:
        out.append(ReviewWarning(
            "low-review", "warning",
            f"人工审核覆盖率过低：{s.review_coverage:.0%}"
            f"（低于 {policy.min_coverage:.0%}）",
        ))
    if policy.warn_untested and s.tested == 0:
        out.append(ReviewWarning(
            "untested", "warning",
            f"完全没有测试通过记录：{s.items} 个可审项都未绑定通过的测试",
        ))
    return out


def format_score(s: ReviewScore) -> str:
    """把评分渲染成人类可读的多行文本。"""
    if s.items == 0:
        return "掌握程度：无可审内容（没有 doc/api/logs/fallbacks 可审项）"

    lines = [
        f"掌握程度：{s.level}  {s.score:.2f} / 1.00",
        f"  可审项    {s.items}（来自 {s.feats} 条 feat）",
        f"  人工审查  {s.reviewed}  {s.review_coverage:.0%}",
        f"  测试通过  {s.tested}  {s.test_coverage:.0%}",
    ]
    if s.warnings:
        lines.append("  告警")
        for w in s.warnings:
            lines.append(f"    ! [{w.code}] {w.message}")
    return "\n".join(lines)
