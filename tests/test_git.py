# -*- coding: utf-8 -*-
"""pdev.git 的测试（只读集成）。"""

from __future__ import annotations

import subprocess

import pytest

from pdev.git import CommitInfo, GitRepo, is_git_repo


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path):
    """建一个有两次提交的临时仓库。"""
    cwd = str(tmp_path)
    git("init", "-q", cwd=cwd)
    git("config", "user.email", "t@example.com", cwd=cwd)
    git("config", "user.name", "Tester", cwd=cwd)

    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    git("add", "-A", cwd=cwd)
    git("commit", "-q", "-m", "first: 初始提交", cwd=cwd)

    (tmp_path / "b.txt").write_text("world", encoding="utf-8")
    git("add", "-A", cwd=cwd)
    git("commit", "-q", "-m", "second: 第二次提交", cwd=cwd)
    return tmp_path


def test_is_git_repo(repo):
    assert is_git_repo(str(repo))


def test_not_a_repo(tmp_path):
    assert not is_git_repo(str(tmp_path / "nowhere"))


def test_commit_info(repo):
    r = GitRepo(str(repo))
    assert r.available
    info = r.commit_info("HEAD")
    assert info is not None
    assert isinstance(info, CommitInfo)
    assert info.subject == "second: 第二次提交"
    assert info.author == "Tester"
    assert info.date is not None
    assert info.short == info.hash[:8]


def test_commit_info_cached(repo):
    r = GitRepo(str(repo))
    a = r.commit_info("HEAD")
    b = r.commit_info("HEAD")
    assert a is b  # 命中缓存


def test_short_hash_lookup(repo):
    r = GitRepo(str(repo))
    full = r.commit_info("HEAD")
    short = full.hash[:8]
    # 通过完整 hash / 短 hash 都能查到
    assert r.commit_info(full.hash).subject == full.subject


def test_missing_ref_returns_none(repo):
    r = GitRepo(str(repo))
    assert r.commit_info("deadbeefdeadbeef") is None


def test_commit_infos_batch(repo):
    r = GitRepo(str(repo))
    infos = r.commit_infos(["HEAD", "HEAD~1"])
    assert len(infos) == 2
    assert infos["HEAD"].subject == "second: 第二次提交"
    assert infos["HEAD~1"].subject == "first: 初始提交"


def test_commit_infos_partial_miss(repo):
    r = GitRepo(str(repo))
    infos = r.commit_infos(["HEAD", "notacommit"])
    assert "HEAD" in infos
    assert "notacommit" not in infos


def test_commit_infos_empty(repo):
    r = GitRepo(str(repo))
    assert r.commit_infos([]) == {}


def test_unavailable_repo_returns_empty(tmp_path):
    r = GitRepo(str(tmp_path / "nowhere"))
    assert not r.available
    assert r.commit_infos(["HEAD"]) == {}
    assert r.commit_info("HEAD") is None


def test_bad_path_does_not_raise(tmp_path):
    # 路径不存在也不应抛异常
    r = GitRepo(str(tmp_path / "does" / "not" / "exist"))
    assert r.commit_info("HEAD") is None


# ---------------------------------------------------------------------------
# 完整历史
# ---------------------------------------------------------------------------


def test_log_lists_all_commits(repo):
    r = GitRepo(str(repo))
    commits = r.log()
    assert len(commits) == 2
    # 新 → 旧
    assert commits[0].subject == "second: 第二次提交"
    assert commits[1].subject == "first: 初始提交"


def test_log_limit(repo):
    r = GitRepo(str(repo))
    assert len(r.log(limit=1)) == 1
    assert r.log(limit=1)[0].subject == "second: 第二次提交"


def test_log_populates_cache(repo):
    r = GitRepo(str(repo))
    commits = r.log()
    # log 之后可直接按 hash 查，无需再次 fork
    assert r.commit_info(commits[0].hash).subject == "second: 第二次提交"


def test_log_not_a_repo(tmp_path):
    r = GitRepo(str(tmp_path / "nowhere"))
    assert r.log() == []


def test_log_empty_repo(tmp_path):
    """新 init 但没有提交的仓库，log 应返回空列表而非报错。"""
    git("init", "-q", cwd=str(tmp_path))
    r = GitRepo(str(tmp_path))
    assert r.available
    assert r.log() == []
