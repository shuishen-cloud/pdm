# -*- coding: utf-8 -*-
"""pdev.check 的测试：Feat 自约束校验。"""

from __future__ import annotations

import subprocess
from datetime import datetime

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


@pytest.fixture
def note_store(tmp_path):
    from pdev.store import NoteStore

    return NoteStore(tmp_path / "notes")


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
    """全审后的合规 feat 不产生任何问题（含审查规则）。"""
    f = add(store, GOOD_FEAT)
    for key, _ in f.review_items():
        f.set_reviewed(key)
    store.update(f)
    assert check_feats(store) == []


def test_unreviewed_feat_reports_review_warnings(store):
    """未审的合规 feat 现在会报 review 规则（行为变化）。"""
    add(store, GOOD_FEAT)
    got = codes(check_feats(store))
    assert "review-none" in got
    assert "review-low" in got


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


# ---------------------------------------------------------------------------
# 规则：stage-prefix / missing-stage（见 docs/feat/stage-prefix.md）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subject,expected", [
    ("doc(feat): 先写文档", "doc"),
    ("test(feat): 写测试", "test"),
    ("feat(tui): 实现", "feat"),
    ("fix(tui): 修 bug", "fix"),
    ("refactor(x): 重构", None),
    ("随便写点东西", None),
    ("", None),
])
def test_classify_stage(subject, expected):
    from pdev.check import classify_stage

    assert classify_stage(subject) == expected


def test_stage_prefix_warns_on_unknown_prefix(store, git_repo):
    from pdev.git import GitRepo

    repo = GitRepo(str(git_repo))
    # git_repo 里的提交信息是 "first"，无阶段前缀
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [repo.log()[0].hash]})
    issues = check_feats(store, git=repo)
    assert "stage-prefix" in codes(issues)


def test_stage_prefix_ok_when_prefixed(store, tmp_path):
    """提交信息带 doc/test/feat/fix 前缀时不告警。"""
    from pdev.git import GitRepo
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat(x): 实现")

    repo = GitRepo(str(tmp_path))
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [repo.log()[0].hash]})
    assert "stage-prefix" not in codes(check_feats(store, git=repo))


def test_missing_stage_on_closed_feat(store, git_repo):
    """closed 但只有 feat 阶段、缺 test/fix → missing-stage。"""
    from pdev.git import GitRepo
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(git_repo),
                              capture_output=True, text=True)

    (git_repo / "b.txt").write_text("y", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat(x): 只实现了没写测试")
    repo = GitRepo(str(git_repo))
    latest = repo.log()[0].hash

    f = Feat(slug="a", title="A", doc="d", api=["f()"],
             fallbacks=["x"], commits=[latest])
    store.add(f)
    for st in (FeatStatus.TESTING, FeatStatus.INTEGRATED,
               FeatStatus.FIXING, FeatStatus.CLOSED):
        store.set_status("a", st)
    assert "missing-stage" in codes(check_feats(store, git=repo))


def test_missing_stage_skipped_for_doc_kind(store, git_repo):
    """kind=doc 的历史归档豁免 missing-stage。"""
    from pdev.feat import FeatKind
    from pdev.git import GitRepo

    repo = GitRepo(str(git_repo))
    f = Feat(slug="hist", title="历史", kind=FeatKind.DOC,
             doc="d", api=["x"], fallbacks=["y"],
             commits=[repo.log()[0].hash])
    store.add(f)
    for st in (FeatStatus.TESTING, FeatStatus.INTEGRATED,
               FeatStatus.FIXING, FeatStatus.CLOSED):
        store.set_status("hist", st)
    assert "missing-stage" not in codes(check_feats(store, git=repo))


def test_stage_checks_skipped_without_git(store):
    add(store, GOOD_FEAT)
    cs = codes(check_feats(store))
    assert "stage-prefix" not in cs
    assert "missing-stage" not in cs


def test_neutral_prefixes_do_not_warn(store, tmp_path):
    """refactor/init 等合法前缀不应触发 stage-prefix。"""
    from pdev.git import GitRepo
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    for i, msg in enumerate(("refactor(x): 重构", "init: 初始化")):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", msg)
    repo = GitRepo(str(tmp_path))
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"],
                "commits": [i.hash for i in repo.log()]})
    assert "stage-prefix" not in codes(check_feats(store, git=repo))


# ---------------------------------------------------------------------------
# 规则：commit-no-note / note-no-verify（见 docs/feat/note-check.md）
# ---------------------------------------------------------------------------


