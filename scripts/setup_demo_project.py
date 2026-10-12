#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""搭建一个“真实”的演示环境：真 git 仓库 + 真提交 + 真测试 + 笔记。

与 ``seed_demo.py``（伪造 hash、无 git）不同，本脚本会：

1. 在一个目录里初始化 git 仓库
2. 造出几个小模块与配套测试（真的能跑）
3. 依次提交，每次提交后记录对应的开发笔记
4. 验证命令绑定到真实测试文件，TUI 里能直接看到脚本

用法::

    python3 scripts/setup_demo_project.py                  # 默认 ./demo-project
    python3 scripts/setup_demo_project.py --dir /tmp/demo  # 指定目录
    python3 scripts/setup_demo_project.py --reset          # 先删再建

完成后::

    cd demo-project
    .venv/bin/pdm ui --store notes      # 或 pdm ui（用 .pdm.json）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def days(d: int, h: int = 0) -> datetime:
    return BASE + timedelta(days=d, hours=h)


def V_test(target: str, method: str = "", expected: str = "passed") -> Verification:
    return Verification(
        kind=VerificationKind.TEST, target=target,
        method=method, expected=expected,
    )


def V_cmd(command: str, method: str = "", expected: str = "") -> Verification:
    return Verification(
        kind=VerificationKind.COMMAND, command=command,
        method=method, expected=expected,
    )


def V_manual(note: str) -> Verification:
    return Verification(kind=VerificationKind.MANUAL, note=note)


# ---------------------------------------------------------------------------
# 各次提交要写入的源文件
# ---------------------------------------------------------------------------

FILES: dict[str, dict[str, str]] = {}

# --- 提交 1：token 缓存层 ---
FILES["auth_token.py"] = '''\
"""访问令牌的缓存与刷新。"""

import time

_CACHE: dict = {}
_COUNTER = {"n": 0}


class TokenError(Exception):
    pass


def get_token(user: str) -> str:
    """取用户的 access token，过期则刷新。"""
    item = _CACHE.get(user)
    if item and item["expire_at"] > time.time():
        return item["token"]
    return refresh(user)


def refresh(user: str) -> str:
    """向授权服务器换取新 token。

    并发下可能重复刷新——已知问题，见提交记录。
    """
    _COUNTER["n"] += 1
    token = f"tok-{user}-{_COUNTER['n']}"
    _CACHE[user] = {"token": token, "expire_at": time.time() + 300}
    return token


def invalidate(user: str) -> None:
    """主动失效缓存。"""
    _CACHE.pop(user, None)
'''

FILES["test_auth_token.py"] = '''\
"""auth_token.py 的测试。"""

import time

import pytest

import auth_token as token_mod
from auth_token import TokenError


def setup_function():
    token_mod._CACHE.clear()


def test_get_token_caches():
    """同一用户第二次取应命中缓存。"""
    a = token_mod.get_token("alice")
    b = token_mod.get_token("alice")
    assert a == b


def test_invalidate_forces_refresh():
    """失效后应拿到新 token。"""
    a = token_mod.get_token("bob")
    token_mod.invalidate("bob")
    b = token_mod.get_token("bob")
    assert a != b


def test_expired_token_refreshes():
    """过期后应刷新出不同的 token。"""
    a = token_mod.get_token("carol")
    token_mod._CACHE["carol"]["expire_at"] = time.time() - 1
    b = token_mod.get_token("carol")
    assert a != b
'''

# --- 提交 2：加锁修复竞态 ---
FILES["auth_token.py"] += '''

_LOCK: set = set()


def refresh_safe(user: str) -> str:
    """带单飞的刷新：同一用户并发时只有一个真正刷新。"""
    item = _CACHE.get(user)
    if item is not None:
        return item["token"]
    if user in _LOCK:
        # 已有刷新在途，等它完成
        for _ in range(100):
            item = _CACHE.get(user)
            if item:
                return item["token"]
            time.sleep(0.01)
        raise TokenError("refresh timeout")
    _LOCK.add(user)
    try:
        return refresh(user)
    finally:
        _LOCK.discard(user)
'''

FILES["test_auth_token.py"] += '''

def test_refresh_safe_single_flight():
    """并发调用只产生一个 token。"""
    token_mod.invalidate("dave")
    results = [token_mod.refresh_safe("dave") for _ in range(20)]
    assert len(set(results)) == 1


def test_lock_released_on_error():
    """刷新失败时锁必须释放。"""
    original = token_mod.refresh

    def boom(_):
        raise TokenError("boom")

    token_mod.refresh = boom
    try:
        with pytest.raises(TokenError):
            token_mod.refresh_safe("erin")
    finally:
        token_mod.refresh = original
    assert "erin" not in token_mod._LOCK
'''

