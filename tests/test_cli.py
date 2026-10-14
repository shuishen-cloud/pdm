# -*- coding: utf-8 -*-
"""pdev.cli 的测试。

直接调 ``pdev.cli.main(argv)``，用 ``capsys`` 检查输出、``tmp_path`` 隔离存储。
"""

from __future__ import annotations

import json

import pytest

from pdev import NoteKind, NoteStatus, NoteStore
from pdev.cli import main, parse_actor, parse_kind


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """隔离项目/用户配置，避免真实环境干扰。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for key in list(__import__("os").environ):
        if key.startswith("PDM_"):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def store_dir(tmp_path):
    return str(tmp_path / "notes")


def run(store_dir, *argv) -> int:
    """以给定存储目录运行 CLI。"""
    return main(["--store", store_dir, *argv])


def add_sample(store_dir):
    """写入三条示例笔记。"""
    assert run(store_dir, "note", "add", "abc123", "-k", "pitfall",
               "-t", "token 刷新有竞态", "-F", "src/auth/token.py",
               "-T", "auth", "-p", "high", "--status", "open",
               "-a", "human:lwy") == 0
    assert run(store_dir, "note", "add", "abc123", "-k", "difficulty",
               "-t", "异步上下文拿不到 config", "-F", "src/auth/token.py",
               "-T", "async", "-a", "ai:claude") == 0
    assert run(store_dir, "note", "add", "def456", "-k", "bug",
               "-t", "Redis 偶发超时", "-F", "src/cache/redis.py",
               "-i", "0001", "-a", "human:lwy") == 0


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("problem", NoteKind.PROBLEM),
        ("pit", NoteKind.PITFALL),
        ("PITFALL", NoteKind.PITFALL),
        ("bug", NoteKind.BUG),
        ("B", NoteKind.BUG),
        ("ce", NoteKind.CONTROLLED_EXCEPTION),
        ("controlled-exception", NoteKind.CONTROLLED_EXCEPTION),
        ("controlledexception", NoteKind.CONTROLLED_EXCEPTION),
        ("exc", NoteKind.CONTROLLED_EXCEPTION),
        ("diff", NoteKind.DIFFICULTY),
    ],
)
def test_parse_kind(raw, expected):
    assert parse_kind(raw) is expected


def test_parse_kind_invalid():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        parse_kind("nope")


def test_parse_actor_defaults_to_human():
    assert str(parse_actor("lwy")) == "human:lwy"
    assert str(parse_actor("ai:claude")) == "ai:claude"
    assert str(parse_actor("ci")) == "human:ci"


# ---------------------------------------------------------------------------
# note add
# ---------------------------------------------------------------------------


def test_note_add(store_dir, capsys):
    rc = run(store_dir, "note", "add", "abc123", "-k", "pitfall",
             "-t", "标题", "-a", "human:lwy")
    assert rc == 0
    out = capsys.readouterr().out
    assert "已记录" in out
    assert "PITFALL" in out

    store = NoteStore(store_dir)
    assert len(store) == 1
    n = next(store.all())
    assert n.commit == "abc123"
    assert n.kind is NoteKind.PITFALL
    assert n.author.raw == "human:lwy"
    assert n.created_at is not None


def test_note_add_all_fields(store_dir):
    run(store_dir, "note", "add", "c1", "-k", "problem", "-t", "标题",
        "-d", "详情", "-F", "a.py", "-F", "b.py", "-T", "t1", "-T", "t2",
        "-p", "critical", "--status", "open", "-i", "0007", "-r", "0003",
        "-a", "ai:bot", "--no-time")

    n = next(NoteStore(store_dir).all())
    assert n.detail == "详情"
    assert n.files == ["a.py", "b.py"]
    assert n.tags == ["t1", "t2"]
    assert n.severity is not None and n.severity.value == "critical"
    assert n.status is NoteStatus.OPEN
    assert n.issue_id == "0007"
    assert n.resolves == ["0003"]
    assert n.author.raw == "ai:bot"
    assert n.created_at is None


def test_note_add_empty_title_fails(store_dir, capsys):
    rc = run(store_dir, "note", "add", "c1", "-k", "pitfall", "-t", "   ")
    assert rc == 2
    assert "错误" in capsys.readouterr().err


def test_note_add_missing_kind_exits(store_dir):
    with pytest.raises(SystemExit):
        run(store_dir, "note", "add", "c1", "-t", "标题")


def test_note_add_requires_detail_when_configured(store_dir, tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "note": {"require_detail": True}}),
        encoding="utf-8",
    )
    rc = main(["note", "add", "c1", "-k", "pitfall", "-t", "标题"])
    assert rc == 2
    assert "必须提供" in capsys.readouterr().err

    # 提供了 detail 就能通过
    assert run(store_dir, "note", "add", "c1", "-k", "pitfall",
               "-t", "标题", "-d", "详情") == 0


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    assert run(store_dir, "show", "abc123") == 0
    out = capsys.readouterr().out
    assert "token 刷新有竞态" in out
    assert "Redis 偶发超时" not in out


def test_show_unknown_commit(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    assert run(store_dir, "show", "nope") == 1
    assert "没有笔记" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------


def test_query_no_filter_returns_all(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    assert run(store_dir, "query") == 0
    assert "共 3 条" in capsys.readouterr().out


def test_query_by_kind(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-k", "bug")
    out = capsys.readouterr().out
    assert "共 1 条" in out
    assert "Redis" in out


def test_query_by_file_glob(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-f", "src/auth/**")
    assert "共 2 条" in capsys.readouterr().out


def test_query_by_text(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-x", "竞态")
    assert "共 1 条" in capsys.readouterr().out


def test_query_by_author_kind(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-a", "ai")
    assert "共 1 条" in capsys.readouterr().out


def test_query_by_issue(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-i", "0001")
    assert "共 1 条" in capsys.readouterr().out


def test_query_limit(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-n", "2")
    assert "共 2 条" in capsys.readouterr().out


def test_query_combined(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-k", "pitfall", "-f", "src/auth/**", "-s", "open")
    assert "共 1 条" in capsys.readouterr().out


def test_query_no_match(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-k", "problem")
    assert "无匹配的笔记" in capsys.readouterr().out


def test_query_json_output(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "query", "-k", "bug", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["kind"] == "bug"
    assert payload[0]["issue_id"] == "0001"


def test_note_list_alias(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    assert run(store_dir, "note", "list", "-k", "difficulty") == 0
    assert "共 1 条" in capsys.readouterr().out


def test_default_limit_from_config(store_dir, tmp_path, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "query": {"default_limit": 1}}),
        encoding="utf-8",
    )
    main(["query"])
    assert "共 1 条" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    assert run(store_dir, "stats") == 0
    out = capsys.readouterr().out
    assert "笔记统计" in out
    assert "总数      3" in out
    assert "覆盖提交  2" in out
    assert "pitfall" in out


def test_stats_json(store_dir, capsys):
    add_sample(store_dir)
    capsys.readouterr()
    run(store_dir, "stats", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 3
    assert payload["commits"] == 2


# ---------------------------------------------------------------------------
# 路径与交互
# ---------------------------------------------------------------------------


def test_store_flag_after_subcommand(store_dir, capsys):
    # --store 写在子命令之后也应生效
    rc = main(["note", "add", "c1", "-k", "pitfall", "-t", "t",
               "--store", store_dir])
    assert rc == 0
    assert len(NoteStore(store_dir)) == 1


def test_default_store_in_cwd(tmp_path, capsys):
    assert main(["note", "add", "c1", "-k", "pitfall", "-t", "t"]) == 0
    assert (tmp_path / ".pdm" / "notes" / "by-commit" / "c1.json").exists()


def test_store_from_project_config(tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": "cfg-notes"}), encoding="utf-8"
    )
    assert main(["note", "add", "c1", "-k", "pitfall", "-t", "t"]) == 0
    assert (tmp_path / "cfg-notes" / "by-commit" / "c1.json").exists()


def test_store_from_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PDM_STORE", "env-notes")
    assert main(["note", "add", "c1", "-k", "pitfall", "-t", "t"]) == 0
    assert (tmp_path / "env-notes" / "by-commit" / "c1.json").exists()


def test_cli_store_beats_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PDM_STORE", "env-notes")
    assert main(["--store", "cli-notes", "note", "add", "c1",
                 "-k", "pitfall", "-t", "t"]) == 0
    assert (tmp_path / "cli-notes" / "by-commit" / "c1.json").exists()
    assert not (tmp_path / "env-notes").exists()


def test_default_author_from_config(store_dir, tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "default_author": "human:alice"}),
        encoding="utf-8",
    )
    assert main(["note", "add", "c1", "-k", "pitfall", "-t", "t"]) == 0
    n = next(NoteStore(store_dir).all())
    assert n.author.raw == "human:alice"


def test_cli_author_overrides_config(store_dir, tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "default_author": "human:alice"}),
        encoding="utf-8",
    )
    main(["note", "add", "c1", "-k", "pitfall", "-t", "t", "-a", "ai:bot"])
    n = next(NoteStore(store_dir).all())
    assert n.author.raw == "ai:bot"


def test_default_status_from_config(store_dir, tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "note": {"default_status": "open"}}),
        encoding="utf-8",
    )
    assert main(["note", "add", "c1", "-k", "pitfall", "-t", "t"]) == 0
    n = next(NoteStore(store_dir).all())
    assert n.status is NoteStatus.OPEN


def test_cli_status_overrides_config(store_dir, tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": store_dir, "note": {"default_status": "open"}}),
        encoding="utf-8",
    )
    main(["note", "add", "c1", "-k", "pitfall", "-t", "t", "--status", "noted"])
    n = next(NoteStore(store_dir).all())
    assert n.status is NoteStatus.NOTED


def test_broken_config_reports_error(tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text("{ bad", encoding="utf-8")
    rc = main(["note", "add", "c1", "-k", "pitfall", "-t", "t"])
    assert rc == 2
    assert "配置错误" in capsys.readouterr().err


def test_jsonc_config_rejected(tmp_path, capsys):
    (tmp_path / ".pdm.json").write_text(
        '{ \n  // comment\n  "store": "x"\n}', encoding="utf-8"
    )
    rc = main(["note", "add", "c1", "-k", "pitfall", "-t", "t"])
    assert rc == 2
    assert "配置错误" in capsys.readouterr().err


def test_query_on_empty_store(store_dir, capsys):
    assert run(store_dir, "query") == 0
    assert "无匹配的笔记" in capsys.readouterr().out


def test_no_color_flag_accepted(store_dir, capsys):
    # --no-color 是顶层选项，放在子命令之前
    rc = main(["--no-color", "--store", store_dir, "note", "add", "c1",
               "-k", "pitfall", "-t", "t"])
    assert rc == 0
    assert "\033[" not in capsys.readouterr().out  # 无 ANSI 转义


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def test_parse_verification_forms():
    from pdev.cli import parse_verification
    from pdev.note import VerificationKind

    t = parse_verification("test=tests/x.py::test_y")
    assert t.kind is VerificationKind.TEST and t.target == "tests/x.py::test_y"

    c = parse_verification("cmd=make check")
    assert c.kind is VerificationKind.COMMAND and c.command == "make check"

    m = parse_verification("manual=手动步骤")
    assert m.kind is VerificationKind.MANUAL and m.note == "手动步骤"

    bare = parse_verification("pytest -q")
    assert bare.kind is VerificationKind.COMMAND and bare.command == "pytest -q"

    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        parse_verification("bogus=x")


def test_note_add_with_verifications(store_dir):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "test=tests/x.py::test_y",
        "--verify", "cmd=make check",
        "--verify", "manual=手动登录")
    n = next(NoteStore(store_dir).all())
    assert len(n.verifications) == 3
    assert n.verifications[0].kind.value == "test"
    assert n.verifications[0].effective_command == "pytest tests/x.py::test_y -q"
    assert n.verifications[2].kind.value == "manual"


def test_verify_list(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "test=tests/x.py::test_y")
    capsys.readouterr()
    assert run(store_dir, "verify", "list") == 0
    out = capsys.readouterr().out
    assert "pytest tests/x.py::test_y -q" in out
    assert "共 1 条笔记，1 条验证" in out


def test_verify_list_json(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=make check")
    capsys.readouterr()
    run(store_dir, "verify", "list", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["verifications"][0]["kind"] == "command"
    assert payload[0]["verifications"][0]["effective_command"] == "make check"


def test_verify_run_dry_run(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=echo hello")
    capsys.readouterr()
    assert run(store_dir, "verify", "run", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "$ echo hello" in out


def test_verify_run_executes_and_persists(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=echo ok")
    capsys.readouterr()
    rc = run(store_dir, "verify", "run", "c1")
    assert rc == 0
    assert "通过 1" in capsys.readouterr().out

    # 结果已回写
    n = next(NoteStore(store_dir).all())
    assert n.verifications[0].last_status.value == "passed"


def test_verify_run_failure_exit_code(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=exit 3")
    capsys.readouterr()
    assert run(store_dir, "verify", "run", "c1") == 1
    assert "失败 1" in capsys.readouterr().out


def test_verify_list_unverified(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "没验证")
    capsys.readouterr()
    assert run(store_dir, "verify", "list", "--unverified") == 0
    assert "需要验证" in capsys.readouterr().out


def test_verify_run_by_status(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "t",
        "--verify", "cmd=exit 1")
    capsys.readouterr()
    run(store_dir, "verify", "run", "c1")     # 变成 failed
    capsys.readouterr()
    assert run(store_dir, "verify", "run", "--status", "failed") == 1
    assert "失败 1" in capsys.readouterr().out


def test_verify_run_no_match(store_dir, capsys):
    assert run(store_dir, "verify", "run") == 0
    assert "没有可执行的验证" in capsys.readouterr().out


def test_parse_verification_with_method_suffix():
    from pdev.cli import parse_verification

    v = parse_verification(
        "test=tests/x.py::test_y;method=并发只刷新一次;expected=passed"
    )
    assert v.target == "tests/x.py::test_y"
    assert v.method == "并发只刷新一次"
    assert v.expected == "passed"

    c = parse_verification("cmd=make check;expected=退出码 0")
    assert c.command == "make check"
    assert c.expected == "退出码 0"


def test_verify_list_verbose_shows_method(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=make check;method=类型检查通过")
    capsys.readouterr()
    run(store_dir, "verify", "list", "-v")
    assert "方法: 类型检查通过" in capsys.readouterr().out


def test_verify_show_displays_details(store_dir, capsys):
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "cmd=make check;method=类型检查;expected=退出码 0",
        "--verify", "manual=手动登录")
    capsys.readouterr()
    assert run(store_dir, "verify", "show", "c1") == 0
    out = capsys.readouterr().out
    assert "验证 1: command" in out
    assert "方法: 类型检查" in out
    assert "命令: make check" in out
    assert "期望: 退出码 0" in out
    assert "验证 2: manual" in out


def test_verify_show_extracts_script(store_dir, tmp_path, capsys):
    # 建一个真实测试文件供抽取
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "t.py").write_text(
        "def test_ok():\n    assert 1 == 1\n", encoding="utf-8"
    )
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "test=tests/t.py::test_ok")
    capsys.readouterr()
    assert run(store_dir, "verify", "show", "c1") == 0
    out = capsys.readouterr().out
    assert "脚本" in out
    assert "def test_ok():" in out


def test_verify_show_no_script(store_dir, tmp_path, capsys):
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "t.py").write_text(
        "def test_ok():\n    pass\n", encoding="utf-8"
    )
    run(store_dir, "note", "add", "c1", "-k", "bug", "-t", "标题",
        "--verify", "test=tests/t.py::test_ok")
    capsys.readouterr()
    run(store_dir, "verify", "show", "c1", "--no-script")
    assert "def test_ok" not in capsys.readouterr().out


def test_verify_show_unknown_commit(store_dir, capsys):
    assert run(store_dir, "verify", "show", "nope") == 1
    assert "没有笔记" in capsys.readouterr().err


def test_ui_accepts_positional_store(store_dir):
    from pdev.cli import build_parser

    args = build_parser().parse_args(["ui", store_dir])
    assert args.store_arg == store_dir
    assert args.func.__name__ == "cmd_ui"


def test_ui_store_flag_also_works(store_dir):
    from pdev.cli import build_parser

    args = build_parser().parse_args(["ui", "--store", store_dir])
    assert args.store == store_dir
    assert args.store_arg is None


def test_ui_positional_takes_priority(store_dir, tmp_path):
    """位置参数优先于 --store。"""
    from pdev.cli import build_parser

    other = str(tmp_path / "other")
    args = build_parser().parse_args(["ui", store_dir, "--store", other])
    assert args.store_arg == store_dir
    assert args.store == other


# ---------------------------------------------------------------------------
# pdm theme
# ---------------------------------------------------------------------------


def test_theme_lists_themes(capsys):
    code = main(["theme"])
    assert code == 0
    out = capsys.readouterr().out
    assert "可选主题" in out
    assert "textual-dark" in out
    # 默认值应被标出
    assert "●" in out


def test_theme_lists_json(capsys):
    code = main(["--json", "theme"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert "textual-dark" in data["themes"]
    assert data["current"] == "catppuccin-macchiato"


def test_theme_sets_and_persists(capsys, tmp_path, monkeypatch):
    user = tmp_path / "user" / "config.json"
    monkeypatch.setattr("pdev.config.USER_CONFIG_PATH", str(user))
    code = main(["theme", "nord"])
    assert code == 0
    out = capsys.readouterr().out
    assert "nord" in out

    # 落盘到用户配置（不进 git），下次读取即生效
    import json as _json

    assert _json.loads(user.read_text(encoding="utf-8"))["ui"]["theme"] == "nord"
    from pdev.config import load_config

    cfg = load_config()
    assert cfg.ui.theme == "nord"


def test_theme_unknown_fails(capsys):
    code = main(["theme", "no-such-theme"])
    assert code == 2
    err = capsys.readouterr().err
    assert "未知主题" in err


def test_theme_suggests_similar(capsys):
    code = main(["theme", "catpp"])
    assert code == 2
    err = capsys.readouterr().err
    assert "是否想要" in err
    assert "catppuccin" in err


def test_theme_shows_current_after_set(capsys):
    main(["theme", "gruvbox"])
    capsys.readouterr()
    main(["theme"])
    out = capsys.readouterr().out
    # gruvbox 那行应有 ● 标记
    line = next(x for x in out.splitlines() if "gruvbox" in x)
    assert "●" in line


# ---------------------------------------------------------------------------
# pdm feat
# ---------------------------------------------------------------------------


def test_feat_new_and_show(capsys):
    code = main(["feat", "new", "my-feat", "-t", "我的功能",
                 "--doc", "docs/feat/my-feat.md",
                 "--api", "FeatStore.add(feat: Feat) -> None",
                 "--log", "创建时记录 slug",
                 "--fallback", "坏输入报错"])
    assert code == 0
    out = capsys.readouterr().out
    assert "my-feat" in out and "draft" in out

    main(["feat", "show", "my-feat"])
    out = capsys.readouterr().out
    assert "我的功能" in out
    assert "docs/feat/my-feat.md" in out
    assert "FeatStore.add(feat: Feat) -> None" in out
    assert "创建时记录 slug" in out
    assert "坏输入报错" in out


def test_feat_new_bad_slug_fails(capsys):
    code = main(["feat", "new", "BadSlug", "-t", "x"])
    assert code == 2
    assert "错误" in capsys.readouterr().err


def test_feat_show_resolves_doc_against_dir(tmp_path, monkeypatch, capsys):
    """feat.doc 存相对路径，show 时按 doc.dir 解析后显示。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": ".pdm/notes", "feat": {"store": ".pdm/feats"},
                    "doc": {"dir": ".pdm/docs"}}),
        encoding="utf-8")
    main(["feat", "new", "a", "-t", "A", "--doc", "feat/a.md"])
    capsys.readouterr()
    main(["feat", "show", "a"])
    out = capsys.readouterr().out
    assert ".pdm/docs/feat/a.md" in out