def _git_repo_with(tmp_path, subjects):
    """建一个 git 仓库，按顺序提交给定的提交信息；返回 GitRepo。"""
    from pdev.git import GitRepo

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    for i, msg in enumerate(subjects):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", msg)
    return GitRepo(str(tmp_path))


def _note(commit, **kw):
    from pdev.note import CommitNote, NoteKind

    base = dict(commit=commit, kind=NoteKind.PITFALL, title="坑")
    base.update(kw)
    return CommitNote(**base)


def test_commit_no_note_warns_on_feat_commit(store, note_store, tmp_path):
    """feat( 提交没有笔记 → commit-no-note。"""
    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    issues = check_feats(store, git=repo, note_store=note_store)
    assert "commit-no-note" in codes(issues)
    assert all(i.level == "warning"
               for i in issues if i.code == "commit-no-note")


def test_commit_no_note_ok_when_note_exists(store, note_store, tmp_path):
    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    note_store.add(_note(h[:7]))          # 短 hash 也应匹配
    assert "commit-no-note" not in codes(
        check_feats(store, git=repo, note_store=note_store))


def test_commit_no_note_skips_doc_and_test_stages(store, note_store, tmp_path):
    """doc( / test( 提交豁免：文档无需笔记，测试本身即验证。"""
    repo = _git_repo_with(tmp_path, ["doc(x): 设计", "test(x): 用例"])
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"],
                "commits": [i.hash for i in repo.log()]})
    assert "commit-no-note" not in codes(
        check_feats(store, git=repo, note_store=note_store))


def test_note_no_verify_warns_when_all_empty(store, note_store, tmp_path):
    """有笔记但全部未绑验证 → note-no-verify。"""
    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    note_store.add(_note(h[:7]))
    assert "note-no-verify" in codes(
        check_feats(store, git=repo, note_store=note_store))


def test_note_no_verify_ok_when_one_bound(store, note_store, tmp_path):
    """只要有一条笔记绑定验证，即视为通过。"""
    from pdev.note import Verification, VerificationKind

    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    note_store.add(_note(h[:7], title="有验证的坑", verifications=[
        Verification(kind=VerificationKind.TEST,
                     target="tests/x.py::test_y")]))
    note_store.add(_note(h[:7], title="没验证的坑"))
    assert "note-no-verify" not in codes(
        check_feats(store, git=repo, note_store=note_store))


def test_note_rules_skipped_without_note_store(store, tmp_path):
    """未传 note_store → 两条规则整体跳过（向后兼容）。"""
    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    cs = codes(check_feats(store, git=repo))
    assert "commit-no-note" not in cs
    assert "note-no-verify" not in cs


def test_note_rules_skipped_without_git(store, note_store):
    add(store, GOOD_FEAT)
    cs = codes(check_feats(store, note_store=note_store))
    assert "commit-no-note" not in cs
    assert "note-no-verify" not in cs


def test_check_one_accepts_note_store(store, note_store, tmp_path):
    """check_one 也应支持 note_store 参数。"""
    repo = _git_repo_with(tmp_path, ["feat(x): 实现"])
    h = repo.log()[0].hash
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": [h]})
    issues = check_one(store, "a", git=repo, note_store=note_store)
    assert "commit-no-note" in codes(issues)


# ---------------------------------------------------------------------------
# 规则：stage-order（顺序式，兜底 stage-commit 门面）
# ---------------------------------------------------------------------------


def test_stage_order_ok_for_pipeline(store, tmp_path):
    """doc→test→feat→fix→doc 顺序正确，不报 stage-order。"""
    repo = _git_repo_with(tmp_path, [
        "doc(x): 设计", "test(x): 测试", "feat(x): 实现",
        "fix(x): 修复", "doc(x): 收尾",
    ])
    hashes = [i.hash for i in reversed(repo.log())]
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": hashes})
    assert "stage-order" not in codes(check_feats(store, git=repo))


def test_stage_order_detects_backward(store, tmp_path):
    """test 出现在 feat 之后 → stage-order。"""
    repo = _git_repo_with(tmp_path, ["feat(x): 实现", "test(x): 后补测试"])
    # 同秒时间戳下用 commits 数组顺序（feat 在前）判定
    hashes = [i.hash for i in reversed(repo.log())]
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": hashes})
    assert "stage-order" in codes(check_feats(store, git=repo))


def test_stage_order_skips_without_git(store):
    add(store, GOOD_FEAT)
    assert "stage-order" not in codes(check_feats(store))