# --- 提交 3:缓存层 ---
FILES["cache.py"] = '''\
"""极简缓存，支持 TTL 与降级。"""

import time

_STORE: dict = {}


class CacheUnavailable(Exception):
    pass


def put(key: str, value, ttl: int = 60) -> None:
    _STORE[key] = {"v": value, "exp": time.time() + ttl}


def get(key: str, default=None):
    item = _STORE.get(key)
    if item is None:
        return default
    if item["exp"] < time.time():
        _STORE.pop(key, None)
        return default
    return item["v"]


def get_or_load(key: str, loader, ttl: int = 60):
    """缓存缺失时调用 loader；loader 抛错则降级返回 None。"""
    hit = get(key)
    if hit is not None:
        return hit
    try:
        value = loader()
    except (ConnectionError, TimeoutError):
        # 可控异常：后端不可用时降级，不让请求失败
        return None
    put(key, value, ttl)
    return value
'''

FILES["test_cache.py"] = '''\
"""cache.py 的测试。"""

import cache


def setup_function():
    cache._STORE.clear()


def test_put_get():
    cache.put("k", 1)
    assert cache.get("k") == 1


def test_expired_returns_default():
    cache.put("k", 1, ttl=0)
    assert cache.get("k", "miss") == "miss"


def test_get_or_load_populates():
    calls = []

    def loader():
        calls.append(1)
        return "value"

    assert cache.get_or_load("x", loader) == "value"
    assert cache.get_or_load("x", loader) == "value"
    assert len(calls) == 1  # 第二次命中缓存


def test_degrade_on_backend_error():
    """后端异常时降级返回 None，不抛给调用方。"""

    def loader():
        raise TimeoutError("backend down")

    assert cache.get_or_load("y", loader) is None
'''

# --- 提交 4：限流 ---
FILES["ratelimit.py"] = '''\
"""滑动窗口限流。"""

import time

_WINDOWS: dict = {}


def allow(key: str, limit: int, window: int = 60) -> bool:
    """key 在 window 秒内是否还有配额。"""
    now = time.time()
    stamps = [t for t in _WINDOWS.get(key, []) if t > now - window]
    if len(stamps) >= limit:
        _WINDOWS[key] = stamps
        return False
    stamps.append(now)
    _WINDOWS[key] = stamps
    return True


def reset(key: str) -> None:
    _WINDOWS.pop(key, None)
'''

FILES["test_ratelimit.py"] = '''\
"""ratelimit.py 的测试。"""

import ratelimit


def setup_function():
    ratelimit._WINDOWS.clear()


def test_allows_under_limit():
    for _ in range(3):
        assert ratelimit.allow("ip", limit=3)


def test_blocks_over_limit():
    for _ in range(3):
        ratelimit.allow("ip", limit=3)
    assert not ratelimit.allow("ip", limit=3)


def test_reset_clears_window():
    for _ in range(3):
        ratelimit.allow("ip", limit=3)
    ratelimit.reset("ip")
    assert ratelimit.allow("ip", limit=3)
'''

# --- 提交 5：错误码映射 ---
FILES["errors.py"] = '''\
"""HTTP 错误码映射。"""


class AppError(Exception):
    code = 500


class NotFound(AppError):
    code = 404


class BadRequest(AppError):
    code = 400


class Unauthorized(AppError):
    code = 401


def to_status(exc: Exception) -> int:
    """把异常映射为 HTTP 状态码。"""
    if isinstance(exc, AppError):
        return exc.code
    if isinstance(exc, KeyError):
        return 404
    if isinstance(exc, (ValueError, TypeError)):
        return 400
    return 500
'''

FILES["test_errors.py"] = '''\
"""errors.py 的测试。"""

import errors


def test_app_errors_keep_code():
    assert errors.to_status(errors.NotFound()) == 404
    assert errors.to_status(errors.Unauthorized()) == 401


def test_builtin_mapping():
    assert errors.to_status(KeyError("x")) == 404
    assert errors.to_status(ValueError("x")) == 400


def test_unknown_is_500():
    assert errors.to_status(RuntimeError("x")) == 500
'''

FILES["README.md"] = "# demo-project\n\n用于演示 ProjectDevelopManager 的小项目。\n"

FILES["conftest.py"] = (
    '"""conftest：把当前目录加入 sys.path，便于 import 平铺的模块。"""\n'
    "\n"
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    "sys.path.insert(0, str(Path(__file__).parent))\n"
)

SETUP = FILES["conftest.py"]


# ---------------------------------------------------------------------------
# 提交定义
# ---------------------------------------------------------------------------

