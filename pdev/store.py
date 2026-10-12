# -*- coding: utf-8 -*-
"""笔记持久化与索引。

存储布局::

    <root>/
    ├── index.json              # 派生缓存，可 rebuild
    └── by-commit/
        └── <commit>.json       # 一个 commit 一个文件，含该 commit 的全部笔记

一 commit 一文件的好处：写入原子、commit 即索引键、与 git 的 by-commit 查询对齐。
``index.json`` 是缓存，丢失可用 :meth:`NoteStore.rebuild_index` 重建。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Union

from .common import Actor
from .issue import Priority
from .note import (
    CommitNote,
    NoteKind,
    NoteStatus,
    Verification,
    VerificationKind,
    VerificationStatus,
)

__all__ = ["NoteStore"]

_INDEX = "index.json"
_BY_COMMIT = "by-commit"


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _verification_to_dict(v: Verification) -> dict:
    """验证 -> 可 JSON 化的 dict。"""
    d = asdict(v)
    d["kind"] = v.kind.value
    d["last_status"] = v.last_status.value
    d["last_run_at"] = v.last_run_at.isoformat() if v.last_run_at else None
    return d


def _verification_from_dict(d: dict) -> Verification:
    """dict -> 验证。"""
    ran = d.get("last_run_at")
    return Verification(
        kind=VerificationKind(d["kind"]),
        target=d.get("target", ""),
        command=d.get("command", ""),
        method=d.get("method", ""),
        script=d.get("script", ""),
        expected=d.get("expected", ""),
        note=d.get("note", ""),
        cwd=d.get("cwd", ""),
        last_run_at=datetime.fromisoformat(ran) if ran else None,
        last_status=VerificationStatus(d.get("last_status", "unknown")),
        last_output=d.get("last_output", ""),
    )


def _note_to_dict(n: CommitNote) -> dict:
    """笔记 -> 可 JSON 化的 dict。"""
    d = asdict(n)
    d["kind"] = n.kind.value
    d["status"] = n.status.value
    d["author"] = str(n.author)
    d["severity"] = n.severity.value if n.severity else None
    d["created_at"] = n.created_at.isoformat() if n.created_at else None
    d["verifications"] = [_verification_to_dict(v) for v in n.verifications]
    return d


def _note_from_dict(d: dict) -> CommitNote:
    """dict -> 笔记。"""
    created = d.get("created_at")
    severity = d.get("severity")
    return CommitNote(
        commit=d["commit"],
        kind=NoteKind(d["kind"]),
        title=d["title"],
        detail=d.get("detail", ""),
        author=Actor(d["author"]),
        files=list(d.get("files", [])),
        severity=Priority(severity) if severity else None,
        status=NoteStatus(d["status"]),
        catches=list(d.get("catches", [])),
        verifications=[
            _verification_from_dict(v) for v in d.get("verifications", [])
        ],
        issue_id=d.get("issue_id"),
        resolves=list(d.get("resolves", [])),
        tags=list(d.get("tags", [])),
        created_at=datetime.fromisoformat(created) if created else None,
    )


class NoteStore:
    """笔记的读写与索引。

    每次 :meth:`add` 立即落盘（一 commit 一文件），并同步更新内存索引。
    """

    def __init__(self, root: Union[str, Path]) -> None:
        self.root = Path(root)
        self._dir = self.root / _BY_COMMIT
        self._dir.mkdir(parents=True, exist_ok=True)
        self._notes: List[CommitNote] = []
        self._load()

    # --- 读 ---

    def _load(self) -> None:
        """从磁盘加载全部笔记到内存。"""
        self._notes = []
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for d in data.get("notes", []):
                self._notes.append(_note_from_dict(d))

    def _path(self, commit: str) -> Path:
        return self._dir / f"{commit}.json"

    def all(self) -> Iterator[CommitNote]:
        """全部笔记。"""
        return iter(list(self._notes))

    def __len__(self) -> int:
        return len(self._notes)

    # --- 写 ---

    def add(self, note: CommitNote) -> None:
        """追加一条笔记并立即落盘。"""
        note.validate()
        self._notes.append(note)
        self._flush_commit(note.commit)
        self.rebuild_index()

    def add_many(self, notes: Iterable[CommitNote]) -> None:
        """批量追加，按 commit 分组落盘。"""
        notes = list(notes)
        for n in notes:
            n.validate()
        self._notes.extend(notes)
        for commit in {n.commit for n in notes}:
            self._flush_commit(commit)
        self.rebuild_index()

    def _flush_commit(self, commit: str) -> None:
        """把某 commit 的全部笔记写成一个文件。"""
        data = {
            "commit": commit,
            "notes": [
                _note_to_dict(n) for n in self._notes if n.commit == commit
            ],
        }
        self._path(commit).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def rebuild_index(self) -> None:
        """重建 ``index.json``（派生缓存，可随时重建）。"""
        index = {
            "count": len(self._notes),
            "by_kind": self._counter(lambda n: n.kind.value),
            "by_status": self._counter(lambda n: n.status.value),
            "by_issue": self._counter(
                lambda n: n.issue_id, skip_none=True
            ),
            "commits": sorted({n.commit for n in self._notes}),
        }
        (self.root / _INDEX).write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _counter(self, key, skip_none: bool = False) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for n in self._notes:
            k = key(n)
            if k is None and skip_none:
                continue
            if k is None:
                continue
            out[k] = out.get(k, 0) + 1
        return out

    # --- 单条件查询 ---

    def by_commit(self, commit: str) -> List[CommitNote]:
        """某次提交的全部笔记。"""
        return [n for n in self._notes if n.commit == commit]

    def by_kind(self, kind: NoteKind) -> List[CommitNote]:
        """按类型筛选。"""
        return [n for n in self._notes if n.kind is kind]

    def by_status(self, status: NoteStatus) -> List[CommitNote]:
        """按状态筛选。"""
        return [n for n in self._notes if n.status is status]

    def by_issue(self, issue_id: str) -> List[CommitNote]:
        """与某 Issue 相关的笔记（升级、或解决了它）。"""
        return [
            n for n in self._notes
            if n.issue_id == issue_id or issue_id in n.resolves
        ]

    def by_tag(self, tag: str) -> List[CommitNote]:
        """按标签筛选。"""
        return [n for n in self._notes if tag in n.tags]

    def by_file(self, path: str) -> List[CommitNote]:
        """按文件筛选（精确匹配，glob 交给 query 层）。"""
        return [n for n in self._notes if path in n.files]

    # --- 验证相关 ---

    def with_verifications(self) -> List[CommitNote]:
        """所有登记了验证方法的笔记。"""
        return [n for n in self._notes if n.verifications]

    def needing_verification(self) -> List[CommitNote]:
        """需要验证但未登记验证方法的笔记。"""
        return [n for n in self._notes if n.needs_verification]

    def get(self, index: int) -> Optional[CommitNote]:
        """按下标取（按追加顺序）。"""
        if 0 <= index < len(self._notes):
            return self._notes[index]
        return None

    # --- 回写 ---

    def update(self, note: CommitNote) -> bool:
        """用同 commit + title 定位并替换一条笔记，落盘后返回是否命中。

        用于回写验证执行结果等会后修改的场景。
        """
        for i, existing in enumerate(self._notes):
            if existing.commit == note.commit and existing.title == note.title:
                self._notes[i] = note
                self._flush_commit(note.commit)
                self.rebuild_index()
                return True
        return False

    def flush(self) -> None:
        """把内存中的全部笔记重新落盘（批量修改后调用）。"""
        for commit in {n.commit for n in self._notes}:
            self._flush_commit(commit)
        self.rebuild_index()
