# -*- coding: utf-8 -*-
"""feat edit 命令与新字段的测试。

对应 ``doc/feat/feat-edit-fields.md``。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pytest

from pdev.check import check_one
from pdev.feat import Feat, FeatImportance, FeatStore


# --- 夹具 -------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> FeatStore:
    s = FeatStore(tmp_path / "feats")
    s.add(Feat(
        slug="demo", title="演示",
        api=["run() -> int"], logs=["启动"], fallbacks=["失败降级"],
        design_note="为什么", impl_note="怎么做",
        data_model=["D: dict"], samples=["{'k': 1}"],
        changes=["pdev/x.py::Y —— 新增"],
        test_note="pytest tests/test_x.py::test_y",
        debug_note="断点在 parse()",
        extend_note="要支持多级则改 Node.children",
        impact="改动序列化，旧 JSON 靠默认值兼容",
        importance=FeatImportance.HIGH,
    ))
    return s


def _args(**kw) -> argparse.Namespace:
    """构造 cmd_feat_edit 的参数命名空间（未指定的为 None）。"""
    base = {
        "slug": "demo",
        "title": None, "doc": None,
        "design_note": None, "impl_note": None,
        "test_note": None, "debug_note": None,
        "extend_note": None, "impact": None, "importance": None,
    }
    for name in ("api", "logs", "fallbacks", "data_model", "samples",
                 "changes"):
        base[f"add_{name}"] = None
        base[f"remove_{name}"] = None
        base[f"set_{name}"] = None
    base.update(kw)
    return argparse.Namespace(**base)


def _run_edit(store, monkeypatch, **kw) -> int:
    """跑 cmd_feat_edit，把 store 注入到 _feat_store。"""
    from pdev.cli import commands

    monkeypatch.setattr(commands, "_feat_store", lambda ctx: store)
    return commands.cmd_feat_edit(object(), _args(**kw))


# --- 字段：持久化与向后兼容 --------------------------------------------------


def test_new_fields_roundtrip(tmp_path):
    """五个新字段能存能读（含枚举）。"""
    root = tmp_path / "feats"
    FeatStore(root).add(Feat(
        slug="x", title="t", importance=FeatImportance.CRITICAL,
        test_note="tn", debug_note="dn", extend_note="en", impact="im"))
    got = FeatStore(root).get("x")
    assert got.importance is FeatImportance.CRITICAL
    assert (got.test_note, got.debug_note, got.extend_note, got.impact) == \
        ("tn", "dn", "en", "im")


def test_old_json_without_new_fields(tmp_path):
    """旧 JSON 无新字段 → 默认值，不报错（向后兼容）。"""
    root = tmp_path / "feats"
    d = root / "by-id"
    d.mkdir(parents=True)
    (d / "old.json").write_text(json.dumps({
        "slug": "old", "title": "旧的",
        "api": ["a()"], "logs": [], "fallbacks": [],
        "design_note": "d", "impl_note": "i",
        "data_model": [], "samples": [], "changes": [],
    }), encoding="utf-8")
    f = FeatStore(root).get("old")
    assert f.importance is None
    assert f.test_note == "" and f.impact == ""


def test_importance_rejects_unknown():
    with pytest.raises(ValueError):
        FeatImportance("super-high")


def test_missing_required_fields_includes_new():
    missing = Feat(slug="x", title="t").missing_required_fields()
    assert "测试方式" in missing
    assert "对现有系统的影响" in missing
    assert "重要性" in missing


def test_missing_required_fields_empty_when_complete():
    f = Feat(
        slug="x", title="t", design_note="a", impl_note="b",
        data_model=["d"], samples=["s"], changes=["pdev/a.py::B —— x"],
        test_note="t", impact="i", importance=FeatImportance.LOW,
    )
    assert f.missing_required_fields() == []


# --- 可审项：整块文本纳入（本次行为变更） ------------------------------------


def test_design_fields_are_reviewable():
    f = Feat(slug="x", title="t", design_note="为什么", impl_note="怎么做",
             test_note="怎么测", impact="影响",
             importance=FeatImportance.HIGH, api=["a()"])
    keys = {r.key for r in f.review_items()}
    for k in ("design_note", "impl_note", "test_note", "impact",
              "importance"):
        assert k in keys, f"{k} 应该是可审项"
    assert "api:0" in keys


def test_empty_text_fields_are_not_reviewable():
    f = Feat(slug="x", title="t", debug_note="", extend_note="")
    keys = {r.key for r in f.review_items()}
    assert "debug_note" not in keys
    assert "extend_note" not in keys


# --- check：missing-review 与严格度开关 -------------------------------------


def _feat_for_check(**kw) -> Feat:
    base = dict(
        slug="c", title="t", doc="feat/c.md",
        api=["a()"], logs=[], fallbacks=[], data_model=["d"], samples=["s"],
        changes=["pdev/a.py::B —— x"],
        design_note="dn", impl_note="in", test_note="tn",
        impact="im", importance=FeatImportance.LOW,
    )
    base.update(kw)
    return Feat(**base)


class _FakeStore:
    """只实现 check_one 需要的接口。"""

    def __init__(self, feat) -> None:
        self._feat = feat

    def get(self, slug):
        return self._feat if slug == self._feat.slug else None

    def all(self):
        return [self._feat]


def test_missing_review_reports_each_item():
    issues = check_one(_FakeStore(_feat_for_check()), "c", None)
    codes = [i.code for i in issues]
    assert "missing-review" in codes
    msg = " ".join(i.message for i in issues if i.code == "missing-review")
    assert "design_note" in msg or "api:0" in msg       # 具体到条目


def test_missing_review_silent_when_all_reviewed():
    f = _feat_for_check()
    for r in list(f.review_items()):
        f.set_reviewed(r.key, True, by="human:lwy")
    issues = check_one(_FakeStore(f), "c", None)
    assert "missing-review" not in [i.code for i in issues]


def test_strict_by_default_for_history():
    """默认严格：创建时间很早的 feat 缺字段也告警。"""
    f = _feat_for_check(test_note="", impact="", importance=None,
                        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    codes = [i.code for i in
             check_one(_FakeStore(f), "c", None, loose_history=False)]
    assert "missing-fields" in codes


def test_loose_history_suppresses_old_feat():
    """loose_history=True 时，历史 feat 的缺字段不再告警。"""
    f = _feat_for_check(test_note="", impact="", importance=None,
                        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    codes = [i.code for i in
             check_one(_FakeStore(f), "c", None, loose_history=True)]
    assert "missing-fields" not in codes


def test_loose_history_does_not_exempt_new_feat():
    """开关不影响新 feat：仍然严格。"""
    f = _feat_for_check(test_note="", impact="", importance=None,
                        created_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    codes = [i.code for i in
             check_one(_FakeStore(f), "c", None, loose_history=True)]
    assert "missing-fields" in codes


# --- 编辑：pdm feat edit ----------------------------------------------------


def test_edit_adds_list_item(store, monkeypatch):
    rc = _run_edit(store, monkeypatch,
                   add_changes=["pdev/y.py::Z —— 再加一条"])
    assert rc == 0
    got = store.get("demo")
    assert "pdev/y.py::Z —— 再加一条" in got.changes
    assert len(got.changes) == 2


def test_edit_removes_by_index(store, monkeypatch):
    assert _run_edit(store, monkeypatch, remove_changes=[0]) == 0
    got = store.get("demo")
    assert got.changes == []
    assert got.design_note == "为什么"          # 只动目标字段


def test_edit_remove_index_out_of_range(store, monkeypatch):
    assert _run_edit(store, monkeypatch, remove_changes=[9]) == 2
    assert len(store.get("demo").changes) == 1  # 未改动


def test_edit_sets_text_field(store, monkeypatch):
    assert _run_edit(store, monkeypatch,
                     debug_note="改成打在 main()") == 0
    assert store.get("demo").debug_note == "改成打在 main()"


def test_edit_sets_importance(store, monkeypatch):
    assert _run_edit(store, monkeypatch, importance="critical") == 0
    assert store.get("demo").importance is FeatImportance.CRITICAL


def test_edit_rejects_bad_importance(store, monkeypatch):
    assert _run_edit(store, monkeypatch, importance="super-high") == 2
    assert store.get("demo").importance is FeatImportance.HIGH


def test_edit_unknown_slug(store, monkeypatch):
    assert _run_edit(store, monkeypatch, slug="nope",
                     add_changes=["x"]) == 2


# --- 编辑可审项 → 自动撤销审查 ----------------------------------------------


def test_edit_reviewable_revokes_review(store, monkeypatch):
    """改了可审项内容 → 该条的 [审] 自动撤销。"""
    f = store.get("demo")
    f.set_reviewed("changes:0", True, by="human:lwy")
    store.update(f)
    assert store.get("demo").review_item("changes:0").reviewed is True

    rc = _run_edit(store, monkeypatch,
                   set_changes=["pdev/z.py::W —— 换成这条"])
    assert rc == 0
    got = store.get("demo")
    assert got.changes == ["pdev/z.py::W —— 换成这条"]
    assert getattr(got.review_item("changes:0"), "reviewed", False) is False, \
        "改内容后应撤销审查"


def test_edit_text_field_keeps_other_review(store, monkeypatch):
    """改一个整块文本字段 → 只影响它自己，不动其它审查位。"""
    f = store.get("demo")
    f.set_reviewed("api:0", True, by="human:lwy")
    store.update(f)
    _run_edit(store, monkeypatch, debug_note="新的调试说明")
    assert store.get("demo").review_item("api:0").reviewed is True


def test_edit_own_text_field_revokes_its_review(store, monkeypatch):
    """改**自身已被审**的整块文本字段 → 撤销**它自己**的审查。

    整块文本字段（design_note/impl_note/test_note/impact）已纳入可审项，
    因此内容变更同样使旧确认失效。这条行为在设计文档里曾漏写，
    本测试补上（fix 阶段回填）。
    """
    f = store.get("demo")
    f.set_reviewed("design_note", True, by="human:lwy")
    store.update(f)
    assert store.get("demo").review_item("design_note").reviewed is True

    assert _run_edit(store, monkeypatch, design_note="换成新的设计思路") == 0
    got = store.get("demo")
    assert got.design_note == "换成新的设计思路"
    assert getattr(got.review_item("design_note"), "reviewed", False) is False, \
        "改了自身内容应撤销该字段的审查"


def test_edit_importance_revokes_its_review(store, monkeypatch):
    """改 importance（也是可审项）→ 撤销它自己的审查。"""
    f = store.get("demo")
    f.set_reviewed("importance", True, by="human:lwy")
    store.update(f)
    assert _run_edit(store, monkeypatch, importance="low") == 0
    got = store.get("demo")
    assert got.importance is FeatImportance.LOW
    assert getattr(got.review_item("importance"), "reviewed", False) is False


def test_edit_preview_without_changes(store, monkeypatch, capsys):
    """不带修改参数 = 预览，返回 0 且不改动。"""
    before = store.get("demo").title
    assert _run_edit(store, monkeypatch) == 0
    assert store.get("demo").title == before
    assert "demo" in capsys.readouterr().out
