#!/usr/bin/env bash
# 便捷启动器：自动找到虚拟环境，直接跑 pdm。
#
# 用法：
#   ./pdm ui                 # 启动 TUI
#   ./pdm ui demo-notes      # 指定 store
#   ./pdm stats              # 任意子命令
#   ./pdm --help
#
# 第一次使用前先建虚拟环境：
#   python3 -m venv .venv && .venv/bin/pip install -e ".[dev,tui]"
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"

if [[ ! -x "$VENV/bin/pdm" ]]; then
    echo "未找到虚拟环境：$VENV" >&2
    echo "请先执行：" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -e \".[dev,tui]\"" >&2
    exit 1
fi

exec "$VENV/bin/pdm" "$@"
