# -*- coding: utf-8 -*-
"""pdev.stage 与阶段提交门面的测试。"""

from __future__ import annotations

import subprocess

import pytest

from pdev.feat import Feat, FeatStore
from pdev.git import GitRepo
from pdev.stage import (
    STAGE_SEQUENCE,
    StageError,
    assert_allowed,
    format_subject,
    infer_stage,
    next_stages,
)


# ---------------------------------------------------------------------------
# 纯逻辑：next_stages / assert_allowed
# ---------------------------------------------------------------------------


def test_sequence_shape():
    assert STAGE_SEQUENCE == ("doc", "test", "script", "feat", "fix", "close")


def test_next_stages_unstarted():
    assert next_stages(None) == ["doc"]


def test_next_stages_allows_stay_and_advance():
    assert next_stages("doc") == ["doc", "test"]
    assert next_stages("fix") == ["fix", "close"]


def test_next_stages_terminal():
    assert next_stages("close") == ["close"]


def test_assert_allowed_ok():
    assert assert_allowed(None, "doc") == "doc"
    assert assert_allowed("doc", "test") == "test"
    assert assert_allowed("feat", "feat") == "feat"


def test_assert_allowed_rejects_backward():
    with pytest.raises(StageError):
        assert_allowed("test", "doc")
    with pytest.raises(StageError):
        assert_allowed("feat", "test")


def test_assert_allowed_rejects_skip():
    with pytest.raises(StageError):
        assert_allowed(None, "feat")
    with pytest.raises(StageError):
        assert_allowed("doc", "fix")


def test_assert_allowed_unknown_stage():
    with pytest.raises(StageError):
        assert_allowed(None, "nope")


# ---------------------------------------------------------------------------
# 提交信息格式
# ---------------------------------------------------------------------------


def test_format_subject():
    assert format_subject("feat", "demo", "实现") == "feat(demo): 实现"
    assert format_subject("close", "demo", "收尾") == "doc(demo): 收尾"


def test_format_subject_multiline_takes_first_line():
    assert format_subject("fix", "d", "首行\n次行") == "fix(d): 首行"


def test_format_subject_empty_raises():
    with pytest.raises(StageError):
        format_subject("doc", "d", "   ")


# ---------------------------------------------------------------------------
# git 集成：真实提交 + 顺序强制
# ---------------------------------------------------------------------------


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    cwd = str(tmp_path)
    _git("init", "-q", cwd=cwd)
    _git("config", "user.email", "t@example.com", cwd=cwd)
    _git("config", "user.name", "Tester", cwd=cwd)
    (tmp_path / "a.txt").write_text("0", encoding="utf-8")
    _git("add", "-A", cwd=cwd)
    _git("commit", "-q", "-m", "init: 初始", cwd=cwd)
    return tmp_path


@pytest.fixture
def store(tmp_path) -> FeatStore:
    return FeatStore(tmp_path / "feats")


def _commit_change(repo, text):
    (repo / "a.txt").write_text(text, encoding="utf-8")
    _git("add", "-A", cwd=str(repo))


def test_full_pipeline(repo, store):
    store.add(Feat(slug="demo", title="演示"))
    git = GitRepo(str(repo))

    stages = ["doc", "test", "feat", "fix", "close"]
    for i, stage in enumerate(stages):
        _commit_change(repo, str(i))
        feat, h, old, new = store.commit_stage(
            "demo", stage, f"{stage} 步骤", cwd=str(repo), git=git,
        )
        assert h
        assert new == stage
        assert h in feat.commits

    assert feat.stage == "close"
    # git log 前缀按序
    log = subprocess.run(
        ["git", "log", "--format=%s"], cwd=str(repo),
        capture_output=True, text=True,
    ).stdout
    assert "doc(demo): doc 步骤" in log
    assert "fix(demo): fix 步骤" in log
    assert "doc(demo): close 步骤" in log


def test_reject_backward(repo, store):
    store.add(Feat(slug="demo", title="演示"))
    git = GitRepo(str(repo))

    _commit_change(repo, "1")
    store.commit_stage("demo", "doc", "设计", cwd=str(repo), git=git)
    _commit_change(repo, "2")
    store.commit_stage("demo", "test", "测试", cwd=str(repo), git=git)

    _commit_change(repo, "3")
    with pytest.raises(StageError):
        store.commit_stage("demo", "doc", "回退", cwd=str(repo), git=git)

    # 被拒绝后 feat.commits 不应增长
    assert store.get("demo").stage == "test"


def test_commit_close_marks_closed(repo, store):
    from pdev.feat import FeatStatus

    store.add(Feat(slug="demo", title="演示"))
    git = GitRepo(str(repo))

    for i, stage in enumerate(["doc", "test", "feat", "fix"]):
        _commit_change(repo, str(i))
        store.commit_stage("demo", stage, stage, cwd=str(repo), git=git)

    _commit_change(repo, "9")
    feat, _, _, _ = store.commit_stage(
        "demo", "close", "收尾", cwd=str(repo), git=git, close=True,
    )
    assert feat.status is FeatStatus.CLOSED


def test_stage_persisted_across_reload(repo, store, tmp_path):
    store.add(Feat(slug="demo", title="演示"))
    git = GitRepo(str(repo))
    _commit_change(repo, "1")
    store.commit_stage("demo", "doc", "设计", cwd=str(repo), git=git)

    reopened = FeatStore(tmp_path / "feats")
    assert reopened.get("demo").stage == "doc"


