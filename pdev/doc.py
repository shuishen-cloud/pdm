# -*- coding: utf-8 -*-
"""文档域：自洽的文档版本快照与索引。"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, List, Optional

from .common import Actor
from .fingerprint import Generated


class Trigger(str, Enum):
    """为何新建文档版本。"""

    INTERFACE = "interface-change"
    DATA_MODEL = "data-model-change"
    CORE_FLOW = "core-flow-change"
    INVARIANT = "invariant-change"
    DETAIL = "detail-update"
    DOC_FIX = "doc-fix"

    @property
    def requires_new_version(self) -> bool:
        """该触发原因是否必须新建版本（而非原地修改）。"""
        return self in (
            Trigger.INTERFACE,
            Trigger.DATA_MODEL,
            Trigger.CORE_FLOW,
            Trigger.INVARIANT,
        )


class VersionStatus(str, Enum):
    """文档版本的状态。"""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


def match_glob(pattern: str, name: str) -> bool:
    """gitignore 风格匹配：``*`` 不跨 ``/``，``**`` 跨 ``/``。"""
    pattern = pattern.lstrip("./")
    name = name.lstrip("./")
    if not pattern:
        return False

    ps = pattern.split("/")
    ns = name.split("/")

    def rec(pi: int, ni: int) -> bool:
        while pi < len(ps):
            if ps[pi] == "**":
                # ** 匹配零个或多个路径段
                if rec(pi + 1, ni):
                    return True
                if ni >= len(ns):
                    return False
                ni += 1
                continue
            if ni >= len(ns):
                return False
            if not fnmatch.fnmatchcase(ns[ni], ps[pi]):
                return False
            pi += 1
            ni += 1
        return ni == len(ns)

    return rec(0, 0)


@dataclass
class Cover:
    """文档版本覆盖的代码范围，用于漂移检测。"""

    paths: List[str] = field(default_factory=list)
    symbols: List[str] = field(default_factory=list)

    def hits(self, file: str) -> bool:
        """给定文件路径是否落在覆盖范围内。"""
        return any(match_glob(p, file) for p in self.paths)


@dataclass
class Version:
    """一个自洽的文档逻辑快照。"""

    id: str
    file: str = ""
    from_commit: str = ""
    to_commit: str = "HEAD"  # HEAD 表示仍为当前
    created_at: Optional[datetime] = None
    reason: str = ""
    trigger: Trigger = Trigger.DETAIL
    doc_origin: Generated = Generated.HUMAN
    reviewed_by: Optional[Actor] = None
    explainability: str = "yes"
    status: VersionStatus = VersionStatus.CURRENT
    covers: Cover = field(default_factory=Cover)

    @property
    def current(self) -> bool:
        return self.status is VersionStatus.CURRENT

    @property
    def risky(self) -> bool:
        """AI 生成未审，或不可解释。"""
        if self.explainability == "no":
            return True
        return self.doc_origin is Generated.AI_FULL and not (
            self.reviewed_by is not None and self.reviewed_by.is_human
        )


@dataclass
class Manifest:
    """一个模块的文档版本索引。"""

    module: str
    current: str
    versions: List[Version] = field(default_factory=list)

    def validate(self) -> None:
        """检查自洽性，不合格抛 ``ValueError``。"""
        if not self.module:
            raise ValueError("manifest: module is required")
        if not self.versions:
            raise ValueError(f"manifest {self.module}: no versions")
        seen = set()
        for v in self.versions:
            if not v.id:
                raise ValueError(f"manifest {self.module}: version with empty id")
            if v.id in seen:
                raise ValueError(
                    f"manifest {self.module}: duplicate version id {v.id!r}"
                )
            seen.add(v.id)
        if self.current not in seen:
            raise ValueError(
                f"manifest {self.module}: current {self.current!r} not in versions"
            )

    def current_version(self) -> Optional[Version]:
        """当前版本的引用；不存在返回 ``None``。"""
        for v in self.versions:
            if v.id == self.current:
                return v
        return None

    def drifted(self, changed: Iterable[str]) -> bool:
        """当前版本 ``to_commit`` 之后，其覆盖的代码是否发生改动。

        :param changed: ``to_commit..HEAD`` 之间被改动的文件列表。
        """
        cur = self.current_version()
        if cur is None:
            return False
        return any(cur.covers.hits(f) for f in changed)
