# -*- coding: utf-8 -*-
"""跨模块共享的测试夹具。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pdev import Actor, Issue, Priority, Status

T0 = datetime(2025, 10, 12, 10, 0, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    """基准时间 + N 分钟。"""
    return T0 + timedelta(minutes=minutes)


@pytest.fixture
def make_issue():
    """构造一个合法 issue，可用关键字覆盖任意字段。"""

    def _make(**kw) -> Issue:
        base = dict(
            id="0001",
            title="登录超时",
            status=Status.OPEN,
            priority=Priority.HIGH,
            reporter=Actor("human:lwy"),
        )
        base.update(kw)
        return Issue(**base)

    return _make
