# -*- coding: utf-8 -*-
"""新 TUI 的纯函数测试。

**不 import textual**，毫秒级完成，进默认 CI。
"""

from __future__ import annotations

import time

from pdev.note import (  # noqa: E402
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    Verification,
    VerificationKind,
    VerificationStatus,
)
from pdev.tui_new_to_fix import core  # noqa: E402


class _Info:
    """伪造的 CommitInfo。"""

    def __init__(self, h: str, subject: str = "") -> None:
        self.hash = h
        self.subject = subject


def _note(commit="aaa1111", kind=NoteKind.BUG, title="t", status=NoteStatus.OPEN):
    return CommitNote(commit=commit, kind=kind, title=title, status=status,
                      author=Actor("human:test"))


# --- 显示宽度 ---------------------------------------------------------------


def test_display_width_ascii():
    assert core.display_width("abc") == 3


def test_display_width_cjk():
    assert core.display_width("中文") == 4


def test_display_width_mixed():
    assert core.display_width("a中b") == 4


# --- 截断 -------------------------------------------------------------------


def test_ellipsize_short_untouched():
    assert core.ellipsize("abc", 10) == "abc"


def test_ellipsize_exact_fit():
    assert core.ellipsize("abcd", 4) == "abcd"


def test_ellipsize_adds_marker():
    out = core.ellipsize("abcdef", 4)
    assert out.endswith("…")
    assert core.display_width(out) <= 4


def test_ellipsize_never_splits_wide_char():
    out = core.ellipsize("中文中文", 5)
    assert core.display_width(out) <= 5
    assert out.endswith("…")


def test_ellipsize_degenerate_widths():
    assert core.ellipsize("abc", 0) == ""
    assert core.ellipsize("abc", -1) == ""
    assert core.ellipsize("abc", 1) == "…"


# --- 计数 -------------------------------------------------------------------


def test_kind_counts_sorted_by_value():
    notes = [_note(kind=NoteKind.BUG), _note(kind=NoteKind.PROBLEM),
             _note(kind=NoteKind.BUG)]
    counts = core.kind_counts(notes)
    assert list(counts) == [NoteKind.BUG, NoteKind.PROBLEM]   # bug < problem
    assert counts[NoteKind.BUG] == 2


def test_kind_counts_empty():
    assert core.kind_counts([]) == {}


# --- 合并 git 历史与笔记 ----------------------------------------------------


def test_commit_entries_projects_git_order():
    notes = [_note(commit="bbb2222")]
    infos = [_Info("bbb2222b" + "0" * 32), _Info("aaa1111a" + "0" * 32)]
    entries = core.commit_entries(notes, infos)
    assert [e[0] for e in entries] == [infos[0].hash, infos[1].hash]
    assert entries[0][1][0].commit == "bbb2222"      # 前缀匹配命中
    assert entries[1][1] == []                        # 无笔记也保留


def test_commit_entries_keeps_unknown_hashes():
    notes = [_note(commit="c0ffee1")]
    entries = core.commit_entries(notes, [])
    assert [e[0] for e in entries] == ["c0ffee1"]
    assert entries[0][2] is None


def test_commit_entries_no_double_claim():
    """同一笔记只能被一条提交认领。"""
    notes = [_note(commit="aaa1111")]
    infos = [_Info("aaa1111" + "0" * 33)]
    entries = core.commit_entries(notes, infos)
    total = sum(len(e[1]) for e in entries)
    assert total == 1


def test_commit_entries_ambiguous_prefix_claimed_once():
    """短 hash 同时是**多条**提交的前缀时，只能认领一次。

    曾经每条提交都从头扫全部笔记，导致同一条笔记在两条提交里
    各显示一次。
    """
    notes = [_note(commit="abc123")]
    infos = [_Info("abc1234" + "0" * 33), _Info("abc1235" + "0" * 33)]
    entries = core.commit_entries(notes, infos)
    assert sum(len(e[1]) for e in entries) == 1
    # 按 git 顺序（新→旧）归属第一条
    assert entries[0][1] and not entries[1][1]


# --- 行渲染 -----------------------------------------------------------------


def test_commit_title_without_notes():
    line = core.commit_title("abc12345", _Info("abc12345", "feat: x"), [], 80)
    assert line.startswith("abc12345")
    assert "feat: x" in line
    assert "无笔记" in line


def test_commit_title_respects_width():
    line = core.commit_title("abc12345", _Info("abc12345", "x" * 200),
                             [_note()], 40)
    assert core.display_width(line) <= 40


def test_note_line_parts_marks():
    v = Verification(kind=VerificationKind.COMMAND, command="true")
    v.last_status = VerificationStatus.PASSED
    n = _note(status=NoteStatus.RESOLVED)
    n.verifications.append(v)
    mark, kind, title, suffix = core.note_line_parts(n, 60)
    assert mark == "●"
    assert kind == "[bug] "
    assert "✓" in suffix


def test_note_line_parts_truncates_title():
    n = _note(title="中" * 100)
    _m, _k, title, _s = core.note_line_parts(n, 20)
    assert core.display_width("● [bug] " + title) <= 20


# --- 时间预算 ---------------------------------------------------------------


def test_core_suite_is_fast():
    """本文件的断言应为微秒级；这里给 0.2s 的宽松上限防回归。"""
    start = time.perf_counter()
    for _ in range(100):
        core.ellipsize("中文中文中文", 8)
        core.kind_counts([_note()])
    assert time.perf_counter() - start < 0.2
