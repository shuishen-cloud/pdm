# -*- coding: utf-8 -*-
"""任务级门面（见 doc/feat/oop-refactor.md、doc/feat/ledger-complete.md）。

把 ``NoteStore`` / ``FeatStore`` / ``NoteKind`` 等**内部结构**藏在后面，
只暴露"要干什么"：

    from pdev.api import open_ledger

    ledger = open_ledger()
    ledger.record(commit="abc1234", kind="pitfall", title="并发竞态")
    ledger.features.new(slug="token-cache", title="token 缓存")
    ledger.checks.of("token-cache")
    ledger.reviews.mark("token-cache", "api:0", by="human:lwy")
    ledger.trace.doc_body("token-cache")
    ledger.overview()

设计约束：

- 门面**只暴露任务级方法**，不暴露 Store / Enum / 裸 dataclass。
- **不破坏现有 CLI** —— 门面是**新增**，不是替换。
- 门面内部**只调用现有内核算**，不新写逻辑。
- ``kind`` 接受普通字符串（内部转 ``NoteKind``）。

**变更策略**（见 ledger-complete.md）：新能力放在 ``LedgerV2`` 子类，
可随时删掉回退；验证通过后再把**子门面属性**合入 ``Ledger``
（只搬 4~5 个属性，不搬 18 个方法）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from .common import Actor
from .feat import Feat, FeatStore, ReviewCounts, ReviewItemRef
from .note import CommitNote, NoteKind, NoteStatus
from .stats import NoteStats, compute_note_stats
from .store import NoteStore

__all__ = [
    "Ledger",
    "LedgerV2",
    "FeatureAPI",
    "CheckAPI",
    "ReviewAPI",
    "VerifyAPI",
    "TraceAPI",
    "open_ledger",
]


# ---------------------------------------------------------------------------
# 子门面：各管一个职责，方法都转发给 Ledger（逻辑只有一份）
# ---------------------------------------------------------------------------


class FeatureAPI:
    """feat 相关任务级操作（``ledger.features``）。"""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger

    def new(self, slug: str, title: str, **fields: Any) -> Feat:
        """新建一条 feat；``fields`` 透传给 :class:`~pdev.feat.Feat`。"""
        feat = Feat(slug=slug, title=title, **fields)
        self._ledger._feats.add(feat)
        return feat

    def get(self, slug: str) -> Optional[Feat]:
        """取一条 feat；不存在返回 ``None``。"""
        return self._ledger._feats.get(slug)

    def list(self) -> List[Feat]:
        """全部 feat（新→旧）。"""
        return list(self._ledger._feats.all())

    def open(self) -> List[Feat]:
        """未关闭的 feat。"""
        return self._ledger._feats.open()


class CheckAPI:
    """校验相关操作（``ledger.checks``）。"""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger

    def of(self, slug: str) -> List[Any]:
        """校验单条 feat，返回问题列表。"""
        return self._ledger._check_impl(slug)

    def all(self) -> List[Any]:
        """校验全部 feat（含孤立 commit 检查）。"""
        return self._ledger._check_all_impl()

    def summary(self, issues) -> Any:
        """把问题列表汇总成 ``CheckSummary``。"""
        return self._ledger._summary_impl(issues)


class ReviewAPI:
    """审查相关操作（``ledger.reviews``）。"""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger

    def list(self, slug: str) -> List[ReviewItemRef]:
        """某 feat 的全部可审项（含勾选态与评论）。"""
        return self._ledger._reviews_impl(slug)

    def counts(self, slug: str) -> ReviewCounts:
        """某 feat 的审查计数。"""
        return self._ledger.counts(slug)

    def overview(self) -> Any:
        """全部 feat 的审查评分（掌握程度）。"""
        return self._ledger.review_overview()

    def mark(self, slug: str, key: str, value: bool = True,
             by: str = "") -> Feat:
        """置/清 ``[审]`` 位。``by`` 缺省时用配置里的作者。"""
        return self._ledger.mark_reviewed(slug, key, value, by)

    def mark_tested(self, slug: str, key: str, value: bool = True,
                    command: str = "", status: str = "") -> Feat:
        """置/清 ``[测]`` 位。"""
        return self._ledger.mark_tested(slug, key, value, command, status)


class VerifyAPI:
    """验证相关操作（``ledger.verify``）。"""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger

    def pending(self, commit: Optional[str] = None) -> List[CommitNote]:
        """列出"需要验证却没有验证方法"的笔记。

        （与 :meth:`runnable` 相对：这里是"该绑验证却没绑"的。）
        """
        return self._ledger.pending_verifications(commit)

    def runnable(self, commit: Optional[str] = None) -> List[CommitNote]:
        """列出"已登记可执行验证"的笔记（准备跑）。"""
        return self._ledger.runnable_verifications(commit)

    def run(self, note: CommitNote) -> List[Any]:
        """执行一条笔记上所有可执行的验证。"""
        return self._ledger._verify_impl(note)

    def commit(self, sha: str) -> List[Any]:
        """执行某次提交上全部笔记的验证。"""
        return self._ledger._verify_commit_impl(sha)


class TraceAPI:
    """追溯相关操作（``ledger.trace``）。"""

    def __init__(self, ledger: "Ledger") -> None:
        self._ledger = ledger

    def doc_body(self, slug: str) -> str:
        """读某 feat 的设计正文（不切窗口即可看）。"""
        return self._ledger._doc_body_impl(slug)

    def notes(self, slug: str) -> List[CommitNote]:
        """某 feat 关联的笔记（按 commit 匹配）。"""
        return self._ledger._notes_of_feat_impl(slug)


# ---------------------------------------------------------------------------
# Ledger：稳定版（旧代码，尽量不动）
# ---------------------------------------------------------------------------


class Ledger:
    """任务级门面：一个入口，完成"记笔记 / 管 feat / 看总览"。

    内部持有 ``NoteStore`` 与 ``FeatStore``，但不对外暴露。
    """

    def __init__(self, root: Optional[str] = None, cwd: str = ".",
                 config=None) -> None:
        """构造账本。

        :param root: 存储根目录；给了就用 ``<root>/notes``、``<root>/feats``
            布局（兼容旧调用）。省略则从 ``config`` 解析。
        :param cwd: 相对路径的基准目录。
        :param config: 已加载的配置；省略时自行 ``load_config()``。
        """
        self._cwd = Path(cwd)
        if config is None:
            try:
                from .config import load_config

                config = load_config(cwd=self._cwd)
            except Exception:  # noqa: BLE001 - 配置不可用则回退默认布局
                config = None
        self._config = config

        def resolve(p: str) -> Path:
            path = Path(p)
            return path if path.is_absolute() else self._cwd / path

        if root is not None:
            self._root = resolve(root)
            note_root, feat_root = self._root / "notes", self._root / "feats"
        elif config is not None:
            self._root = resolve(config.store).parent
            note_root = resolve(config.store)
            feat_root = resolve(config.feat.store)
        else:
            self._root = resolve(".pdm")
            note_root, feat_root = self._root / "notes", self._root / "feats"

        self._doc_dir = self._resolve_doc_dir(config)
        self._author = getattr(config, "default_author", "human:unknown")

        self._notes = NoteStore(note_root)
        self._feats = FeatStore(feat_root)
        self._features = FeatureAPI(self)

    # --- 笔记 ---

    def record(self, *, commit: str, kind: str, title: str,
               detail: str = "", by: str = "",
               files: Optional[List[str]] = None,
               tags: Optional[List[str]] = None,
               **extra: Any) -> CommitNote:
        """记一条笔记。``kind`` 接受普通字符串（如 ``"pitfall"``）。"""
        note = CommitNote(
            commit=commit,
            kind=NoteKind(kind) if not isinstance(kind, NoteKind) else kind,
            title=title,
            detail=detail,
            author=Actor(by or self._author),
            files=list(files or []),
            tags=list(tags or []),
            status=extra.pop("status", NoteStatus.NOTED),
            **extra,
        )
        self._notes.add(note)
        return note

    def notes(self) -> List[CommitNote]:
        """全部笔记。"""
        return list(self._notes.all())

    def notes_of(self, commit: str) -> List[CommitNote]:
        """某次提交的全部笔记。"""
        return self._notes.by_commit(commit)

    # --- feat ---

    @property
    def features(self) -> FeatureAPI:
        """feat 操作入口。"""
        return self._features

    # --- 总览 ---

    def overview(self) -> NoteStats:
        """笔记总览统计。"""
        return compute_note_stats(self._notes)

    # --- 供子门面转发（实现只此一份）---

    def _check_impl(self, slug: str) -> List[Any]:
        """校验单条 feat（自动凑 store / git / note_store）。"""
        from .check import check_one

        return check_one(self._feats, slug, git=self._git(),
                         note_store=self._notes)

    def _check_all_impl(self) -> List[Any]:
        """校验全部 feat。"""
        from .check import check_feats

        return check_feats(self._feats, git=self._git(),
                           note_store=self._notes)

    def _summary_impl(self, issues) -> Any:
        """把问题列表汇总。"""
        from .check import summarize

        return summarize(issues)

    def _reviews_impl(self, slug: str) -> List[ReviewItemRef]:
        """某 feat 的可审项。"""
        return self._require_feat(slug).review_items()

    def counts(self, slug: str) -> ReviewCounts:
        """某 feat 的审查计数。"""
        return self._require_feat(slug).review_counts()

    def review_overview(self) -> Any:
        """全部 feat 的审查评分。"""
        from .review import compute_review

        return compute_review(list(self._feats.all()))

    def mark_reviewed(self, slug: str, key: str, value: bool = True,
                      by: str = "") -> Feat:
        """置/清 ``[审]`` 位。"""
        return self._feats.set_reviews(
            slug, [key], reviewed=bool(value), by=by or self._author)

    def mark_tested(self, slug: str, key: str, value: bool = True,
                    command: str = "", status: str = "") -> Feat:
        """置/清 ``[测]`` 位。"""
        return self._feats.set_reviews(
            slug, [key], tested=bool(value), command=command,
            status=status or ("passed" if value else ""))

    def pending_verifications(self,
                              commit: Optional[str] = None) -> List[CommitNote]:
        """列出"需要验证却没有验证方法"的笔记。"""
        notes = list(self._notes.all())
        if commit is not None:
            notes = [n for n in notes if n.commit == commit]
        return [n for n in notes if n.needs_verification]

    def runnable_verifications(self,
                               commit: Optional[str] = None) -> List[CommitNote]:
        """列出"已登记可执行验证"的笔记。"""
        from .verify import pick_notes

        return pick_notes(list(self._notes.all()), commit=commit)

    def _verify_impl(self, note: CommitNote) -> List[Any]:
        """执行一条笔记上所有可执行的验证。"""
        from .verify import run_note

        return run_note(note, cwd=str(self._cwd))

    def _verify_commit_impl(self, sha: str) -> List[Any]:
        """执行某次提交上全部笔记的验证。"""
        out: List[Any] = []
        for note in self._notes.by_commit(sha):
            out.extend(self._verify_impl(note))
        return out

    def _doc_body_impl(self, slug: str) -> str:
        """读某 feat 的设计正文。"""
        from .featview import read_doc_body

        feat = self._require_feat(slug)
        if not feat.doc:
            return ""
        return read_doc_body(self._doc_dir, feat.doc)

    def _notes_of_feat_impl(self, slug: str) -> List[CommitNote]:
        """某 feat 关联的笔记。"""
        from .featview import notes_for_feat

        return list(notes_for_feat(self._require_feat(slug), self._notes))

    # --- 内部 ---

    def _resolve_doc_dir(self, config) -> str:
        """设计文档根目录，相对 ``cwd`` 解析为绝对路径。

        ``featview.read_doc_body`` 用 ``Path(doc_dir)`` 直接读，
        因此传绝对路径才能不受进程 cwd 影响。
        """
        raw = getattr(getattr(config, "doc", None), "dir", "doc") or "doc"
        p = Path(raw)
        return str(p if p.is_absolute() else self._cwd / p)

    def _require_feat(self, slug: str) -> Feat:
        feat = self._feats.get(slug)
        if feat is None:
            from .feat import FeatError

            raise FeatError(f"找不到 feat：{slug}")
        return feat

    def _git(self):
        """git 仓库（不可用时返回 None，check 已容忍）。"""
        try:
            from .git import GitRepo

            repo = GitRepo(str(self._cwd))
            return repo if repo.available else None
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# LedgerV2：子门面版（本 feat 新增；验证后可将属性合入 Ledger）
# ---------------------------------------------------------------------------


class LedgerV2(Ledger):
    """在 ``Ledger`` 之上按**子门面**组织能力。

    新增的四个子门面：``checks`` / ``reviews`` / ``verify`` / ``trace``。
    逻辑全部转发给 ``Ledger``，本类**不含实现**——只做分区。

    可随时删掉本类回退到 ``Ledger``（旧行为）。
    """

    @property
    def checks(self) -> CheckAPI:
        return CheckAPI(self)

    @property
    def reviews(self) -> ReviewAPI:
        return ReviewAPI(self)

    @property
    def verify(self) -> VerifyAPI:
        return VerifyAPI(self)

    @property
    def trace(self) -> TraceAPI:
        return TraceAPI(self)


def open_ledger(root: Optional[str] = None, cwd: str = ".",
                config=None) -> LedgerV2:
    """打开一个账本（任务级入口）。"""
    return LedgerV2(root=root, cwd=cwd, config=config)
