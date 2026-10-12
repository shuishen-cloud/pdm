# -*- coding: utf-8 -*-
"""Issue 域：问题记录及其附属类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from .common import Actor
from .fingerprint import Generated


class Status(str, Enum):
    """issue 状态。"""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @property
    def is_terminal(self) -> bool:
        """已结束的状态不再产生动作。"""
        return self in (Status.RESOLVED, Status.CLOSED)


class Priority(str, Enum):
    """issue 优先级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(str, Enum):
    """issue 上的事件类型。"""

    NOTE = "note"              # 本地进展记录
    GH_COMMENT = "gh-comment"  # GitHub 评论回拉
    GH_CLOSE = "gh-close"      # GitHub 关闭
    GH_OPEN = "gh-open"        # GitHub 重新打开
    PUSH = "push"              # 本地推送到 GitHub


class SyncState(str, Enum):
    """本地与远端的同步状态。"""

    SYNCED = "synced"
    DIRTY = "dirty"
    CONFLICT = "conflict"


@dataclass
class Event:
    """issue 上发生的一件事，按时间追加，不修改历史。"""

    at: datetime
    type: EventType
    actor: Actor
    text: str = ""


@dataclass
class GitHubLink:
    """本地 issue 与 GitHub issue 的锚点。"""

    repo: str = ""
    number: int = 0
    etag: str = ""
    last_synced_at: Optional[datetime] = None

    @property
    def url(self) -> str:
        """GitHub issue 的网页地址；信息不全时返回空串。"""
        if not self.repo or not self.number:
            return ""
        return f"https://github.com/{self.repo}/issues/{self.number}"


@dataclass
class Sync:
    """同步游标与状态。"""

    direction: str = "push"  # 目前恒为 push
    state: SyncState = SyncState.SYNCED
    local_rev: int = 0
    remote_rev: int = 0


@dataclass
class Issue:
    """一条本地问题记录（唯一真源）。"""

    id: str
    title: str
    status: Status = Status.OPEN
    priority: Priority = Priority.MEDIUM

    # 溯源
    reporter: Actor = field(default_factory=lambda: Actor("human:unknown"))
    origin_commit: str = ""
    origin_fingerprint: Generated = Generated.HUMAN
    fix_commit: str = ""
    verified_by: Optional[Actor] = None

    # GitHub 锚点（可空）
    external: Optional[GitHubLink] = None
    sync: Sync = field(default_factory=Sync)

    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    body: str = ""
    events: List[Event] = field(default_factory=list)

    # --- 校验 ---

    def validate(self) -> None:
        """检查基本约束，不合格抛 ``ValueError``。"""
        if not self.id.strip():
            raise ValueError("issue: id is required")
        if not self.title.strip():
            raise ValueError(f"issue {self.id}: title is required")

    # --- 派生：溯源 ---

    @property
    def caused_by_ai(self) -> bool:
        """触发该问题的代码是否含 AI 生成成分。"""
        return self.origin_fingerprint.is_ai

    @property
    def reported_by_ai(self) -> bool:
        """该问题是否由 AI 发现。"""
        return self.reporter.is_ai

    # --- 派生：状态流转 ---

    @property
    def open(self) -> bool:
        """问题是否仍打开。"""
        return not self.status.is_terminal

    def add_event(self, event: Event) -> None:
        """追加事件并推进 ``updated_at``（单调，不回退）。"""
        self.events.append(event)
        if self.updated_at is None or event.at > self.updated_at:
            self.updated_at = event.at

    def mark_dirty(self) -> None:
        """标记本地有改动待推送。"""
        self.sync.local_rev += 1
        self.sync.state = SyncState.DIRTY
