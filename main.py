#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ProjectDevelopManager 命令行入口。

保留应用生命周期（日志、信号处理、优雅退出）骨架，
业务分发交给 :mod:`pdev.cli`。

用法::

    python main.py note add abc123 -k pitfall -t "token 刷新有竞态"
    python main.py query -k pitfall -f 'src/auth/**'
    python main.py show abc123
    python main.py stats
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pdev.cli import main as cli_main
from pdev.cli import build_parser as build_cli_parser


@dataclass
class AppConfig:
    """应用运行配置。"""

    name: str = "pdm"
    debug: bool = False
    log_level: str = "INFO"
    extra: dict = field(default_factory=dict)


class Application:
    """应用主体，负责组织启动、运行与关闭流程。"""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = self._setup_logger()
        self._running = False
        self.argv: Optional[List[str]] = None

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.config.name)
        logger.setLevel(self.config.log_level.upper())
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)
        return logger

    def setup(self) -> None:
        """初始化资源。"""
        self.logger.debug("初始化资源...")

    def run(self) -> int:
        """解析参数并分发到子命令，返回退出码。

        实际的配置合并与上下文构造由 :func:`pdev.cli.main` 完成。
        """
        self._running = True
        return cli_main(self.argv)

    def teardown(self) -> None:
        """释放资源。"""
        self.logger.debug("释放资源...")

    def start(self) -> int:
        try:
            self.setup()
            return self.run()
        except KeyboardInterrupt:
            self.logger.warning("收到中断信号，正在退出...")
            return 130
        except Exception:  # noqa: BLE001
            self.logger.exception("应用运行异常")
            return 1
        finally:
            self._running = False
            self.teardown()


def build_parser() -> argparse.ArgumentParser:
    """CLI 参数解析器（委托给 :mod:`pdev.cli`）。"""
    return build_cli_parser()


def parse_args(argv: Optional[List[str]] = None) -> AppConfig:
    """把全局选项解析成 :class:`AppConfig`。

    实际配置合并由 :func:`pdev.cli.main` 完成，这里只保留进程生命周期设置。
    """
    return AppConfig()


def install_signal_handlers(app: Application) -> None:
    def _handler(signum: int, _frame: Any) -> None:
        app.logger.warning("捕获信号 %s，准备退出...", signum)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def main(argv: Optional[List[str]] = None) -> int:
    config = parse_args(argv)
    app = Application(config)
    app.argv = list(argv) if argv is not None else None
    install_signal_handlers(app)
    return app.start()


if __name__ == "__main__":
    sys.exit(main())
