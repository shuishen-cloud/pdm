# -*- coding: utf-8 -*-
"""跨域派生指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, TYPE_CHECKING

from .issue import Issue
from .note import NoteStatus, VerificationStatus

if TYPE_CHECKING:  # pragma: no cover
    from .note import NoteKind
    from .store import NoteStore


# ---------------------------------------------------------------------------
# Issue 统计
# ---------------------------------------------------------------------------


@dataclass
class Stats:
    """从 issue 集合算出的汇总指标。"""

    total: int = 0
    open: int = 0
    ai_caused: int = 0    # 由 AI 写的代码引起
    ai_reported: int = 0  # 由 AI 发现
    fixed: int = 0        # 有 fix_commit
    ai_cause_rate: float = 0.0  # ai_caused / total


def compute_stats(issues: Iterable[Issue]) -> Stats:
    """汇总一组 issue。"""
    issues = list(issues)
    s = Stats(total=len(issues))
    for i in issues:
        if i.open:
            s.open += 1
        if i.caused_by_ai:
            s.ai_caused += 1
        if i.reported_by_ai:
            s.ai_reported += 1
        if i.fix_commit:
            s.fixed += 1
    if s.total:
        s.ai_cause_rate = s.ai_caused / s.total
    return s


# ---------------------------------------------------------------------------
# Note 统计
# ---------------------------------------------------------------------------


@dataclass
class NoteStats:
    """从笔记算出的汇总指标。"""

    total: int = 0
    by_kind: Dict[str, int] = field(default_factory=dict)
    open: int = 0
    promoted: int = 0        # 升级为 Issue 的数量
    resolved: int = 0        # 标记为已解决的
    written_by_ai: int = 0   # AI 撰写的笔记
    risky: int = 0           # 风险项（含未修缺陷与未升级的 open）
    commits: int = 0         # 覆盖的 commit 数
    files: int = 0           # 覆盖的文件数

    # 缺陷（负债）
    bugs: int = 0
    bugs_open: int = 0       # 未修复的缺陷

    # 可控异常（资产）
    controlled_exceptions: int = 0
    caught_types: int = 0    # 去重后被捕获的异常类型数

    # 验证覆盖
    verified_notes: int = 0     # 登记了验证方法的笔记
    verifications: int = 0      # 验证条目总数
    verification_passed: int = 0
    verification_failed: int = 0
    needs_verification: int = 0  # 需要验证却没有验证方法


def compute_note_stats(store: "NoteStore") -> NoteStats:
    """汇总一个笔记存储。"""
    s = NoteStats()
    commits = set()
    files = set()
    caught = set()
    for n in store.all():
        s.total += 1
        k = n.kind.value
        s.by_kind[k] = s.by_kind.get(k, 0) + 1
        if n.status.value == "open":
            s.open += 1
        if n.promotes_issue:
            s.promoted += 1
        if n.status.value == "resolved":
            s.resolved += 1
        if n.written_by_ai:
            s.written_by_ai += 1
        if n.risky:
            s.risky += 1
        if n.is_bug:
            s.bugs += 1
            if n.status is not NoteStatus.RESOLVED:
                s.bugs_open += 1
        if n.is_controlled_exception:
            s.controlled_exceptions += 1
            caught.update(n.catches)
        if n.needs_verification:
            s.needs_verification += 1
        if n.verifications:
            s.verified_notes += 1
        for v in n.verifications:
            s.verifications += 1
            if v.last_status is VerificationStatus.PASSED:
                s.verification_passed += 1
            elif v.last_status in (VerificationStatus.FAILED,
                                   VerificationStatus.ERROR):
                s.verification_failed += 1
        commits.add(n.commit)
        files.update(n.files)
    s.commits = len(commits)
    s.files = len(files)
    s.caught_types = len(caught)
    return s
