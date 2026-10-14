# -*- coding: utf-8 -*-
"""零依赖本地 Web UI（web-ui）。

设计见 ``doc/feat/web-ui.md``。三条约束：

1. **零第三方依赖**：只用标准库 ``http.server`` + ``json``；
   前端是内嵌的原生 HTML/CSS/JS，无构建步骤。
2. **分层**：``build_data`` 是纯函数（不 import http），可脱离网络单测。
3. **只读**：所有路由仅 ``GET``；服务只绑 ``127.0.0.1``，不对外暴露。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .git import GitRepo
from .note import CommitNote
from .store import NoteStore

__all__ = ["build_data", "make_handler", "run", "PAGE"]

BIND_HOST = "127.0.0.1"


# ---------------------------------------------------------------------------
# 纯函数：数据组装
# ---------------------------------------------------------------------------


def _note_dict(n: CommitNote) -> Dict[str, Any]:
    """一条笔记 → 前端友好的 dict。"""
    return {
        "commit": n.commit,
        "kind": n.kind.value,
        "title": n.title,
        "detail": n.detail or "",
        "author": n.author.raw,
        "status": n.status.value,
        "severity": n.severity.value if n.severity is not None else "",
        "files": list(n.files),
        "tags": list(n.tags),
        "catches": list(n.catches),
        "issue_id": n.issue_id or "",
        "verifications": [
            {
                "kind": v.kind.value,
                "target": v.target or "",
                "command": v.command or "",
                "note": v.note or "",
                "method": v.method or "",
                "expected": v.expected or "",
            }
            for v in n.verifications
        ],
    }


def build_data(store: NoteStore, git, cwd: str = ".") -> Dict[str, Any]:
    """组装前端所需全部数据。**纯函数，不 import http.server。**

    返回 ``{"commits": [...], "notes": {短hash: [...]}, "store_root": str,
    "git_available": bool, "warnings": [...]}``。
    """
    warnings: List[str] = []

    # 1. 提交列表：优先 git 历史，否则退回笔记里的 commit
    commits: List[Dict[str, Any]] = []
    git_ok = git is not None and getattr(git, "available", False)
    if git_ok:
        try:
            history = git.log()
        except Exception as e:  # noqa: BLE001
            warnings.append(f"git log 失败：{e}")
            history = []
        for info in history:
            commits.append({
                "hash": info.hash,
                "short": info.hash[:8],
                "subject": getattr(info, "subject", "") or "",
                "author": getattr(info, "author", "") or "",
                "note_count": 0,
            })
    if not commits:
        seen = set()
        for n in store.all():
            if n.commit and n.commit not in seen:
                seen.add(n.commit)
                commits.append({
                    "hash": n.commit,
                    "short": n.commit[:8],
                    "subject": "",
                    "author": "",
                    "note_count": 0,
                })

    # 2. 笔记：按提交归类（用 8 位短 hash 作键，前端只需精确匹配）
    notes: Dict[str, List[Dict[str, Any]]] = {}
    for c in commits:
        try:
            items = store.by_commit(c["hash"])
        except Exception as e:  # noqa: BLE001
            warnings.append(f"读取 {c['hash'][:8]} 的笔记失败：{e}")
            items = []
        if not items:
            continue
        notes[c["short"]] = [_note_dict(n) for n in items]
        c["note_count"] = len(items)

    # 3. 非 git：尝试从笔记补标题（无 git 时 subject 为空已可接受）

    return {
        "commits": commits,
        "notes": notes,
        "store_root": str(getattr(store, "root", "")),
        "git_available": bool(git_ok),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------

# 单页前端：原生 JS，无框架、无构建。三栏 + 点击 + 键盘 + 筛选。
PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDM — 提交笔记</title>
<style>
  :root {
    --bg: #1e1e2e; --fg: #cdd6f4; --dim: #7f849c; --line: #313244;
    --sel: #45475a; --acc: #89b4fa;
    --bug: #f38ba8; --pit: #fab387; --pro: #f38ba8;
    --dif: #89dceb; --exc: #a6e3a1;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: var(--bg); color: var(--fg);
    font: 13px/1.5 ui-monospace, "Cascadia Code", Consolas, monospace;
    display: flex; flex-direction: column;
  }
  header {
    padding: 8px 12px; border-bottom: 1px solid var(--line);
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  }
  header .title { font-weight: 700; color: var(--acc); }
  header .meta { color: var(--dim); font-size: 12px; }
  header input {
    flex: 1; min-width: 160px; background: #181825; color: var(--fg);
    border: 1px solid var(--line); border-radius: 4px; padding: 4px 8px;
    font: inherit;
  }
  main { flex: 1; display: flex; min-height: 0; }
  .col { overflow: auto; border-right: 1px solid var(--line); }
  #col-commits { width: 34%; }
  #col-notes   { width: 28%; }
  #col-detail  { flex: 1; padding: 8px 12px; }
  .row { padding: 4px 10px; cursor: pointer; white-space: nowrap;
         overflow: hidden; text-overflow: ellipsis; }
  .row:hover { background: #181825; }
  .row.sel { background: var(--sel); }
  .row .hash { color: var(--dim); margin-right: 6px; }
  .row .cnt { color: var(--acc); margin-left: 6px; }
  .empty { color: var(--dim); padding: 12px; }
  .detail h3 { margin: 4px 0 8px; font-size: 14px; }
  .detail .kv { color: var(--dim); }
  .detail .kv b { color: var(--fg); font-weight: 400; }
  .kind { padding: 0 5px; border-radius: 3px; margin-right: 6px; }
  .kind.pitfall { background: var(--pit); color: #111; }
  .kind.bug { background: var(--bug); color: #111; }
  .kind.problem { background: var(--pro); color: #111; }
  .kind.difficulty { background: var(--dif); color: #111; }
  .kind.controlled-exception { background: var(--exc); color: #111; }
  .verify { margin-top: 10px; border-top: 1px solid var(--line); padding-top: 8px; }
  .verify code { background: #181825; padding: 1px 5px; border-radius: 3px; }
  footer { padding: 6px 12px; border-top: 1px solid var(--line);
           color: var(--dim); font-size: 12px; }
  kbd { background: #181825; border: 1px solid var(--line);
        border-radius: 3px; padding: 0 4px; }
</style>
</head>
<body>
<header>
  <span class="title">✎ PDM</span>
  <input id="filter" placeholder="筛选（按 / 聚焦）…" autocomplete="off">
  <span class="meta" id="meta"></span>
</header>
<main>
  <div class="col" id="col-commits"></div>
  <div class="col" id="col-notes"></div>
  <div class="col detail" id="col-detail"></div>
</main>
<footer>
  <kbd>j</kbd>/<kbd>k</kbd> 移动 · <kbd>/</kbd> 筛选 · <kbd>R</kbd> 刷新 ·
  <kbd>Esc</kbd> 清筛选 · 点击切换
</footer>
<script>
"use strict";
let DATA = {commits: [], notes: {}};
let ci = 0;          // 选中的提交下标
let ni = 0;          // 选中的笔记下标
let q = "";          // 筛选词

function filteredCommits() {
  if (!q) return DATA.commits;
  const k = q.toLowerCase();
  return DATA.commits.filter(c => {
    const blob = (c.subject + " " + c.hash + " " +
      JSON.stringify(DATA.notes[c.short] || [])).toLowerCase();
    return blob.includes(k);
  });
}

function notesOf(commit) {
  if (!commit) return [];
  return DATA.notes[commit.short] || [];
}

function fmtNotes(c) {
  return c.note_count ? `<span class="cnt">${c.note_count}</span>` : "";
}

function render() {
  const list = filteredCommits();
  if (ci >= list.length) ci = Math.max(0, list.length - 1);
  const cur = list[ci];

  // 提交栏
  document.getElementById("col-commits").innerHTML = list.length
    ? list.map((c, i) =>
        `<div class="row ${i === ci ? "sel" : ""}" data-i="${i}">` +
        `<span class="hash">${c.short}</span>` +
        `${escapeHtml(c.subject || "(无标题)")}${fmtNotes(c)}</div>`).join("")
    : `<div class="empty">（无提交）</div>`;

  // 笔记栏
  const notes = notesOf(cur);
  if (ni >= notes.length) ni = Math.max(0, notes.length - 1);
  document.getElementById("col-notes").innerHTML = notes.length
    ? notes.map((n, i) =>
        `<div class="row ${i === ni ? "sel" : ""}" data-n="${i}">` +
        `<span class="kind ${n.kind}">${n.kind}</span>` +
        `${escapeHtml(n.title)}</div>`).join("")
    : `<div class="empty">（该提交暂无笔记）</div>`;

  // 详情栏
  const n = notes[ni];
  document.getElementById("col-detail").innerHTML = n
    ? detailHtml(cur, n)
    : `<div class="empty">选中左侧提交与笔记查看详情</div>`;

  document.getElementById("meta").textContent =
    `${list.length} 提交 · store ${DATA.store_root}`;
}

function detailHtml(c, n) {
  const rows = [
    ["提交", c.subject || c.short],
    ["作者", n.author],
    ["类型", n.kind + "   状态 " + n.status + (n.severity ? "   严重 " + n.severity : "")],
    ["文件", (n.files || []).join(", ")],
    ["标签", (n.tags || []).join(", ")],
    ["捕获", (n.catches || []).join(", ")],
  ].filter(r => r[1]);
  let h = `<h3>${escapeHtml(n.title)}</h3>`;
  h += rows.map(r => `<div class="kv">${r[0]}  <b>${escapeHtml(String(r[1]))}</b></div>`).join("");
  if (n.detail) h += `<pre>${escapeHtml(n.detail)}</pre>`;
  if ((n.verifications || []).length) {
    h += `<div class="verify"><b>验证</b>`;
    for (const v of n.verifications) {
      const t = v.target || v.command || v.note || "";
      h += `<div class="kv">${v.kind}  <code>${escapeHtml(t)}</code></div>`;
      if (v.method) h += `<div class="kv">&nbsp;&nbsp;方法  <b>${escapeHtml(v.method)}</b></div>`;
      if (v.expected) h += `<div class="kv">&nbsp;&nbsp;期望  <b>${escapeHtml(v.expected)}</b></div>`;
    }
    h += `</div>`;
  }
  return h;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]
  ));
}

// --- 事件 ---

document.getElementById("col-commits").addEventListener("click", e => {
  const row = e.target.closest(".row"); if (!row) return;
  ci = +row.dataset.i; ni = 0; render();
});

document.getElementById("col-notes").addEventListener("click", e => {
  const row = e.target.closest(".row"); if (!row) return;
  ni = +row.dataset.n; render();
});

document.getElementById("filter").addEventListener("input", e => {
  q = e.target.value.trim(); ci = 0; ni = 0; render();
});

document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" && e.key !== "Escape") return;
  if (e.key === "j" || e.key === "ArrowDown") { ci++; render(); e.preventDefault(); }
  else if (e.key === "k" || e.key === "ArrowUp") { ci--; render(); e.preventDefault(); }
  else if (e.key === "/") { document.getElementById("filter").focus(); e.preventDefault(); }
  else if (e.key === "R") { load(); }
  else if (e.key === "Escape") {
    const f = document.getElementById("filter");
    f.value = ""; q = ""; f.blur(); ci = 0; ni = 0; render();
  }
});

async function load() {
  const r = await fetch("/api/data");
  DATA = await r.json();
  ci = 0; ni = 0; render();
}

render();
load();
</script>
</body>
</html>
"""


