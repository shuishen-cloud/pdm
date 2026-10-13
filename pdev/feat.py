# -*- coding: utf-8 -*-
"""Feat —— 一次功能开发的设计与交付记录。

一个 ``Feat`` 对应"一次开发"（通常是一个 feature，也可能是 fix/refactor），
写在整个流程的**最前面**（先有设计，再写测试、再实现）。

它承载的信息：

- 实现方式、交付 API、数据结构
- 预先准备的 Mock 数据（指向可执行的 fixture 文件）
- 异常兜底、外化日志、Debug 方式
- 对既有代码的边界（``touches``）与约定跟随（``follows``）
- 落地后回填的 commit 与 fix 阶段发现的异常

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

    DRAFT = "draft"              # 设计文档完成
    TESTING = "testing"          # 正在用它写测试
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def valid_slug(slug: str) -> bool:
    """slug 只允许小写字母、数字、连字符，且不能以连字符开头/结尾。"""
    if not slug or slug[0] == "-" or slug[-1] == "-":
        return False
    return all(c in VALID_SLUG_CHARS for c in slug)


@dataclass
class Feat:
    """一次功能开发的完整设计记录。"""

    slug: str                              # 唯一键，如 "feat-doc-storage"
    title: str = ""
    kind: FeatKind = FeatKind.FEAT
    status: FeatStatus = FeatStatus.DRAFT

    # --- 设计内容（你方法论要求的字段）---
    design: str = ""                       # 实现方式
    api: List[str] = field(default_factory=list)          # 交付的 API
    data_model: str = ""                   # 数据结构
    fixtures: List[str] = field(default_factory=list)     # Mock 数据（可执行文件路径）
    fallbacks: List[str] = field(default_factory=list)    # 异常兜底
    touches: List[str] = field(default_factory=list)      # 既有代码边界（影响面）
    follows: List[str] = field(default_factory=list)      # 既有约定跟随
    logs: List[str] = field(default_factory=list)         # 外化日志
    debug: str = ""                        # Debug 方式

    # --- 关联 ---
    commits: List[str] = field(default_factory=list)      # 落地后回填
    notes: List[str] = field(default_factory=list)        # 关联的 note 标题
    discovered: List[str] = field(default_factory=list)   # fix 阶段发现的异常

    # --- 时间 ---
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
        """把实现 commit 回填到 feat 上（已存在则忽略）。"""
        feat = self._require(slug)
        if commit not in feat.commits:
            feat.commits.append(commit)
            self.update(feat)
        return feat

    def add_discovered(self, slug: str, item: str) -> Feat:
        """记录 fix 阶段新发现的异常/问题。"""
        feat = self._require(slug)
        if item not in feat.discovered:
            feat.discovered.append(item)
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
        "design": f.design,
        "api": list(f.api),
        "data_model": f.data_model,
        "fixtures": list(f.fixtures),
        "fallbacks": list(f.fallbacks),
        "touches": list(f.touches),
        "follows": list(f.follows),
        "logs": list(f.logs),
        "debug": f.debug,
        "commits": list(f.commits),
        "notes": list(f.notes),
        "discovered": list(f.discovered),
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _from_dict(d: dict) -> Feat:
    def dt(key: str) -> Optional[datetime]:
        raw = d.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    return Feat(
        slug=d["slug"],
        title=d.get("title", ""),
        kind=FeatKind(d.get("kind", "feat")),
        status=FeatStatus(d.get("status", "draft")),
        design=d.get("design", ""),
        api=list(d.get("api") or []),
        data_model=d.get("data_model", ""),
        fixtures=list(d.get("fixtures") or []),
        fallbacks=list(d.get("fallbacks") or []),
        touches=list(d.get("touches") or []),
        follows=list(d.get("follows") or []),
        logs=list(d.get("logs") or []),
        debug=d.get("debug", ""),
        commits=list(d.get("commits") or []),
        notes=list(d.get("notes") or []),
        discovered=list(d.get("discovered") or []),
        created_at=dt("created_at"),
        updated_at=dt("updated_at"),
    )
