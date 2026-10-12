# -*- coding: utf-8 -*-
"""组合查询层。

``NoteStore`` 提供单条件查询，本模块把它们组合起来（kind + file + status +
全文等），供 TUI 直接调用。空查询返回全部。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .doc import match_glob
from .note import CommitNote, NoteKind, NoteStatus
from .store import NoteStore

__all__ = ["Query", "search"]


@dataclass
class Query:
    """组合查询条件。所有字段为 ``None`` 时表示该维度不筛选。

    ``file`` 支持 gitignore 风格 glob（见 :func:`pdev.doc.match_glob`）。
    ``text`` 对 ``title`` / ``detail`` / ``tags`` 做不区分大小写的子串匹配。
    """

    kind: Optional[NoteKind] = None
    status: Optional[NoteStatus] = None
    file: Optional[str] = None
    tag: Optional[str] = None
    text: Optional[str] = None
    commit: Optional[str] = None
    issue_id: Optional[str] = None
    author: Optional[str] = None            # 匹配 actor kind，如 "ai"
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    limit: Optional[int] = None

    def matches(self, n: CommitNote) -> bool:
        """笔记是否满足全部条件。"""
        if self.kind is not None and n.kind is not self.kind:
            return False
        if self.status is not None and n.status is not self.status:
            return False
        if self.commit is not None and n.commit != self.commit:
            return False
        if self.tag is not None and self.tag not in n.tags:
            return False
        if self.issue_id is not None:
            if n.issue_id != self.issue_id and self.issue_id not in n.resolves:
                return False
        if self.author is not None and n.author.kind != self.author:
            return False
        if self.file is not None and not any(
            match_glob(self.file, f) for f in n.files
        ):
            return False
        if self.text is not None and not self._text_hit(n):
            return False
        if self.since is not None:
            if n.created_at is None or n.created_at < self.since:
                return False
        if self.until is not None:
            if n.created_at is None or n.created_at > self.until:
                return False
        return True

    def _text_hit(self, n: CommitNote) -> bool:
        needle = self.text.lower()
        haystack = " ".join(
            [n.title, n.detail, *n.tags, *n.catches]
        ).lower()
        return needle in haystack


def search(store: NoteStore, q: Query) -> List[CommitNote]:
    """按条件过滤，按 created_at 降序（新→旧），无时间则排最后。

    :param store: 笔记存储。
    :param q: 查询条件。
    """
    hits = [n for n in store.all() if q.matches(n)]
    hits.sort(key=_sort_key, reverse=True)
    if q.limit is not None and q.limit >= 0:
        hits = hits[: q.limit]
    return hits


def _sort_key(n: CommitNote):
    # 有时间的按时间排；无时间排到最后
    if n.created_at is not None:
        return (1, n.created_at.timestamp())
    return (0, 0.0)
