# -*- coding: utf-8 -*-
"""Feat —— 一次功能开发的索引卡。

Feat 是**抽象的开发单元**：一次 feat（或 fix/refactor），横跨多个 commit。
它不存长文档，只做两件事：

1. **约束**：这个功能的设计规格（接口签名、日志、兜底）
2. **检索**：slug / 状态 / 关联的 commit 与 note

设计正文（简短）外置为 Markdown，Feat 里只存路径 ``doc``。
与 commit 的关联为**手动** ``link_commit``，可用 ``pdev/git.py`` 补齐标题。

存储：``<root>/by-id/<slug>.json``，一条一个文件，可进 git、可 review。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterator, List, Optional, Union

__all__ = [
    "FeatKind",
    "FeatStatus",
    "Feat",
    "FeatError",
    "FeatStore",
    "ReviewItem",
    "valid_slug",
    "VALID_SLUG_CHARS",
]

_BY_ID = "by-id"
VALID_SLUG_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"


class FeatError(ValueError):
    """Feat 相关的错误（非法 slug、重复、缺失字段等）。"""


class FeatKind(str, Enum):
    """这次开发的类型。"""

    FEAT = "feat"
    FIX = "fix"
    REFACTOR = "refactor"
    DOC = "doc"
    TEST = "test"


class FeatStatus(str, Enum):
    """开发流程的阶段（对应 doc→test→feat→fix→doc）。"""

    DRAFT = "draft"              # doc 阶段：设计规格已定
    TESTING = "testing"          # 按 doc 写测试
    INTEGRATED = "integrated"    # 已模块化接入系统
    FIXING = "fixing"            # Code Review / 修 Bug 中
    CLOSED = "closed"            # 完成，异常已回填

    @property
    def order(self) -> int:
        return _STATUS_ORDER[self]


_STATUS_ORDER = {
    FeatStatus.DRAFT: 0,
    FeatStatus.TESTING: 1,
    FeatStatus.INTEGRATED: 2,
    FeatStatus.FIXING: 3,
    FeatStatus.CLOSED: 4,
}

_NEXT = {
    FeatStatus.DRAFT: "按本 doc 编写测试（pdm feat set <slug> testing）",
    FeatStatus.TESTING: "写 MVP 脚本验证，通过后模块化接入"
                         "（pdm feat set <slug> integrated）",
    FeatStatus.INTEGRATED: "Code Review 并修复接入 Bug"
                           "（pdm feat set <slug> fixing）",
    FeatStatus.FIXING: "回填发现的异常，关闭"
                       "（pdm feat set <slug> closed）",
    FeatStatus.CLOSED: None,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def valid_slug(slug: str) -> bool:
    """slug 只允许小写字母、数字、连字符，且不能以连字符开头/结尾。"""
    if not slug or slug[0] == "-" or slug[-1] == "-":
        return False
    return all(c in VALID_SLUG_CHARS for c in slug)


@dataclass
class ReviewItem:
    """一个可审项的**双勾选位**记录（见 doc/feat/review-model.md）。

    ``reviewed`` 与 ``tested`` 是**独立**布尔位，互不蕴含：可以只审不测，
    也可以只测未审。只有被操作过的 key 才落盘。
    """

    reviewed: bool = False
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    tested: bool = False
    test_command: str = ""
    test_status: str = ""
    tested_at: Optional[datetime] = None

    @property
    def is_empty(self) -> bool:
        """两个勾选位都清、且无附加信息——不必落盘。"""
        return not (self.reviewed or self.tested)


# 可审项的字段顺序（review_items 据此展开）
_REVIEW_FIELDS = ("api", "logs", "fallbacks",
                  "data_model", "samples", "changes")

# 新 feat 必填字段：(属性名, 人类可读名)
_REQUIRED_FIELDS = (
    ("design_note", "设计思路"),
    ("impl_note", "实现方式"),
    ("data_model", "核心数据结构"),
    ("samples", "样例数据"),
    ("changes", "对既有代码的改动"),
)


@dataclass
class Feat:
    """一次功能开发的索引卡。

    :param slug: 唯一标识。
    :param api: 交付的**代码接口**（真实签名，可直接照着实现）。
    :param logs: 该功能**会产生什么日志**（内容/时机，不是格式串）。
    """

    slug: str
    title: str = ""
    kind: FeatKind = FeatKind.FEAT
    status: FeatStatus = FeatStatus.DRAFT

    # 简短设计文档的路径（正文外置，AI 生成/维护）
    doc: str = ""

    # 设计规格：这三栏要能直接写进实现代码
    api: List[str] = field(default_factory=list)        # 真实接口签名
    logs: List[str] = field(default_factory=list)       # 会打什么日志
    fallbacks: List[str] = field(default_factory=list)  # 异常兜底策略

    # 五项设计字段（见 doc/feat/feat-fields.md）；全必填
    design_note: str = ""                               # 设计思路
    impl_note: str = ""                                 # 实现方式
    data_model: List[str] = field(default_factory=list)  # 核心数据结构
    samples: List[str] = field(default_factory=list)     # 样例数据
    changes: List[str] = field(default_factory=list)     # 对既有代码的改动

    # 关联（手动串联）
    commits: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    discovered: List[str] = field(default_factory=list)

    # 阶段提交游标（doc→test→feat→fix→close）；None 表示尚未开始
    stage: Optional[str] = None

    # 审查项：{key: ReviewItem}，key 形如 doc / api:0 / logs:1 / fallbacks:0
    reviews: dict = field(default_factory=dict)

    # 条目级人工评论：{key: 文本}，key 同上（见 doc/feat/feat-comment.md）
    comments: dict = field(default_factory=dict)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not valid_slug(self.slug):
            raise FeatError(
                f"非法 slug：{self.slug!r}"
                f"（只允许小写字母/数字/连字符，且首尾不能是连字符）"
            )
        # 允许传字符串（如从 dict 构造），统一转成枚举
        if not isinstance(self.kind, FeatKind):
            self.kind = FeatKind(self.kind)
        if not isinstance(self.status, FeatStatus):
            self.status = FeatStatus(self.status)
        if self.created_at is None:
            self.created_at = _now()
        if self.updated_at is None:
            self.updated_at = self.created_at

    # --- 便捷 ---

    def validate(self) -> None:
        """检查自洽性，不合格抛 ``FeatError``。"""
        if not valid_slug(self.slug):
            raise FeatError(f"非法 slug：{self.slug!r}")
        if not self.title:
            raise FeatError(f"feat {self.slug}: title 不能为空")

    def touch(self) -> None:
        """更新修改时间。"""
        self.updated_at = _now()

    def advance(self, status: FeatStatus) -> None:
        """推进状态（不允许倒退）。"""
        if status.order < self.status.order:
            raise FeatError(
                f"状态不能倒退：{self.status.value} → {status.value}"
            )
        self.status = status
        self.touch()

    @property
    def next_step(self) -> Optional[str]:
        """当前流程的下一步（供 Agent 提示）。"""
        return _NEXT.get(self.status)

    # --- 审查项 ---

    def missing_required_fields(self) -> List[str]:
        """新 feat 必填字段检查；返回缺失项的**人类可读名**（空 = 齐全）。"""
        out: List[str] = []
        for attr, label in _REQUIRED_FIELDS:
            val = getattr(self, attr, None)
            if not val:
                out.append(label)
        return out

    def review_items(self) -> List[tuple]:
        """展开可审项，返回 ``[(key, label), ...]``。

        顺序固定：``doc`` → ``api`` → ``logs`` → ``fallbacks``。
        ``doc`` 为空、或某个列表为空时，不产生对应项。
        """
        out: List[tuple] = []
        if self.doc:
            out.append(("doc", self.doc))
        for name in _REVIEW_FIELDS:
            for i, text in enumerate(getattr(self, name, []) or []):
                out.append((f"{name}:{i}", text))
        return out

    def _review_keys(self) -> set:
        return {k for k, _ in self.review_items()}

    def review_item(self, key: str) -> Optional[ReviewItem]:
        """取某 key 的勾选记录；未记录返回 ``None``。"""
        return self.reviews.get(key)

    def _review_slot(self, key: str) -> ReviewItem:
        """取（必要时创建）某 key 的勾选记录，校验 key 合法。"""
        if key not in self._review_keys():
            raise FeatError(
                f"非法审查项 key：{key!r}（不在 {sorted(self._review_keys())}）"
            )
        item = self.reviews.get(key)
        if item is None:
            item = ReviewItem()
            self.reviews[key] = item
        return item

    def set_reviewed(self, key: str, value: bool = True,
                     by: str = "") -> ReviewItem:
        """置/清 ``[审]`` 位；为真时记录 by 与时间。"""
        item = self._review_slot(key)
        item.reviewed = bool(value)
        if value:
            item.reviewed_by = by or item.reviewed_by
            item.reviewed_at = _now()
        self._prune(key, item)
        self.touch()
        return item

    def set_tested(self, key: str, value: bool = True,
                   command: str = "", status: str = "") -> ReviewItem:
        """置/清 ``[测]`` 位；为真时记录命令、状态与时间。"""
        item = self._review_slot(key)
        item.tested = bool(value)
        if value:
            if command:
                item.test_command = command
            if status:
                item.test_status = status
            item.tested_at = _now()
        self._prune(key, item)
        self.touch()
        return item

    def _prune(self, key: str, item: ReviewItem) -> None:
        """两个位都清的记录从 dict 移除，保持 JSON 精简。"""
        if item.is_empty:
            self.reviews.pop(key, None)

    def review_counts(self) -> tuple:
        """返回 ``(items, reviewed, tested)``，孤儿记录不计入。"""
        keys = self._review_keys()
        reviewed = tested = 0
        for k in keys:
            item = self.reviews.get(k)
            if item is None:
                continue
            if item.reviewed:
                reviewed += 1
            if item.tested:
                tested += 1
        return len(keys), reviewed, tested

    # --- 条目级评论（feat-comment）---

    def comment(self, key: str) -> str:
        """取某条目的评论；没有返回 ``""``。"""
        return self.comments.get(key, "")

    def set_comment(self, key: str, text: str) -> None:
        """写/清某条目的评论；``text`` 为空即清除。非法 key 抛 FeatError。"""
        if key not in self._review_keys():
            raise FeatError(
                f"非法评论 key：{key!r}（不在 {sorted(self._review_keys())}）"
            )
        text = text or ""
        if text:
            self.comments[key] = text
        else:
            self.comments.pop(key, None)
        self.touch()

    def commented_items(self) -> List[tuple]:
        """返回 ``[(key, label, comment), ...]``，只含**非空**评论。

        按 `review_items()` 的项顺序；孤儿 key 不返回。
        """
        out: List[tuple] = []
        for key, label in self.review_items():
            text = self.comments.get(key, "")
            if text:
                out.append((key, label, text))
        return out


class FeatStore:
    """Feat 的读写。

    一条 feat 一个 JSON 文件（``by-id/<slug>.json``），写入即落盘。
    """

    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self._dir = self.root / _BY_ID
        self._dir.mkdir(parents=True, exist_ok=True)
        self._feats: dict[str, Feat] = {}
        self._load()

    # --- 读 ---

    def _load(self) -> None:
        self._feats = {}
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            try:
                feat = _from_dict(data)
            except (FeatError, KeyError, ValueError):
                continue
            self._feats[feat.slug] = feat

    def _path(self, slug: str) -> Path:
        return self._dir / f"{slug}.json"

    def all(self) -> Iterator[Feat]:
        """全部 feat（按创建时间排序，新→旧）。"""
        return iter(sorted(self._feats.values(),
                           key=lambda f: f.created_at or _now(),
                           reverse=True))

    def __len__(self) -> int:
        return len(self._feats)

    def get(self, slug: str) -> Optional[Feat]:
        return self._feats.get(slug)

    def has(self, slug: str) -> bool:
        return slug in self._feats

    def by_status(self, status: FeatStatus) -> List[Feat]:
        return [f for f in self.all() if f.status is status]

    def by_kind(self, kind: FeatKind) -> List[Feat]:
        return [f for f in self.all() if f.kind is kind]

    def by_commit(self, commit: str) -> Optional[Feat]:
        """哪个 feat 关联了这个 commit（支持短 hash 前缀）。"""
        for f in self.all():
            for c in f.commits:
                if c == commit or c.startswith(commit) or commit.startswith(c):
                    return f
        return None

    def open(self) -> List[Feat]:
        """未关闭的 feat（status != closed）。"""
        return [f for f in self.all() if f.status is not FeatStatus.CLOSED]

    # --- 写 ---

    def add(self, feat: Feat) -> None:
        """新增一条 feat；slug 已存在则报错。"""
        feat.validate()
        if feat.slug in self._feats:
            raise FeatError(
                f"feat 已存在：{feat.slug}（用 pdm feat show {feat.slug} 查看）"
            )
        self._feats[feat.slug] = feat
        self._flush(feat)

    def update(self, feat: Feat) -> None:
        """覆盖写回一条已存在的 feat。"""
        feat.validate()
        feat.touch()
        self._feats[feat.slug] = feat
        self._flush(feat)

    def link_commit(self, slug: str, commit: str) -> Feat:
        """把实现 commit 手动串联到 feat 上（已存在则忽略）。"""
        feat = self._require(slug)
        if commit not in feat.commits:
            feat.commits.append(commit)
            self.update(feat)
        return feat

    def set_stage(self, slug: str, stage: Optional[str]) -> Feat:
        """设置阶段提交游标。"""
        feat = self._require(slug)
        feat.stage = stage
        self.update(feat)
        return feat

    def commit_stage(self, slug: str, stage: str, message: str,
                     *, cwd: str, files=None, body: str = "",
                     no_verify: bool = False, dry_run: bool = False,
                     git=None, close: bool = False) -> tuple:
        """阶段提交：校验顺序 → git commit → link → 推进游标。

        :param git: 用于推断当前游标的 :class:`pdev.git.GitRepo`。
        :param close: 为真且阶段为 ``close`` 时，同时把状态置为 closed。
        :returns: ``(feat, hash, old_stage, new_stage)``。
        :raises StageError: 顺序非法、提交失败。
        """
        from .stage import assert_allowed, format_subject, infer_stage, \
            run_commit

        feat = self._require(slug)

        # 游标缺失时，从已有 commit 前缀推断（兼容旧数据）
        current = feat.stage
        if current is None and feat.commits and git is not None:
            current = infer_stage(feat.commits, git)

        assert_allowed(current, stage)
        subject = format_subject(stage, slug, message)

        commit_hash = run_commit(
            cwd, subject, body=body, files=files,
            no_verify=no_verify, dry_run=dry_run,
        )

        old_stage = current
        # 收尾 close 归一为 doc 记录，但游标记为 close
        if not dry_run and commit_hash and commit_hash not in feat.commits:
            feat.commits.append(commit_hash)
        feat.stage = stage
        if close and stage == "close":
            feat.status = FeatStatus.CLOSED
        self.update(feat)
        return feat, commit_hash, old_stage, stage

    def unlink_commit(self, slug: str, commit: str) -> Feat:
        """解除某个 commit 的关联。"""
        feat = self._require(slug)
        if commit in feat.commits:
            feat.commits.remove(commit)
            self.update(feat)
        return feat

    def add_discovered(self, slug: str, item: str) -> Feat:
        """记录 fix 阶段新发现的异常/问题。"""
        feat = self._require(slug)
        if item not in feat.discovered:
            feat.discovered.append(item)
            self.update(feat)
        return feat

    def set_reviewed(self, slug: str, key: str, value: bool = True,
                     by: str = "") -> Feat:
        """置/清某可审项的 ``[审]`` 位并落盘。"""
        feat = self._require(slug)
        feat.set_reviewed(key, value, by=by)
        self.update(feat)
        return feat

    def set_tested(self, slug: str, key: str, value: bool = True,
                   command: str = "", status: str = "") -> Feat:
        """置/清某可审项的 ``[测]`` 位并落盘。"""
        feat = self._require(slug)
        feat.set_tested(key, value, command=command, status=status)
        self.update(feat)
        return feat

    def set_comment(self, slug: str, key: str, text: str) -> Feat:
        """写/清某条目的评论并落盘。"""
        feat = self._require(slug)
        feat.set_comment(key, text)
        self.update(feat)
        return feat

    def resolve_keys(self, slug: str, item: str = "",
                     all_items: bool = False) -> List[tuple]:
        """把 ``--item`` / ``--all`` 展开成 ``[(key, label), ...]``。

        - ``all_items`` → 全部可审项；无可审项抛 ``FeatError``
        - ``item`` 是精确 key → 该项
        - ``item`` 是字段前缀（如 ``"api"``）→ 所有 ``"api:*"``
        - 无匹配 → 抛 ``FeatError``
        """
        feat = self._require(slug)
        items = feat.review_items()
        if all_items:
            if not items:
                raise FeatError(f"feat {slug} 没有可审项")
            return list(items)
        if not item:
            raise FeatError("需要 --item <KEY> 或 --all")
        for key, label in items:
            if key == item:
                return [(key, label)]
        prefix = f"{item}:"
        matched = [(k, lbl) for k, lbl in items if k.startswith(prefix)]
        if not matched:
            avail = sorted(k for k, _ in items)
            raise FeatError(
                f"没有匹配的可审项：{item!r}（可选 {avail}）"
            )
        return matched

    def set_reviews(self, slug: str, keys, *, reviewed=None, tested=None,
                    by: str = "", command: str = "",
                    status: str = "") -> Feat:
        """批量置位（只落盘一次）。

        :param reviewed: True/False/None（None 不动审查位）
        :param tested: True/False/None（None 不动测试位）
        """
        feat = self._require(slug)
        for key in keys:
            if reviewed is not None:
                feat.set_reviewed(key, reviewed, by=by)
            if tested is not None:
                feat.set_tested(key, tested, command=command, status=status)
        self.update(feat)
        return feat

    def set_status(self, slug: str, status: FeatStatus) -> Feat:
        feat = self._require(slug)
        feat.advance(status)
        self.update(feat)
        return feat

    def _require(self, slug: str) -> Feat:
        feat = self._feats.get(slug)
        if feat is None:
            raise FeatError(f"找不到 feat：{slug}")
        return feat

    def _flush(self, feat: Feat) -> None:
        self._path(feat.slug).write_text(
            json.dumps(_to_dict(feat), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _to_dict(f: Feat) -> dict:
    return {
        "slug": f.slug,
        "title": f.title,
        "kind": f.kind.value,
        "status": f.status.value,
        "doc": f.doc,
        "api": list(f.api),
        "logs": list(f.logs),
        "fallbacks": list(f.fallbacks),
        "design_note": f.design_note,
        "impl_note": f.impl_note,
        "data_model": list(f.data_model),
        "samples": list(f.samples),
        "changes": list(f.changes),
        "commits": list(f.commits),
        "notes": list(f.notes),
        "discovered": list(f.discovered),
        "stage": f.stage,
        "reviews": {k: _review_to_dict(v) for k, v in f.reviews.items()},
        "comments": dict(f.comments),
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _review_to_dict(r: ReviewItem) -> dict:
    return {
        "reviewed": r.reviewed,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "tested": r.tested,
        "test_command": r.test_command,
        "test_status": r.test_status,
        "tested_at": r.tested_at.isoformat() if r.tested_at else None,
    }


def _review_from_dict(d: dict) -> ReviewItem:
    """构造 ReviewItem；时间非法值一律静默置 None，不阻断加载。"""
    def dt(key: str) -> Optional[datetime]:
        raw = d.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    return ReviewItem(
        reviewed=bool(d.get("reviewed")),
        reviewed_by=d.get("reviewed_by", "") or "",
        reviewed_at=dt("reviewed_at"),
        tested=bool(d.get("tested")),
        test_command=d.get("test_command", "") or "",
        test_status=d.get("test_status", "") or "",
        tested_at=dt("tested_at"),
    )


# 旧版字段：读取时忽略即可（不做兼容迁移）
_LEGACY_IGNORED = {"design", "data_model", "fixtures", "touches",
                   "follows", "debug"}


def _from_dict(d: dict) -> Feat:
    def dt(key: str) -> Optional[datetime]:
        raw = d.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    raw_reviews = d.get("reviews")
    reviews = {}
    if isinstance(raw_reviews, dict):
        for key, val in raw_reviews.items():
            if isinstance(val, dict):
                reviews[key] = _review_from_dict(val)

    raw_comments = d.get("comments")
    comments = {}
    if isinstance(raw_comments, dict):
        for key, val in raw_comments.items():
            if isinstance(val, str):
                comments[key] = val

    return Feat(
        slug=d["slug"],
        title=d.get("title", ""),
        kind=FeatKind(d.get("kind", "feat")),
        status=FeatStatus(d.get("status", "draft")),
        doc=d.get("doc", ""),
        api=list(d.get("api") or []),
        logs=list(d.get("logs") or []),
        fallbacks=list(d.get("fallbacks") or []),
        design_note=d.get("design_note", "") or "",
        impl_note=d.get("impl_note", "") or "",
        data_model=list(d.get("data_model") or []),
        samples=list(d.get("samples") or []),
        changes=list(d.get("changes") or []),
        commits=list(d.get("commits") or []),
        notes=list(d.get("notes") or []),
        discovered=list(d.get("discovered") or []),
        stage=d.get("stage") or None,
        reviews=reviews,
        comments=comments,
        created_at=dt("created_at"),
        updated_at=dt("updated_at"),
    )
