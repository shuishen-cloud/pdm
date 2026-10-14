# -*- coding: utf-8 -*-
"""Feat 自约束校验。

扫描所有 Feat 及其关联的 commit，报告**状态与事实不符**、**覆盖缺口**、
**关联冲突**等问题——让 pdev 从"记账本"变成"护栏"。

设计见 ``doc/feat/feat-check.md``。
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
    "check_notes",
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
    "stage-order",
    "missing-stage",
    "commit-no-note",
    "note-no-verify",
    "review-none",
    "review-low",
    "missing-fields",
    "vague-change",
    "empty-sample",
)

# 敷衍样例的占位词（光秃秃才算；带说明如「无：纯计算」不算）
_SAMPLE_PLACEHOLDERS = {"无", "none", "n/a", "na", "tbd", "-", "待定"}

# 开发阶段 → commit 信息前缀（见 doc/feat/stage-prefix.md）
STAGES = ("doc", "test", "feat", "fix")

# 非流程性但仍合法的前缀：不告警（归为 other）
NEUTRAL_PREFIXES = ("refactor", "init", "chore", "style", "perf",
                    "build", "ci")


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


def is_neutral(subject: str) -> bool:
    """前缀合法但不属流程阶段（如 refactor/init）——不告警。"""
    if not subject:
        return False
    s = subject.strip().lower()
    return any(s.startswith(f"{p}(") or s.startswith(f"{p}:")
               for p in NEUTRAL_PREFIXES)


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


def check_one(store: FeatStore, slug: str, git=None,
              note_store=None, min_coverage: float = 0.6) -> List[CheckIssue]:
    """检查单个 feat。

    :param git: 可选的 :class:`pdev.git.GitRepo`；为 ``None`` 时跳过
        依赖 git 的规则（``commit-missing`` / ``orphan-commit``）。
    :param note_store: 可选的 :class:`pdev.store.NoteStore`；为 ``None``
        时跳过依赖笔记的规则（``commit-no-note`` / ``note-no-verify``）。
    :param min_coverage: 人工审核覆盖率下限，低于它报 ``review-low``。
    """
    feat = store.get(slug)
    if feat is None:
        raise KeyError(f"找不到 feat：{slug}")
    return _check_feat(feat, git, note_store, min_coverage)


def check_feats(store: FeatStore, git=None, *,
                include_orphans: bool = True,
                note_store=None,
                min_coverage: float = 0.6) -> List[CheckIssue]:
    """检查全部 feat（含跨 feat 的冲突与孤儿 commit）。

    :param git: 可选的 :class:`pdev.git.GitRepo`。
    :param include_orphans: 是否检查未被认领的 commit。
    :param note_store: 可选的 :class:`pdev.store.NoteStore`。
    :param min_coverage: 人工审核覆盖率下限。
    """
    issues: List[CheckIssue] = []
    feats = list(store.all())

    # 逐个 feat 的局部规则
    for feat in feats:
        issues.extend(_check_feat(feat, git, note_store, min_coverage))

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


def _check_feat(feat: Feat, git, note_store=None,
                min_coverage: float = 0.6) -> List[CheckIssue]:
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

    # 笔记与验证覆盖（见 doc/feat/note-check.md）
    if (note_store is not None and git is not None
            and getattr(git, "available", False)):
        out.extend(check_notes(feat, git, note_store))

    # 审查覆盖率（见 doc/feat/review-check.md）
    out.extend(_check_review(feat, min_coverage))

    # 五项设计字段（见 doc/feat/feat-fields-check.md）
    out.extend(_check_fields(feat))

    return out


# 五项字段的强制起点：此时间之后新建的 feat 才报 missing-fields。
# 不用 stage 游标做判据——走新流程的历史 feat 也有 stage，会被误伤。
# 取 feat-fields 落地之后的那一刻（2026-10-14 11:15 之后）为界。
FIELDS_SINCE = "2026-10-14T11:16:00+00:00"


def _fields_enforced(feat: Feat) -> bool:
    """该 feat 是否受五项必填字段约束（历史豁免）。"""
    from datetime import datetime

    created = getattr(feat, "created_at", None)
    if created is None:
        return False
    try:
        since = datetime.fromisoformat(FIELDS_SINCE)
    except ValueError:                       # 常量写错则不强制，不拖垮 check
        return False
    return created >= since


def _check_fields(feat: Feat) -> List[CheckIssue]:
    """五项设计字段规则：``missing-fields`` / ``vague-change`` / ``empty-sample``。

    - ``missing-fields``：仅对**有 stage 游标**的 feat 报（历史豁免）。
    - ``vague-change``：``changes`` 某条既无 ``::`` 也无 ``.``。
    - ``empty-sample``：``samples`` 某条过短或光秃秃占位词。
    """
    out: List[CheckIssue] = []

    if _fields_enforced(feat):
        missing = feat.missing_required_fields()
        if missing:
            out.append(CheckIssue(
                feat.slug, "missing-fields", "warning",
                f"缺必填字段：{'、'.join(missing)}",
            ))

    for c in (getattr(feat, "changes", None) or []):
        if not _locates_symbol(c):
            out.append(CheckIssue(
                feat.slug, "vague-change", "warning",
                f"改动未定位到符号（缺 :: 或类.成员）：{c[:40]!r}",
            ))

    for s in (getattr(feat, "samples", None) or []):
        if _is_lazy_sample(s):
            out.append(CheckIssue(
                feat.slug, "empty-sample", "warning",
                f"样例过于敷衍：{s[:40]!r}（应写结构的真实实例）",
            ))

    return out


# 常见文件扩展名：这些点不算「定位到符号」
_FILE_EXTS = ("py", "md", "json", "txt", "sh", "toml", "yaml", "yml",
              "ts", "js", "tcss", "cfg", "ini")


def _locates_symbol(text: str) -> bool:
    """判断一条改动说明是否定位到了符号。

    - 含 ``::`` → 算（``pdev/x.py::Feat.f``）
    - 否则看是否含**非文件扩展名**的点（``Feat.member``）
    """
    s = text or ""
    if "::" in s:
        return True
    for part in s.split():
        if "." not in part:
            continue
        head, _, tail = part.rpartition(".")
        tail_clean = tail.strip("，,。;；:：)")
        if head and tail_clean and tail_clean.lower() not in _FILE_EXTS:
            return True
    return False


def _is_lazy_sample(s: str) -> bool:
    """判定敷衍样例：过短，或去掉空白后是纯占位词。"""
    text = (s or "").strip()
    if len(text) < 3:
        return True
    return text.lower() in _SAMPLE_PLACEHOLDERS


def _check_review(feat: Feat, min_coverage: float = 0.6) -> List[CheckIssue]:
    """人工审查覆盖率规则：``review-none`` / ``review-low``。

    不依赖 git / note_store；无可审项时不报。
    """
    out: List[CheckIssue] = []
    items, reviewed, _tested = feat.review_counts()
    if items == 0:
        return out

    suffix = "（已 closed）" if feat.status is FeatStatus.CLOSED else ""
    if reviewed == 0:
        out.append(CheckIssue(
            feat.slug, "review-none", "warning",
            f"规格字段无一项被人工审查：{items} 个可审项{suffix}"
            f"（用 pdm feat review {feat.slug} --item <KEY> --review）",
        ))
    coverage = reviewed / items
    if coverage < min_coverage:
        out.append(CheckIssue(
            feat.slug, "review-low", "warning",
            f"人工审核覆盖率过低：{coverage:.0%}"
            f"（低于 {min_coverage:.0%}）",
        ))
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
            if is_neutral(info.subject):
                continue          # refactor/init 等合法前缀，不告警
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

    out.extend(check_stage_order(feat, git))

    return out


# 阶段在流水线中的序号；doc 既可首也可尾，按出现位置判定
_PIPELINE = ("doc", "test", "feat", "fix")


def check_stage_order(feat: Feat, git) -> List[CheckIssue]:
    """按提交先后顺序校验阶段不倒退（兜底 ``stage-commit`` 门面）。

    允许停留在同一阶段或前进一阶；后退（如 feat 后又 test）报
    ``stage-order`` warning。识别不出的前缀跳过。

    首阶段 ``doc`` 与收尾 ``doc`` 前缀相同，靠**位置**区分：出现于
    test/feat/fix 之后的 ``doc`` 视为收尾，不判倒退。
    """
    out: List[CheckIssue] = []
    if git is None or not getattr(git, "available", False):
        return out

    # 按 git 提交时间排序；时间相同或缺失时，退回 feat.commits 的录入顺序
    dated = []
    for i, c in enumerate(feat.commits):
        info = git.commit_info(c)
        if info is None:
            continue
        stage = classify_stage(info.subject)
        if stage is None:
            continue
        dated.append((info.date, i, info.hash, stage))
    dated.sort(key=lambda t: (t[0] is None, t[0], t[1]))

    best = -1
    for _, _, h, stage in dated:
        if stage == "doc":
            # 首阶段与收尾 doc 前缀相同，不参与单调性判定
            continue
        idx = _PIPELINE.index(stage)
        if idx < best:
            out.append(CheckIssue(
                feat.slug, "stage-order", "warning",
                f"阶段倒退：commit {h[:8]} 是 {stage}，出现在更晚阶段之后"
                f"（应为 doc→test→feat→fix→doc）",
            ))
        best = max(best, idx)
    return out


def _note_for(note_store, commit) -> list:
    """取某 commit 的笔记（前缀互匹配，≥６位，避免短串误配）。"""
    if not commit:
        return []
    out = []
    for n in note_store.all():
        nc = n.commit or ""
        if nc == commit:
            out.append(n)
            continue
        if len(commit) >= 6 and nc.startswith(commit):
            out.append(n)
            continue
        if len(nc) >= 6 and commit.startswith(nc):
            out.append(n)
    return out


def check_notes(feat: Feat, git, note_store) -> List[CheckIssue]:
    """检查 commit 是否有笔记、笔记是否绑定验证。

    规则（见 doc/feat/note-check.md）：

    - ``commit-no-note``：``feat(`` / ``fix(`` 前缀的 commit 无笔记
    - ``note-no-verify``：该 commit 的笔记全部未绑定验证

    均为 warning：历史仓库普遍存在，不宜让 check 一律失败。
    """
    out: List[CheckIssue] = []
    if note_store is None or git is None \
            or not getattr(git, "available", False):
        return out

    for c in feat.commits:
        info = git.commit_info(c)
        if info is None:
            continue          # commit-missing 已另行告警
        notes = _note_for(note_store, c)
        if not notes:
            if classify_stage(info.subject) in ("feat", "fix"):
                out.append(CheckIssue(
                    feat.slug, "commit-no-note", "warning",
                    f"commit {info.hash[:8]}（{info.subject[:24]}）没有笔记",
                ))
            continue
        # 至少一条笔记绑定验证才算覆盖
        if not any(n.verifications for n in notes):
            out.append(CheckIssue(
                feat.slug, "note-no-verify", "warning",
                f"commit {info.hash[:8]} 的笔记均未绑定验证"
                f"（用 --verify 登记复现/验证方法）",
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
