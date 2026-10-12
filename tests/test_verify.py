# -*- coding: utf-8 -*-
"""pdev.verify 执行器的测试（不依赖真实外部命令）。"""

from __future__ import annotations

import sys

from pdev import CommitNote, NoteKind, Verification, VerificationKind
from pdev.note import VerificationStatus
from pdev.verify import (
    pick_notes,
    run_note,
    run_verification,
    summarize_output,
)

PY = sys.executable


def cmd(command: str) -> Verification:
    return Verification(kind=VerificationKind.COMMAND, command=command)


# ---------------------------------------------------------------------------
# summarize_output
# ---------------------------------------------------------------------------


def test_summarize_short_unchanged():
    assert summarize_output("hello") == "hello"


def test_summarize_strips_whitespace():
    assert summarize_output("  hi  \n") == "hi"


def test_summarize_truncates_keeping_tail():
    text = "A" * 5000 + "TAIL"
    out = summarize_output(text, limit=100)
    assert out.endswith("TAIL")
    assert "前部省略" in out


# ---------------------------------------------------------------------------
# run_verification
# ---------------------------------------------------------------------------


def test_run_passing_command():
    r = run_verification(cmd(f'{PY} -c "print(1)"'))
    assert r.status is VerificationStatus.PASSED
    assert r.ok
    assert "1" in r.output


def test_run_failing_command():
    r = run_verification(cmd(f'{PY} -c "import sys; sys.exit(3)"'))
    assert r.status is VerificationStatus.FAILED
    assert not r.ok


def test_run_captures_stderr():
    r = run_verification(cmd(f'{PY} -c "import sys; print(\'boom\', file=sys.stderr)"'))
    assert "boom" in r.output


def test_run_manual_is_skipped():
    v = Verification(kind=VerificationKind.MANUAL, note="手动")
    r = run_verification(v)
    assert r.skipped
    assert r.status is VerificationStatus.SKIPPED


def test_run_empty_command_is_error():
    r = run_verification(Verification(kind=VerificationKind.COMMAND))
    assert r.status is VerificationStatus.ERROR
    assert "无可执行命令" in r.output


def test_run_timeout_is_error():
    r = run_verification(cmd(f'{PY} -c "import time; time.sleep(5)"'), timeout=1)
    assert r.status is VerificationStatus.ERROR
    assert "超时" in r.output


def test_run_does_not_mutate_verification():
    v = cmd("true")
    run_verification(v)
    assert v.last_status is VerificationStatus.UNKNOWN


# ---------------------------------------------------------------------------
# run_note
# ---------------------------------------------------------------------------


def make_note(*verifications) -> CommitNote:
    return CommitNote(
        commit="c1", kind=NoteKind.BUG, title="t",
        verifications=list(verifications),
    )


def test_run_note_writes_back_results():
    note = make_note(cmd(f'{PY} -c "print(1)"'),
                     cmd(f'{PY} -c "import sys; sys.exit(1)"'))
    results = run_note(note)
    assert len(results) == 2
    assert note.verifications[0].last_status is VerificationStatus.PASSED
    assert note.verifications[1].last_status is VerificationStatus.FAILED
    assert note.verifications[0].last_run_at is not None


def test_run_note_skips_manual_by_default():
    manual = Verification(kind=VerificationKind.MANUAL, note="m")
    note = make_note(cmd("true"), manual)
    results = run_note(note)
    assert len(results) == 1
    assert manual.last_status is VerificationStatus.UNKNOWN  # 未被回写


def test_run_note_only_runnable_false_includes_manual():
    manual = Verification(kind=VerificationKind.MANUAL, note="m")
    note = make_note(manual)
    results = run_note(note, only_runnable=False)
    assert len(results) == 1
    assert results[0].skipped


# ---------------------------------------------------------------------------
# pick_notes
# ---------------------------------------------------------------------------


def test_pick_notes_by_commit():
    a = CommitNote(commit="a", kind=NoteKind.BUG, title="t",
                   verifications=[cmd("true")])
    b = CommitNote(commit="b", kind=NoteKind.BUG, title="t",
                   verifications=[cmd("true")])
    assert pick_notes([a, b], commit="a") == [a]


def test_pick_notes_by_status():
    passed = cmd("true")
    passed.last_status = VerificationStatus.PASSED
    failed = cmd("false")
    failed.last_status = VerificationStatus.FAILED
    a = CommitNote(commit="a", kind=NoteKind.BUG, title="t", verifications=[passed])
    b = CommitNote(commit="b", kind=NoteKind.BUG, title="t", verifications=[failed])
    assert pick_notes([a, b], status=VerificationStatus.FAILED) == [b]


def test_pick_notes_by_target():
    a = CommitNote(commit="a", kind=NoteKind.BUG, title="t",
                   verifications=[Verification(kind=VerificationKind.TEST,
                                               target="tests/x.py::test_y")])
    b = CommitNote(commit="b", kind=NoteKind.BUG, title="t",
                   verifications=[cmd("make check")])
    assert pick_notes([a, b], target="test_y") == [a]
    assert pick_notes([a, b], target="make") == [b]


def test_pick_notes_excludes_notes_without_runnable():
    manual = Verification(kind=VerificationKind.MANUAL, note="m")
    a = CommitNote(commit="a", kind=NoteKind.BUG, title="t", verifications=[manual])
    assert pick_notes([a]) == []
