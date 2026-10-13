# -*- coding: utf-8 -*-
"""Feat 自约束校验。

扫描所有 Feat 及其关联的 commit，报告**状态与事实不符**、**覆盖缺口**、
**关联冲突**等问题——让 pdev 从"记账本"变成"护栏"。

设计见 ``docs/feat/feat-check.md``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .feat import Feat, FeatStatus, FeatStore

__all__ = [
    "CheckIssue",
    "check_feats",
    "check_one",
    "classify_stage",
    "check_stages",
    "format_issue",
    "summarize",
    "LEVEL_MARK",
    "STAGES",
]

LEVEL_MARK = {"error": "✗", "warning": "!"}

# 所有校验规则代号
CODES = (
    "draft-has-commit",
    "closed-no-commit",
    "empty-doc",
    "no-api",
    "no-fallback",
    "discovered-not-closed",
    "commit-conflict",
    "commit-missing",
    "status-skipped",
    "orphan-commit",
    "stage-prefix",
    "missing-stage",
)

# 开发阶段 → commit 信息前缀（见 docs/feat/stage-prefix.md）
STAGES = ("doc", "test", "feat", "fix")


def classify_stage(subject: str) -> Optional[str]:
    """从 commit 信息前缀识别开发阶段。

    识别不出返回 ``None``。``doc`` 可同时是①设计与⑤收尾，均归为 doc。
    """
    if not subject:
        return None
    s = subject.strip().lower()
    for stage in STAGES:
        if s.startswith(f"{stage}(") or s.startswith(f"{stage}:"):
            return stage
    return None


@dataclass
class CheckIssue:
    """一条校验发现。"""

    slug: str            # 哪个 feat（全局问题用 "" 或 "(仓库)"）
    code: str            # 规则代号
    level: str           # "error" | "warning"
    message: str         # 人话描述

    @property
    def is_error(self) -> bool:
        return self.level == "error"

    @property
    def mark(self) -> str:
        return LEVEL_MARK.get(self.level, "?")


def format_issue(issue: CheckIssue, color: bool = False) -> str:
    """把一条发现格式化成一行文本。

    :param color: 为真时用 ANSI 着色（错误红、警告黄）。
    """
    where = issue.slug or "(仓库)"
    body = f"  {issue.mark} [{issue.code}] {where}: {issue.message}"
    if not color:
        return body
    code = "31" if issue.level == "error" else "33"
    return f"\033[{code}m{body}\033[0m"


def check_one(store: FeatStore, slug: str, git=None) -> List[CheckIssue]:
    """检查单个 feat。

    :param git: 可选的 :class:`pdev.git.GitRepo`；为 ``None`` 时跳过
        依赖 git 的规则（``commit-missing`` / ``orphan-commit``）。
    """
    feat = store.get(slug)
    if feat is None:
        raise KeyError(f"找不到 feat：{slug}")
    return _check_feat(feat, git)


def check_feats(store: FeatStore, git=None, *,
                include_orphans: bool = True) -> List[CheckIssue]:
    """检查全部 feat（含跨 feat 的冲突与孤儿 commit）。

    :param git: 可选的 :class:`pdev.git.GitRepo`。
    :param include_orphans: 是否检查未被认领的 commit。
    """
    issues: List[CheckIssue] = []
    feats = list(store.all())

    # 逐个 feat 的局部规则
    for feat in feats:
        issues.extend(_check_feat(feat, git))

    # 跨 feat：commit 冲突
    owners: dict[str, List[str]] = {}
    for feat in feats:
        for c in feat.commits:
            owners.setdefault(c, []).append(feat.slug)
    for commit, slugs in owners.items():
        if len(slugs) > 1:
            issues.append(CheckIssue(
                slug=", ".join(sorted(slugs)),
                code="commit-conflict",
                level="error",
                message=f"commit {commit[:8]} 被 {len(slugs)} 个 feat 认领",
            ))

    # 孤儿 commit：git 里有、但没人认领
    if include_orphans and git is not None and getattr(git, "available", False):
        claimed = list(owners)

        def _is_claimed(full_hash: str) -> bool:
            """存储的可能是任意长度前缀，按前缀互相匹配。"""
            for c in claimed:
                if full_hash.startswith(c) or c.startswith(full_hash):
                    return True
            return False

        for info in git.log():
            if _is_claimed(info.hash):
                continue
            issues.append(CheckIssue(
                slug="(仓库)",
                code="orphan-commit",
                level="warning",
                message=f"commit {info.hash[:8]} {info.subject!r} 未被任何 feat 认领",
            ))

    return issues


# ---------------------------------------------------------------------------
# 单个 feat 的规则
# ---------------------------------------------------------------------------


def _check_feat(feat: Feat, git) -> List[CheckIssue]:
    out: List[CheckIssue] = []

    def add(code: str, level: str, message: str) -> None:
        out.append(CheckIssue(feat.slug, code, level, message))

    # 状态与 commit 的一致性
    if feat.status is FeatStatus.DRAFT and feat.commits:
        add("draft-has-commit", "warning",
            f"draft 却已串联 {len(feat.commits)} 个 commit（设计未完已有实现）")
    if feat.status is FeatStatus.CLOSED and not feat.commits:
        add("closed-no-commit", "error",
            "closed 却未串联任何 commit（声称完成但无落地）")

    # 字段完整性
    if not feat.doc:
        add("empty-doc", "warning", "缺少 doc 路径（设计正文缺失）")
    if not feat.api:
        add("no-api", "warning", "缺少 api（未定义交付接口）")
    if not feat.fallbacks:
        add("no-fallback", "warning", "缺少 fallbacks（异常兜底未定义）")

    # discovered 与状态
    if feat.discovered and feat.status is not FeatStatus.CLOSED:
        add("discovered-not-closed", "warning",
            f"有 {len(feat.discovered)} 条发现的异常，但尚未 closed")

    # commit 是否真实存在于 git
    if git is not None and getattr(git, "available", False):
        for c in feat.commits:
            if git.commit_info(c) is None:
                add("commit-missing", "error",
                    f"commit {c[:8]} 在 git 中不存在")

    # 阶段前缀与流程完整性
    if git is not None and getattr(git, "available", False):
        out.extend(check_stages(feat, git))

    return out


def check_stages(feat: Feat, git, exempt: bool = False) -> List[CheckIssue]:
    """检查 commit 是否体现 doc→test→feat→fix 阶段。

    :param exempt: 为真时跳过 ``missing-stage``（历史归档豁免）。
    """
    out: List[CheckIssue] = []
    if git is None or not getattr(git, "available", False):
        return out

    seen: set = set()
    for c in feat.commits:
        info = git.commit_info(c)
        if info is None:
            # 查不到 subject：记一条 stage-prefix warning，不崩
            out.append(CheckIssue(
                feat.slug, "stage-prefix", "warning",
                f"commit {c[:8]} 无法读取提交信息，无法识别阶段",
            ))
            continue
        stage = classify_stage(info.subject)
        if stage is None:
            out.append(CheckIssue(
                feat.slug, "stage-prefix", "warning",
                f"commit {info.hash[:8]} 前缀不是 doc/test/feat/fix："
                f"{info.subject[:30]!r}",
            ))
        else:
            seen.add(stage)

    # 归档豁免：kind == doc 不强制 test/fix
    from .feat import FeatKind

    if (feat.status is FeatStatus.CLOSED and not exempt
            and feat.kind is not FeatKind.DOC and feat.commits):
        missing = [s for s in ("test", "fix") if s not in seen]
        if missing and seen:
            out.append(CheckIssue(
                feat.slug, "missing-stage", "warning",
                f"closed 的 feat 缺少阶段：{'、'.join(missing)}",
            ))

    return out


def summarize(issues: List[CheckIssue]) -> dict:
    """统计 error / warning 数量。"""
    errors = sum(1 for i in issues if i.is_error)
    return {
        "total": len(issues),
        "errors": errors,
        "warnings": len(issues) - errors,
    }