COMMITS = [
    {
        "files": ["README.md", "auth_token.py", "test_auth_token.py",
                  "conftest.py"],
        "message": "feat: 增加访问令牌缓存层",
        "notes": [
            CommitNote(
                commit="", kind=NoteKind.PITFALL,
                title="并发刷新同一个 token 会重复请求",
                detail="refresh 没有单飞保护，并发时会向授权服务器发多次请求，"
                       "还可能互相覆盖缓存。",
                author=Actor("human:lwy"), files=["auth_token.py"],
                severity=Priority.HIGH, status=NoteStatus.OPEN,
                tags=["token", "concurrency"], created_at=days(0, 2),
            ),
            CommitNote(
                commit="", kind=NoteKind.DIFFICULTY,
                title="缓存过期时间与时区无关但容易被误解",
                detail="expire_at 用 monotonic 思路存的是 time.time()，"
                       "不涉及时区，但读代码时容易误以为和本地时间有关。",
                author=Actor("human:lwy"), files=["auth_token.py"],
                status=NoteStatus.NOTED, tags=["token"],
                created_at=days(0, 3),
            ),
        ],
    },
    {
        "files": ["auth_token.py", "test_auth_token.py"],
        "message": "fix: 用单飞锁修复 token 刷新竞态",
        "notes": [
            CommitNote(
                commit="", kind=NoteKind.BUG,
                title="锁在异常路径未释放导致后续刷新全部超时",
                detail="refresh_safe 早期版本没走 finally，异常时锁残留，"
                       "该用户后续所有刷新都会等待到超时。",
                author=Actor("human:lwy"), files=["auth_token.py"],
                severity=Priority.CRITICAL, status=NoteStatus.RESOLVED,
                tags=["token", "lock"], created_at=days(5, 3),
                verifications=[
                    V_test("test_auth_token.py::test_lock_released_on_error",
                           method="制造刷新失败，断言锁被释放"),
                    V_test("test_auth_token.py::test_refresh_safe_single_flight",
                           method="20 次并发断言只产生一个 token"),
                ],
            ),
            CommitNote(
                commit="", kind=NoteKind.PROBLEM,
                title="单飞锁让等待方无法感知刷新失败",
                detail="等待方只轮询缓存，刷新失败时要等满超时。"
                       "可接受，但要在文档里写明。",
                author=Actor("human:lwy"), files=["auth_token.py"],
                status=NoteStatus.NOTED, tags=["token", "tradeoff"],
                created_at=days(5, 4),
            ),
        ],
    },
    {
        "files": ["cache.py", "test_cache.py"],
        "message": "feat: 增加带降级的缓存层",
        "notes": [
            CommitNote(
                commit="", kind=NoteKind.CONTROLLED_EXCEPTION,
                title="缓存后端不可用时降级直读，不阻断请求",
                detail="get_or_load 捕获后端超时/连接错误，返回 None 让调用方"
                       "走兜底逻辑。这是设计选择，不是缺陷。",
                author=Actor("human:lwy"), files=["cache.py"],
                status=NoteStatus.NOTED,
                catches=["ConnectionError", "TimeoutError"],
                tags=["cache", "resilience"], created_at=days(8, 2),
                verifications=[
                    V_test("test_cache.py::test_degrade_on_backend_error",
                           method="让 loader 抛 TimeoutError，断言返回 None"),
                ],
            ),
            CommitNote(
                commit="", kind=NoteKind.DIFFICULTY,
                title="TTL=0 与缺失难以区分",
                detail="get 对已过期和从未写入都返回 default，"
                       "调用方无法区分“没有”和“过期了”。",
                author=Actor("ai:claude"), files=["cache.py"],
                status=NoteStatus.NOTED, tags=["cache"],
                created_at=days(8, 4),
            ),
        ],
    },
    {
        "files": ["ratelimit.py", "test_ratelimit.py"],
        "message": "feat: 增加滑动窗口限流",
        "notes": [
            CommitNote(
                commit="", kind=NoteKind.BUG,
                title="限流窗口列表长期不清理会占满内存",
                detail="_WINDOWS 只在 allow 被调用时顺带裁剪，"
                       "key 一旦不再出现，其列表会一直留着。",
                author=Actor("ai:claude"), files=["ratelimit.py"],
                severity=Priority.HIGH, status=NoteStatus.OPEN,
                tags=["ratelimit", "memory"], created_at=days(11, 2),
            ),
            CommitNote(
                commit="", kind=NoteKind.CONTROLLED_EXCEPTION,
                title="存储故障时限流选择放行而非阻断",
                detail="限流依赖外部存储时，故障期间倾向 fail-open，"
                       "避免把整个服务拖垮。需要配合监控告警。",
                author=Actor("human:lwy"), files=["ratelimit.py"],
                status=NoteStatus.NOTED,
                catches=["ConnectionError", "TimeoutError"],
                tags=["ratelimit", "resilience"], created_at=days(11, 3),
            ),
            CommitNote(
                commit="", kind=NoteKind.PITFALL,
                title="窗口边界处会出现瞬时双倍配额",
                detail="滑动窗口按时间戳计数，窗口切换瞬间可能同时计入"
                       "两段配额，需要按业务容忍度评估。",
                author=Actor("human:lwy"), files=["ratelimit.py"],
                severity=Priority.MEDIUM, status=NoteStatus.OPEN,
                tags=["ratelimit", "boundary"], created_at=days(11, 5),
            ),
        ],
    },
    {
        "files": ["errors.py", "test_errors.py"],
        "message": "refactor: 统一异常到 HTTP 状态码的映射",
        "notes": [
            CommitNote(
                commit="", kind=NoteKind.PITFALL,
                title="重构后缺失键的语义从 500 变成 404",
                detail="原先 KeyError 走默认 500，重构后显式映射为 404。"
                       "依赖旧行为的客户端需要同步调整。",
                author=Actor("human:lwy"), files=["errors.py"],
                severity=Priority.MEDIUM, status=NoteStatus.OPEN,
                tags=["errors", "breaking"], created_at=days(13, 2),
                verifications=[
                    V_test("test_errors.py::test_builtin_mapping",
                           method="断言 KeyError -> 404、ValueError -> 400"),
                ],
            ),
            CommitNote(
                commit="", kind=NoteKind.PROBLEM,
                title="业务异常继承树缺一层领域划分",
                detail="全部挂在 AppError 下，未来难以按领域区分处理策略。",
                author=Actor("human:lwy"), files=["errors.py"],
                status=NoteStatus.NOTED, tags=["errors", "design"],
                created_at=days(13, 4),
            ),
        ],
    },
]


