#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成模拟笔记数据，用于体验查询 / 统计 / 展示功能。

用法::

    python3 scripts/seed_demo.py                 # 写入 ./demo-notes
    python3 scripts/seed_demo.py --store notes   # 写入指定目录
    python3 scripts/seed_demo.py --reset         # 先清空再生成

生成的数据覆盖：

- 4 个模块：auth / cache / api / payment
- 6 次提交（含 feat / fix / refactor 场景）
- 五类笔记：problem / difficulty / pitfall / controlled-exception / bug
- 人写与 AI 写、不同状态、严重程度、标签
- 部分笔记关联 Issue（升级 / 解决）
- 时间跨度约两周
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 允许直接以脚本方式运行（无需安装）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdev import (  # noqa: E402
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    NoteStore,
    Priority,
    Verification,
    VerificationKind,
)

BASE = datetime(2025, 10, 1, 9, 0, 0, tzinfo=timezone.utc)


def days(d: int, hours: int = 0, minutes: int = 0) -> datetime:
    return BASE + timedelta(days=d, hours=hours, minutes=minutes)


def V_test(target: str, **kw) -> Verification:
    return Verification(kind=VerificationKind.TEST, target=target, **kw)


def V_cmd(command: str, **kw) -> Verification:
    return Verification(kind=VerificationKind.COMMAND, command=command, **kw)


def V_manual(note: str, **kw) -> Verification:
    return Verification(kind=VerificationKind.MANUAL, note=note, **kw)