def test_stage_order_ignores_neutral_prefix(store, tmp_path):
    """refactor 等中性前缀不参与顺序判定。"""
    repo = _git_repo_with(tmp_path, [
        "doc(x): 设计", "test(x): 测试", "feat(x): 实现",
        "refactor(x): 重构", "fix(x): 修复",
    ])
    hashes = [i.hash for i in reversed(repo.log())]
    add(store, {"slug": "a", "title": "A", "doc": "d", "api": ["f()"],
                "fallbacks": ["x"], "commits": hashes})
    assert "stage-order" not in codes(check_feats(store, git=repo))


# ---------------------------------------------------------------------------
# 规则：review-none / review-low（见 doc/feat/review-check.md）
# ---------------------------------------------------------------------------


def _feat_with_items(slug="a", n_api=2):
    return Feat(slug=slug, title=slug, doc="d.md",
                api=[f"f{i}()" for i in range(n_api)],
                logs=["l"], fallbacks=["fb"])


def test_review_none_warning(store):
    store.add(_feat_with_items())
    issues = check_one(store, "a")
    assert "review-none" in codes(issues)
    assert all(i.level == "warning"
               for i in issues if i.code == "review-none")


def test_review_low_warning_when_partial(store):
    f = _feat_with_items(n_api=10)
    f.set_reviewed("api:0")                 # 13 项里审 1 项
    store.add(f)
    issues = check_one(store, "a")
    got = codes(issues)
    assert "review-low" in got
    assert "review-none" not in got         # 已审过一项


def test_review_clean_when_coverage_ok(store):
    f = _feat_with_items(n_api=2)           # 4 项
    for k, _ in f.review_items():
        f.set_reviewed(k)
    store.add(f)
    got = codes(check_one(store, "a"))
    assert "review-none" not in got
    assert "review-low" not in got


def test_review_skipped_when_no_items(store):
    store.add(Feat(slug="bare", title="裸"))
    got = codes(check_one(store, "bare"))
    assert "review-none" not in got
    assert "review-low" not in got


def test_review_respects_min_coverage(store):
    f = _feat_with_items(n_api=10)
    for i in range(5):                      # 13 项里审 5 项 ≈ 38%
        f.set_reviewed(f"api:{i}")
    store.add(f)
    assert "review-low" in codes(check_one(store, "a", min_coverage=0.6))
    # 放宽阈值 → 不再报
    assert "review-low" not in codes(check_one(store, "a", min_coverage=0.3))


def test_review_works_without_git_or_notes(store):
    """不依赖 git / note_store，无它们也生效。"""
    store.add(_feat_with_items())
    got = codes(check_one(store, "a", git=None, note_store=None))
    assert "review-none" in got


def test_review_closed_none_mentions_closed(store):
    f = _feat_with_items()
    f.status = FeatStatus.CLOSED
    store.add(f)
    issues = [i for i in check_one(store, "a") if i.code == "review-none"]
    assert issues
    assert "closed" in issues[0].message


def test_review_rules_in_check_feats(store):
    store.add(_feat_with_items())
    got = codes(check_feats(store, git=None))
    assert "review-none" in got


def test_review_codes_registered():
    from pdev.check import CODES

    assert "review-none" in CODES
    assert "review-low" in CODES


def test_review_boundary_equal_threshold_not_reported(store):
    """覆盖率恰等于阈值 → 不报 review-low（低于才报）。"""
    f = Feat(slug="a", title="A", api=["f()", "g()"], doc="")
    f.set_reviewed("api:0")                 # 2 项审 1 项 = 50%
    store.add(f)
    assert "review-low" not in codes(check_one(store, "a", min_coverage=0.5))
    assert "review-low" in codes(check_one(store, "a", min_coverage=0.6))


def test_review_none_and_low_coexist_when_zero(store):
    """一项都没审时，review-none 与 review-low 同时出现。"""
    store.add(_feat_with_items())
    got = codes(check_one(store, "a"))
    assert {"review-none", "review-low"} <= got


# ---------------------------------------------------------------------------
# 五项设计字段规则（见 doc/feat/feat-fields-check.md）
# ---------------------------------------------------------------------------


def _fielded(slug="a", **over):
    kw = dict(
        slug=slug, title=slug, doc="d.md", api=["f()"], fallbacks=["x"],
        design_note="思路", impl_note="方式",
        data_model=["X: int"], samples=["X=1"],
        changes=["pdev/x.py::X —— 新增"],
        stage="feat",
        # 设为强制起点之后，使其受 missing-fields 约束
        created_at=datetime.fromisoformat("2026-10-15T00:00:00+00:00"),
    )
    kw.update(over)
    return Feat(**kw)


