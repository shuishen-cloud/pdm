# -*- coding: utf-8 -*-
"""设计现状文档的一致性测试（design-audit）。

保证导出的文档与实际代码/数据一致——文档漂移一次就报一次。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "doc"
DATA_STRUCT = DOCS / "DATA_STRUCTURE_EXPORT.md"
INTERFACE = DOCS / "INTERFACE_AUDIT.md"
OBSERVATIONS = DOCS / "DESIGN_OBSERVATIONS.md"


def test_three_documents_exist():
    for p in (DATA_STRUCT, INTERFACE, OBSERVATIONS):
        assert p.is_file(), f"缺文档 {p.name}"
        assert p.read_text(encoding="utf-8").strip(), f"{p.name} 为空"


def test_data_structure_doc_covers_all_enums():
    """数据结构文档必须列出全部 Enum 取值（防漂移）。"""
    import enum

    import pdev

    text = DATA_STRUCT.read_text(encoding="utf-8")
    missing = []
    for name in dir(pdev):
        if name.startswith("_"):
            continue
        obj = getattr(pdev, name)
        if isinstance(obj, type) and issubclass(obj, enum.Enum):
            for member in obj:
                if member.value not in text:
                    missing.append(f"{name}.{member.value}")
    assert not missing, f"数据结构文档缺 Enum 取值：{missing[:8]}"


def test_data_structure_doc_mentions_all_dataclasses():
    """数据结构文档必须提到主要 dataclass。"""
    from dataclasses import is_dataclass

    import pdev
    from pdev.feat import ReviewItem, StageReview

    text = DATA_STRUCT.read_text(encoding="utf-8")
    objs = {
        "CommitNote": pdev.CommitNote,
        "Verification": pdev.Verification,
        "Feat": pdev.Feat,
        "ReviewItem": ReviewItem,
        "StageReview": StageReview,
        "Issue": pdev.Issue,
        "Fingerprint": pdev.Fingerprint,
        "Version": pdev.Version,
        "Config": pdev.Config,
    }
    for name, obj in objs.items():
        assert is_dataclass(obj), f"{name} 不是 dataclass"
        assert name in text, f"数据结构文档缺 {name}"


def test_review_item_not_exported_at_top_level():
    """记录一个事实：ReviewItem/StageReview 未在 pdev 顶层导出。

    这本身是可读性问题（使用者必须知道去 pdev.feat 里找）。
    若将来导出，本测试会失败——届时更新观察文档。
    """
    import pdev

    assert not hasattr(pdev, "ReviewItem"), \
        "ReviewItem 已导出，请更新 DESIGN_OBSERVATIONS.md"
    assert not hasattr(pdev, "StageReview")


def test_interface_audit_mentions_real_functions():
    """接口审计里点名的 D 级函数必须真的存在。"""
    from pdev import webui
    from pdev.check import summarize
    from pdev.feat import Feat
    from pdev.scripts import parse_target

    assert callable(summarize)
    assert callable(parse_target)
    assert hasattr(Feat, "review_counts")
    assert hasattr(Feat, "review_items")
    assert hasattr(Feat, "commented_items")
    assert hasattr(webui, "build_data")


def test_observations_have_evidence_sections():
    """观察文档每条都应有「原话要点」与「核实结论」。"""
    text = OBSERVATIONS.read_text(encoding="utf-8")
    assert text.count("**原话要点**") >= 5
    assert text.count("**核实结论**") >= 5


def test_observations_include_critical_lessons():
    """关键教训必须记录在案。"""
    text = OBSERVATIONS.read_text(encoding="utf-8")
    for kw in ("主数据是 commit", "伪造", "掌握感", "Event Sourcing",
               "加一个 kind 要改 6 处"):
        assert kw in text, f"观察文档缺关键内容：{kw}"


def test_fake_review_checker_runs():
    """防伪检查脚本可执行且当前通过（无批量伪造痕迹）。"""
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_no_fake_reviews.py")],
        capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, f"检测到批量审查痕迹：{r.stdout}"
    assert "OK" in r.stdout


def test_fake_review_checker_detects_planted_batch(tmp_path):
    """脚本必须能识别人为植入的批量记录（不能永远返回 OK）。"""
    import json
    import subprocess
    import sys

    # 造一个含"同秒 5 条"的 feat store
    d = tmp_path / ".pdm" / "feats" / "by-id"
    d.mkdir(parents=True)
    same = "2026-01-01T00:00:00+00:00"
    (d / "fake.json").write_text(json.dumps({
        "slug": "fake", "title": "t",
        "reviews": {f"api:{i}": {"reviewed": True, "reviewed_at": same}
                    for i in range(5)},
    }, ensure_ascii=False), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_no_fake_reviews.py")],
        capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 1, "应识别出批量伪造"
    assert "疑似" in r.stdout or "发现" in r.stdout
