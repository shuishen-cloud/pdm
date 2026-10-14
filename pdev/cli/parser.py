# -*- coding: utf-8 -*-
"""命令行参数解析。

``--store`` 等全局选项在顶层与子命令均以 ``default=SUPPRESS`` 定义，
因此既能写在子命令之前，也能写在之后，且不会相互覆盖。
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from ..common import Actor
from ..stage import STAGE_SEQUENCE
from ..feat import FeatKind, FeatStatus
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
    p.add_argument("--json", action="store_true",
                   default=argparse.SUPPRESS, help="以 JSON 输出")
    p.add_argument("--store", default=argparse.SUPPRESS, help="笔记存储目录")


def build_parser() -> argparse.ArgumentParser:
    """构造完整命令解析器。"""
    parser = argparse.ArgumentParser(
        prog="pdm",
        description="ProjectDevelopManager —— 提交笔记与问题追踪",
    )
    parser.add_argument("--store", default=argparse.SUPPRESS,
                        help="笔记存储目录")
    parser.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS,
                        help="以 JSON 输出")
    parser.add_argument("--no-color", action="store_true",
                        default=argparse.SUPPRESS,
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
    show.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    show.add_argument("--store", default=argparse.SUPPRESS)
    show.set_defaults(func=commands.cmd_show)

    # --- verify ---
    ver = sub.add_parser("verify", help="验证方法与执行")
    ver_sub = ver.add_subparsers(dest="verify_command", required=True)

    vshow = ver_sub.add_parser("show", help="展开笔记及其验证详情与脚本")
    vshow.add_argument("commit", help="提交 hash")
    vshow.add_argument("--no-script", action="store_true",
                       help="不抽取测试脚本")
    vshow.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
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
    vlist.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
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

    # --- feat ---
    feat = sub.add_parser("feat", help="功能开发记录（设计→测试→实现）")
    feat_sub = feat.add_subparsers(dest="feat_command", required=True)

    fnew = feat_sub.add_parser("new", help="新建一条 feat")
    fnew.add_argument("slug", help="唯一标识，如 feat-doc-storage")
    fnew.add_argument("-t", "--title", required=True, help="一句话标题")
    fnew.add_argument("-k", "--kind", default="feat",
                      choices=[k.value for k in FeatKind])
    fnew.add_argument("--doc", default="",
                      help="简短设计文档的路径（正文外置）")
    fnew.add_argument("--api", action="append", default=[],
                      metavar="SIG", help="代码接口签名（可多次）")
    fnew.add_argument("--log", action="append", default=[],
                      metavar="TEXT", help="会打什么日志（可多次）")
    fnew.add_argument("--fallback", action="append", default=[],
                      metavar="TEXT", help="异常兜底（可多次）")
    fnew.add_argument("--design-note", default="",
                      help="设计思路（为什么这么做）")
    fnew.add_argument("--impl-note", default="",
                      help="实现方式（怎么落地的）")
    fnew.add_argument("--data-model", action="append", default=[],
                      metavar="TEXT", help="核心数据结构（可多次）")
    fnew.add_argument("--sample", action="append", default=[],
                      metavar="TEXT", help="样例数据（可多次）")
    fnew.add_argument("--change", action="append", default=[],
                      metavar="TEXT",
                      help="对既有代码的改动，格式 文件::符号 —— 说明（可多次）")
    fnew.set_defaults(func=commands.cmd_feat_new)

    flist = feat_sub.add_parser("list", help="列出 feat")
    flist.add_argument("--status", default=None,
                       choices=[s.value for s in FeatStatus])
    flist.add_argument("--kind", default=None,
                       choices=[k.value for k in FeatKind])
    flist.add_argument("--open", action="store_true", help="只看未关闭")
    flist.set_defaults(func=commands.cmd_feat_list)

    fshow = feat_sub.add_parser("show", help="查看一条 feat")
    fshow.add_argument("slug")
    fshow.add_argument("--doc", action="store_true",
                       help="打印设计文档正文")
    fshow.add_argument("--notes", action="store_true",
                       help="附关联笔记（按 kind 分组）")
    fshow.add_argument("--verify", action="store_true",
                       help="附笔记的验证命令与上次状态")
    fshow.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    fshow.add_argument("--debug", action="store_true",
                       help="额外打印原始 JSON 与存储路径")
    fshow.set_defaults(func=commands.cmd_feat_show)

    fset = feat_sub.add_parser("set", help="推进状态")
    fset.add_argument("slug")
    fset.add_argument("status", choices=[s.value for s in FeatStatus])
    fset.set_defaults(func=commands.cmd_feat_set)

    flink = feat_sub.add_parser("link", help="串联实现 commit")
    flink.add_argument("slug")
    flink.add_argument("commit")
    flink.set_defaults(func=commands.cmd_feat_link)

    fcommit = feat_sub.add_parser(
        "commit", help="阶段提交（由 pdm 创建 commit，强制阶段顺序）")
    fcommit.add_argument("stage",
                        choices=list(STAGE_SEQUENCE),
                        help="阶段；close 为收尾 doc")
    fcommit.add_argument("slug")
    fcommit.add_argument("-m", "--message", required=True,
                         help="提交信息（自动加 <stage>(<slug>): 前缀）")
    fcommit.add_argument("--body", default="", help="提交正文（可选）")
    fcommit.add_argument("--files", action="append", default=[],
                         metavar="PATH", help="只提交这些路径（可多次）")
    fcommit.add_argument("--close", action="store_true",
                         help="close 阶段同时将 feat 置为 closed")
    fcommit.add_argument("--no-verify", action="store_true",
                         help="跳过 pre-commit 钩子")
    fcommit.add_argument("--dry-run", action="store_true",
                         help="只打印将提交的内容，不真正提交")
    fcommit.set_defaults(func=commands.cmd_feat_commit)

    funlink = feat_sub.add_parser("unlink", help="解除 commit 关联")
    funlink.add_argument("slug")
    funlink.add_argument("commit")
    funlink.set_defaults(func=commands.cmd_feat_unlink)

    fcheck = feat_sub.add_parser("check", help="自约束校验（检查流程合规）")
    fcheck.add_argument("slug", nargs="?", help="只检查某条；省略则全检")
    fcheck.add_argument("--strict", action="store_true",
                       help="warning 也算失败（退出码 1）")
    fcheck.add_argument("--json", action="store_true",
                       default=argparse.SUPPRESS)
    fcheck.set_defaults(func=commands.cmd_feat_check)

    fbug = feat_sub.add_parser("found", help="记录 fix 阶段发现的异常")
    fbug.add_argument("slug")
    fbug.add_argument("text")
    fbug.set_defaults(func=commands.cmd_feat_found)

    freview = feat_sub.add_parser(
        "review", help="逐项人工审查 / 测试勾选（[审][测] 双勾选位）")
    freview.add_argument("slug")
    freview.add_argument("--item", metavar="KEY",
                         help="可审项键（api:0 / logs:1 / doc）或字段前缀（api）")
    freview.add_argument("--all", action="store_true",
                         help="作用于该 feat 的全部可审项")
    freview.add_argument("--by", metavar="WHO",
                         help="审查者（默认取配置 default_author）")
    freview.add_argument("--cmd", metavar="CMD",
                         help="--test 时登记实际执行的命令")
    freview.add_argument("--status", default="passed",
                         choices=["passed", "failed", "error"],
                         help="--test 时登记的执行结果（默认 passed）")
    freview.add_argument("--json", action="store_true",
                         default=argparse.SUPPRESS, help="以 JSON 输出")
    act = freview.add_mutually_exclusive_group()
    act.add_argument("--review", action="store_true", help="置 [审]")
    act.add_argument("--unreview", action="store_true", help="清 [审]")
    act.add_argument("--test", action="store_true", help="置 [测]")
    act.add_argument("--untest", action="store_true", help="清 [测]")
    freview.set_defaults(func=commands.cmd_feat_review)

    fcomment = feat_sub.add_parser(
        "comment", help="条目级人工评论（人手动填写，可留空）")
    fcomment.add_argument("slug")
    fcomment.add_argument("--on", metavar="KEY",
                          help="评论对象，如 api:0 / logs:1 / doc")
    _cacts = fcomment.add_mutually_exclusive_group()
    _cacts.add_argument("-m", "--message", default=None,
                        help="评论正文；缺省时查看，空串则清除")
    _cacts.add_argument("--clear", action="store_true",
                        help="清除该条目评论（与 -m 互斥）")
    fcomment.add_argument("--json", action="store_true",
                          default=argparse.SUPPRESS)
    fcomment.set_defaults(func=commands.cmd_feat_comment)

    fsrev = feat_sub.add_parser(
        "stage-review", help="阶段级人工审核（进入下一阶段前需上一阶段已审）")
    fsrev.add_argument("slug")
    fsrev.add_argument("stage", nargs="?",
                       choices=list(STAGE_SEQUENCE),
                       help="要标记已审的阶段")
    fsrev.add_argument("--by", metavar="WHO",
                       help="审核人（默认取配置 default_author）")
    fsrev.add_argument("--note", default="", help="审核备注")
    fsrev.add_argument("--clear", action="store_true",
                       help="撤销该阶段的审核")
    fsrev.add_argument("--list", action="store_true",
                       help="列出各阶段审核状态")
    fsrev.add_argument("--json", action="store_true",
                       default=argparse.SUPPRESS)
    fsrev.set_defaults(func=commands.cmd_feat_stage_review)

    # --- review ---
    review = sub.add_parser("review", help="项目代码掌握程度与告警")
    review.add_argument("--unreviewed", action="store_true",
                        help="只列出未人工审查的可审项")
    review.add_argument("--untested", action="store_true",
                        help="只列出未测试通过的可审项（与 --unreviewed 同给则取交集）")
    review.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS)
    review.set_defaults(func=commands.cmd_review)

    # --- theme ---
    theme = sub.add_parser("theme", help="查看 / 设置 TUI 主题")
    theme.add_argument("name", nargs="?", metavar="NAME",
                       help="主题名；省略则列出可选主题")
    theme.set_defaults(func=commands.cmd_theme)

    # --- ui ---
    ui = sub.add_parser("ui", help="图形界面（TUI，仿 lazygit）")
    ui.add_argument("store_arg", nargs="?", metavar="STORE",
                    help="笔记存储目录（等同 --store）")
    ui.add_argument("--curses", action="store_true",
                    help="用标准库 curses 版（零依赖，只读浏览）")
    ui.add_argument("--web", action="store_true",
                    help="启动本地 Web UI（浏览器里交互，零依赖）")
    ui.add_argument("--port", type=int, default=0,
                    help="Web UI 端口（0 = 自动分配，仅 --web）")
    ui.add_argument("--no-browser", action="store_true",
                    help="Web UI 不自动开浏览器（仅 --web）")
    ui.add_argument("--store", default=argparse.SUPPRESS)
    ui.set_defaults(func=commands.cmd_ui)

    # --- stats ---
    stats = sub.add_parser("stats", help="汇总统计")
    stats.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    stats.add_argument("--store", default=argparse.SUPPRESS)
    stats.set_defaults(func=commands.cmd_stats)

    return parser
