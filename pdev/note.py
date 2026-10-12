# -*- coding: utf-8 -*-
"""提交笔记域：每次提交中沉淀的问题 / 难点 / 易错点 / 异常。

笔记是"记录"，Issue 是"流程"，Doc 是"快照"。
一条笔记可以升级为 Issue（``issue_id``），也可以标记它解决了某些 Issue（``resolves``）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from .common import Actor
from .issue import Priority


class NoteKind(str, Enum):
    """笔记类型。

    问题面（资产）：描述这次开发中遇到的阻力。
    负债面（要追踪）：描述不该发生、必须修复的缺陷。
    """

    PROBLEM = "problem"        # 问题
    DIFFICULTY = "difficulty"  # 难点
    PITFALL = "pitfall"        # 易错点
    CONTROLLED_EXCEPTION = "controlled-exception"  # 可控异常（已捕获，资产）
    BUG = "bug"                # 缺陷（不该发生，负债）

    @property
    def is_debt(self) -> bool:
        """是否属于“负债”（需限期修复）。"""
        return self is NoteKind.BUG

    @property
    def is_asset(self) -> bool:
        """是否属于“资产”（沉淀的领域知识）。"""
        return not self.is_debt


class NoteStatus(str, Enum):
    """笔记自身的状态。"""

    OPEN = "open"          # 还没解决
    RESOLVED = "resolved"  # 已解决
    NOTED = "noted"        # 只是记一笔，无需解决


class VerificationKind(str, Enum):
    """验证方式。"""

    TEST = "test"        # 绑定测试用例
    COMMAND = "command"  # 任意命令（构建、类型检查、压测）
    MANUAL = "manual"    # 人工步骤，无法自动执行


class VerificationStatus(str, Enum):
    """上次验证的结果。"""

    UNKNOWN = "unknown"  # 从未跑过
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"      # 命令本身出错（如未找到）
    SKIPPED = "skipped"  # 人工验证，未执行


@dataclass
class Verification:
    """一条可执行的验证。

    - ``test``：绑定测试用例（``target`` 如 ``tests/x.py::test_y``），
      执行时拼成 ``pytest <target>``，也可用 ``command`` 覆盖。
    - ``command``：直接跑 ``command``。
    - ``manual``：只记录人工步骤，不自动执行。
    """

    kind: VerificationKind
    target: str = ""     # test 的用例标识，或 command 的简述
    command: str = ""    # 可执行命令（test 可省略，自动拼）
    method: str = ""     # 验证思路（人写的一句话）
    script: str = ""     # 内联脚本，优先于从 target 抽取
    expected: str = ""   # 期望结果说明，如 "passed" / 退出码 0
    note: str = ""       # 补充说明
    cwd: str = ""        # 工作目录（相对 git.repo）

    # 执行状态（由 verify run 回写）
    last_run_at: Optional[datetime] = None
    last_status: VerificationStatus = VerificationStatus.UNKNOWN
    last_output: str = ""

    @property
    def runnable(self) -> bool:
        """是否可自动执行。"""
        return self.kind is not VerificationKind.MANUAL

    @property
    def effective_command(self) -> str:
        """实际要执行的命令。test 未指定 command 时自动拼 pytest。"""
        if self.command:
            return self.command
        if self.kind is VerificationKind.TEST and self.target:
            return f"pytest {self.target} -q"
        return ""

    def record(
        self,
        status: VerificationStatus,
        at: datetime,
        output: str = "",
    ) -> None:
        """回写一次执行结果。"""
        self.last_status = status
        self.last_run_at = at
        self.last_output = output


@dataclass
class CommitNote:
    """挂在某个 commit 上的一条开发笔记。"""

    commit: str
    kind: NoteKind
    title: str
    detail: str = ""
    author: Actor = field(default_factory=lambda: Actor("human:unknown"))
    files: List[str] = field(default_factory=list)
    severity: Optional[Priority] = None
    status: NoteStatus = NoteStatus.NOTED

    # 可控异常专用：被捕获的异常类型，如 ["TimeoutError", "ConnectionError"]
    catches: List[str] = field(default_factory=list)

    # 验证方法（与测试/命令绑定）
    verifications: List[Verification] = field(default_factory=list)

    # 与 Issue 的关联
    issue_id: Optional[str] = None        # 该笔记升级成的 Issue
    resolves: List[str] = field(default_factory=list)  # 该笔记解决了哪些 Issue

    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    # --- 校验 ---

    def validate(self) -> None:
        """检查基本约束，不合格抛 ``ValueError``。"""
        if not self.commit.strip():
            raise ValueError("note: commit is required")
        if not self.title.strip():
            raise ValueError("note: title is required")

    # --- 派生 ---

    @property
    def promotes_issue(self) -> bool:
        """该笔记是否已升级为 Issue。"""
        return bool(self.issue_id)

    @property
    def resolves_issue(self) -> bool:
        """该笔记是否解决了某个 Issue。"""
        return bool(self.resolves)

    @property
    def unresolved(self) -> bool:
        """是否仍未解决（open 且没有升级为 Issue）。"""
        return self.status is NoteStatus.OPEN

    @property
    def written_by_ai(self) -> bool:
        """笔记是否由 AI 撰写。"""
        return self.author.is_ai

    @property
    def is_controlled_exception(self) -> bool:
        """是否为可控异常（已捕获的异常）。"""
        return self.kind is NoteKind.CONTROLLED_EXCEPTION

    @property
    def is_bug(self) -> bool:
        """是否为缺陷。"""
        return self.kind is NoteKind.BUG

    # --- 派生：验证 ---

    @property
    def has_verification(self) -> bool:
        """是否登记了验证方法。"""
        return bool(self.verifications)

    @property
    def runnable_verifications(self) -> List[Verification]:
        """可自动执行的验证。"""
        return [v for v in self.verifications if v.runnable]

    @property
    def all_passed(self) -> bool:
        """所有可执行验证均通过（且至少有一条）。"""
        runnable = self.runnable_verifications
        return bool(runnable) and all(
            v.last_status is VerificationStatus.PASSED for v in runnable
        )

    @property
    def verification_failed(self) -> bool:
        """是否有失败/出错的验证。"""
        return any(
            v.last_status in (VerificationStatus.FAILED, VerificationStatus.ERROR)
            for v in self.verifications
        )

    @property
    def needs_verification(self) -> bool:
        """需要验证却没有验证方法（已解决/已修但无验证）。"""
        if self.verifications:
            return False
        return self.status is NoteStatus.RESOLVED or self.is_bug

    @property
    def risky(self) -> bool:
        """是否构成风险项。

        - 缺陷：未解决即风险（负债未还）。
        - 其他：未解决且从未升级为 Issue 才算风险。
        """
        if self.is_bug:
            return self.status is not NoteStatus.RESOLVED
        return self.status is NoteStatus.OPEN and self.issue_id is None
