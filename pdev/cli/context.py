# -*- coding: utf-8 -*-
"""运行时上下文。

由 :func:`pdev.cli.main` 构造一次，传给所有命令。命令只读它，不再自己
打开存储或解析配置。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config import Config
from ..store import NoteStore

__all__ = ["AppContext"]


@dataclass
class AppContext:
    """进程级共享状态。

    :param config: 合并后的配置快照。
    :param store: 已构造的笔记存储。
    :param cwd: 进程工作目录。
    :param color: 是否输出彩色（``config.color`` 与 tty 的合成结果）。
    """

    config: Config
    store: NoteStore
    cwd: Path = field(default_factory=Path.cwd)
    color: bool = False

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        cwd: Optional[Path] = None,
        stream: Any = None,
    ) -> "AppContext":
        """按配置构造上下文；store 目录在这里解析为绝对路径。"""
        base = cwd or Path.cwd()
        store_path = Path(config.store)
        if not store_path.is_absolute():
            store_path = base / store_path

        out = stream if stream is not None else sys.stdout
        color = config.color and not config.json_output and _is_tty(out)

        return cls(
            config=config,
            store=NoteStore(store_path),
            cwd=base,
            color=color,
        )


def _is_tty(stream: Any) -> bool:
    """安全判断输出流是否为终端。"""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False