def test_missing_fields_reported_for_staged_feat(store):
    f = _fielded(design_note="", samples=[])
    store.add(f)
    got = [i for i in check_one(store, "a") if i.code == "missing-fields"]
    assert got
    assert "设计思路" in got[0].message
    assert "样例数据" in got[0].message


def test_missing_fields_exempt_for_legacy_feat(store):
    """早期建立的 feat 豁免 missing-fields（按 created_at 判定）。"""
    store.add(Feat(slug="old", title="旧", api=["f()"],
                   created_at=datetime.fromisoformat(
                       "2026-10-01T00:00:00+00:00")))
    got = codes(check_one(store, "old"))
    assert "missing-fields" not in got


def test_missing_fields_enforced_after_since(store):
    """创建的 feat 在强制起点之后才报。"""
    f = _fielded(design_note="")
    store.add(f)
    assert "missing-fields" in codes(check_one(store, "a"))


def test_complete_feat_no_missing_fields(store):
    store.add(_fielded())
    got = codes(check_one(store, "a"))
    assert "missing-fields" not in got


def test_vague_change_reported(store):
    store.add(_fielded(changes=["改了一下 pdev/feat.py"]))   # 无 :: 也无 .
    got = [i for i in check_one(store, "a") if i.code == "vague-change"]
    assert got
    assert "pdev/feat.py" in got[0].message


def test_vague_change_accepts_symbol(store):
    store.add(_fielded(changes=["pdev/feat.py::Feat.x —— 新增"]))
    assert "vague-change" not in codes(check_one(store, "a"))
    store.add(_fielded(slug="b", changes=["Feat.x 新增字段"]))     # 含点
    assert "vague-change" not in codes(check_one(store, "b"))


def test_vague_change_not_reported_when_empty(store):
    store.add(_fielded(changes=[]))
    assert "vague-change" not in codes(check_one(store, "a"))


def test_empty_sample_placeholder(store):
    store.add(_fielded(samples=["无"]))
    got = [i for i in check_one(store, "a") if i.code == "empty-sample"]
    assert got


def test_empty_sample_accepts_placeholder_with_note(store):
    """「无：纯计算」带说明，不算敷衍。"""
    store.add(_fielded(samples=["无：纯计算无外部数据"]))
    assert "empty-sample" not in codes(check_one(store, "a"))


def test_empty_sample_too_short(store):
    store.add(_fielded(samples=["x"]))
    assert "empty-sample" in codes(check_one(store, "a"))


def test_empty_sample_not_reported_when_empty(store):
    store.add(_fielded(samples=[]))
    assert "empty-sample" not in codes(check_one(store, "a"))


def test_field_rules_registered():
    from pdev.check import CODES

    for c in ("missing-fields", "vague-change", "empty-sample"):
        assert c in CODES


def test_empty_sample_various_placeholders(store):
    for i, bad in enumerate(["无", "none", "N/A", "tbd", "  "]):
        slug = f"p{i}"
        store.add(_fielded(slug=slug, samples=[bad]))
        assert "empty-sample" in codes(check_one(store, slug)), bad


def test_vague_change_ignores_file_extension_dot(store):
    """文件名里的 .py 不算符号定位。"""
    store.add(_fielded(changes=["改了 pdev/feat.py 这个文件"]))
    assert "vague-change" in codes(check_one(store, "a"))


def test_vague_change_accepts_class_member(store):
    store.add(_fielded(changes=["Feat.set_comment 新增方法"]))
    assert "vague-change" not in codes(check_one(store, "a"))


# ---------------------------------------------------------------------------
# stage-unreviewed（见 doc/feat/stage-review.md）
# ---------------------------------------------------------------------------


def test_stage_unreviewed_reported(store):
    """有阶段 commit 但未审 → 报 stage-unreviewed。"""
    f = _fielded()
    f.stage = "feat"
    f.commits = ["aaa"]
    store.add(f)
    got = codes(check_one(store, "a"))
    assert "stage-unreviewed" in got


def test_stage_unreviewed_gone_after_review(store):
    f = _fielded()
    f.stage = "feat"
    store.add(f)
    store.review_stage("a", "test", "human:lwy")
    store.review_stage("a", "feat", "human:lwy")
    assert "stage-unreviewed" not in codes(check_one(store, "a"))


def test_stage_unreviewed_registered():
    from pdev.check import CODES

    assert "stage-unreviewed" in CODES
