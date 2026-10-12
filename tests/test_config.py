# -*- coding: utf-8 -*-
"""pdev.config 的测试：加载、合并、优先级。"""

from __future__ import annotations

import json

import pytest

from pdev import Config, NoteStatus, load_config
from pdev.config import ConfigError, find_project_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """清空 PDM_* 环境变量，并把 HOME 指到临时目录。"""
    import os

    for key in list(os.environ):
        if key.startswith("PDM_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------


def test_defaults(tmp_path):
    cfg = load_config(env={}, cwd=tmp_path, find=False)
    assert isinstance(cfg, Config)
    assert cfg.store == "notes"
    assert cfg.default_author == "human:unknown"
    assert cfg.color is True
    assert cfg.json_output is False
    assert cfg.git.repo == "."
    assert cfg.git.auto_commit is False
    assert cfg.note.default_status is NoteStatus.NOTED
    assert cfg.issue.store == "issues"
    assert cfg.doc.dir == "docs"
    assert cfg.query.default_limit is None


# ---------------------------------------------------------------------------
# 各来源
# ---------------------------------------------------------------------------


def test_project_config(tmp_path):
    write(tmp_path / ".pdm.json", {
        "store": "my-notes",
        "default_author": "human:alice",
        "note": {"default_status": "open"},
        "query": {"default_limit": 5},
    })
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.store == "my-notes"
    assert cfg.default_author == "human:alice"
    assert cfg.note.default_status is NoteStatus.OPEN
    assert cfg.query.default_limit == 5


def test_find_project_config_walks_up(tmp_path):
    write(tmp_path / ".pdm.json", {"store": "root-notes"})
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    cfg = load_config(env={}, cwd=deep)
    assert cfg.store == "root-notes"
    assert find_project_config(deep) == tmp_path / ".pdm.json"


def test_no_project_config(tmp_path):
    assert find_project_config(tmp_path) is None


def test_cwd_accepts_str(tmp_path):
    write(tmp_path / ".pdm.json", {"store": "s"})
    assert load_config(env={}, cwd=str(tmp_path)).store == "s"
    assert find_project_config(str(tmp_path)) == tmp_path / ".pdm.json"


def test_env_overrides_project(tmp_path):
    write(tmp_path / ".pdm.json", {"store": "project"})
    cfg = load_config(env={"PDM_STORE": "env"}, cwd=tmp_path)
    assert cfg.store == "env"


def test_cli_overrides_env(tmp_path):
    write(tmp_path / ".pdm.json", {"store": "project"})
    cfg = load_config(
        {"store": "cli"}, env={"PDM_STORE": "env"}, cwd=tmp_path
    )
    assert cfg.store == "cli"


def test_cli_none_values_ignored(tmp_path):
    # CLI 未指定（None）不应覆盖已有值
    write(tmp_path / ".pdm.json", {"store": "project"})
    cfg = load_config({"store": None}, env={}, cwd=tmp_path)
    assert cfg.store == "project"


# ---------------------------------------------------------------------------
# 环境变量细节
# ---------------------------------------------------------------------------


def test_env_bool_and_int(tmp_path):
    cfg = load_config(env={
        "PDM_GIT_AUTO_COMMIT": "true",
        "PDM_QUERY_DEFAULT_LIMIT": "10",
    }, cwd=tmp_path, find=False)
    assert cfg.git.auto_commit is True
    assert cfg.query.default_limit == 10


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_env_bool_variants(tmp_path, val):
    cfg = load_config(env={"PDM_GIT_AUTO_COMMIT": val}, cwd=tmp_path, find=False)
    assert cfg.git.auto_commit is True


def test_env_no_color(tmp_path):
    cfg = load_config(env={"PDM_NO_COLOR": "1"}, cwd=tmp_path, find=False)
    assert cfg.color is False


def test_env_token(tmp_path):
    cfg = load_config(env={"PDM_GITHUB_TOKEN": "secret"}, cwd=tmp_path, find=False)
    assert cfg.github.token == "secret"


def test_empty_env_value_ignored(tmp_path):
    cfg = load_config(env={"PDM_STORE": ""}, cwd=tmp_path, find=False)
    assert cfg.store == "notes"  # 空值不覆盖默认


# ---------------------------------------------------------------------------
# 用户配置
# ---------------------------------------------------------------------------


def test_user_config(tmp_path):
    home = tmp_path / "home"
    write(home / ".config" / "pdm" / "config.json", {"color": False})
    cfg = load_config(env={}, cwd=tmp_path, find=False)
    assert cfg.color is False


def test_project_overrides_user(tmp_path):
    home = tmp_path / "home"
    write(home / ".config" / "pdm" / "config.json", {"store": "user"})
    write(tmp_path / ".pdm.json", {"store": "project"})
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.store == "project"


# ---------------------------------------------------------------------------
# 健壮性
# ---------------------------------------------------------------------------


def test_corrupt_project_config_raises(tmp_path):
    # 静默失败很危险：配置写错必须报错
    (tmp_path / ".pdm.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="解析失败"):
        load_config(env={}, cwd=tmp_path)


def test_non_object_config_raises(tmp_path):
    (tmp_path / ".pdm.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ConfigError, match="顶层必须是对象"):
        load_config(env={}, cwd=tmp_path)


def test_missing_config_is_fine(tmp_path):
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.store == "notes"


def test_jsonc_comment_rejected(tmp_path):
    # 标准 JSON 不支持注释，含注释应报错而非静默忽略
    (tmp_path / ".pdm.json").write_text(
        '{\n  // comment\n  "store": "x"\n}', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="解析失败"):
        load_config(env={}, cwd=tmp_path)


def test_unknown_keys_ignored(tmp_path):
    write(tmp_path / ".pdm.json", {"store": "x", "unknown": 1, "git": {"nope": 2}})
    cfg = load_config(env={}, cwd=tmp_path)
    assert cfg.store == "x"
    assert not hasattr(cfg, "unknown")
    assert not hasattr(cfg.git, "nope")


def test_bad_status_raises(tmp_path):
    write(tmp_path / ".pdm.json", {"note": {"default_status": "bogus"}})
    with pytest.raises(ValueError):
        load_config(env={}, cwd=tmp_path)


def test_config_serializable(tmp_path):
    cfg = load_config({"store": "x"}, env={}, cwd=tmp_path, find=False)
    d = cfg.to_dict()
    assert d["store"] == "x"
    assert d["note"]["default_status"] == "noted"


def test_token_masked_in_to_dict(tmp_path):
    cfg = load_config(env={"PDM_GITHUB_TOKEN": "s3cr3t"}, cwd=tmp_path, find=False)
    assert cfg.to_dict()["github"]["token"] == "***"
