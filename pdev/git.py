# -*- coding: utf-8 -*-
"""git 集成（只读）。

TUI 的提交面板需要显示 commit message，但笔记里只存了 hash。
本模块用 ``git log`` 补齐提交标题/作者/时间，**只读、不写**。

所有函数在非 git 仓库或 git 不可用时都安全降级（返回空）。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

__all__ = ["CommitInfo", "GitRepo", "is_git_repo"]


@dataclass(frozen=True)
class CommitInfo:
    """一次提交的元信息。"""

    hash: str
    subject: str = ""          # 首行
    author: str = ""
    date: Optional[datetime] = None

    @property
    def short(self) -> str:
        return self.hash[:8]


def _run(args: List[str], cwd: str) -> Optional[str]:
    """跑 git 命令，失败返回 None。"""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def is_git_repo(path: str = ".") -> bool:
    """path 是否在 git 工作区内。"""
    return _run(["rev-parse", "--is-inside-work-tree"], path) is not None


class GitRepo:
    """只读的 git 仓库视图。

    :param path: 仓库（或子目录）路径。
    """

    def __init__(self, path: str = ".") -> None:
        self.path = path
        self.available = is_git_repo(path)
        self._cache: Dict[str, CommitInfo] = {}

    def commit_info(self, ref: str) -> Optional[CommitInfo]:
        """查某个 ref 的提交信息；找不到返回 None。

        结果会缓存（同一个进程内 hash 不会变）。
        """
        if ref in self._cache:
            return self._cache[ref]

        out = _run(
            ["log", "-1", "--format=%H%x1f%s%x1f%an%x1f%aI", ref, "--"],
            self.path,
        )
        if out is None:
            return None
        parsed = self._absorb(out)
        if not parsed:
            return None
        info = parsed[0]
        self._cache[ref] = info
        return info

    def commit_infos(self, refs: List[str]) -> Dict[str, CommitInfo]:
        """批量查若干 ref，返回 ``{原始ref: CommitInfo}``。

        一次 ``git log`` 拿全部，避免逐个 fork。
        无效的 ref 无法混在同一个命令里（git 会整体失败），
        所以逐个回退查询。
        """
        if not refs or not self.available:
            return {}

        unknown = [r for r in refs if r not in self._cache]
        if unknown:
            out = _run(
                ["log", "--no-walk", "--format=%H%x1f%s%x1f%an%x1f%aI",
                 *unknown, "--"],
                self.path,
            )
            if out:
                resolved = self._absorb(out)
                # git 只返回 hash，需把请求的 ref（如 HEAD）也映射过去
                for ref, info in zip(unknown, resolved):
                    self._cache[ref] = info
            else:
                # 有无效 ref：逐个查，能拿到的部分不丢
                for one in unknown:
                    self.commit_info(one)

        result = {}
        for r in refs:
            info = self._cache.get(r)
            if info is None:
                info = self._match_prefix(r)
            if info is not None:
                result[r] = info
        return result

    def log(self, limit: int = 0, ref: str = "HEAD") -> List[CommitInfo]:
        """列出提交历史（新→旧）。

        :param limit: 最多返回多少条，``0`` 表示不限。
        :param ref: 起始 ref，默认 ``HEAD``。
        """
        if not self.available:
            return []

        args = ["log", "--format=%H%x1f%s%x1f%an%x1f%aI"]
        if limit > 0:
            args.append(f"-n{limit}")
        args += [ref, "--"]

        out = _run(args, self.path)
        if not out:
            return []
        # _absorb 会写缓存；顺序与 git log 一致（新→旧）
        return self._absorb(out)

    def _absorb(self, out: str) -> List[CommitInfo]:
        """把 ``git log --format`` 的输出解析并写入缓存；返回解析出的列表。"""
        parsed: List[CommitInfo] = []
        for line in out.strip().splitlines():
            parts = line.split("\x1f")
            if len(parts) < 3:
                continue
            info = CommitInfo(
                hash=parts[0],
                subject=parts[1],
                author=parts[2],
                date=_parse_date(parts[3]) if len(parts) > 3 else None,
            )
            self._cache[info.hash] = info
            self._cache[info.short] = info
            parsed.append(info)
        return parsed

    def _match_prefix(self, ref: str) -> Optional[CommitInfo]:
        """按短 hash 前缀在缓存里找。"""
        if len(ref) < 4:
            return None
        for cached in list(self._cache.values()):
            if cached.hash.startswith(ref):
                self._cache[ref] = cached
                return cached
        return None


def _parse_date(raw: str) -> Optional[datetime]:
    """解析 git 的 ISO 时间。"""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
