# -*- coding: utf-8 -*-
"""验证执行器：跑验证命令并回写结果。

只负责“执行 + 记录”，不改数据结构的其他部分。
实际跑命令的入口是 :func:`run_verification`，便于测试时替换。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

from .note import CommitNote, Verification, VerificationKind, VerificationStatus

__all__ = [
    "RunResult",
    "run_verification",
    "run_note",
    "pick_notes",
    "summarize_output",
]

_MAX_OUTPUT = 2000  # 落盘时保留的输出上限


@dataclass
class RunResult:
    """一次命令执行的结果。"""

    verification: Verification
    status: VerificationStatus
    output: str = ""
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.status is VerificationStatus.PASSED


def summarize_output(output: str, limit: int = _MAX_OUTPUT) -> str:
    """截断过长输出，保留尾部（错误通常在最末）。"""
    output = output.strip()
    if len(output) <= limit:
        return output
    return "…(前部省略)…\n" + output[-limit:]


def run_verification(
    v: Verification,
    *,
    cwd: Optional[str] = None,
    timeout: int = 600,
) -> RunResult:
    """执行一条验证并返回结果（不修改入参）。

    - ``manual``：跳过，标记为 SKIPPED。
    - 无有效命令：标记为 ERROR。
    - 退出码 0 -> PASSED，非 0 -> FAILED，超时/未找到 -> ERROR。
    """
    if v.kind is VerificationKind.MANUAL:
        return RunResult(v, VerificationStatus.SKIPPED, skipped=True)

    command = v.effective_command
    if not command:
        return RunResult(v, VerificationStatus.ERROR, output="无可执行命令")

    workdir = cwd or v.cwd or None
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            v, VerificationStatus.ERROR,
            output=f"超时（>{timeout}s）",
        )
    except FileNotFoundError as e:
        return RunResult(v, VerificationStatus.ERROR, output=str(e))

    output = summarize_output((proc.stdout or "") + (proc.stderr or ""))
    status = (
        VerificationStatus.PASSED if proc.returncode == 0
        else VerificationStatus.FAILED
    )
    return RunResult(v, status, output=output)


def run_note(
    note: CommitNote,
    *,
    cwd: Optional[str] = None,
    timeout: int = 600,
    only_runnable: bool = True,
) -> List[RunResult]:
    """执行一条笔记的全部验证，并把结果回写到 ``note``。

    :returns: 每条验证的执行结果。
    """
    targets = note.runnable_verifications if only_runnable else note.verifications
    results: List[RunResult] = []
    now = datetime.now().astimezone()
    for v in targets:
        result = run_verification(v, cwd=cwd, timeout=timeout)
        if not result.skipped:
            v.record(result.status, now, result.output)
        results.append(result)
    return results


def pick_notes(
    notes: Sequence[CommitNote],
    *,
    commit: Optional[str] = None,
    status: Optional[VerificationStatus] = None,
    target: Optional[str] = None,
) -> List[CommitNote]:
    """按条件筛选要执行的笔记。"""
    out = []
    for n in notes:
        if commit is not None and n.commit != commit:
            continue
        if target is not None and not any(
            target in v.target or target in v.command for v in n.verifications
        ):
            continue
        if status is not None and not any(
            v.last_status is status for v in n.verifications
        ):
            continue
        if not n.runnable_verifications:
            continue
        out.append(n)
    return out
