# -*- coding: utf-8 -*-
"""Ledger 门面的**用法说明书**（ledger-complete）。

本文件的测试**不只是断言**——每个用例演示**一个完整目的**是怎么达成的。
读它应该能知道："我想做 X，该调哪几个方法"。

五个闭环：

    1. 记录闭环   —— 记笔记 → 看总览
    2. 审查闭环   —— 建 feat → 看可审项 → 勾审 → 看计数
    3. 校验闭环   —— 校验 → 拿 issue → 知道该做什么
    4. 追溯闭环   —— 从代码/文档追溯 → 拿 feat → 读设计正文
    5. 验证闭环   —— 列待验证 → 跑验证 → 看结果

**设计见** ``doc/feat/ledger-complete.md``。
"""

from __future__ import annotations

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStore, Verification, VerificationKind
from pdev.api import Ledger, LedgerV2, open_ledger
from pdev.feat import Feat, FeatKind, FeatStore


# ---------------------------------------------------------------------------
# 构造：一个"可用环境"，只需一个对象
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path) -> LedgerV2:
    """一个干净的账本（唯一需要构造的对象）。"""
    return open_ledger(root=str(tmp_path / ".pdm"), cwd=str(tmp_path))


def test_one_object_is_enough(tmp_path):
    """用法：open_ledger() 一个入口拿到全部能力，无需 import 内核。"""
    led = open_ledger(root=str(tmp_path / ".pdm"), cwd=str(tmp_path))
    # 四个子门面都在，且不需要自己 new Store / GitRepo
    assert led.features is not None
    assert led.checks is not None
    assert led.reviews is not None
    assert led.trace is not None


def test_ledger_reads_config(tmp_path, monkeypatch):
    """用法：不传 root 时，路径来自 config（而非写死 .pdm）。"""
    from pdev.config import load_config

    cfg = load_config(env={"PDM_STORE": str(tmp_path / "mynotes"),
                           "PDM_FEAT_STORE": str(tmp_path / "myfeats")},
                      cwd=tmp_path, find=False)
    led = LedgerV2(cwd=str(tmp_path), config=cfg)
    # store 落在 config 指定的位置
    led.record(commit="abc1234", kind="pitfall", title="x")
    assert (tmp_path / "mynotes").exists()


def test_v2_is_a_ledger():
    """LedgerV2 继承 Ledger —— 可回退（删掉 V2 即回到旧行为）。"""
    assert issubclass(LedgerV2, Ledger)


# ---------------------------------------------------------------------------
# 闭环 1：记录 → 总览
# ---------------------------------------------------------------------------


def test_usage_record_then_overview(ledger):
    """目的：把一次开发中踩的坑记下来，并看一眼总量。

    用的方法：

        ledger.features.new(slug, title)      # 先建一条 feat
        ledger.record(commit, kind, title)    # 记一条笔记
        ledger.overview()                     # 看总览
    """
    # 1) 建 feat（记笔记前先有"这是哪次开发"）
    ledger.features.new("token-cache", "token 缓存层")

    # 2) 记一条笔记——kind 直接写字符串，不用知道 NoteKind
    note = ledger.record(
        commit="abc1234",
        kind="pitfall",
        title="并发刷新会写出旧 token",
        detail="两个线程同时刷新，后者用旧值覆盖",
        by="human:lwy",
        files=["src/auth/token.py"],
        tags=["auth"],
    )

    # 3) 看总览
    st = ledger.overview()
    assert st.total == 1
    assert st.by_kind["pitfall"] == 1
    assert note.kind is NoteKind.PITFALL


# ---------------------------------------------------------------------------
# 闭环 2：审查 —— 建 feat → 看可审项 → 勾 → 看计数
# ---------------------------------------------------------------------------


def test_usage_review_flow(ledger):
    """目的：审阅一条 feat 的规格，逐项打勾，确认覆盖率。

    用的方法：

        ledger.features.new(...)               # 建 feat（带规格）
        ledger.reviews.list(slug)              # 看有哪些可审项
        ledger.reviews.mark(slug, key, by=...) # 勾 [审]
        ledger.reviews.counts(slug)            # 看覆盖数
        ledger.reviews.overview()              # 看全局掌握程度
    """
    # 1) 建一条带规格的 feat
    ledger.features.new(
        "web-ui", "本地 Web UI",
        doc="feat/web-ui.md",
        api=["build_data(store, git) -> dict"],
        logs=["启动时打印地址"],
        fallbacks=["端口占用则退出 2"],
    )

    # 2) 看有哪些可审项（每一项都能单独审）
    items = ledger.reviews.list("web-ui")
    keys = [r.key for r in items]
    assert keys == ["doc", "api:0", "logs:0", "fallbacks:0"]
    assert all(not r.reviewed for r in items)     # 默认都没审

    # 3) 逐项打勾
    ledger.reviews.mark("web-ui", "api:0", by="human:lwy")
    ledger.reviews.mark("web-ui", "logs:0", by="human:lwy")

    # 4) 看计数
    c = ledger.reviews.counts("web-ui")
    assert c.total == 4
    assert c.reviewed == 2
    assert c.coverage == 0.5

    # 5) 看全局掌握程度（跨所有 feat）
    score = ledger.reviews.overview()
    assert score.items == 4
    assert score.reviewed == 2


