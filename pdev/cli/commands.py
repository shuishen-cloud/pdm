# -*- coding: utf-8 -*-
"""命令实现：解析后的参数 + 上下文 -> 输出与退出码。

命令只依赖 :class:`~pdev.cli.context.AppContext`，不自己读配置或打开存储。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import List

from .. import utcnow
from ..common import Actor
from ..note import (
    CommitNote,
    NoteKind,
    NoteStatus,
    VerificationStatus,
)
from ..query import Query, search
from ..stats import compute_note_stats
from ..store import NoteStore
from ..verify import pick_notes, run_note
from .context import AppContext

__all__ = [
    "cmd_note_add",
    "cmd_note_list",
    "cmd_query",
    "cmd_show",
    "cmd_verify_list",
    "cmd_verify_run",
    "cmd_verify_show",
    "cmd_ui",
    "cmd_theme",
    "cmd_feat_new",
    "cmd_feat_list",
    "cmd_feat_show",
    "cmd_feat_set",
    "cmd_feat_link",
    "cmd_feat_unlink",
    "cmd_feat_found",
    "cmd_feat_check",
    "cmd_feat_commit",
    "cmd_feat_review",
    "cmd_review",
    "render_review_marks",
    "cmd_stats",
    "print_notes",
    "format_note",
    "group_by_commit",
]

_MARK = {
    NoteStatus.OPEN: "○",
    NoteStatus.RESOLVED: "●",
    NoteStatus.NOTED: "·",
}

_COLOR = {
    NoteKind.BUG: "31",                   # 红（负债）
    NoteKind.PROBLEM: "31",               # 红
    NoteKind.CONTROLLED_EXCEPTION: "32",  # 绿（可控，资产）
    NoteKind.PITFALL: "35",               # 紫
    NoteKind.DIFFICULTY: "36",            # 青
}


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def note_to_dict(n: CommitNote) -> dict:
    """笔记 -> 可 JSON 化的 dict。"""
    d = asdict(n)
    d["kind"] = n.kind.value
    d["status"] = n.status.value
    d["author"] = str(n.author)
    d["severity"] = n.severity.value if n.severity else None
    d["created_at"] = n.created_at.isoformat() if n.created_at else None
    d["verifications"] = [verification_to_dict(v) for v in n.verifications]
    return d


def format_note(n: CommitNote, color: bool = False,
                indent: str = "") -> str:
    """把一条笔记渲染成多行文本。

    :param indent: 分组显示时的缩进前缀（如 ``"    "``）。
    """
    kind = n.kind.value.upper()
    mark = _MARK[n.status]
    lines = [f"{indent}{mark} [{kind:<10}] {n.title}"]

    meta = [f"commit={n.commit[:12]}"]
    if n.files:
        meta.append(",".join(n.files))
    if n.tags:
        meta.append("#" + " #".join(n.tags))
    if n.catches:
        meta.append("catches=" + ",".join(n.catches))
    if n.issue_id:
        meta.append(f"issue={n.issue_id}")
    if n.resolves:
        meta.append("resolves=" + ",".join(n.resolves))
    if n.severity:
        meta.append(f"sev={n.severity.value}")
    lines.append(indent + "    " + "  ".join(meta))

    text = "\n".join(lines)
    if color:
        c = _COLOR.get(n.kind, "0")
        return f"\033[{c}m{text}\033[0m"
    return text


def group_by_commit(
    notes: List[CommitNote],
) -> List[tuple]:
    """按 commit 分组，保持首次出现顺序。

    返回 ``[(commit, [note, ...]), ...]``。
    """
    order: List[str] = []
    buckets: dict = {}
    for n in notes:
        if n.commit not in buckets:
            buckets[n.commit] = []
            order.append(n.commit)
        buckets[n.commit].append(n)
    return [(c, buckets[c]) for c in order]


def print_notes(
    notes: List[CommitNote],
    *,
    as_json: bool,
    color: bool,
    out=None,
    infos: dict = None,
) -> None:
    """打印笔记列表。

    :param infos: ``{commit: CommitInfo}``。给定时按 commit 分组，
        每组头部显示 commit message；否则平铺（原行为）。
    """
    out = out or sys.stdout
    if as_json:
        payload = [note_to_dict(n) for n in notes]
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=out)
        return
    if not notes:
        print("（无匹配的笔记）", file=out)
        return

    if not infos:
        # 无 git：回退平铺
        for n in notes:
            print(format_note(n, color=color), file=out)
            print(file=out)
        return

    for commit, group in group_by_commit(notes):
        info = infos.get(commit)
        subject = getattr(info, "subject", "") if info else ""
        header = f"★ {commit[:8]}"
        if subject:
            header += f"  {subject}"
        print(header, file=out)
        for n in group:
            print(format_note(n, color=color, indent="    "), file=out)
        print(file=out)


# ---------------------------------------------------------------------------
# 验证渲染
# ---------------------------------------------------------------------------

_VERIFY_MARK = {
    VerificationStatus.PASSED: "\u2713",   # ✓
    VerificationStatus.FAILED: "\u2717",   # ✗
    VerificationStatus.ERROR: "!",
    VerificationStatus.SKIPPED: "-",
    VerificationStatus.UNKNOWN: "?",
}


def format_verification(v, color: bool = False, verbose: bool = False) -> str:
    """渲染单条验证。"""
    mark = _VERIFY_MARK.get(v.last_status, "?")
    cmd = v.effective_command or (v.note if v.note else "(人工)")
    line = f"  {mark} [{v.kind.value:<7}] {cmd}"
    if v.expected:
        line += f"  (期望: {v.expected})"
    if color:
        c = {
            VerificationStatus.PASSED: "32",
            VerificationStatus.FAILED: "31",
            VerificationStatus.ERROR: "33",
        }.get(v.last_status)
        if c:
            line = f"\033[{c}m{line}\033[0m"
    if verbose and v.method:
        line += f"\n            \u65b9\u6cd5: {v.method}"
    return line


def _rule(title: str = "", width: int = 68) -> str:
    """分隔线。"""
    if not title:
        return "\u2500" * width
    return f"\u2500\u2500 {title} " + "\u2500" * max(0, width - len(title) - 4)


def verification_to_dict(v) -> dict:
    """验证 -> 可 JSON 化的 dict。"""
    return {
        "kind": v.kind.value,
        "target": v.target,
        "command": v.command,
        "effective_command": v.effective_command,
        "method": v.method,
        "script": v.script,
        "expected": v.expected,
        "note": v.note,
        "last_status": v.last_status.value,
        "last_run_at": v.last_run_at.isoformat() if v.last_run_at else None,
        "last_output": v.last_output,
    }


def print_note_with_verifications(n, color: bool, out=None,
                                  verbose: bool = False) -> None:
    """打印一条笔记及其验证。"""
    out = out or sys.stdout
    print(format_note(n, color=color), file=out)
    for v in n.verifications:
        print(format_verification(v, color=color, verbose=verbose), file=out)


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------


def cmd_verify_show(ctx: AppContext, args) -> int:
    """展开某次提交的全部笔记及其验证详情与脚本。"""
    from ..scripts import extract_script

    notes = ctx.store.by_commit(args.commit)
    if not notes:
        print(f"commit {args.commit} 没有笔记", file=sys.stderr)
        return 1

    if not args.no_script:
        for n in notes:
            for v in n.verifications:
                if v.script or v.kind.value != "test" or not v.target:
                    continue
                r = extract_script(v.target, root=ctx.cwd)
                if r.ok:
                    v.script = r.code

    if args.json:
        payload = [
            {"commit": n.commit, "title": n.title, "kind": n.kind.value,
             "verifications": [verification_to_dict(v) for v in n.verifications]}
            for n in notes
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for n in notes:
        print(format_note(n, color=ctx.color))
        if not n.verifications:
            print("  （未登记验证方法）")
            print()
            continue
        for i, v in enumerate(n.verifications, 1):
            print()
            print(f"  验证 {i}: {v.kind.value}")
            if v.method:
                print(f"    方法: {v.method}")
            if v.effective_command:
                print(f"    命令: {v.effective_command}")
            if v.expected:
                print(f"    期望: {v.expected}")
            if v.note:
                print(f"    说明: {v.note}")
            status_line = f"    状态: {v.last_status.value}"
            if v.last_run_at:
                status_line += f"  上次: {v.last_run_at:%Y-%m-%d %H:%M}"
            print(status_line)
            if v.script:
                print()
                print("  " + _rule("脚本"))
                for line in v.script.splitlines():
                    print("    " + line)
                print("  " + _rule())
        print()
    return 0


def cmd_verify_list(ctx: AppContext, args) -> int:
    """列出验证条目。"""
    from ..doc import match_glob

    notes = list(ctx.store.all())
    if args.commit:
        notes = [n for n in notes if n.commit == args.commit]
    if args.kind:
        notes = [n for n in notes if n.kind is args.kind]
    if args.file:
        notes = [n for n in notes
                 if any(match_glob(args.file, f) for f in n.files)]

    if args.unverified:
        pending = [n for n in notes if n.needs_verification]
        if not pending:
            print("（没有需要补充验证的笔记）")
            return 0
        for n in pending:
            print(format_note(n, color=ctx.color))
        print(f"共 {len(pending)} 条需要验证")
        return 0

    notes = [n for n in notes if n.verifications]
    if args.target:
        notes = [n for n in notes
                 if any(args.target in v.target or args.target in v.command
                        for v in n.verifications)]
    if args.status:
        notes = [n for n in notes
                 if any(v.last_status is args.status for v in n.verifications)]

    if not notes:
        print("（无匹配的验证）")
        return 0

    if args.json:
        payload = [
            {"commit": n.commit, "title": n.title, "kind": n.kind.value,
             "verifications": [verification_to_dict(v) for v in n.verifications]}
            for n in notes
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for n in notes:
        print_note_with_verifications(n, color=ctx.color,
                                      verbose=getattr(args, "verbose", False))
        print()
    print(f"共 {len(notes)} 条笔记，"
          f"{sum(len(n.verifications) for n in notes)} 条验证")
    return 0


def cmd_verify_run(ctx: AppContext, args) -> int:
    """执行验证并回写结果。"""
    from ..doc import match_glob

    notes = list(ctx.store.all())
    if args.file:
        notes = [n for n in notes
                 if any(match_glob(args.file, f) for f in n.files)]
    notes = pick_notes(
        notes, commit=args.commit, status=args.status, target=args.target
    )

    if not notes:
        print("（没有可执行的验证）")
        return 0

    if args.dry_run:
        for n in notes:
            print(f"{n.commit[:12]}  {n.title}")
            for v in n.runnable_verifications:
                print(f"    $ {v.effective_command}")
        return 0

    cwd = str(ctx.cwd)
    total = passed = failed = 0
    for n in notes:
        print(f"{n.commit[:12]}  {n.title}")
        for r in run_note(n, cwd=cwd, timeout=args.timeout):
            total += 1
            if r.status is VerificationStatus.PASSED:
                passed += 1
            elif r.status in (VerificationStatus.FAILED,
                              VerificationStatus.ERROR):
                failed += 1
            print(format_verification(r.verification, color=ctx.color))
        ctx.store.update(n)
        print()

    print(f"共 {total} 条验证：通过 {passed}，失败 {failed}")
    return 0 if failed == 0 else 1


def cmd_ui(ctx: AppContext, args) -> int:
    """启动 TUI。

    ``pdm ui`` 用配置里的 store；``pdm ui <dir>`` 直接指定。
    """
    store = ctx.store
    positional = getattr(args, "store_arg", None)
    if positional:
        from pathlib import Path

        from ..store import NoteStore

        p = Path(positional)
        if not p.is_absolute():
            p = ctx.cwd / p
        store = NoteStore(p)
    try:
        from ..tui import run as run_tui
    except ImportError:
        print(
            "需要安装 textual 才能使用 TUI：pip install textual",
            file=sys.stderr,
        )
        return 2
    if not _tui_available():
        print(
            "需要安装 textual 才能使用 TUI：pip install textual",
            file=sys.stderr,
        )
        return 2
    if not sys.stdout.isatty():
        print("TUI 需要交互式终端", file=sys.stderr)
        return 2
    from ..config import find_project_config

    return run_tui(
        store,
        cwd=str(ctx.cwd),
        config=ctx.config,
        config_path=find_project_config(ctx.cwd),
    )


def _feat_store(ctx: AppContext):
    """按配置构造 FeatStore（相对路径按 cwd 解析）。"""
    from pathlib import Path

    from ..feat import FeatStore

    p = Path(ctx.config.feat.store)
    if not p.is_absolute():
        p = ctx.cwd / p
    return FeatStore(p)


def cmd_feat_new(ctx: AppContext, args) -> int:
    """新建一条 feat。"""
    from ..feat import Feat, FeatError, FeatKind

    try:
        feat = Feat(
            slug=args.slug,
            title=args.title,
            kind=FeatKind(args.kind),
            doc=args.doc or "",
            api=list(args.api),
            logs=list(args.log),
            fallbacks=list(args.fallback),
        )
        _feat_store(ctx).add(feat)
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"已创建 feat：{feat.slug} [{feat.status.value}] {feat.title}")
    if feat.next_step:
        print(f"下一步：{feat.next_step}")
    return 0


def cmd_feat_list(ctx: AppContext, args) -> int:
    """列出 feat。"""
    from ..feat import FeatKind, FeatStatus

    store = _feat_store(ctx)
    feats = list(store.open() if args.open else store.all())
    if args.status:
        st = FeatStatus(args.status)
        feats = [f for f in feats if f.status is st]
    if args.kind:
        k = FeatKind(args.kind)
        feats = [f for f in feats if f.kind is k]

    if ctx.config.json_output:
        from ..feat import _to_dict

        print(json.dumps([_to_dict(f) for f in feats],
                         ensure_ascii=False, indent=2))
        return 0

    if not feats:
        print("（无 feat）")
        return 0
    for f in feats:
        commits = f"  commits={len(f.commits)}" if f.commits else ""
        print(f"[{f.status.value:10}] {f.slug:28} {f.title}{commits}")
    return 0


def cmd_feat_show(ctx: AppContext, args) -> int:
    """查看一条 feat。"""
    from ..feat import _to_dict

    store = _feat_store(ctx)
    feat = store.get(args.slug)
    if feat is None:
        print(f"找不到 feat：{args.slug}", file=sys.stderr)
        return 2

    if ctx.config.json_output or args.json:
        print(json.dumps(_to_dict(feat), ensure_ascii=False, indent=2))
        return 0
    print(f"{feat.slug}  [{feat.kind.value} / {feat.status.value}]")
    print(f"{feat.title}")
    print("═" * 50)

    from ..config import resolve_doc_path
    from ..featview import (group_notes_by_kind, notes_for_feat,
                            read_doc_body)

    # 开关：显式 flag > 配置 feat.view > 内置默认
    view = getattr(ctx.config.feat, "view", None)
    def _flag(cli_flag: bool, name: str, default: bool) -> bool:
        if cli_flag:
            return True
        v = getattr(view, name, default) if view is not None else default
        return bool(v)

    show_doc = _flag(getattr(args, "doc", False), "doc_body", False)
    show_notes = _flag(getattr(args, "notes", False), "notes_detail", False)
    show_verify = _flag(getattr(args, "verify", False), "verify", True)
    max_lines = getattr(view, "doc_max_lines", 0) if view is not None else 0
    grouped = getattr(view, "notes_grouped", True) if view is not None else True

    doc_path = resolve_doc_path(ctx.config.doc.dir, feat.doc)
    sections = [
        ("设计文档", [(doc_path, feat.doc)] if doc_path else []),
        ("交付接口", [(x, x) for x in feat.api]),
        ("会打的日志", [(x, x) for x in feat.logs]),
        ("异常兜底", [(x, x) for x in feat.fallbacks]),
        ("关联 commit", [(x, x) for x in feat.commits]),
        ("关联 note", [(x, x) for x in feat.notes]),
        ("发现的异常", [(x, x) for x in feat.discovered]),
    ]
    # 可审项 → 行前带 [审][测] 标记（见 doc/feat/review-cli.md）
    # 匹配用 feat.doc / 原文，显示用 (显示文本, 匹配文本)
    _review_at = {}
    for rkey, rlabel in feat.review_items():
        field = rkey.split(":")[0]
        _review_at[(field, rlabel)] = render_review_marks(feat, rkey)

    def _mark_for(section: str, match_text: str) -> str:
        field = {"设计文档": "doc", "交付接口": "api",
                 "会打的日志": "logs", "异常兜底": "fallbacks"}.get(section)
        if field is None:
            return ""
        return _review_at.get((field, match_text), "")

    for name, pairs in sections:
        if not pairs:
            continue
        print(f"\n{name}")
        for display, match in pairs:
            print(f"  {_mark_for(name, match)}· {display}")

    # 审查覆盖小结
    if feat.review_items():
        total, reviewed, tested = feat.review_counts()
        print(f"\n审查  审查 {reviewed}/{total}  测试 {tested}/{total}"
              f"   （pdm feat review {feat.slug}）")

    # 内联设计正文
    if show_doc and feat.doc:
        print("\n── 设计正文 ──")
        print(read_doc_body(ctx.config.doc.dir, feat.doc, max_lines))

    # 关联笔记（复用内核聚合）
    if show_notes or show_verify:
        notes = notes_for_feat(feat, ctx.store)
        print("\n── 关联笔记 ──")
        if not notes:
            print("  （该 feat 暂无笔记）")
        else:
            groups = group_notes_by_kind(notes) if grouped else [("", notes)]
            for kind, items in groups:
                if kind:
                    print(f"  [{kind}] ×{len(items)}")
                for n in items:
                    pre = "    " if kind else "  "
                    print(f"{pre}{n.commit[:8]} {n.title}")
                    if show_notes and n.detail:
                        print(f"{pre}    {n.detail}")
                    if show_notes and n.files:
                        print(f"{pre}    files: {', '.join(n.files)}")
                    if show_verify:
                        for v in n.verifications:
                            cmd = v.effective_command or v.target
                            print(f"{pre}    ✓ {cmd}  ({v.last_status.value})")

    if feat.next_step:
        print(f"\n下一步：{feat.next_step}")

    if args.debug:
        from ..feat import _to_dict
        from ..store import NoteStore  # noqa: F401

        print(f"\n路径：{store._path(feat.slug)}")
        print(f"原始 JSON：\n{json.dumps(_to_dict(feat), ensure_ascii=False, indent=2)}")
    return 0


def cmd_feat_set(ctx: AppContext, args) -> int:
    """推进 feat 状态。"""
    from ..feat import FeatError, FeatStatus

    store = _feat_store(ctx)
    try:
        feat = store.set_status(args.slug, FeatStatus(args.status))
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"{feat.slug} → [{feat.status.value}]")
    if feat.next_step:
        print(f"下一步：{feat.next_step}")
    return 0


def cmd_feat_link(ctx: AppContext, args) -> int:
    """串联实现 commit。"""
    from ..feat import FeatError

    try:
        feat = _feat_store(ctx).link_commit(args.slug, args.commit)
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"{feat.slug} ← {args.commit}（现有 {len(feat.commits)} 个）")
    return 0


def cmd_feat_unlink(ctx: AppContext, args) -> int:
    """解除 commit 关联。"""
    from ..feat import FeatError

    try:
        feat = _feat_store(ctx).unlink_commit(args.slug, args.commit)
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"{feat.slug} ✗ {args.commit}（现有 {len(feat.commits)} 个）")
    return 0


def cmd_feat_found(ctx: AppContext, args) -> int:
    """记录 fix 阶段发现的异常。"""
    from ..feat import FeatError

    try:
        feat = _feat_store(ctx).add_discovered(args.slug, args.text)
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    print(f"{feat.slug} 发现 {len(feat.discovered)} 条异常")
    return 0


def cmd_feat_commit(ctx: AppContext, args) -> int:
    """阶段提交门面：由 pdm 创建 commit，强制 doc→test→feat→fix→close 顺序。

    - ``pdm feat commit <stage> <slug> -m <msg>``
    - 顺序非法直接拒绝（退出码 2），不产生 commit
    """
    from ..feat import FeatError
    from ..git import GitRepo
    from ..stage import StageError

    store = _feat_store(ctx)
    git = GitRepo(str(ctx.cwd))

    try:
        feat, commit_hash, old_stage, new_stage = store.commit_stage(
            args.slug, args.stage, args.message,
            cwd=str(ctx.cwd),
            files=args.files or None,
            body=args.body or "",
            no_verify=args.no_verify,
            dry_run=args.dry_run,
            git=git,
            close=args.close,
        )
    except (StageError, FeatError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    cur = old_stage or "（未开始）"
    arrow = f"{cur} → {new_stage}"
    if args.dry_run:
        print(f"[dry-run] 将提交 {cur} → {new_stage}")
        print(f"  {feat.slug}: <{new_stage}>({feat.slug}): {args.message.strip()}")
        return 0

    print(f"✓ {feat.slug} {arrow}  {commit_hash[:8]}")
    if args.close and new_stage == "close":
        print(f"  {feat.slug} → [closed]")
    elif feat.next_step:
        print(f"下一步：{feat.next_step}")
    return 0


def cmd_feat_check(ctx: AppContext, args) -> int:
    """自约束校验，返回非 0 表示有问题。

    - ``pdm feat check`` 全检
    - ``pdm feat check <slug>`` 只检一条
    - ``--strict`` 时 warning 也算失败
    """
    from ..check import check_feats, check_one, format_issue, summarize

    store = _feat_store(ctx)
    from ..git import GitRepo

    git = GitRepo(str(ctx.cwd))

    try:
        if args.slug:
            issues = check_one(store, args.slug, git, note_store=ctx.store)
        else:
            issues = check_feats(store, git, note_store=ctx.store)
    except KeyError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    stats = summarize(issues)

    if ctx.config.json_output or getattr(args, "json", False):
        print(json.dumps({
            "issues": [
                {"slug": i.slug, "code": i.code, "level": i.level,
                 "message": i.message}
                for i in issues
            ],
            **stats,
        }, ensure_ascii=False, indent=2))
    else:
        if not issues:
            print("✓ 全部 feat 均通过校验")
        else:
            for i in issues:
                print(format_issue(i, color=ctx.color))
            print(f"\n共 {stats['total']} 条："
                  f"{stats['errors']} 错误，{stats['warnings']} 警告")

    if stats["errors"]:
        return 1
    if getattr(args, "strict", False) and stats["warnings"]:
        return 1
    return 0


# ---------------------------------------------------------------------------
# 审查勾选（review-cli）
# ---------------------------------------------------------------------------


def render_review_marks(feat, key: str = "") -> str:
    """生成 ``"[x][ ] "`` 前缀（供 show / 列表复用）。"""
    item = feat.review_item(key) if key else None
    r = "x" if item is not None and item.reviewed else " "
    t = "x" if item is not None and item.tested else " "
    return f"[{r}][{t}] "


def _review_lines(feat) -> List[str]:
    """把可审项渲染成 ``"[x][ ] api:0  f() -> int"`` 列表。"""
    out = []
    for key, label in feat.review_items():
        out.append(f"{render_review_marks(feat, key)}{key:<12} {label}")
    return out


def _review_snapshot(feat) -> dict:
    """可审项 + 勾选状态（供 ``--json``）。"""
    items = []
    for key, label in feat.review_items():
        it = feat.review_item(key)
        items.append({
            "key": key,
            "label": label,
            "reviewed": bool(it and it.reviewed),
            "tested": bool(it and it.tested),
            "reviewed_by": it.reviewed_by if it else "",
            "test_command": it.test_command if it else "",
            "test_status": it.test_status if it else "",
        })
    total, reviewed, tested = feat.review_counts()
    return {"slug": feat.slug, "items": items, "total": total,
            "reviewed": reviewed, "tested": tested}


def cmd_feat_review(ctx: AppContext, args) -> int:
    """列出或勾选某 feat 的审查项。"""
    from ..feat import FeatError

    store = _feat_store(ctx)
    feat = store.get(args.slug)
    if feat is None:
        print(f"错误：找不到 feat：{args.slug}", file=sys.stderr)
        return 2

    key = getattr(args, "item", None)
    action = _review_action(args)

    if action is None:
        return _print_review_list(ctx, feat)

    if not key:
        print("错误：勾选需要 --item <KEY>", file=sys.stderr)
        return 2

    try:
        if action == "review":
            store.set_reviewed(args.slug, key, True, by=args.by or "")
        elif action == "unreview":
            store.set_reviewed(args.slug, key, False)
        elif action == "test":
            store.set_tested(args.slug, key, True,
                             command=args.cmd or "",
                             status=args.status or "passed")
        elif action == "untest":
            store.set_tested(args.slug, key, False)
    except FeatError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    feat = store.get(args.slug)
    total, reviewed, tested = feat.review_counts()
    if action == "test" and not (args.cmd or ""):
        print("提示：建议用 --cmd 记录实际执行的验证命令", file=sys.stderr)
    print(f"{args.slug}  {render_review_marks(feat, key)}{key}"
          f"  （审查 {reviewed}/{total}，测试 {tested}/{total}）")
    return 0


def _review_action(args) -> str:
    """从互斥参数中取出动作名；无动作返回 None。"""
    for name in ("review", "unreview", "test", "untest"):
        if getattr(args, name, False):
            return name
    return None


def _print_review_list(ctx: AppContext, feat) -> int:
    """打印某 feat 的可审项与勾选状态。"""
    if ctx.config.json_output:
        print(json.dumps(_review_snapshot(feat), ensure_ascii=False, indent=2))
        return 0

    total, reviewed, tested = feat.review_counts()
    print(f"{feat.slug}  审查 {reviewed}/{total}  测试 {tested}/{total}")
    lines = _review_lines(feat)
    if not lines:
        print("  （无可审内容：doc/api/logs/fallbacks 均为空）")
        return 0
    for line in lines:
        print(line)
    return 0


def cmd_review(ctx: AppContext, args) -> int:
    """全仓掌握程度与告警；有告警返回 1。"""
    from ..review import ReviewPolicy, compute_review, format_score

    store = _feat_store(ctx)
    cfg = getattr(ctx.config, "review", None)
    policy = ReviewPolicy(
        min_coverage=getattr(cfg, "min_coverage", 0.6),
        warn_no_review=getattr(cfg, "warn_no_review", True),
        warn_untested=getattr(cfg, "warn_untested", True),
    )
    score = compute_review(list(store.all()), policy)

    if ctx.config.json_output or getattr(args, "json", False):
        print(json.dumps({
            "items": score.items,
            "reviewed": score.reviewed,
            "tested": score.tested,
            "feats": score.feats,
            "review_coverage": score.review_coverage,
            "test_coverage": score.test_coverage,
            "score": score.score,
            "level": score.level,
            "warnings": [
                {"code": w.code, "level": w.level, "message": w.message}
                for w in score.warnings
            ],
        }, ensure_ascii=False, indent=2))
        return 1 if score.warnings else 0

    print(format_score(score))
    return 1 if score.warnings else 0


def cmd_theme(ctx: AppContext, args) -> int:
    """查看 / 设置 TUI 主题。

    - ``pdm theme`` 列出全部可选主题，标出当前值
    - ``pdm theme nord`` 写入**用户配置**（个人偏好，不进 git）
    """
    # 内置主题列表：从 textual 导入，未安装时退回空
    names: list = []
    try:
        from textual.theme import BUILTIN_THEMES

        names = sorted(BUILTIN_THEMES)
    except Exception:
        try:
            from textual.app import App

            names = sorted(App().available_themes)
        except Exception:
            names = []

    current = ctx.config.ui.theme
    name = getattr(args, "name", None)

    if not name:
        if not names:
            print("未能加载主题列表（需要安装 textual）", file=sys.stderr)
            return 2
        if ctx.config.json_output:
            print(json.dumps({"current": current, "themes": names},
                             ensure_ascii=False, indent=2))
            return 0
        print("可选主题")
        for n in names:
            mark = "●" if n == current else " "
            print(f"  {mark} {n}")
        print(f"\n当前：{current}；用 `pdm theme <名字>` 设置")
        return 0

    # 校验
    if names and name not in names:
        print(f"未知主题：{name}", file=sys.stderr)
        near = [n for n in names if name.lower() in n.lower()]
        if near:
            print("是否想要：" + ", ".join(near), file=sys.stderr)
        return 2

    from ..config import save_user_config

    path = save_user_config({"ui": {"theme": name}})
    print(f"已设置主题 {name} → {path}")
    return 0


def _tui_available() -> bool:
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


def cmd_note_add(ctx: AppContext, args) -> int:
    """新增一条笔记。"""
    if ctx.config.note.require_detail and not args.detail:
        print("错误：配置要求必须提供 --detail", file=sys.stderr)
        return 2

    # 未在命令行指定时，回退到配置
    author = args.author or Actor(ctx.config.default_author)
    status = args.status or ctx.config.note.default_status

    note = CommitNote(
        commit=args.commit,
        kind=args.kind,
        title=args.title,
        detail=args.detail or "",
        author=author,
        files=args.files or [],
        severity=args.severity,
        status=status,
        catches=args.catches or [],
        verifications=args.verify or [],
        issue_id=args.issue,
        resolves=args.resolves or [],
        tags=args.tags or [],
    )
    if not args.no_time:
        note.created_at = utcnow()

    try:
        ctx.store.add(note)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    print(f"已记录：{format_note(note, color=ctx.color)}")
    return 0


def _build_query(ctx: AppContext, args) -> Query:
    limit = getattr(args, "limit", None)
    if limit is None:
        limit = ctx.config.query.default_limit
    return Query(
        kind=getattr(args, "kind", None),
        status=getattr(args, "status", None),
        file=getattr(args, "file", None),
        tag=getattr(args, "tag", None),
        text=getattr(args, "text", None),
        commit=getattr(args, "commit", None),
        issue_id=getattr(args, "issue", None),
        author=getattr(args, "author", None),
        limit=limit,
    )


def _commit_infos(ctx: AppContext, notes) -> dict:
    """从 git 查笔记涉及的 commit 信息（非 git 仓库返回空）。

    优先用 cwd 找 git；找不到则试 store 所在目录（笔记可能在
    另一个 git 仓库里）。
    """
    from ..git import GitRepo

    commits = list({n.commit for n in notes})
    for base in (str(ctx.cwd), str(ctx.store.root)):
        try:
            git = GitRepo(base)
        except Exception:
            continue
        if git.available:
            return git.commit_infos(commits)
    return {}


def _run_query(ctx: AppContext, args) -> int:
    hits = search(ctx.store, _build_query(ctx, args))
    infos = None if args.json else _commit_infos(ctx, hits)
    print_notes(hits, as_json=args.json, color=ctx.color, infos=infos)
    if not args.json:
        print(f"共 {len(hits)} 条")
    return 0


def cmd_note_list(ctx: AppContext, args) -> int:
    """列出笔记。"""
    return _run_query(ctx, args)


def cmd_query(ctx: AppContext, args) -> int:
    """组合查询。"""
    return _run_query(ctx, args)


def cmd_show(ctx: AppContext, args) -> int:
    """查看某次提交的全部笔记。"""
    notes = ctx.store.by_commit(args.commit)
    if not notes:
        print(f"commit {args.commit} 没有笔记", file=sys.stderr)
        return 1
    infos = None if args.json else _commit_infos(ctx, notes)
    print_notes(notes, as_json=args.json, color=ctx.color, infos=infos)
    return 0


def cmd_stats(ctx: AppContext, args) -> int:
    """汇总统计。"""
    s = compute_note_stats(ctx.store)
    from ..review import ReviewPolicy, compute_review, format_score

    cfg = getattr(ctx.config, "review", None)
    policy = ReviewPolicy(
        min_coverage=getattr(cfg, "min_coverage", 0.6),
        warn_no_review=getattr(cfg, "warn_no_review", True),
        warn_untested=getattr(cfg, "warn_untested", True),
    )
    score = compute_review(list(_feat_store(ctx).all()), policy)

    if args.json:
        payload = dict(s.__dict__)
        payload["review"] = {
            "items": score.items,
            "reviewed": score.reviewed,
            "tested": score.tested,
            "feats": score.feats,
            "review_coverage": score.review_coverage,
            "test_coverage": score.test_coverage,
            "score": score.score,
            "level": score.level,
            "warnings": [w.code for w in score.warnings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("笔记统计")
    print(f"  总数      {s.total}")
    print(f"  覆盖提交  {s.commits}")
    print(f"  覆盖文件  {s.files}")
    print(f"  未解决    {s.open}")
    print(f"  已升级    {s.promoted}")
    print(f"  已解决    {s.resolved}")
    print(f"  AI 撰写   {s.written_by_ai}")
    print(f"  风险项    {s.risky}")
    print("  负债（缺陷）")
    print(f"    总数    {s.bugs}")
    print(f"    未修复  {s.bugs_open}")
    print("  资产（可控异常）")
    print(f"    条数    {s.controlled_exceptions}")
    print(f"    已覆盖类型 {s.caught_types}")
    print("  验证")
    print(f"    已登记  {s.verified_notes} 条笔记 / {s.verifications} 条验证")
    print(f"    通过    {s.verification_passed}")
    print(f"    失败    {s.verification_failed}")
    print(f"    待补充  {s.needs_verification}")
    if s.by_kind:
        print("  按类型")
        for k, v in sorted(s.by_kind.items()):
            print(f"    {k:<22}{v}")
    print()
    print(format_score(score))
    return 0
