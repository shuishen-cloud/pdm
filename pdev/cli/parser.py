# -*- coding: utf-8 -*-
"""命令行参数解析。

``--store`` 等全局选项在顶层与子命令均以 ``default=SUPPRESS`` 定义，
因此既能写在子命令之前，也能写在之后，且不会相互覆盖。
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from ..common import Actor
from ..issue import Priority
from ..note import (
    NoteKind,
    NoteStatus,
    Verification,
    VerificationKind,
    VerificationStatus as VerifyStatus,
)
from ..store import NoteStore
from . import commands

__all__ = [
    "build_parser",
    "parse_kind",
    "parse_actor",
    "parse_verification",
    "KIND_ALIASES",
]
# 额外短名（全名会自动派生，无需重复）
_KIND_SHORT = {
    NoteKind.PROBLEM: ["p"],
    NoteKind.DIFFICULTY: ["d", "diff"],
    NoteKind.PITFALL: ["pit"],
    NoteKind.CONTROLLED_EXCEPTION: ["ce", "ctrl", "exc"],
    NoteKind.BUG: ["b"],
}


def _build_aliases() -> dict:
    """全名 + 短名 + 无连字符形式。"""
    out = {}
    for k in NoteKind:
        out[k.value] = k                      # 全名，如 controlled-exception
        out[k.value.replace("-", "")] = k     # 去连字符，如 controlledexception
        for short in _KIND_SHORT.get(k, []):
            out[short] = k
    return out


_KIND_ALIASES = _build_aliases()
KIND_ALIASES = _KIND_ALIASES


def parse_kind(raw: str) -> NoteKind:
    """把用户输入的类型简写解析成 ``NoteKind``。"""
    key = raw.strip().lower()
    if key in _KIND_ALIASES:
        return _KIND_ALIASES[key]
    raise argparse.ArgumentTypeError(
        f"未知笔记类型 {raw!r}，可选：{', '.join(k.value for k in NoteKind)}"
    )


def parse_actor(raw: str) -> Actor:
    """``lwy`` -> ``human:lwy``；已带冒号的保持原样。"""
    raw = raw.strip()
    if not raw:
        raise argparse.ArgumentTypeError("author 不能为空")
    return Actor(raw if ":" in raw else f"human:{raw}")


def parse_verification(raw: str) -> Verification:
    """解析 ``--verify`` 参数。

    支持在主体后用 ``;`` 附加 ``method=`` / ``expected=`` / ``note=``::

        test=tests/x.py::test_y;method=并发下只刷新一次;expected=passed
        cmd=make check;expected=退出码 0
        manual=重建集群后登录三次
        <裸字符串>   -> 视为 command
    """
    raw = raw.strip()
    if not raw:
        raise argparse.ArgumentTypeError("verify 不能为空")

    parts = [p for p in raw.split(";")]
    head = parts[0].strip()
    extra = {}
    for p in parts[1:]:
        if "=" in p:
            k, _, v = p.partition("=")
            extra[k.strip().lower()] = v.strip()

    if "=" in head:
        prefix, _, body = head.partition("=")
        prefix = prefix.strip().lower()
        body = body.strip()
        if prefix in ("test", "t"):
            v = Verification(kind=VerificationKind.TEST, target=body)
        elif prefix in ("cmd", "command", "c"):
            v = Verification(kind=VerificationKind.COMMAND, command=body)
        elif prefix in ("manual", "m"):
            v = Verification(kind=VerificationKind.MANUAL, note=body)
        else:
            raise argparse.ArgumentTypeError(
                f"未知验证类型 {prefix!r}，可选：test/cmd/manual"
            )
    else:
        v = Verification(kind=VerificationKind.COMMAND, command=head)

    if "method" in extra:
        v.method = extra["method"]
    if "expected" in extra:
        v.expected = extra["expected"]
    if "note" in extra:
        v.note = extra["note"]
    return v


def _add_common_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("-k", "--kind", type=parse_kind, help="按类型筛选")
    p.add_argument("-s", "--status", choices=[x.value for x in NoteStatus],
                   type=NoteStatus, help="按状态筛选")
    p.add_argument("-f", "--file", help="按文件筛选（支持 src/** glob）")
    p.add_argument("-T", "--tag", help="按标签筛选")
    p.add_argument("-x", "--text", help="全文搜索（title/detail/tags/catches）")
    p.add_argument("-C", "--commit", help="按提交筛选")
    p.add_argument("-i", "--issue", help="按关联 Issue 筛选")
    p.add_argument("-a", "--author", help="按作者种类筛选，如 human / ai")
    p.add_argument("-n", "--limit", type=int, default=None, help="最多返回条数")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--store", default=argparse.SUPPRESS, help="笔记存储目录")


def build_parser() -> argparse.ArgumentParser:
    """构造完整命令解析器。"""
    parser = argparse.ArgumentParser(
        prog="pdm",
        description="ProjectDevelopManager —— 提交笔记与问题追踪",
    )
    parser.add_argument("--store", default=argparse.SUPPRESS,
                        help="笔记存储目录")
    parser.add_argument("--json", action="store_true", default=None,
                        help="以 JSON 输出")
    parser.add_argument("--no-color", action="store_true", default=None,
                        help="禁用彩色输出")
    sub = parser.add_subparsers(dest="command", required=True)

    # --- note ---
    note = sub.add_parser("note", help="笔记操作")
    note_sub = note.add_subparsers(dest="note_command", required=True)

    add = note_sub.add_parser("add", help="新增一条笔记")
    add.add_argument("commit", help="关联的 commit hash")
    add.add_argument("-k", "--kind", type=parse_kind, required=True,
                     help="类型：problem/difficulty/pitfall/"
                          "controlled-exception/bug")
    add.add_argument("-t", "--title", required=True, help="一句话摘要")
    add.add_argument("-d", "--detail", help="详细描述")
    add.add_argument("-F", "--file", dest="files", action="append",
                     help="涉及文件，可重复")
    add.add_argument("-c", "--catches", action="append",
                     help="可控异常捕获的异常类型，可重复（用于 -k controlled-exception）")
    add.add_argument("--verify", dest="verify", action="append",
                     type=parse_verification, metavar="KIND=VAL",
                     help="验证方法，可重复。test=<用例> / cmd=<命令> / manual=<步骤>")
    add.add_argument("-T", "--tag", dest="tags", action="append",
                     help="标签，可重复")
    add.add_argument("-p", "--priority", dest="severity",
                     choices=[x.value for x in Priority], type=Priority,
                     help="严重程度")
    add.add_argument("--status", choices=[x.value for x in NoteStatus],
                     type=NoteStatus, default=None,
                     help="笔记状态（默认取配置 note.default_status）")
    add.add_argument("-i", "--issue", help="升级成的 Issue ID")
    add.add_argument("-r", "--resolve", dest="resolves", action="append",
                     help="该笔记解决了哪个 Issue，可重复")
    add.add_argument("-a", "--author", type=parse_actor, default=None,
                     help="作者，如 human:lwy 或 ai:claude（默认取配置 default_author）")
    add.add_argument("--no-time", action="store_true", help="不记录当前时间")
    add.add_argument("--store", default=argparse.SUPPRESS)
    add.set_defaults(func=commands.cmd_note_add)

    lst = note_sub.add_parser("list", help="列出笔记")
    _add_common_filters(lst)
    lst.set_defaults(func=commands.cmd_note_list)

    # --- query ---
    q = sub.add_parser("query", help="组合查询")
    _add_common_filters(q)
    q.set_defaults(func=commands.cmd_query)

    # --- show ---
    show = sub.add_parser("show", help="查看某提交的全部笔记")
    show.add_argument("commit")
    show.add_argument("--json", action="store_true", default=None)
    show.add_argument("--store", default=argparse.SUPPRESS)
    show.set_defaults(func=commands.cmd_show)

    # --- verify ---
    ver = sub.add_parser("verify", help="验证方法与执行")
    ver_sub = ver.add_subparsers(dest="verify_command", required=True)

    vshow = ver_sub.add_parser("show", help="展开笔记及其验证详情与脚本")
    vshow.add_argument("commit", help="提交 hash")
    vshow.add_argument("--no-script", action="store_true",
                       help="不抽取测试脚本")
    vshow.add_argument("--json", action="store_true", default=None)
    vshow.add_argument("--store", default=argparse.SUPPRESS)
    vshow.set_defaults(func=commands.cmd_verify_show)

    vlist = ver_sub.add_parser("list", help="列出验证条目")
    vlist.add_argument("-C", "--commit", help="按提交筛选")
    vlist.add_argument("-k", "--kind", type=parse_kind, help="按笔记类型筛选")
    vlist.add_argument("-f", "--file", help="按文件筛选（支持 glob）")
    vlist.add_argument("-t", "--target", help="按测试/命令关键字筛选")
    vlist.add_argument("-v", "--verbose", action="store_true",
                       help="每条验证多显示一行方法说明")
    vlist.add_argument("--status", choices=[s.value for s in VerifyStatus],
                       type=VerifyStatus, help="按上次结果筛选")
    vlist.add_argument("--unverified", action="store_true",
                       help="只看需要验证却没有验证方法的笔记")
    vlist.add_argument("--json", action="store_true", default=None)
    vlist.add_argument("--store", default=argparse.SUPPRESS)
    vlist.set_defaults(func=commands.cmd_verify_list)

    vrun = ver_sub.add_parser("run", help="执行验证并回写结果")
    vrun.add_argument("commit", nargs="?", help="只跑某次提交的验证")
    vrun.add_argument("-f", "--file", help="只跑涉及该文件的验证（支持 glob）")
    vrun.add_argument("-t", "--target", help="按测试/命令关键字筛选")
    vrun.add_argument("--status", choices=[s.value for s in VerifyStatus],
                      type=VerifyStatus, help="只跑指定上次结果的验证")
    vrun.add_argument("-n", "--dry-run", action="store_true",
                      help="只打印将执行的命令，不真的执行")
    vrun.add_argument("--timeout", type=int, default=600, help="单条超时秒数")
    vrun.add_argument("--store", default=argparse.SUPPRESS)
    vrun.set_defaults(func=commands.cmd_verify_run)

    # --- ui ---
    ui = sub.add_parser("ui", help="图形界面（TUI，仿 lazygit）")
    ui.add_argument("--store", default=argparse.SUPPRESS)
    ui.set_defaults(func=commands.cmd_ui)

    # --- stats ---
    stats = sub.add_parser("stats", help="汇总统计")
    stats.add_argument("--json", action="store_true", default=None)
    stats.add_argument("--store", default=argparse.SUPPRESS)
    stats.set_defaults(func=commands.cmd_stats)

    return parser
