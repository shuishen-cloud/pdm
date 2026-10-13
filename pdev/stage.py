# -*- coding: utf-8 -*-
"""阶段提交门面。

把「doc → test → feat → fix → doc」的顺序从**事后审计**升级为
**提交前强制**：commit 由 pdm 创建，顺序不对直接拒绝，不产生提交。

设计见 ``.pdm/docs/feat/stage-commit.md``。
"""

from __future__ import annotations

import subprocess
from typing import List, Optional, Sequence

__all__ = [
    "StageError",
    "STAGE_SEQUENCE",
    "STAGE_PREFIX",
    "next_stages",
    "infer_stage",
    "format_subject",
    "run_commit",
]

# 单向流水线：收尾 doc 用 "close" 区分于首阶段 doc
STAGE_SEQUENCE = ("doc", "test", "feat", "fix", "close")

# 阶段 → commit 信息前缀
STAGE_PREFIX = {
    "doc": "doc",
    "test": "test",
    "feat": "feat",
    "fix": "fix",
    "close": "doc",       # 收尾 doc 仍是 doc( 前缀
}

# 前缀 → 归一阶段（doc 无法区分首/尾，归 doc 位）
_PREFIX_TO_STAGE = {
    "doc": "doc",
    "test": "test",
    "feat": "feat",
    "fix": "fix",
}


class StageError(ValueError):
    """阶段顺序错误或提交失败。"""


def _index(stage: str) -> int:
    try:
        return STAGE_SEQUENCE.index(stage)
    except ValueError:
        raise StageError(
            f"未知阶段 {stage!r}，可选：{'/'.join(STAGE_SEQUENCE)}"
        )


def next_stages(current: Optional[str]) -> List[str]:
    """当前阶段下允许进入的下一阶段（含停留在当前）。

    :param current: 当前游标阶段；``None`` 表示尚未开始。
    """
    if current is None:
        return ["doc"]
    i = _index(current)
    # 允许停在原地（重复提交），以及前进一阶
    allowed = [current]
    if i + 1 < len(STAGE_SEQUENCE):
        allowed.append(STAGE_SEQUENCE[i + 1])
    return allowed


def assert_allowed(current: Optional[str], stage: str) -> str:
    """校验能否从 ``current`` 进入 ``stage``，非法抛 ``StageError``。"""
    stage = stage.strip().lower()
    if stage not in STAGE_SEQUENCE:
        raise StageError(
            f"未知阶段 {stage!r}，可选：{'/'.join(STAGE_SEQUENCE)}"
        )
    allowed = next_stages(current)
    if stage not in allowed:
        cur = current or "（未开始）"
        raise StageError(
            f"阶段顺序不允许：当前 [{cur}]，只能进入 "
            f"[{'/'.join(allowed)}]，但你请求 [{stage}]。"
            f"流程是 doc→test→feat→fix→close，不能回退。"
        )
    return stage


def infer_stage(commits: Sequence[str], git) -> Optional[str]:
    """由已关联 commit 的前缀推断当前所处阶段。

    取所有能识别前缀的 commit 中**最靠后**的阶段作为游标。
    ``doc`` 前缀既可代表首阶段也可代表收尾，为安全起见视为 ``doc``。
    推断不出返回 ``None``。
    """
    latest: Optional[str] = None
    best = -1
    for c in commits:
        info = git.commit_info(c) if git is not None else None
        if info is None:
            continue
        prefix = _subject_prefix(info.subject)
        stage = _PREFIX_TO_STAGE.get(prefix)
        if stage is None:
            continue
        idx = _index(stage)
        if idx >= best:
            best = idx
            latest = stage
    # 已有 feat/fix 的，说明收尾 doc 尚未发生或已发生无从判断，保持推断值
    return latest


def _subject_prefix(subject: str) -> Optional[str]:
    """从 ``feat(slug): msg`` 取出 ``feat``；取不出返回 None。"""
    if not subject:
        return None
    s = subject.strip().lower()
    for prefix in ("doc", "test", "feat", "fix"):
        if s.startswith(f"{prefix}(") or s.startswith(f"{prefix}:"):
            return prefix
    return None


def format_subject(stage: str, slug: str, message: str) -> str:
    """生成提交首行 ``<prefix>(<slug>): <message>``。"""
    stage = stage.strip().lower()
    prefix = STAGE_PREFIX.get(stage)
    if prefix is None:
        raise StageError(f"未知阶段 {stage!r}")
    msg = (message or "").strip()
    if not msg:
        raise StageError("提交信息不能为空")
    if "\n" in msg:
        msg = msg.splitlines()[0].strip()
    return f"{prefix}({slug}): {msg}"


def run_commit(
    cwd: str,
    subject: str,
    *,
    body: str = "",
    files: Optional[Sequence[str]] = None,
    no_verify: bool = False,
    dry_run: bool = False,
    timeout: int = 30,
) -> str:
    """执行 ``git commit``，返回新 commit 的完整 hash。

    :param files: 只提交这些路径；为 ``None`` 时提交全部已跟踪改动
        （不 ``git add -A``，避免误纳入未跟踪文件）。
    :param no_verify: 透传 ``--no-verify``，跳过 pre-commit 钩子。
    :param dry_run: 为真时只校验参数、不执行。
    :raises StageError: git 不可用或提交失败。
    """
    full_message = subject if not body else f"{subject}\n\n{body.strip()}"

    if dry_run:
        return ""

    cmd = ["git", "commit", "-m", full_message]
    if no_verify:
        cmd.append("--no-verify")
    if files:
        # 新文件必须先 add，否则 `git commit -- <path>` 不认
        add = subprocess.run(
            ["git", "add", "--", *files],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        if add.returncode != 0:
            detail = (add.stderr or add.stdout or "").strip()
            raise StageError(f"git add 失败：{detail}")
        cmd = ["git", "commit", "-m", full_message, "--", *files]
        if no_verify:
            cmd.insert(2, "--no-verify")

    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        raise StageError("找不到 git 命令")
    except subprocess.SubprocessError as e:  # noqa: BLE001
        raise StageError(f"git 执行失败：{e}")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise StageError(f"git commit 失败：{detail}")

    return _head_hash(cwd, timeout)


def _head_hash(cwd: str, timeout: int) -> str:
    """取 HEAD 的完整 hash。"""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()