def build_notes() -> list[CommitNote]:
    """构造模拟笔记。"""
    N = CommitNote
    K, S, P = NoteKind, NoteStatus, Priority

    return [
        # ---------------------------------------------------------------
        # c0ffee1 — feat: 用户登录 + JWT 签发
        # ---------------------------------------------------------------
        N(
            commit="c0ffee1", kind=K.PITFALL,
            title="JWT 签发未设置过期时间",
            detail="token 默认永不过期，安全性问题。应显式设置 exp claim。",
            author=Actor("human:lwy"), files=["src/auth/jwt.py"],
            severity=P.HIGH, status=S.RESOLVED,
            tags=["auth", "security"], created_at=days(0, 2),
        ),
        N(
            commit="c0ffee1", kind=K.DIFFICULTY,
            title="异步上下文里拿不到 request 对象",
            detail="FastAPI 的 request 依赖注入在后台任务中失效，需通过依赖手动传递。",
            author=Actor("human:lwy"), files=["src/auth/jwt.py", "src/core/ctx.py"],
            status=S.NOTED, tags=["async", "fastapi"], created_at=days(0, 3),
        ),
        N(
            commit="c0ffee1", kind=K.BUG,
            title="bcrypt 密码长度超 72 字节被静默截断",
            detail="bcrypt 只取前 72 字节，长密码会静默截断导致安全弱化。已改用预哈希方案。",
            author=Actor("ai:claude"), files=["src/auth/password.py"],
            severity=P.CRITICAL, status=S.RESOLVED,
            tags=["auth", "security"], created_at=days(0, 5),
            verifications=[
                V_test("tests/auth/test_password.py::test_long_password",
                       method="用 100 字节密码注册后验证能正常登录，断言不被截断",
                       expected="passed"),
                V_manual("用 100 字节密码注册后验证能正常登录"),
            ],
        ),

        # ---------------------------------------------------------------
        # c0ffee2 — feat: token 缓存层
        # ---------------------------------------------------------------
        N(
            commit="c0ffee2", kind=K.PITFALL,
            title="token 刷新存在竞态",
            detail="并发刷新时会写出旧 token 覆盖新值，需要分布式锁或单飞。",
            author=Actor("human:lwy"), files=["src/auth/token.py"],
            severity=P.HIGH, status=S.OPEN, issue_id="0001",
            tags=["auth", "concurrency"], created_at=days(2, 4),
        ),
        N(
            commit="c0ffee2", kind=K.DIFFICULTY,
            title="Redis 集群下 SETNX 返回值语义不一致",
            detail="单机 Redis 返回 1/0，集群模式下偶发返回 nil，需兼容处理。",
            author=Actor("ai:claude"), files=["src/auth/token.py", "src/cache/redis.py"],
            status=S.NOTED, tags=["redis", "cluster"], created_at=days(2, 6),
        ),
        N(
            commit="c0ffee2", kind=K.PROBLEM,
            title="缓存击穿导致数据库压力骤增",
            detail="热点 key 过期瞬间大量请求穿透到 DB，需加空值缓存 + 互斥重建。",
            author=Actor("human:lwy"), files=["src/cache/redis.py"],
            severity=P.MEDIUM, status=S.OPEN, issue_id="0002",
            tags=["cache", "performance"], created_at=days(3, 1),
        ),
        N(
            commit="c0ffee2", kind=K.CONTROLLED_EXCEPTION,
            title="Redis 不可用时降级为直读数据库",
            detail="缓存层所有调用都包了熔断，Redis 抖动时走 DB 兜底，保证可用性。",
            author=Actor("human:lwy"), files=["src/cache/redis.py"],
            status=S.NOTED, catches=["RedisTimeout", "ConnectionError"],
            tags=["cache", "resilience"], created_at=days(3, 2),
        ),

        # ---------------------------------------------------------------
        # c0ffee3 — fix: 修复 token 竞态
        # ---------------------------------------------------------------
        N(
            commit="c0ffee3", kind=K.PROBLEM,
            title="加分布式锁修复 token 刷新竞态",
            detail="使用 Redis SET NX PX 实现单飞，刷新期间其他请求等待并复用结果。",
            author=Actor("human:lwy"), files=["src/auth/token.py"],
            status=S.RESOLVED, resolves=["0001"],
            tags=["auth", "concurrency"], created_at=days(5, 3),
            verifications=[
                V_test("tests/auth/test_token.py::test_refresh_concurrent",
                       method="200 并发断言 Redis 只被写入一次",
                       expected="passed"),
                V_cmd("make typecheck", method="类型检查通过",
                      expected="退出码 0"),
            ],
        ),
        N(
            commit="c0ffee3", kind=K.BUG,
            title="锁未释放导致后续刷新全部超时",
            detail="异常路径没走 finally，锁泄漏。已改为上下文管理器。",
            author=Actor("human:lwy"), files=["src/auth/token.py"],
            severity=P.CRITICAL, status=S.RESOLVED,
            tags=["auth", "lock"], created_at=days(5, 7),
            verifications=[
                V_test("tests/auth/test_token.py::test_lock_released",
                       method="异常路径下断言锁被释放",
                       expected="passed"),
                V_cmd("wrk -t2 -c200 -d60s http://localhost:8000/token",
                      method="200 并发压测 60 秒，看错误率",
                      expected="无超时，错误率 0"),
            ],
        ),

        # ---------------------------------------------------------------
        # c0ffee4 — feat: 支付回调
        # ---------------------------------------------------------------
        N(
            commit="c0ffee4", kind=K.PITFALL,
            title="支付回调未做幂等",
            detail="第三方会重复推送通知，缺少幂等键导致重复发货。",
            author=Actor("human:lwy"), files=["src/payment/callback.py"],
            severity=P.CRITICAL, status=S.OPEN, issue_id="0003",
            tags=["payment", "idempotency"], created_at=days(8, 2),
        ),
        N(
            commit="c0ffee4", kind=K.CONTROLLED_EXCEPTION,
            title="支付网关超时后进入对账补偿流程",
            detail="回调处理超时不会直接失败，而是标记待对账，由定时任务补救。",
            author=Actor("human:lwy"), files=["src/payment/callback.py"],
            status=S.NOTED, catches=["GatewayTimeout", "ConnectionError"],
            tags=["payment", "resilience"], created_at=days(8, 3),
        ),
        N(
            commit="c0ffee4", kind=K.DIFFICULTY,
            title="金额计算浮点误差",
            detail="用 float 累加金额出现 0.01 级误差，已统一改为 Decimal。",
            author=Actor("ai:claude"), files=["src/payment/amount.py"],
            status=S.RESOLVED, tags=["payment", "precision"], created_at=days(8, 4),
        ),
        N(
            commit="c0ffee4", kind=K.PROBLEM,
            title="回调签名校验在时钟偏差下失败",
            detail="服务器时间与第三方相差超过 5 分钟时验签失败，需放宽窗口或改用 NTP。",
            author=Actor("ai:claude"), files=["src/payment/callback.py"],
            severity=P.MEDIUM, status=S.NOTED,
            tags=["payment", "security"], created_at=days(9, 1),
        ),

        # ---------------------------------------------------------------
        # c0ffee5 — refactor: API 层重构
        # ---------------------------------------------------------------
        N(
            commit="c0ffee5", kind=K.DIFFICULTY,
            title="N+1 查询难以在 ORM 层发现",
            detail="序列化嵌套对象时逐条查询，需 eager load 并加测试防回归。",
            author=Actor("human:lwy"), files=["src/api/serializers.py"],
            status=S.NOTED, tags=["api", "performance"], created_at=days(11, 3),
        ),
        N(
            commit="c0ffee5", kind=K.PITFALL,
            title="重构后错误码语义悄然变化",
            detail="异常映射表改动导致 404 变 400，客户端依赖旧语义会受影响。",
            author=Actor("human:lwy"), files=["src/api/errors.py"],
            severity=P.MEDIUM, status=S.OPEN,
            tags=["api", "breaking"], created_at=days(11, 5),
        ),

        # ---------------------------------------------------------------
        # c0ffee6 — feat: 限流
        # ---------------------------------------------------------------
        N(
            commit="c0ffee6", kind=K.BUG,
            title="滑动窗口计数器内存泄漏",
            detail="过期的窗口未清理，长时间运行内存持续增长。需定期裁剪或改用 Redis ZSET。",
            author=Actor("ai:claude"), files=["src/api/ratelimit.py"],
            severity=P.HIGH, status=S.OPEN, issue_id="0004",
            tags=["api", "memory", "leak"], created_at=days(13, 2),
        ),
        N(
            commit="c0ffee6", kind=K.CONTROLLED_EXCEPTION,
            title="限流器存储故障时放行而非阻断",
            detail="Redis 不可用时限流将失效，选择 fail-open 保证业务可用，并报警。",
            author=Actor("human:lwy"), files=["src/api/ratelimit.py"],
            status=S.NOTED, catches=["RedisError", "TimeoutError"],
            tags=["api", "resilience", "tradeoff"], created_at=days(13, 3),
        ),
        N(
            commit="c0ffee6", kind=K.DIFFICULTY,
            title="限流粒度选择困难",
            detail="按 IP 会被 NAT 误伤，按用户需先鉴权，双维度组合又会放大存储。",
            author=Actor("human:lwy"), files=["src/api/ratelimit.py"],
            status=S.NOTED, tags=["api", "design"], created_at=days(13, 4),
        ),
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成模拟笔记数据")
    parser.add_argument("--store", default="demo-notes", help="输出目录")
    parser.add_argument("--reset", action="store_true", help="生成前先清空目录")
    args = parser.parse_args(argv)

    root = Path(args.store)
    if args.reset and root.exists():
        shutil.rmtree(root)

    store = NoteStore(root)
    notes = build_notes()
    for n in notes:
        n.validate()
    store.add_many(notes)

    commits = {n.commit for n in notes}
    kinds: dict = {}
    for n in notes:
        kinds[n.kind.value] = kinds.get(n.kind.value, 0) + 1

    print(f"已生成 {len(notes)} 条笔记 -> {root}")
    print(f"  覆盖提交 {len(commits)} 个：{', '.join(sorted(commits))}")
    print(f"  类型分布：{kinds}")
    print()
    print("试试这些命令：")
    print(f'  python3 main.py --store {root} stats')
    print(f'  python3 main.py --store {root} show c0ffee2')
    print(f'  python3 main.py --store {root} query -k pitfall')
    print(f'  python3 main.py --store {root} query -f "src/auth/**"')
    print(f'  python3 main.py --store {root} query -x 竞态')
    print(f'  python3 main.py --store {root} query -a ai')
    print(f'  python3 main.py --store {root} query -s open')
    print(f'  python3 main.py --store {root} query -i 0001')
    return 0


if __name__ == "__main__":
    sys.exit(main())