def test_legacy_infer_stage(repo, store):
    """旧数据无 stage 字段时，从 commit 前缀推断游标。"""
    git = GitRepo(str(repo))
    _commit_change(repo, "1")
    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): 实现"],
                   cwd=str(repo), check=True)

    hash_ = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo),
        capture_output=True, text=True,
    ).stdout.strip()

    store.add(Feat(slug="legacy", title="旧", commits=[hash_]))
    # 无 stage：推断为 feat，test 应被拒
    with pytest.raises(StageError):
        store.commit_stage("legacy", "test", "回退", cwd=str(repo), git=git)


def test_infer_stage_helper(repo):
    git = GitRepo(str(repo))
    _commit_change(repo, "1")
    subprocess.run(["git", "commit", "-q", "-m", "test(x): 测试"],
                   cwd=str(repo), check=True)
    h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                       capture_output=True, text=True).stdout.strip()
    assert infer_stage([h], git) == "test"


def test_infer_stage_empty():
    assert infer_stage([], None) is None


def test_commit_no_verify(repo, store):
    """--no-verify 能跳过失败的 pre-commit 钩子。"""
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    store.add(Feat(slug="demo", title="演示"))
    git = GitRepo(str(repo))
    _commit_change(repo, "1")

    # 默认会被钩子拦截
    with pytest.raises(StageError):
        store.commit_stage("demo", "doc", "设计", cwd=str(repo), git=git)

    # --no-verify 通过
    feat, h, _, _ = store.commit_stage(
        "demo", "doc", "设计", cwd=str(repo), git=git, no_verify=True,
    )
    assert h


# ---------------------------------------------------------------------------
# previous_stage（stage-review）
# ---------------------------------------------------------------------------


def test_previous_stage():
    from pdev.stage import previous_stage

    assert previous_stage("doc") is None
    assert previous_stage("test") == "doc"
    assert previous_stage("script") == "test"
    assert previous_stage("feat") == "script"
    assert previous_stage("fix") == "feat"
    assert previous_stage("close") == "fix"


def test_previous_stage_bad():
    from pdev.stage import StageError, previous_stage

    with pytest.raises(StageError):
        previous_stage("nope")


# ---------------------------------------------------------------------------
# 阶段审核门禁（stage-review）
# ---------------------------------------------------------------------------


def test_commit_blocked_when_prev_stage_unreviewed(tmp_path):
    from pdev.feat import FeatStore
    from pdev.stage import StageError

    store = FeatStore(tmp_path / "feats")
    store.add(Feat(slug="a", title="A", api=["f()"], stage="doc"))
    with pytest.raises(StageError, match="尚未人工审核"):
        store.commit_stage("a", "test", "t", cwd=str(tmp_path),
                           dry_run=True, require_stage_review=True)


def test_commit_passes_after_prev_reviewed(tmp_path):
    from pdev.feat import FeatStore

    store = FeatStore(tmp_path / "feats")
    store.add(Feat(slug="a", title="A", api=["f()"], stage="doc"))
    store.review_stage("a", "doc", "human:lwy")
    # 不应抛
    store.commit_stage("a", "test", "t", cwd=str(tmp_path),
                       dry_run=True, require_stage_review=True)


def test_commit_no_gate_when_disabled(tmp_path):
    from pdev.feat import FeatStore

    store = FeatStore(tmp_path / "feats")
    store.add(Feat(slug="a", title="A", api=["f()"], stage="doc"))
    store.commit_stage("a", "test", "t", cwd=str(tmp_path),
                       dry_run=True, require_stage_review=False)


def test_commit_no_gate_for_legacy_feat(tmp_path):
    """历史 feat（早于强制起点）免门禁。"""
    from datetime import datetime

    from pdev.feat import FeatStore

    store = FeatStore(tmp_path / "feats")
    store.add(Feat(slug="old", title="旧", api=["f()"], stage="doc",
                   created_at=datetime.fromisoformat(
                       "2026-01-01T00:00:00+00:00")))
    store.commit_stage("old", "test", "t", cwd=str(tmp_path),
                       dry_run=True, require_stage_review=True)


# ---------------------------------------------------------------------------
# script 可选阶段（script-stage）
# ---------------------------------------------------------------------------


def test_sequence_has_script_between_test_and_feat():
    from pdev.stage import STAGE_SEQUENCE

    i = STAGE_SEQUENCE.index("script")
    assert STAGE_SEQUENCE[i - 1] == "test"
    assert STAGE_SEQUENCE[i + 1] == "feat"


def test_next_stages_from_test_allows_skip():
    """test 可直接进 feat（跳过可选的 script）。"""
    assert set(next_stages("test")) == {"test", "script", "feat"}


def test_next_stages_from_script():
    assert set(next_stages("script")) == {"script", "feat"}


def test_next_stages_from_doc():
    assert set(next_stages("doc")) == {"doc", "test"}


def test_script_in_optional_stages():
    from pdev.stage import OPTIONAL_STAGES

    assert "script" in OPTIONAL_STAGES
    assert "feat" not in OPTIONAL_STAGES


def test_format_subject_script():
    from pdev.stage import format_subject

    assert format_subject("script", "a", "先跑通 MVP") == \
        "script(a): 先跑通 MVP"


def test_subject_prefix_recognizes_script():
    from pdev.stage import _subject_prefix

    assert _subject_prefix("script(a): x") == "script"


def test_assert_allowed_script_path():
    from pdev.stage import assert_allowed

    assert assert_allowed("test", "script") == "script"
    assert assert_allowed("test", "feat") == "feat"      # 跳过 script
    assert assert_allowed("script", "feat") == "feat"
    with pytest.raises(StageError):
        assert_allowed("feat", "script")                 # 倒退
