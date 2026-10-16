# -*- coding: utf-8 -*-
"""``python -m pdev.tui_new_to_fix`` 入口。

按配置找 store 与 cwd，等价于 ``pdm ui --new``。
"""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not sys.stdout.isatty():
        print("TUI 需要交互式终端", file=sys.stderr)
        return 2

    try:
        from . import available, run
    except ImportError:
        print("需要安装 textual：pip install textual", file=sys.stderr)
        return 2
    if not available():
        print("需要安装 textual：pip install textual", file=sys.stderr)
        return 2

    from pathlib import Path

    from ..config import load_config
    from ..store import NoteStore

    cwd = Path.cwd()
    config = load_config(cwd=str(cwd))
    root = Path(getattr(config, "store", ".pdm/notes") or ".pdm/notes")
    if not root.is_absolute():
        root = cwd / root
    if argv:                          # 位置参数可覆盖 store
        root = Path(argv[0])
        if not root.is_absolute():
            root = cwd / root

    return run(NoteStore(root), cwd=str(cwd), config=config)


if __name__ == "__main__":
    sys.exit(main())