def make_handler(data: Dict[str, Any]):
    """返回一个绑定好数据的 ``BaseHTTPRequestHandler`` 子类。"""
    import http.server

    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    page = PAGE.encode("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "pdm-webui/1"

        def log_message(self, *args):  # noqa: D102 - 静默，避免刷屏
            return

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - http.server 约定
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            elif path == "/api/data":
                self._send(200, payload, "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        def do_POST(self):  # noqa: N802
            self._send(405, b"read-only", "text/plain; charset=utf-8")

        do_PUT = do_DELETE = do_PATCH = do_POST

    return Handler


# ---------------------------------------------------------------------------
# IO 层
# ---------------------------------------------------------------------------


def run(store: NoteStore, cwd: str = ".", port: int = 0,
        open_browser: bool = True, stdout=None,
        _serve_forever: bool = True) -> int:
    """起本地 Web 服务；返回退出码。

    只绑 ``127.0.0.1``（不对外暴露）。``port=0`` 时由系统分配空闲端口。
    """
    import sys
    import webbrowser

    out = stdout if stdout is not None else sys.stdout

    git = GitRepo(cwd)
    data = build_data(store, git, cwd=str(cwd))
    handler = make_handler(data)

    import http.server
    import socketserver

    class _Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        httpd = _Server((BIND_HOST, int(port)), handler)
    except OSError as e:
        print(f"无法绑定 {BIND_HOST}:{port} —— {e}", file=sys.stderr)
        return 2

    actual = httpd.server_address[1]
    url = f"http://{BIND_HOST}:{actual}"
    print(f"Web UI: {url}")
    print(f"store:  {data['store_root']}   ({len(data['commits'])} 提交)")
    for w in data.get("warnings", []):
        print(f"警告: {w}", file=sys.stderr)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - 打不开浏览器不算错
            pass

    if not _serve_forever:
        httpd.server_close()
        return 0

    try:
        print("按 Ctrl+C 结束")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已结束")
    finally:
        httpd.server_close()
    return 0
