# -*- coding: utf-8 -*-
"""ProjectDevelopManager 核心数据结构。

三个数据域各有分工，通过字段直接关联（无需额外的关系层）：

- :mod:`pdev.fingerprint` 代码来源指纹（commit 层）
- :mod:`pdev.note`        开发笔记（问题/难点/易错点/异常，commit 层）
- :mod:`pdev.issue`       问题流程（工作项层）
- :mod:`pdev.doc`         文档版本快照（模块层）

支撑模块：

- :mod:`pdev.common`      跨域共享类型（Actor、utcnow）
- :mod:`pdev.store`       笔记持久化与索引
- :mod:`pdev.query`       组合查询
- :mod:`pdev.stats`       派生统计
"""

from __future__ import annotations

from datetime import datetime, timezone

from .common import Actor
from .config import (
    Config,
    ConfigError,
    DocConfig,
    GitHubConfig,
    GitConfig,
    IssueConfig,
    NoteConfig,
    QueryConfig,
    find_project_config,
    load_config,
)
from .doc import (
    Cover,
    Manifest,
    Trigger,
    Version,
    VersionStatus,
    match_glob,
)
from .fingerprint import Fingerprint, Generated
from .issue import (
    Event,
    EventType,
    GitHubLink,
    Issue,
    Priority,
    Status,
    Sync,
    SyncState,
)
from .note import (
    CommitNote,
    NoteKind,
    NoteStatus,
    Verification,
    VerificationKind,
    VerificationStatus,
)
from .query import Query, search
from .stats import NoteStats, Stats, compute_note_stats, compute_stats
from .store import NoteStore
from .scripts import ScriptResult, extract_script, parse_target
from .verify import (
    RunResult,
    pick_notes,
    run_note,
    run_verification,
    summarize_output,
)

__all__ = [
    # common
    "Actor",
    "utcnow",
    # config
    "Config",
    "ConfigError",
    "GitConfig",
    "NoteConfig",
    "QueryConfig",
    "IssueConfig",
    "DocConfig",
    "GitHubConfig",
    "load_config",
    "find_project_config",
    # fingerprint
    "Fingerprint",
    "Generated",
    # note
    "CommitNote",
    "NoteKind",
    "NoteStatus",
    "Verification",
    "VerificationKind",
    "VerificationStatus",
    "NoteStore",
    "Query",
    "search",    # issue
    "Issue",
    "Event",
    "EventType",
    "GitHubLink",
    "Sync",
    "SyncState",
    "Status",
    "Priority",
    # doc
    "Manifest",
    "Version",
    "VersionStatus",
    "Trigger",
    "Cover",
    "match_glob",
    # stats
    "Stats",
    "compute_stats",
    "NoteStats",
    "compute_note_stats",
    # verify
    "RunResult",
    "run_verification",
    "run_note",
    "pick_notes",
    "summarize_output",
    # scripts
    "ScriptResult",
    "extract_script",
    "parse_target",
]


def utcnow() -> datetime:
    """带时区的当前时间，统一时间基准。"""
    return datetime.now(timezone.utc)