# ---------------------------------------------------------------------------
# 构建
# ---------------------------------------------------------------------------


def run(cmd, cwd, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check,
                          capture_output=True, text=True)


def build(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    run(["git", "config", "user.email", "demo@example.com"], root)
    run(["git", "config", "user.name", "Demo Dev"], root)

    (root / "conftest.py").write_text(SETUP, encoding="utf-8")
    store = NoteStore(root / "notes")

    # .pdm.json 让 pdm 命令默认用本地 notes/
    (root / ".pdm.json").write_text(
        '{\n  "store": "notes",\n  "default_author": "human:lwy"\n}\n',
        encoding="utf-8",
    )

    written: set = set()
    for i, spec in enumerate(COMMITS, 1):
        # 写文件（累积：token.py 等会被追加）
        for name in spec["files"]:
            content = FILES[name]
            (root / name).write_text(content, encoding="utf-8")
            written.add(name)

        run(["git", "add", "-A"], root)
        run(["git", "commit", "-q", "-m", spec["message"]], root)
        sha = run(["git", "rev-parse", "HEAD"], root).stdout.strip()

        # 记录笔记（绑定真实 commit）
        for note in spec["notes"]:
            note.commit = sha
            store.add(note)
        print(f"  {i}. {sha[:8]}  {spec['message']}  ({len(spec['notes'])} notes)")

    # 写一份 README 说明
    (root / "README.md").write_text(
        "# demo-project\n\n"
        "ProjectDevelopManager 的演示项目：真实的 git 提交 + 绑定的开发笔记。\n\n"
        "```bash\n"
        ".venv/bin/pdm ui --store notes      # 图形界面\n"
        ".venv/bin/pdm stats --store notes   # 统计\n"
        ".venv/bin/pdm verify list -v        # 验证条目\n"
        "```\n",
        encoding="utf-8",
    )
    run(["git", "add", "-A"], root)
    run(["git", "commit", "-q", "-m", "docs: 补充演示说明"], root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="搭建演示项目（真 git + 真测试）")
    parser.add_argument("--dir", default="demo-project", help="目标目录")
    parser.add_argument("--reset", action="store_true", help="先删除目标目录")
    args = parser.parse_args(argv)

    root = Path(args.dir).resolve()
    if args.reset and root.exists():
        shutil.rmtree(root)
    if root.exists() and any(root.iterdir()):
        print(f"目录已存在且非空：{root}\n用 --reset 覆盖", file=sys.stderr)
        return 1

    print(f"正在搭建 {root} ...")
    build(root)

    print()
    print("完成。试试：")
    print(f"  cd {root}")
    print("  .venv/bin/pdm ui            # TUI（能看到提交标题与测试脚本）")
    print("  .venv/bin/pdm stats")
    print("  .venv/bin/pdm verify list -v")
    print("  .venv/bin/pdm verify run --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