def test_feat_new_doc_stored_raw(capsys):
    """--doc 原样存储（相对 doc.dir），非全路径。"""
    main(["feat", "new", "rawdoc", "-t", "A", "--doc", "feat/rawdoc.md"])
    capsys.readouterr()
    main(["--json", "feat", "show", "rawdoc"])
    data = json.loads(capsys.readouterr().out)
    assert data["doc"] == "feat/rawdoc.md"


def test_feat_new_duplicate_fails(capsys):
    main(["feat", "new", "dup", "-t", "A"])
    capsys.readouterr()
    code = main(["feat", "new", "dup", "-t", "B"])
    assert code == 2
    assert "已存在" in capsys.readouterr().err


def test_feat_list_and_filters(capsys):
    main(["feat", "new", "a", "-t", "A", "-k", "feat"])
    main(["feat", "new", "b", "-t", "B", "-k", "fix"])
    main(["feat", "set", "a", "integrated"])
    capsys.readouterr()

    main(["feat", "list"])
    out = capsys.readouterr().out
    assert "a" in out and "b" in out

    main(["feat", "list", "--kind", "fix"])
    out = capsys.readouterr().out
    assert "b" in out and "\n" + "a" not in out

    main(["feat", "list", "--status", "integrated"])
    out = capsys.readouterr().out
    assert "a" in out
    assert " b " not in out


