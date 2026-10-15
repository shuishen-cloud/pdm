# -*- coding: utf-8 -*-
"""任务级门面（见 doc/feat/oop-refactor.md）。

把 ``NoteStore`` / ``FeatStore`` / ``NoteKind`` 等**内部结构**藏在后面，
只暴露"要干什么"：

    from pdev.api import open_ledger

    ledger = open_ledger()
    ledger.record(commit="abc1234", kind="pitfall", title="并发竞态")
    ledger.features.new(slug="token-cache", title="token 缓存")
    ledger.overview()

设计约束：

- 门面**只暴露任务级方法**，不暴露 Store / Enum / 裸 dataclass。
- **不破坏现有 CLI** —— 门面是**新增**，不是替换。
- 门面内部**只调用现有内核算**，不新写逻辑。
- ``kind`` 接受普通字符串（内部转 ``NoteKind``）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from .common import Actor
from .feat import Feat, FeatStore
from .note import CommitNote, NoteKind, NoteStatus
from .stats import NoteStats, compute_note_stats
from .store import NoteStore

__all__ = ["Ledger", "FeatureAPI", "open_ledger"]


class FeatureAPI:
    """feat 相关任务级操作（``ledger.features``）。"""

    def __init__(self, store: FeatStore) -> None:
        self._store = store

    def new(self, slug: str, title: str, **fields: Any) -> Feat:
        """新建一条 feat；``fields`` 透传给 :class:`~pdev.feat.Feat`。"""
        feat = Feat(slug=slug, title=title, **fields)
        self._store.add(feat)
        return feat

    def get(self, slug: str) -> Optional[Feat]:
        """取一条 feat；不存在返回 ``None``。"""
        return self._store.get(slug)

    def list(self) -> List[Feat]:
        """全部 feat（新→旧）。"""
        return list(self._store.all())

    def open(self) -> List[Feat]:
        """未关闭的 feat。"""
        return self._store.open()


class Ledger:
    """任务级门面：一个入口，完成"记笔记 / 管 feat / 看总览"。

    内部持有 ``NoteStore`` 与 ``FeatStore``，但不对外暴露。
    """

    def __init__(self, root: str = ".pdm", cwd: str = ".") -> None:
        self._root = Path(root)
        self._cwd = Path(cwd)
        if not self._root.is_absolute():
            self._root = self._cwd / self._root
        self._notes = NoteStore(self._root / "notes")
        self._feats = FeatStore(self._root / "feats")
        self._features = FeatureAPI(self._feats)

    # --- 笔记 ---

    def record(self, *, commit: str, kind: str, title: str,
               detail: str = "", by: str = "",
               files: Optional[List[str]] = None,
               tags: Optional[List[str]] = None,
               **extra: Any) -> CommitNote:
        """记一条笔记。``kind`` 接受普通字符串（如 ``"pitfall"``）。"""
        note = CommitNote(
            commit=commit,
            kind=NoteKind(kind) if not isinstance(kind, NoteKind) else kind,
            title=title,
            detail=detail,
            author=Actor(by or "human:unknown"),
            files=list(files or []),
            tags=list(tags or []),
            status=extra.pop("status", NoteStatus.NOTED),
            **extra,
        )
        self._notes.add(note)
        return note

    def notes(self) -> List[CommitNote]:
        """全部笔记。"""
        return list(self._notes.all())

    def notes_of(self, commit: str) -> List[CommitNote]:
        """某次提交的全部笔记。"""
        return self._notes.by_commit(commit)

    # --- feat ---

    @property
    def features(self) -> FeatureAPI:
        """feat 操作入口。"""
        return self._features

    # --- 总览 ---

    def overview(self) -> NoteStats:
        """笔记总览统计。"""
        return compute_note_stats(self._notes)


def open_ledger(root: str = ".pdm", cwd: str = ".") -> Ledger:
    """打开一个账本（任务级入口）。"""
    return Ledger(root=root, cwd=cwd)
