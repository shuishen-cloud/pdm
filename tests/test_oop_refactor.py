# -*- coding: utf-8 -*-
"""接口重构的测试（oop-refactor）。

设计见 ``doc/feat/oop-refactor.md``。三批：
1. 类型化返回值（解 A1/A3/A7）
2. 门面对象（解 A6）
3. 单一真相 + 守卫（解 B1/B3/B4）
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from pdev import Actor, CommitNote, NoteKind, NoteStore
from pdev.feat import Feat, FeatKind, FeatStore


@pytest.fixture
def feat_store(tmp_path) -> FeatStore:
    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(
        slug="alpha", title="功能甲", kind=FeatKind.FEAT,
        doc="feat/alpha.md",
        api=["Alpha.run(x) -> int", "Alpha.stop() -> None"],
        logs=["运行日志"],
        fallbacks=["降级为 0"],
        data_model=["Alpha: dict[str,int]"],
        samples=['{"a": 1}'],
        changes=["pdev/x.py::Alpha —— 新增"],
    ))
    return fs


@pytest.fixture
def note_store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add(CommitNote(commit="abc1234def", kind=NoteKind.PITFALL,
                     title="竞态", author=Actor("human:lwy")))
    return s


# ---------------------------------------------------------------------------
# 批次 1：类型化返回值
# ---------------------------------------------------------------------------


def test_review_counts_is_named_type(feat_store):
    """review_counts 返回具名类型，不再是可以解包的裸 tuple。"""
    from pdev.feat import ReviewCounts

    c = feat_store.get("alpha").review_counts()
    assert isinstance(c, ReviewCounts)
    # 属性访问（不是解包）
    assert c.total == 6          # doc + api:0/1 + logs + fallbacks + data_model + samples + changes
    assert c.reviewed == 0
    assert c.tested == 0
    assert c.coverage == 0.0


def test_review_counts_not_unpackable(feat_store):
    """具名类型不得支持 3 元解包（避免退回旧习惯）。"""
    c = feat_store.get("alpha").review_counts()
    with pytest.raises((TypeError, ValueError)):
        a, b, d = c


def test_review_counts_coverage_no_divzero():
    from pdev.feat import ReviewCounts

    c = ReviewCounts(total=0, reviewed=0, tested=0)
    assert c.coverage == 0.0


def test_review_items_named_type(feat_store):
    from pdev.feat import ReviewItemRef

    items = feat_store.get("alpha").review_items()
    assert items and all(isinstance(i, ReviewItemRef) for i in items)
    assert items[0].key == "doc"
    assert items[0].label


def test_commented_items_named_type(feat_store):
    from pdev.feat import ReviewItemRef

    fs = feat_store
    fs.set_reviews("alpha", ["api:0"], reviewed=True, by="human:lwy")
    fs.get("alpha").set_comment("api:0", "评语")
    fs.update(fs.get("alpha"))
    items = fs.get("alpha").commented_items()
    assert items and isinstance(items[0], ReviewItemRef)
    assert items[0].comment == "评语"


def test_check_summary_named_type(feat_store, note_store):
    from pdev.check import CheckSummary, check_feats, summarize

    issues = check_feats(feat_store, note_store=note_store)
    s = summarize(issues)
    assert isinstance(s, CheckSummary)
    assert s.total == len(issues)
    assert s.error + s.warning == s.total


def test_parsed_target_named_type():
    from pdev.scripts import ParsedTarget, parse_target

    p = parse_target("pytest tests/x.py -q")
    assert isinstance(p, ParsedTarget)
    assert p.command == "pytest"
    assert "tests/x.py" in p.args


def test_feat_dict_fields_have_element_types():
    """reviews/comments/stage_reviews 的标注应带元素类型。"""
    import inspect
    import re

    from pdev import feat as feat_mod

    src = inspect.getsource(feat_mod)
    for name, elem in (("reviews", "ReviewItem"),
                       ("comments", "str"),
                       ("stage_reviews", "StageReview")):
        pat = re.compile(rf"^\s+{name}:.*{elem}", re.M)
        assert pat.search(src), f"{name} 字段标注缺元素类型 {elem}"


# ---------------------------------------------------------------------------
# 批次 2：门面对象
# ---------------------------------------------------------------------------


def test_ledger_facade_roundtrip(tmp_path):
    """门面：一个入口完成"记笔记 + 建 feat + 总览"。"""
    from pdev.api import open_ledger

    ledger = open_ledger(root=str(tmp_path / ".pdm"), cwd=str(tmp_path))
    note = ledger.record(commit="abc1234", kind="pitfall", title="竞态",
                         detail="详情", by="human:lwy")
    assert note.commit == "abc1234"
    assert note.kind is NoteKind.PITFALL

    ledger.features.new(slug="demo", title="演示")
    assert ledger.features.get("demo").title == "演示"

    ov = ledger.overview()
    assert ov.total == 1


def test_ledger_facade_hides_internals(tmp_path):
    """门面不暴露 Store/Enum（任务级接口）。"""
    from pdev.api import Ledger

    public = [n for n in dir(Ledger) if not n.startswith("_")]
    for forbidden in ("store", "note_store", "feat_store"):
        assert forbidden not in public, f"门面不应暴露 {forbidden}"


def test_ledger_record_kind_accepts_plain_string(tmp_path):
    """门面接受普通字符串 kind，不要求调用者知道 NoteKind 枚举。"""
    from pdev.api import open_ledger

    ledger = open_ledger(root=str(tmp_path / ".pdm"), cwd=str(tmp_path))
    n = ledger.record(commit="abc1234", kind="difficulty", title="难点")
    assert n.kind is NoteKind.DIFFICULTY


# ---------------------------------------------------------------------------
# 批次 3：单一真相 + 守卫
# ---------------------------------------------------------------------------


def test_kind_specs_single_source():
    """kind 的展示信息有单一来源。"""
    from pdev.note import KIND_SPECS, KindSpec, NoteKind

    assert KIND_SPECS
    for k in NoteKind:
        assert k.value in KIND_SPECS, f"缺 {k.value} 的 spec"
        spec = KIND_SPECS[k.value]
        assert isinstance(spec, KindSpec)
        assert spec.short
        assert spec.color


def test_kind_spec_is_debt_matches_enum():
    """spec 的 is_debt 必须与 NoteKind.is_debt 一致（防分叉）。"""
    from pdev.note import KIND_SPECS, NoteKind

    for k in NoteKind:
        assert KIND_SPECS[k.value].is_debt == k.is_debt, k.value


def test_no_hardcoded_stage_sequence():
    """除 stage.py 外，不得硬编码阶段序列字面量。"""
    import re

    offenders = []
    for p in sorted((ROOT / "pdev").rglob("*.py")):
        if p.name == "stage.py":
            continue
        src = p.read_text(encoding="utf-8")
        # 连续出现 3 个以上阶段名的字面量
        if re.search(r'["\']doc["\']\s*,\s*["\']test["\']', src):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"硬编码阶段序列：{offenders}"


def test_no_hardcoded_coverage_default():
    """覆盖率默认阈值只应有一处定义。"""
    import re

    hits = []
    for p in sorted((ROOT / "pdev").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"min_coverage\s*:\s*float\s*=\s*([0-9.]+)", src):
            hits.append((str(p.relative_to(ROOT)), m.group(1)))
        for m in re.finditer(r"min_coverage\s*=\s*([0-9.]+)\s*$", src, re.M):
            hits.append((str(p.relative_to(ROOT)), m.group(1)))
    assert len(hits) <= 1, f"覆盖率阈值多处定义：{hits}"


def test_stage_sequence_single_definition():
    """阶段序列只在 stage.py 定义。"""
    from pdev.stage import STAGE_SEQUENCE

    assert STAGE_SEQUENCE == ("doc", "test", "script", "feat", "fix", "close")
    # check.py 的 STAGES 应从 STAGE_SEQUENCE 派生
    from pdev.check import STAGES

    assert set(STAGES) <= set(STAGE_SEQUENCE)


# ---------------------------------------------------------------------------
# 兼容性
# ---------------------------------------------------------------------------


def test_old_json_still_loads(tmp_path):
    """旧格式 JSON（无新字段/裸结构）必须仍可读。"""
    d = tmp_path / "feats" / "by-id"
    d.mkdir(parents=True)
    (d / "legacy.json").write_text(json.dumps({
        "slug": "legacy", "title": "旧数据", "kind": "feat",
        "status": "draft", "api": ["f() -> int"],
        "reviews": {"api:0": {"reviewed": True, "reviewed_by": "human:lwy"}},
        "comments": {"api:0": "旧评论"},
    }, ensure_ascii=False), encoding="utf-8")

    fs = FeatStore(tmp_path / "feats")
    f = fs.get("legacy")
    assert f is not None and f.title == "旧数据"
    assert f.review_item("api:0").reviewed is True
    assert f.comment("api:0") == "旧评论"
    c = f.review_counts()
    assert c.total == 1 and c.reviewed == 1


def test_cli_summary_still_works(tmp_path):
    """CLI 行为不变：stats 命令仍能跑。"""
    r = subprocess.run(
        [sys.executable, "-m", "pdev.cli", "stats", "--store", str(tmp_path / "n")],
        capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode in (0, 1), r.stderr
