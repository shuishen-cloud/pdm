# -*- coding: utf-8 -*-
"""pdev.note 中 Verification 的测试。"""

from __future__ import annotations

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStatus
from pdev.note import (
    Verification,
    VerificationKind,
    VerificationStatus,
)
from tests.conftest import at


def test_verification_kind_values():
    assert [k.value for k in VerificationKind] == ["test", "command", "manual"]


def test_verification_status_values():
    assert [s.value for s in VerificationStatus] == [
        "unknown", "passed", "failed", "error", "skipped"
    ]


# ---------------------------------------------------------------------------
# effective_command
# ---------------------------------------------------------------------------


def test_test_kind_builds_pytest_command():
    v = Verification(kind=VerificationKind.TEST, target="tests/x.py::test_y")
    assert v.effective_command == "pytest tests/x.py::test_y -q"
    assert v.runnable


def test_test_kind_command_override():
    v = Verification(kind=VerificationKind.TEST, target="tests/x.py::test_y",
                     command="pytest -k y -vv")
    assert v.effective_command == "pytest -k y -vv"


def test_command_kind_uses_command():
    v = Verification(kind=VerificationKind.COMMAND, command="make check")
    assert v.effective_command == "make check"
    assert v.runnable


def test_manual_kind_not_runnable():
    v = Verification(kind=VerificationKind.MANUAL, note="手动登录三次")
    assert not v.runnable
    assert v.effective_command == ""


def test_empty_command_not_runnable_but_test_kind_is():
    assert Verification(kind=VerificationKind.COMMAND).effective_command == ""


def test_no_target_no_command():
    v = Verification(kind=VerificationKind.TEST)
    assert v.effective_command == ""


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


def test_record_writes_status_and_output():
    v = Verification(kind=VerificationKind.COMMAND, command="true")
    assert v.last_status is VerificationStatus.UNKNOWN
    assert v.last_run_at is None

    v.record(VerificationStatus.PASSED, at(5), "ok")
    assert v.last_status is VerificationStatus.PASSED
    assert v.last_run_at == at(5)
    assert v.last_output == "ok"


# ---------------------------------------------------------------------------
# CommitNote 验证派生属性
# ---------------------------------------------------------------------------


def make_note(**kw) -> CommitNote:
    base = dict(commit="abc123", kind=NoteKind.PITFALL, title="t")
    base.update(kw)
    return CommitNote(**base)


def test_has_and_runnable_verifications():
    assert not make_note().has_verification
    n = make_note(verifications=[
        Verification(kind=VerificationKind.TEST, target="t"),
        Verification(kind=VerificationKind.MANUAL, note="m"),
    ])
    assert n.has_verification
    assert len(n.runnable_verifications) == 1


def test_all_passed():
    passed = Verification(kind=VerificationKind.COMMAND, command="x",
                          last_status=VerificationStatus.PASSED)
    failed = Verification(kind=VerificationKind.COMMAND, command="y",
                          last_status=VerificationStatus.FAILED)
    manual = Verification(kind=VerificationKind.MANUAL, note="m")

    assert make_note(verifications=[passed]).all_passed
    assert make_note(verifications=[passed, manual]).all_passed  # 人工不算
    assert not make_note(verifications=[passed, failed]).all_passed
    assert not make_note().all_passed  # 无验证
    assert not make_note(verifications=[manual]).all_passed  # 仅人工


def test_verification_failed():
    failed = Verification(kind=VerificationKind.COMMAND, command="x",
                          last_status=VerificationStatus.FAILED)
    errored = Verification(kind=VerificationKind.COMMAND, command="y",
                           last_status=VerificationStatus.ERROR)
    passed = Verification(kind=VerificationKind.COMMAND, command="z",
                          last_status=VerificationStatus.PASSED)

    assert make_note(verifications=[failed]).verification_failed
    assert make_note(verifications=[errored]).verification_failed
    assert not make_note(verifications=[passed]).verification_failed


def test_needs_verification():
    # 已解决但无验证 -> 需要
    assert make_note(status=NoteStatus.RESOLVED).needs_verification
    # 缺陷但无验证 -> 需要
    assert make_note(kind=NoteKind.BUG).needs_verification
    # 有验证 -> 不需要
    v = Verification(kind=VerificationKind.TEST, target="t")
    assert not make_note(status=NoteStatus.RESOLVED,
                         verifications=[v]).needs_verification
    # 普通 noted 笔记 -> 不需要
    assert not make_note(kind=NoteKind.DIFFICULTY).needs_verification


def test_verification_method_and_script_fields():
    v = Verification(
        kind=VerificationKind.TEST,
        target="tests/x.py::test_y",
        method="并发下断言只刷新一次",
        script="def test_y():\n    pass\n",
    )
    assert v.method == "并发下断言只刷新一次"
    assert v.script.startswith("def test_y")