def test_feat_list_json(capsys):
    main(["feat", "new", "a", "-t", "A", "--api", "f()"])
    capsys.readouterr()
    code = main(["--json", "feat", "list"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["slug"] == "a"
    assert data[0]["api"] == ["f()"]


def test_feat_show_json(capsys):
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    main(["feat", "show", "a", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["slug"] == "a"
    assert data["status"] == "draft"


def test_feat_show_missing_fails(capsys):
    code = main(["feat", "show", "nope"])
    assert code == 2
    assert "找不到" in capsys.readouterr().err


def test_feat_set_progression(capsys):
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    code = main(["feat", "set", "a", "testing"])
    assert code == 0
    assert "testing" in capsys.readouterr().out


def test_feat_set_backwards_fails(capsys):
    main(["feat", "new", "a", "-t", "A"])
    main(["feat", "set", "a", "integrated"])
    capsys.readouterr()
    code = main(["feat", "set", "a", "draft"])
    assert code == 2
    assert "倒退" in capsys.readouterr().err


def test_feat_link_and_found(capsys):
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    assert main(["feat", "link", "a", "deadbeef"]) == 0
    assert main(["feat", "found", "a", "接入时列表多一行"]) == 0
    capsys.readouterr()

    main(["feat", "show", "a", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["commits"] == ["deadbeef"]
    assert data["discovered"] == ["接入时列表多一行"]


def test_feat_uses_config_store_dir(capsys, tmp_path):
    """feat.store 配置生效。"""
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"feat": {"store": "myfeats"}}), encoding="utf-8")
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    assert (tmp_path / "myfeats" / "by-id" / "a.json").is_file()


# ---------------------------------------------------------------------------
# 全局 --json（历史 Bug：被子命令的 --json 覆盖）
# ---------------------------------------------------------------------------


def test_global_json_flag_for_show(capsys):
    """`pdm --json show <commit>` 应输出 JSON（曾被子命令默认值覆盖）。"""
    main(["note", "add", "abc123", "-k", "bug", "-t", "缺陷"])
    capsys.readouterr()
    code = main(["--json", "show", "abc123"])
    assert code == 0
    # 能解析即说明是 JSON
    data = json.loads(capsys.readouterr().out)
    assert data


def test_subcommand_json_flag_still_works(capsys):
    main(["note", "add", "abc123", "-k", "bug", "-t", "缺陷"])
    capsys.readouterr()
    code = main(["show", "abc123", "--json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)


def test_global_json_flag_for_feat(capsys):
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    code = main(["--json", "feat", "show", "a"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["slug"] == "a"


def test_global_json_flag_for_stats(capsys):
    main(["note", "add", "abc123", "-k", "bug", "-t", "缺陷"])
    capsys.readouterr()
    code = main(["--json", "stats"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)


def test_no_json_flag_gives_human_output(capsys):
    main(["feat", "new", "a", "-t", "A"])
    capsys.readouterr()
    main(["feat", "show", "a"])
    out = capsys.readouterr().out
    assert out.lstrip().startswith("a")     # 不是 JSON
    assert "{" not in out.splitlines()[0]


# ---------------------------------------------------------------------------
# pdm feat check
# ---------------------------------------------------------------------------


def test_feat_check_clean(capsys):
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    main(["feat", "set", "a", "testing"])
    main(["feat", "set", "a", "integrated"])
    main(["feat", "set", "a", "fixing"])
    main(["feat", "link", "a", "abc1234"])
    main(["feat", "set", "a", "closed"])
    # 审查全部可审项，才是真正「通过校验」
    for key in ("doc", "api:0", "fallbacks:0"):
        main(["feat", "review", "a", "--item", key, "--review"])
    capsys.readouterr()
    code = main(["feat", "check", "a"])
    out = capsys.readouterr().out
    assert code == 0
    assert "通过校验" in out


def test_feat_check_reports_unreviewed(capsys):
    """流程齐全但未审 → 仍退出码 0，但报 review 警告。"""
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    capsys.readouterr()
    code = main(["feat", "check", "a"])
    out = capsys.readouterr().out
    assert code == 0
    assert "review-none" in out


def test_feat_check_reports_draft_with_commit(capsys):
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    main(["feat", "link", "a", "deadbeef"])
    capsys.readouterr()
    code = main(["feat", "check", "a"])
    out = capsys.readouterr().out
    assert "draft-has-commit" in out
    assert code == 0        # warning 不导致失败


def test_feat_check_closed_without_commit_is_error(capsys):
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    for st in ("testing", "integrated", "fixing", "closed"):
        main(["feat", "set", "a", st])
    capsys.readouterr()
    code = main(["feat", "check", "a"])
    out = capsys.readouterr().out
    assert "closed-no-commit" in out
    assert code == 1


def test_feat_check_strict(capsys):
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    main(["feat", "link", "a", "deadbeef"])
    capsys.readouterr()
    assert main(["feat", "check", "a"]) == 0            # 只有 warning
    assert main(["feat", "check", "a", "--strict"]) == 1


def test_feat_check_json(capsys):
    main(["feat", "new", "a", "-t", "A", "--doc", "d.md",
          "--api", "f()", "--fallback", "x"])
    main(["feat", "link", "a", "deadbeef"])
    capsys.readouterr()
    main(["--json", "feat", "check", "a"])
    data = json.loads(capsys.readouterr().out)
    assert data["warnings"] >= 1
    assert any(i["code"] == "draft-has-commit" for i in data["issues"])


def test_feat_check_all(capsys):
    main(["feat", "new", "a", "-t", "A"])
    main(["feat", "new", "b", "-t", "B"])
    capsys.readouterr()
    code = main(["feat", "check"])
    out = capsys.readouterr().out
    assert "a" in out and "b" in out


def test_feat_check_missing_slug_fails(capsys):
    code = main(["feat", "check", "nope"])
    assert code == 2
    assert "找不到" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# note 显示 commit message（见 docs/feat/note-commit-msg.md）
# ---------------------------------------------------------------------------


def test_group_by_commit_preserves_order():
    from pdev.cli.commands import group_by_commit
    from pdev import CommitNote, NoteKind

    notes = [
        CommitNote(commit="aaa", kind=NoteKind.BUG, title="A1"),
        CommitNote(commit="bbb", kind=NoteKind.BUG, title="B1"),
        CommitNote(commit="aaa", kind=NoteKind.PITFALL, title="A2"),
    ]
    groups = group_by_commit(notes)
    assert [c for c, _ in groups] == ["aaa", "bbb"]
    assert [n.title for n in groups[0][1]] == ["A1", "A2"]
    assert [n.title for n in groups[1][1]] == ["B1"]


def test_note_list_grouped_by_commit_with_message(capsys):
    """note list 应按 commit 分组，并显示 commit message。"""
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (__import__("pathlib").Path("a.txt")).write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "fix(x): 修正某问题")
    h = git("rev-parse", "--short", "HEAD").stdout.strip()

    main(["note", "add", h, "-k", "bug", "-t", "短串误匹配"])
    capsys.readouterr()
    main(["note", "list"])
    out = capsys.readouterr().out
    assert "fix(x): 修正某问题" in out      # message 出现了
    assert "短串误匹配" in out
    assert out.count("fix(x): 修正某问题") == 1     # 每组只出现一次


def test_note_list_falls_back_without_git(capsys, tmp_path, monkeypatch):
    """非 git 目录下应回退平铺，不报错。"""
    monkeypatch.chdir(tmp_path)
    main(["note", "add", "abc1234", "-k", "bug", "-t", "X"])
    capsys.readouterr()
    code = main(["note", "list"])
    assert code == 0
    assert "X" in capsys.readouterr().out


def test_show_prints_commit_header(capsys):
    import subprocess

    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (__import__("pathlib").Path("a.txt")).write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat(y): 新增功能")
    h = git("rev-parse", "--short", "HEAD").stdout.strip()

    main(["note", "add", h, "-k", "problem", "-t", "某问题"])
    capsys.readouterr()
    main(["show", h])
    out = capsys.readouterr().out
    assert "feat(y): 新增功能" in out
    assert "某问题" in out


def test_note_list_json_unchanged(capsys):
    """--json 仍是笔记数组，不含 message。"""
    main(["note", "add", "abc1234", "-k", "bug", "-t", "X"])
    capsys.readouterr()
    main(["--json", "note", "list"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["title"] == "X"
    assert "subject" not in data[0]


def test_note_list_finds_git_via_store_dir(capsys, tmp_path, monkeypatch):
    """cwd 非 git 时，应回溯 store 所在目录找 git（Review 发现）。"""
    import subprocess
    from pathlib import Path

    # 在 tmp_path 建 git 仓库，笔记存在其子目录
    def git(*a):
        return subprocess.run(["git", *a], cwd=str(tmp_path),
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@e.com")
    git("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "feat(z): 在仓库里")
    h = git("rev-parse", "--short", "HEAD").stdout.strip()

    store = str(tmp_path / "notes")
    main(["--store", store, "note", "add", h, "-k", "bug", "-t", "X"])
    capsys.readouterr()

    # 切到非 git 目录再列
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    monkeypatch.chdir(outside)
    main(["--store", store, "note", "list"])
    out = capsys.readouterr().out
    assert "feat(z): 在仓库里" in out


# ---------------------------------------------------------------------------
# feat show --doc / --notes / --verify（见 doc/feat/feat-cli-parity.md）
# ---------------------------------------------------------------------------


def _feat_env(tmp_path, monkeypatch):
    """建 .pdm.json + feat + 设计文档 + 关联笔记，返回临时目录。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pdm.json").write_text(json.dumps({
        "store": ".pdm/notes",
        "feat": {"store": ".pdm/feats"},
        "doc": {"dir": ".pdm/docs"},
    }), encoding="utf-8")
    (tmp_path / ".pdm" / "docs" / "feat").mkdir(parents=True)
    (tmp_path / ".pdm" / "docs" / "feat" / "x.md").write_text(
        "# 数据结构\n\n```\nfield: int\n```\n", encoding="utf-8")
    main(["feat", "new", "x", "-t", "X", "--doc", "feat/x.md",
          "--api", "f()"])
    main(["note", "add", "deadbee", "-k", "bug", "-t", "一个坑",
          "-d", "详细说明"])
    main(["feat", "link", "x", "deadbee"])
    return tmp_path


def test_feat_show_doc_prints_body(tmp_path, monkeypatch, capsys):
    _feat_env(tmp_path, monkeypatch)
    capsys.readouterr()
    code = main(["feat", "show", "x", "--doc"])
    assert code == 0
    out = capsys.readouterr().out
    assert "数据结构" in out
    assert "field: int" in out


def test_feat_show_notes_aggregates(tmp_path, monkeypatch, capsys):
    _feat_env(tmp_path, monkeypatch)
    capsys.readouterr()
    main(["feat", "show", "x", "--notes"])
    out = capsys.readouterr().out
    assert "关联笔记" in out
    assert "一个坑" in out


def test_feat_show_notes_detail(tmp_path, monkeypatch, capsys):
    _feat_env(tmp_path, monkeypatch)
    capsys.readouterr()
    main(["feat", "show", "x", "--notes", "--verify"])
    out = capsys.readouterr().out
    assert "详细说明" in out          # notes_detail 展开


def test_feat_show_no_notes_marker(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pdm.json").write_text(
        json.dumps({"store": ".pdm/notes", "feat": {"store": ".pdm/feats"}}),
        encoding="utf-8")
    main(["feat", "new", "y", "-t", "Y"])
    capsys.readouterr()
    main(["feat", "show", "y", "--notes"])
    out = capsys.readouterr().out
    assert "暂无笔记" in out


def test_feat_show_from_config_defaults(tmp_path, monkeypatch, capsys):
    """未指定 flag 时，配置 feat.view.doc_body=true 应打印正文。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".pdm.json").write_text(json.dumps({
        "store": ".pdm/notes",
        "feat": {"store": ".pdm/feats", "view": {"doc_body": True}},
        "doc": {"dir": ".pdm/docs"},
    }), encoding="utf-8")
    (tmp_path / ".pdm" / "docs").mkdir(parents=True)
    (tmp_path / ".pdm" / "docs" / "z.md").write_text("正文内容ABC",
                                                     encoding="utf-8")
    main(["feat", "new", "z", "-t", "Z", "--doc", "z.md"])
    capsys.readouterr()
    main(["feat", "show", "z"])
    out = capsys.readouterr().out
    assert "正文内容ABC" in out


def test_cli_imports_without_textual():
    """CLI 入口不应把 textual 拉进 import 链。"""
    import subprocess
    import sys

    code = ("import sys; import pdev.cli; "
            "print('textual' in sys.modules)")
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "False", r.stderr


# ---------------------------------------------------------------------------
# feat review / pdm review（见 doc/feat/review-cli.md）
# ---------------------------------------------------------------------------


def _make_feat(capsys, slug="a", title="A"):
    """建一条带规格字段的 feat，清空输出。"""
    code = main(["feat", "new", slug, "-t", title,
                 "--doc", "feat/x.md",
                 "--api", "f() -> int", "--api", "g() -> str",
                 "--log", "记录调用", "--fallback", "抛错"])
    assert code == 0
    capsys.readouterr()


def test_feat_review_lists_items(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a"])
    out = capsys.readouterr().out
    assert code == 0
    assert "api:0" in out and "api:1" in out
    assert "logs:0" in out and "fallbacks:0" in out and "doc" in out
    assert "[ ]" in out                      # 未勾选


def test_feat_review_missing_slug(capsys):
    code = main(["feat", "review", "nope"])
    err = capsys.readouterr().err
    assert code == 2
    assert "找不到" in err


def test_feat_review_check_reviewed(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "api:0", "--review"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[x]" in out
    # 再列出，应显示已勾
    main(["feat", "review", "a"])
    out = capsys.readouterr().out
    assert "[x][ ]  api:0" in out or "[x][ ] api:0" in out


def test_feat_review_records_author(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review",
          "--by", "human:lwy"])
    capsys.readouterr()
    from pdev.feat import FeatStore
    fs = FeatStore(tmp_path / '.pdm' / 'feats')
    item = fs.get("a").review_item("api:0")
    assert item.reviewed is True
    assert item.reviewed_by == "human:lwy"


def test_feat_review_unreview(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    capsys.readouterr()
    code = main(["feat", "review", "a", "--item", "api:0", "--unreview"])
    assert code == 0
    capsys.readouterr()
    from pdev.feat import FeatStore
    item = FeatStore(tmp_path / '.pdm' / 'feats').get("a").review_item("api:0")
    assert item is None or item.reviewed is False


def test_feat_review_test_records_command(capsys, tmp_path):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "api:0", "--test",
                 "--cmd", "pytest tests/x.py::test_y", "--status", "passed"])
    assert code == 0
    capsys.readouterr()
    from pdev.feat import FeatStore
    item = FeatStore(tmp_path / '.pdm' / 'feats').get("a").review_item("api:0")
    assert item.tested is True
    assert item.test_command == "pytest tests/x.py::test_y"
    assert item.test_status == "passed"


def test_feat_review_test_without_cmd_warns(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "api:0", "--test"])
    out = capsys.readouterr()
    assert code == 0
    assert "--cmd" in (out.out + out.err)      # 提示建议记录命令


def test_feat_review_bad_item(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "api:99", "--review"])
    err = capsys.readouterr().err
    assert code == 2
    assert "api:99" in err or "非法" in err


def test_feat_review_actions_mutually_exclusive(capsys):
    _make_feat(capsys)
    with pytest.raises(SystemExit):
        main(["feat", "review", "a", "--item", "api:0",
              "--review", "--test"])


def test_feat_review_json(capsys):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    capsys.readouterr()
    main(["--json", "feat", "review", "a"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["slug"] == "a"
    items = {i["key"]: i for i in data["items"]}
    assert items["api:0"]["reviewed"] is True
    assert items["api:1"]["reviewed"] is False


def test_pdm_review_shows_score(capsys):
    _make_feat(capsys)
    for key in ("api:0", "api:1", "logs:0", "fallbacks:0", "doc"):
        main(["feat", "review", "a", "--item", key, "--review"])
        main(["feat", "review", "a", "--item", key, "--test",
              "--cmd", "pytest x"])
    capsys.readouterr()
    code = main(["review"])
    out = capsys.readouterr().out
    assert "掌握程度" in out
    assert "100%" in out
    assert code == 0                              # 全覆盖无告警


def test_pdm_review_warns_when_no_review(capsys):
    _make_feat(capsys)
    code = main(["review"])
    out = capsys.readouterr().out
    assert code == 1                              # 有告警 → 退出码 1
    assert "no-review" in out or "完全不审查" in out


def test_pdm_review_json(capsys):
    _make_feat(capsys)
    capsys.readouterr()
    code = main(["--json", "review"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["items"] == 5
    assert data["reviewed"] == 0
    assert any(w["code"] == "no-review" for w in data["warnings"])
    assert code == 1


def test_pdm_review_empty(capsys):
    code = main(["review"])
    out = capsys.readouterr().out
    assert code == 0
    assert "无可审内容" in out


def test_feat_show_has_review_marks(capsys):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    capsys.readouterr()
    main(["feat", "show", "a"])
    out = capsys.readouterr().out
    assert "[x]" in out and "[ ]" in out


def test_stats_shows_review(capsys, store_dir):
    _make_feat(capsys)
    capsys.readouterr()
    code = main(["stats"])
    out = capsys.readouterr().out
    assert code == 0
    assert "掌握程度" in out


def test_stats_json_has_review(capsys, store_dir):
    _make_feat(capsys)
    capsys.readouterr()
    main(["--json", "stats"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "review" in data
    assert data["review"]["items"] == 5


def test_review_end_to_end_flow(capsys):
    """端到端：勾选 → 覆盖率和告警同步变化 → 撤销回落。"""
    _make_feat(capsys)
    # 初始：全未审，有告警
    assert main(["review"]) == 1
    capsys.readouterr()

    # 逐项审查 + 测试（用真实 key）
    keys = ["api:0", "api:1", "logs:0", "fallbacks:0", "doc"]
    for k in keys:
        assert main(["feat", "review", "a", "--item", k, "--review"]) == 0
        assert main(["feat", "review", "a", "--item", k, "--test",
                     "--cmd", "pytest x"]) == 0
    capsys.readouterr()

    code = main(["review"])
    out = capsys.readouterr().out
    assert code == 0                      # 全覆盖 → 无告警
    assert "100%" in out
    assert "excellent" in out

    # 撤销一项审查 → 覆盖率回落、告警复现
    main(["feat", "review", "a", "--item", "api:0", "--unreview"])
    capsys.readouterr()
    code = main(["review"])
    out = capsys.readouterr().out
    assert code == 0                      # 4/5=80% 仍高于 0.6，无 low-review
    # 人工审查行显示 80%（不再 100%）
    review_line = [l for l in out.splitlines() if "人工审查" in l][0]
    assert "80%" in review_line
    assert "100%" not in review_line


# ---------------------------------------------------------------------------
# pdm review --unreviewed / --untested（见 doc/feat/review-query.md）
# ---------------------------------------------------------------------------


def test_review_unreviewed_lists_items(capsys):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    capsys.readouterr()
    code = main(["review", "--unreviewed"])
    out = capsys.readouterr().out
    assert code == 0
    assert "api:1" in out
    assert "api:0" not in out.split("未审查")[0]   # 已审的不列
    assert "未审查：" in out


def test_review_untested_lists_items(capsys):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--test", "--cmd", "x"])
    capsys.readouterr()
    code = main(["review", "--untested"])
    out = capsys.readouterr().out
    assert code == 0
    assert "未测试：" in out
    assert "api:1" in out


def test_review_both_filters_intersection(capsys):
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    capsys.readouterr()
    code = main(["review", "--unreviewed", "--untested"])
    out = capsys.readouterr().out
    assert code == 0
    assert "未审查且未测试" in out
    assert "api:0" not in out.split("未审查")[0]


def test_review_unreviewed_empty(capsys):
    """全部审完 → 无待办，退出码 0。"""
    _make_feat(capsys)
    for key in ("doc", "api:0", "api:1", "logs:0", "fallbacks:0"):
        main(["feat", "review", "a", "--item", key, "--review"])
    capsys.readouterr()
    code = main(["review", "--unreviewed"])
    out = capsys.readouterr().out
    assert code == 0
    assert "没有未审查的项" in out


def test_review_unreviewed_json(capsys):
    _make_feat(capsys)
    capsys.readouterr()
    main(["--json", "review", "--unreviewed"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["filter"] == "unreviewed"
    assert data["count"] == data["total"]
    slugs = [f["slug"] for f in data["feats"]]
    assert "a" in slugs


def test_review_no_filter_keeps_summary(capsys):
    """不带筛选时保持汇总行为（向后兼容）。"""
    _make_feat(capsys)
    capsys.readouterr()
    main(["review"])
    out = capsys.readouterr().out
    assert "掌握程度" in out
    assert "未审查：" not in out


def test_review_unreviewed_json_empty(capsys):
    """无 feat 时 --json 输出空清单，退出码 0。"""
    code = main(["--json", "review", "--unreviewed"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 0
    assert data["total"] == 0
    assert data["count"] == 0
    assert data["feats"] == []


# ---------------------------------------------------------------------------
# pdm feat comment（见 doc/feat/feat-comment.md）
# ---------------------------------------------------------------------------


def test_feat_comment_write_and_read(capsys):
    _make_feat(capsys)
    code = main(["feat", "comment", "a", "--on", "api:0",
                 "-m", "这个签名保持最小"])
    out = capsys.readouterr().out
    assert code == 0
    assert "这个签名保持最小" in out

    code = main(["feat", "comment", "a", "--on", "api:0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "这个签名保持最小" in out


def test_feat_comment_list_all(capsys):
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "接口评论"])
    main(["feat", "comment", "a", "--on", "logs:0", "-m", "日志评论"])
    capsys.readouterr()
    code = main(["feat", "comment", "a"])
    out = capsys.readouterr().out
    assert code == 0
    assert "接口评论" in out and "日志评论" in out


def test_feat_comment_clear(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "x"])
    capsys.readouterr()
    code = main(["feat", "comment", "a", "--on", "api:0", "--clear"])
    assert code == 0
    capsys.readouterr()
    from pdev.feat import FeatStore
    assert FeatStore(tmp_path / ".pdm" / "feats").get("a").comment("api:0") == ""


def test_feat_comment_empty_message_clears(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "x"])
    capsys.readouterr()
    main(["feat", "comment", "a", "--on", "api:0", "-m", ""])
    capsys.readouterr()
    from pdev.feat import FeatStore
    assert FeatStore(tmp_path / ".pdm" / "feats").get("a").comment("api:0") == ""


def test_feat_comment_missing_slug(capsys):
    code = main(["feat", "comment", "nope", "--on", "api:0"])
    err = capsys.readouterr().err
    assert code == 2
    assert "找不到" in err


def test_feat_comment_bad_key(capsys):
    _make_feat(capsys)
    code = main(["feat", "comment", "a", "--on", "api:99", "-m", "x"])
    err = capsys.readouterr().err
    assert code == 2
    assert "api:99" in err or "非法" in err


def test_feat_comment_missing_on_with_message(capsys):
    """给 -m 但没给 --on → 报错。"""
    _make_feat(capsys)
    code = main(["feat", "comment", "a", "-m", "x"])
    err = capsys.readouterr().err
    assert code == 2
    assert "--on" in err


def test_feat_comment_json(capsys):
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "评论"])
    capsys.readouterr()
    code = main(["--json", "feat", "comment", "a"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 0
    assert data["comments"]["api:0"] == "评论"


def test_feat_comment_shown_in_feat_show(capsys):
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "为什么这么定"])
    capsys.readouterr()
    main(["feat", "show", "a"])
    out = capsys.readouterr().out
    assert "为什么这么定" in out


def test_feat_comment_clear_and_message_conflict(capsys):
    _make_feat(capsys)
    with pytest.raises(SystemExit):
        main(["feat", "comment", "a", "--on", "api:0",
              "--clear", "-m", "x"])


def test_feat_comment_multiline_display(capsys):
    """多行评论：首行带 💬，续行缩进对齐（写入与 show 一致）。"""
    _make_feat(capsys)
    main(["feat", "comment", "a", "--on", "api:0", "-m", "第一行\n第二行"])
    out = capsys.readouterr().out
    assert "💬 第一行" in out
    assert "💬 第二行" not in out          # 续行不带 💬
    assert "第二行" in out

    main(["feat", "show", "a"])
    out = capsys.readouterr().out
    assert "💬 第一行" in out
    assert "💬 第二行" not in out


# ---------------------------------------------------------------------------
# 批量勾选 --all / 前缀（review-batch）
# ---------------------------------------------------------------------------


def test_review_all_review(capsys, tmp_path):
    _make_feat(capsys)                       # doc + api:0/1 + logs:0 + fb:0
    code = main(["feat", "review", "a", "--all", "--review",
                 "--by", "human:lwy"])
    out = capsys.readouterr().out
    assert code == 0
    assert "5/5" in out
    from pdev.feat import FeatStore
    assert FeatStore(tmp_path / ".pdm" / "feats").get("a").review_counts() \
        == (5, 5, 0)


def test_review_prefix_review(capsys, tmp_path):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "api", "--review"])
    out = capsys.readouterr().out
    assert code == 0
    assert "2/5" in out
    from pdev.feat import FeatStore
    f = FeatStore(tmp_path / ".pdm" / "feats").get("a")
    assert f.review_item("api:0").reviewed
    assert f.review_item("api:1").reviewed
    it = f.review_item("logs:0")           # 未被操作 → None
    assert it is None or not it.reviewed


def test_review_all_test(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "review", "a", "--all", "--test", "--cmd", "pytest x"])
    capsys.readouterr()
    from pdev.feat import FeatStore
    f = FeatStore(tmp_path / ".pdm" / "feats").get("a")
    assert f.review_counts() == (5, 0, 5)
    assert f.review_item("api:0").test_command == "pytest x"


def test_review_all_unreview(capsys, tmp_path):
    _make_feat(capsys)
    main(["feat", "review", "a", "--all", "--review"])
    capsys.readouterr()
    main(["feat", "review", "a", "--all", "--unreview"])
    capsys.readouterr()
    from pdev.feat import FeatStore
    assert FeatStore(tmp_path / ".pdm" / "feats").get("a").review_counts() \
        == (5, 0, 0)


def test_review_single_item_output_unchanged(capsys):
    """单条命中仍用原输出格式。"""
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "api:0", "--review"])
    out = capsys.readouterr().out
    assert "[x][ ] api:0" in out


def test_review_all_and_item_conflict(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--all", "--item", "api:0",
                 "--review"])
    err = capsys.readouterr().err
    assert code == 2
    assert "--all" in err


def test_review_prefix_no_match(capsys):
    _make_feat(capsys)
    code = main(["feat", "review", "a", "--item", "nope", "--review"])
    err = capsys.readouterr().err
    assert code == 2


def test_review_all_on_empty_feat(capsys):
    main(["feat", "new", "bare", "-t", "B"])
    capsys.readouterr()
    code = main(["feat", "review", "bare", "--all", "--review"])
    err = capsys.readouterr().err
    assert code == 2


def test_review_all_json(capsys):
    """批量勾选 + --json 只输出 JSON。"""
    _make_feat(capsys)
    code = main(["--json", "feat", "review", "a", "--all", "--review"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)                 # 必须是纯 JSON
    assert data["action"] == "review"
    assert data["scope"] == "all"
    assert data["reviewed"] == data["total"] == 5


def test_review_item_exact_doc(capsys):
    """--item doc 是精确匹配（不是前缀）。"""
    _make_feat(capsys)
    main(["feat", "review", "a", "--item", "doc", "--review"])
    out = capsys.readouterr().out
    assert "1/5" in out                    # 只勾了 doc 一项
