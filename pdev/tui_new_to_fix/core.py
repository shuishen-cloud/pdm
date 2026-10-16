# -*- coding: utf-8 -*-
"""新 TUI 的纯函数内核。

**不 import textual**：全部是可单测的纯逻辑，测试毫秒级完成。
所有渲染细节（截断、宽字符、标记、颜色）都在这里，
app 层只负责把这些结果塞进 widget。
"""

from __future__ import annotations

import unicodedata
from typing import Dict, Iterable, List, Optional

from ..note import NoteKind, NoteStatus, VerificationStatus

__all__ = [
    "display_width",
    "ellipsize",
    "kind_counts",
    "KIND_SHORT",
    "KIND_COLOR",
    "STATUS_MARK",
    "VERIFY_MARK",
    "commit_entries",
]

# --- 展示常量（单一来源；颜色用语义名，界面自行转译） ---

KIND_SHORT: Dict[NoteKind, str] = {
    NoteKind.PROBLEM: "pro",
    NoteKind.BUG: "bug",
    NoteKind.PITFALL: "pit",
    NoteKind.DIFFICULTY: "dif",
    NoteKind.CONTROLLED_EXCEPTION: "exc",
}

KIND_COLOR: Dict[NoteKind, str] = {
    NoteKind.PROBLEM: "bright_red",
    NoteKind.BUG: "red",
    NoteKind.PITFALL: "bright_yellow",
    NoteKind.DIFFICULTY: "bright_cyan",
    NoteKind.CONTROLLED_EXCEPTION: "bright_green",
}

STATUS_MARK: Dict[NoteStatus, str] = {
    NoteStatus.OPEN: "○",
    NoteStatus.RESOLVED: "●",
    NoteStatus.NOTED: "·",
}

VERIFY_MARK: Dict[VerificationStatus, str] = {
    VerificationStatus.PASSED: "✓",
    VerificationStatus.FAILED: "✗",
    VerificationStatus.ERROR: "!",
    VerificationStatus.SKIPPED: "-",
    VerificationStatus.UNKNOWN: "·",
}


def display_width(text: str) -> int:
    """近似显示宽度（CJK 算 2 列）。"""
    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def ellipsize(text: str, width: int) -> str:
    """按显示宽度截断，超出用 ``…`` 结尾。

    width <= 0 返回空串；width == 1 只能放下省略号本身。
    """
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    out: List[str] = []
    used = 0
    budget = width - 1                      # 留一列给 …
    for ch in text:
        w = display_width(ch)
        if used + w > budget:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def kind_counts(notes: Iterable) -> Dict[NoteKind, int]:
    """按 kind 计数，键按 ``kind.value`` 排序（稳定输出）。"""
    counts: Dict[NoteKind, int] = {}
    for n in notes:
        counts[n.kind] = counts.get(n.kind, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[0].value))


def commit_entries(notes: List, git_infos: List) -> List[tuple]:
    """把笔记与 git 历史合并成 ``[(commit, notes, info|None), ...]``。

    规则（与旧 TUI 一致，这里显式化以便测试）：

    - 以 git 历史顺序（新→旧）为主，即使没有笔记也保留；
    - 笔记按 hash 前缀互相匹配（7 位短 hash 对 40 位长 hash）；
    - 不在 git 历史里的伪造 hash 追加在末尾，按 hash 倒序。
    """
    order = [info.hash for info in git_infos]
    info_by_hash = {info.hash: info for info in git_infos}
    claimed: set = set()

    def _pick(commit: str, taken: set) -> List:
        """挑出属于 commit 且**尚未被认领**的笔记。

        必须排除已认领的：一条短 hash 笔记可能同时是多个长 hash 的
        前缀，不排除就会被两条提交重复显示。
        """
        return [
            n for n in notes
            if id(n) not in taken
            and (
                n.commit == commit
                or (len(commit) >= 6 and n.commit.startswith(commit))
                or (len(n.commit) >= 6 and commit.startswith(n.commit))
            )
        ]

    entries: List[tuple] = []
    for h in order:
        ns = _pick(h, claimed)
        claimed.update(id(n) for n in ns)
        entries.append((h, ns, info_by_hash[h]))

    extra: Dict[str, List] = {}
    for n in notes:
        if id(n) not in claimed:
            extra.setdefault(n.commit, []).append(n)
    for c in sorted(extra, reverse=True):
        entries.append((c, extra[c], None))
    return entries


def _tail(notes: List, sep: str = "  ") -> tuple:
    """类型分布的 (纯文本, [(片段, 颜色), ...])。"""
    counts = kind_counts(notes)
    if not counts:
        return "无笔记", [("无笔记", "dim italic")]
    parts, spans = [], []
    for i, (kind, n) in enumerate(counts.items()):
        if i:
            parts.append(" ")
            spans.append((" ", ""))
        piece = f"{KIND_SHORT.get(kind, '?')}:{n}"
        parts.append(piece)
        spans.append((piece, KIND_COLOR.get(kind, "white")))
    return " ".join(parts), spans


def commit_line_parts(commit: str, info, notes: List, width: int) -> tuple:
    """提交行拆成可组装的片段，便于纯文本断言。

    返回 ``(hash, subject, tail_text, tail_spans, avail)``。
    """
    hash_part = commit[:8]
    subject = getattr(info, "subject", "") if info is not None else ""
    tail_text, tail_spans = _tail(notes)
    gap = 2
    avail = width - len(hash_part) - gap - display_width(tail_text) - gap
    if subject:
        subject = ellipsize(subject, max(avail, 4))
    return hash_part, subject, tail_text, tail_spans, avail


def note_line_parts(note, width: int) -> tuple:
    """笔记行拆成 ``(mark, kind, title, suffix_text)``。"""
    mark = STATUS_MARK.get(note.status, "·")
    kind = f"[{note.kind.value}] "
    suffix = ""
    if note.verifications:
        suffix += "  " + "".join(
            VERIFY_MARK.get(v.last_status, "?") for v in note.verifications
        )
    if getattr(note, "severity", None):
        suffix += f"  {note.severity.value}"
    prefix_len = display_width(mark) + 1 + display_width(kind)
    avail = width - prefix_len - display_width(suffix) - 2
    return mark, kind, ellipsize(note.title, max(avail, 1)), suffix


def commit_title(commit: str, info, notes: List, width: int) -> str:
    """供测试用的单行纯文本形式（无颜色）。"""
    hash_part, subject, tail, _spans, _avail = commit_line_parts(
        commit, info, notes, width
    )
    head = hash_part
    if subject:
        head += "  " + subject
    return f"{head}  {tail}"
