# -*- coding: utf-8 -*-
"""命令行接口层。

职责：解析参数 -> 合并配置 -> 构造上下文 -> 分发命令。
数据逻辑全在 :mod:`pdev` 内核，本层不含业务规则。
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional, Sequence

from ..config import ConfigError, load_config
from .context import AppContext
from .parser import build_parser, parse_actor, parse_kind, parse_verification

__all__ = [
    "main",
    "entry",
    "build_parser",
    "parse_kind",
    "parse_actor",
    "parse_verification",
    "AppContext",
]


def _cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """从解析结果里提取需要覆盖配置的项（``None`` 表示未指定）。"""
    return {
        "store": getattr(args, "store", None),
        "json_output": getattr(args, "json", None),
        "color": getattr(args, "color", None),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 主入口，返回退出码。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    # --no-color 与 --json 是相反的开关
    if getattr(args, "no_color", None):
        args.color = False
    else:
        args.color = None

    try:
        config = load_config(_cli_overrides(args))
    except ConfigError as e:
        print(f"\u914d\u7f6e\u9519\u8bef\uff1a{e}", file=sys.stderr)
        return 2

    ctx = AppContext.from_config(config)
    return args.func(ctx, args)


def entry() -> None:
    """``pdm`` 控制台脚本入口（供 pyproject ``[project.scripts]`` 使用）。"""
    import sys

    sys.exit(main())