def test_usage_review_can_be_reverted(ledger):
    """目的：审错了要能撤销。"""
    ledger.features.new("a", "A", api=["f()"])
    ledger.reviews.mark("a", "api:0", by="human:lwy")
    assert ledger.reviews.counts("a").reviewed == 1

    ledger.reviews.mark("a", "api:0", value=False)   # 撤销
    assert ledger.reviews.counts("a").reviewed == 0


# ---------------------------------------------------------------------------
# 闭环 3：校验 —— 校验 → 拿 issue → 知道该做什么
# ---------------------------------------------------------------------------


def test_usage_check_flow(ledger):
    """目的：检查一条 feat 是否合规，并知道下一步做什么。

    用的方法：

        ledger.features.new(...)
        ledger.checks.of(slug)     # 单条校验
        ledger.checks.summary(...) # 汇总
        ledger.checks.all()        # 全仓校验
    """
    ledger.features.new("bare", "缺字段的 feat")   # 故意缺 api/logs/...

    # 1) 单条校验
    issues = ledger.checks.of("bare")
    codes = {i.code for i in issues}
    # 缺字段、缺 doc 等都会被指出
    assert issues, "缺规格的 feat 应报出问题"

    # 2) 汇总（知道有几条错误几条警告）
    s = ledger.checks.summary(issues)
    assert s.total == len(issues)
    assert s.error + s.warning == s.total

    # 3) 全仓校验
    all_issues = ledger.checks.all()
    assert isinstance(all_issues, list)


def test_usage_check_empty_store_ok(ledger):
    """目的：空仓库校验应返回空，而不是崩。"""
    assert ledger.checks.all() == []


# ---------------------------------------------------------------------------
# 闭环 4：追溯 —— 从代码/设计追溯
# ---------------------------------------------------------------------------


def test_usage_trace_flow(ledger, tmp_path):
    """目的：看到一条 feat，想知道"当初为什么这么设计"。

    用的方法：

        ledger.trace.doc_body(slug)   # 读设计正文（避免切窗口）
        ledger.trace.notes(slug)      # 看这条 feat 关联的笔记
    """
    # 造一份设计文档
    d = tmp_path / "doc" / "feat"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text("# 甲的设计\n\n## 规范\n\n正文\n",
                                encoding="utf-8")

    ledger.features.new("alpha", "功能甲", doc="feat/alpha.md",
                        commits=["abc1234"])

    # 1) 读设计正文
    body = ledger.trace.doc_body("alpha")
    assert "甲的设计" in body

    # 2) 看关联笔记（按 commit 匹配）
    ledger.record(commit="abc1234", kind="difficulty", title="难点")
    notes = ledger.trace.notes("alpha")
    assert [n.title for n in notes] == ["难点"]


def test_usage_trace_missing_doc_ok(ledger):
    """目的：设计文档缺失时应给提示而非异常。"""
    ledger.features.new("nodoc", "没有文档", doc="feat/nope.md")
    body = ledger.trace.doc_body("nodoc")
    assert body == "" or "不可读" in body


# ---------------------------------------------------------------------------
# 闭环 5：验证 —— 列待验证 → 跑 → 看结果
# ---------------------------------------------------------------------------


def test_usage_verify_flow(ledger):
    """目的：找出"记了但没验证"的笔记，并执行验证。

    用的方法：

        ledger.verify.pending()      # 列待验证的笔记
        ledger.verify.run(note)      # 执行某笔记的验证
    """
    # 1) 记一条**带可执行验证**的笔记
    ledger.record(
        commit="abc1234", kind="pitfall", title="可用 true 验证",
        verifications=[Verification(kind=VerificationKind.COMMAND,
                                    command="true", expected="退出码 0")],
    )
    # 2) 记一条**没有验证**的笔记
    ledger.record(commit="abc1234", kind="bug", title="还没绑验证")

    # 3) 列待验证（没有验证方法的）
    pending = ledger.verify.pending()
    assert any(n.title == "还没绑验证" for n in pending)

    # 4) 跑一条验证
    notes = [n for n in ledger.notes() if n.verifications]
    results = ledger.verify.run(notes[0])
    assert results, "应有执行结果"


# ---------------------------------------------------------------------------
# 回归：内核未被动
# ---------------------------------------------------------------------------


def test_no_kernel_signature_changed():
    """关键内核签名台账（变更时同步更新，以防意外破坏）。

    原为 ``ledger-complete`` 立的“本 feat 不动内核”防线；
    后续 feat 有意变更 API 时，**同步更新本台账**并说明原因。

    变更记录：

    - ``check_one`` / ``check_feats`` 新增 ``loose_history``
      （feat-edit-fields：历史 feat 的字段豁免改为由开关决定）。
    """
    import inspect

    from pdev.check import check_feats, check_one
    from pdev.review import compute_review
    from pdev.stats import compute_note_stats

    sigs = {
        check_one: ["store", "slug", "git", "note_store", "min_coverage",
                    "loose_history"],
        check_feats: ["store", "git", "include_orphans", "note_store",
                      "min_coverage", "loose_history"],
        compute_review: ["feats", "policy"],
        compute_note_stats: ["store"],
    }
    for fn, params in sigs.items():
        got = list(inspect.signature(fn).parameters)
        assert got == params, f"{fn.__name__} 签名变了：{got}"
