# -*- coding: utf-8 -*-
"""pdev.check 的测试：Feat 自约束校验。"""

from __future__ import annotations

import subprocess

import pytest

from pdev.feat import Feat, FeatStatus, FeatStore
from pdev.check import (
    CheckIssue,
    check_feats,
    check_one,
    format_issue,
)
from tests.fixtures.feat_storage import (
    BARE_FEAT,
    CLOSED_NO_COMMIT,
    DRAFT_WITH_COMMIT,
    GOOD_FEAT,
)


@pytest.fixture
def store(tmp_path) -> FeatStore:
    return FeatStore(tmp_path / "feats")


def codes(issues) -> set:
    return {i.code for i in issues}


def add(store: FeatStore, data: dict) -> Feat:
    f = Feat(**data)
    store.add(f)
    return f


# ---------------------------------------------------------------------------
# 规则：draft-has-commit
# ---------------------------------------------------------------------------


def test_draft_with_commit_is_warning(store):
    add(store, DRAFT_WITH_COMMIT)
    issues = check_one(store, "draft-commit")
    assert "draft-has-commit" in codes(issues)
    assert all(i.level == "warning"
               for i in issues if i.code == "draft-has-commit")


def test_closed_with_commit_is_clean(store):
    add(store, GOOD_FEAT)
    issues = [i for i in check_one(store, "good-feat")
              if i.level == "error"]
    assert issues == []


# ---------------------------------------------------------------------------
# 规则：closed-no-commit
# ---------------------------------------------------------------------------


def test_closed_without_commit_is_error(store):
    add(store, CLOSED_NO_COMMIT)
    issues = check_one(store, "closed-empty")
    hit = [i for i in issues if i.code == "closed-no-commit"]
    assert hit and hit[0].level == "error"


# ---------------------------------------------------------------------------
# 规则：字段完整性
# ---------------------------------------------------------------------------


def test_bare_feat_reports_missing_fields(store):
    add(store, BARE_FEAT)
    cs = codes(check_one(store, "bare"))
    assert "empty-doc" in cs
    assert "no-api" in cs
    assert "no-fallback" in cs


def test_full_feat_no_field_warnings(store):
    add(store, GOOD_FEAT)
    cs = codes(check_one(store, "good-feat"))
    assert "empty-doc" not in cs
    assert "no-api" not in cs
    assert "no-fallback" not in cs


# ---------------------------------------------------------------------------
# 规则：discovered-not-closed
# ---------------------------------------------------------------------------


def test_discovered_but_not_closed(store):
    f = Feat(slug="a", title="A", status=FeatStatus.FIXING)
    store.add(f)
    store.add_discovered("a", "发现了问题")
    assert "discovered-not-closed" in codes(check_one(store, "a"))


def test_discovered_and_closed_ok(store):
    f = Feat(slug="a", title="A", doc="d", api=["f()"],
             fallbacks=["x"], commits=["c1"])
    store.add(f)
    store.add_discovered("a", "发现")
    store.set_status("a", FeatStatus.TESTING)
    store.set_status("a", FeatStatus.INTEGRATED)
    store.set_status("a", FeatStatus.FIXING)
    store.set_status("a", FeatStatus.CLOSED)
    assert "discovered-not-closed" not in codes(check_one(store, "a"))


# ---------------------------------------------------------------------------
# 规则：commit-conflict
# ---------------------------------------------------------------------------


def test_commit_conflict_is_error(store):
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": ["shared1"]})
    add(store, {"slug": "b", "title": "B", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": ["shared1"]})
    issues = check_feats(store)
    conflict = [i for i in issues if i.code == "commit-conflict"]
    assert conflict and conflict[0].level == "error"


def test_no_conflict_when_commits_distinct(store):
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": ["c1"]})
    add(store, {"slug": "b", "title": "B", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": ["c2"]})
    assert "commit-conflict" not in codes(check_feats(store))


# ---------------------------------------------------------------------------
# 规则：commit-missing（需要 git）
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "first")
    return tmp_path


def test_commit_missing_detected(store, git_repo):
    from pdev.git import GitRepo

    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": ["deadbeef"]})
    issues = check_feats(store, git=GitRepo(str(git_repo)))
    assert "commit-missing" in codes(issues)


def test_real_commit_not_missing(store, git_repo):
    from pdev.git import GitRepo

    repo = GitRepo(str(git_repo))
    real = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [real]})
    issues = check_feats(store, git=repo)
    assert "commit-missing" not in codes(issues)


# ---------------------------------------------------------------------------
# 规则：orphan-commit
# ---------------------------------------------------------------------------


def test_orphan_commit_detected(store, git_repo):
    from pdev.git import GitRepo

    # 仓库有 1 个 commit，但没有任何 feat 认领
    issues = check_feats(store, git=GitRepo(str(git_repo)))
    assert "orphan-commit" in codes(issues)


def test_no_orphan_when_claimed(store, git_repo):
    from pdev.git import GitRepo

    repo = GitRepo(str(git_repo))
    real = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [real]})
    issues = check_feats(store, git=repo)
    assert "orphan-commit" not in codes(issues)


def test_orphan_check_skipped_without_git(store):
    add(store, GOOD_FEAT)
    # 不传 git → 不应出现与 git 相关的检查
    cs = codes(check_feats(store))
    assert "orphan-commit" not in cs
    assert "commit-missing" not in cs


# ---------------------------------------------------------------------------
# 汇总与格式
# ---------------------------------------------------------------------------


def test_check_all_returns_issues_for_every_feat(store):
    add(store, DRAFT_WITH_COMMIT)
    add(store, CLOSED_NO_COMMIT)
    add(store, BARE_FEAT)
    issues = check_feats(store)
    assert {i.slug for i in issues} >= {"draft-commit", "closed-empty", "bare"}


def test_check_one_unknown_slug_raises(store):
    with pytest.raises(Exception):
        check_one(store, "nope")


def test_format_issue_contains_code_and_message():
    issue = CheckIssue(slug="a", code="no-api", level="warning",
                       message="缺少 api")
    text = format_issue(issue)
    assert "a" in text and "no-api" in text and "缺少 api" in text


def test_format_issue_marks_level():
    err = CheckIssue(slug="a", code="x", level="error", message="m")
    warn = CheckIssue(slug="a", code="y", level="warning", message="m")
    assert "✗" in format_issue(err) or "error" in format_issue(err)
    assert "!" in format_issue(warn) or "warning" in format_issue(warn)


def test_clean_store_has_no_issues(store):
    add(store, GOOD_FEAT)
    assert check_feats(store) == []


def test_short_hash_prefix_not_orphan(store, git_repo):
    """feat 里存 7 位短 hash，git 给 8 位——不应误报 orphan。"""
    from pdev.git import GitRepo

    repo = GitRepo(str(git_repo))
    full = repo.log()[0].hash
    short7 = full[:7]
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [short7]})
    issues = check_feats(store, git=repo)
    assert "orphan-commit" not in codes(issues)
