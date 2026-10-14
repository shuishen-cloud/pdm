# -*- coding: utf-8 -*-
"""本地 Web UI 的测试（web-ui）。

设计见 ``doc/feat/web-ui.md``。

**关键**：``build_data`` 是纯函数（不 import http.server），
因此大多数用例不起真服务，只断言 JSON 结构。
"""

from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from pdev import (
    Actor,
    CommitNote,
    NoteKind,
    NoteStatus,
    NoteStore,
    Verification,
    VerificationKind,
)
from pdev.git import CommitInfo
from pdev.webui import build_data, make_handler, run


@pytest.fixture
def store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="aaa1111222", kind=NoteKind.PITFALL, title="并发竞态",
                   status=NoteStatus.OPEN, files=["src/auth/token.py"],
                   tags=["auth"], author=Actor("human:lwy")),
        CommitNote(commit="bbb2222333", kind=NoteKind.BUG, title="计数泄漏",
                   status=NoteStatus.RESOLVED,
                   author=Actor("ai:claude"),
                   verifications=[Verification(kind=VerificationKind.COMMAND,
                                               command="true")]),
    ])
    return s


class _FakeGit:
    available = True

    def __init__(self):
        self._infos = {
            "aaa1111222": CommitInfo(hash="aaa1111222", subject="feat(x): 实现",
                                     author="lwy"),
            "bbb2222333": CommitInfo(hash="bbb2222333", subject="fix(x): 修复",
                                     author="lwy"),
        }

    def log(self, limit: int = 0, ref: str = "HEAD"):
        return list(self._infos.values())

    def commit_info(self, ref: str):
        return self._infos.get(ref)


# ---------------------------------------------------------------------------
# 纯函数：build_data
# ---------------------------------------------------------------------------


def test_build_data_shape(store):
    data = build_data(store, _FakeGit())
    assert set(data) >= {"commits", "notes", "store_root", "git_available"}
    assert data["git_available"] is True
    assert len(data["commits"]) == 2
    first = data["commits"][0]
    for key in ("hash", "short", "subject", "author", "note_count"):
        assert key in first, key


def test_build_data_notes_grouped_by_short_hash(store):
    data = build_data(store, _FakeGit())
    notes = data["notes"]
    # 键为 8 位短 hash（hash[:8]）
    assert "aaa11112" in notes
    assert "bbb22223" in notes
    # 标题能被找到（序列化后不应丢中文）
    joined = json.dumps(data, ensure_ascii=False)
    assert "并发竞态" in joined
    assert "计数泄漏" in joined


def test_build_data_is_json_serializable(store):
    data = build_data(store, _FakeGit())
    s = json.dumps(data, ensure_ascii=False)
    assert json.loads(s)


def test_build_data_pure_no_http_import():
    """build_data 源码不得出现 http 相关依赖（保持可脱离网络单测）。"""
    import inspect
    import re

    from pdev import webui

    src = inspect.getsource(webui.build_data)
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    assert "http" not in src
    assert "socket" not in src


def test_build_data_non_git_uses_note_commits(tmp_path):
    class _NoGit:
        available = False

        def log(self, limit: int = 0, ref: str = "HEAD"):
            return []

        def commit_info(self, ref: str):
            return None

    s = NoteStore(tmp_path / "n")
    s.add(CommitNote(commit="ccc3333444", kind=NoteKind.BUG, title="孤立"))
    data = build_data(s, _NoGit())
    assert data["git_available"] is False
    assert [c["hash"] for c in data["commits"]] == ["ccc3333444"]


def test_build_data_empty_store(tmp_path):
    class _NoGit:
        available = False

        def log(self, limit: int = 0, ref: str = "HEAD"):
            return []

        def commit_info(self, ref: str):
            return None

    data = build_data(NoteStore(tmp_path / "e"), _NoGit())
    assert data["commits"] == []
    assert data["notes"] == {}


# ---------------------------------------------------------------------------
# HTTP 层（起真服务，但只两三个用例）
# ---------------------------------------------------------------------------


def _serve(data):
    """在后台线程起服务，返回 (base_url, shutdown_callable)。"""
    import http.server
    import socketserver

    handler = make_handler(data)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    def stop():
        httpd.shutdown()
        httpd.server_close()

    return f"http://127.0.0.1:{port}", stop


def test_handler_serves_html_and_api(store):
    data = build_data(store, _FakeGit())
    base, stop = _serve(data)
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            html = r.read().decode("utf-8")
            assert r.status == 200
            assert "<html" in html.lower()

        with urllib.request.urlopen(base + "/api/data", timeout=5) as r:
            assert r.status == 200
            payload = json.loads(r.read().decode("utf-8"))
            assert "commits" in payload
    finally:
        stop()


def test_unknown_path_returns_404(store):
    data = build_data(store, _FakeGit())
    base, stop = _serve(data)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/nope", timeout=5)
        assert e.value.code == 404
    finally:
        stop()


def test_non_get_returns_405(store):
    import urllib.error

    data = build_data(store, _FakeGit())
    base, stop = _serve(data)
    try:
        req = urllib.request.Request(base + "/api/data", method="POST",
                                     data=b"{}")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 405
    finally:
        stop()


def test_run_rejects_non_localhost_bind():
    """run 只允许绑 127.0.0.1（不对外暴露）。"""
    import inspect

    from pdev import webui

    src = inspect.getsource(webui.run)
    assert "127.0.0.1" in src or "localhost" in src


# ---------------------------------------------------------------------------
# 前端页面契约（零依赖不可被悄悄破坏）
# ---------------------------------------------------------------------------


def test_page_has_no_external_resources():
    """单页不得引用任何外部资源（CDN/字体/脚本）——零依赖的硬约束。"""
    import re

    from pdev.webui import PAGE

    # 找出所有 src=/href= 的外链
    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', PAGE)
    external = [u for u in urls if u.startswith(("http://", "https://", "//"))]
    assert not external, f"页面引用了外部资源：{external}"


def test_page_has_interaction_hooks():
    """关键交互钩子存在（防止重构时悄悄删掉）。"""
    from pdev.webui import PAGE

    for token in ("/api/data", "addEventListener", "escapeHtml",
                  "filteredCommits", "col-commits", "col-notes", "col-detail"):
        assert token in PAGE, token


def test_page_escapes_html():
    """必须转义用户内容，避免笔记标题里的 < 破坏页面。"""
    from pdev.webui import PAGE

    assert "escapeHtml" in PAGE
    assert "&amp;" in PAGE


def test_api_data_matches_ui_expectations(store):
    """API 返回的字段要与前端读取的键一致。"""
    data = build_data(store, _FakeGit())
    c = data["commits"][0]
    # 前端读取 c.short / c.subject / c.note_count
    for key in ("short", "subject", "note_count"):
        assert key in c
    note = data["notes"]["aaa11112"][0]
    for key in ("kind", "title", "author", "status", "files", "tags",
                "detail", "verifications"):
        assert key in note, key


def test_embedded_js_is_syntactically_valid(tmp_path):
    """用 node --check 校验内嵌 JS 语法（无 node 则跳过）。"""
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("未安装 node")

    from pdev.webui import PAGE

    m = re.search(r"<script>(.*?)</script>", PAGE, re.S)
    assert m, "页面应含 <script> 块"
    js = tmp_path / "page.js"
    js.write_text(m.group(1), encoding="utf-8")
    r = subprocess.run([node, "--check", str(js)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
