# -*- coding: utf-8 -*-
"""Feat 视图内核：设计正文读取 + 笔记聚合。

CLI 与 TUI 共享的纯函数，**不依赖 textual**，保证 CLI 零依赖。

- :func:`read_doc_body`  读设计文档正文（相对 ``doc.dir``）
- :func:`notes_for_feat` 聚合某 feat 关联 commit 上的笔记
- :func:`group_notes_by_kind` 笔记按 kind 分组

设计见 ``.pdm/docs/feat/feat-cli-parity.md``。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

__all__ = [
    "read_doc_body",
    "notes_for_feat",
    "group_notes_by_kind",
    "DEFAULT_DOC_DIR",
]

DEFAULT_DOC_DIR = ".pdm/docs"


def read_doc_body(doc_dir: str, feat_doc: str, max_lines: int = 0) -> str:
    """读设计文档正文（相对 ``doc.dir`` 解析）。

    - ``feat_doc`` 为空 → ``""``
    - 文件不存在 / 读取失败 → ``"（设计文档不可读）"``
    - ``max_lines > 0`` → 截断并提示
    """
    if not feat_doc:
        return ""
    from .config import resolve_doc_path

    root = doc_dir or DEFAULT_DOC_DIR
    path = Path(resolve_doc_path(root, feat_doc))
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "（设计文档不可读）"
    lines = text.splitlines()
    if max_lines and len(lines) > max_lines:
        kept = lines[:max_lines]
        kept.append(f"…（已截断，共 {len(lines)} 行）")
        return "\n".join(kept)
    return text


def notes_for_feat(feat, note_store) -> list:
    """该 feat 关联 commit 上的全部笔记。

    匹配规则：完全相等，或一方是另一方的 hash 前缀（至少 6 位），
    避免短串误匹配。
    """
    if note_store is None:
        return []
    wanted = [c for c in feat.commits if c]
    out = []
    for n in note_store.all():
        nc = n.commit or ""
        if not nc:
            continue
        for c in wanted:
            if nc == c:
                out.append(n)
                break
            if len(c) >= 6 and nc.startswith(c):
                out.append(n)
                break
            if len(nc) >= 6 and c.startswith(nc):
                out.append(n)
                break
    return out


def group_notes_by_kind(notes) -> List[Tuple[str, list]]:
    """把笔记按 kind 分组，保持 kind 首次出现顺序。

    返回 ``[(kind_value, [note, ...]), ...]``。
    """
    order: List[str] = []
    buckets: dict = {}
    for n in notes:
        k = n.kind.value
        if k not in buckets:
            buckets[k] = []
            order.append(k)
        buckets[k].append(n)
    return [(k, buckets[k]) for k in order]
