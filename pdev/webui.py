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

__all__ = [
    "build_data",
    "build_feats",
    "build_feat_detail",
    "build_review_items",
    "apply_review",
    "make_handler",
    "run",
    "PAGE",
]

BIND_HOST = "127.0.0.1"

# featview.read_doc_body 读不到文件时返回的占位串（视作缺失）
_DOC_UNREADABLE = "（设计文档不可读）"


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


def build_feats(feat_store, note_store) -> List[Dict[str, Any]]:
    """Feat 列表（**不含设计正文**，保持响应轻量）。**纯函数。**

    无 ``feat_store`` → ``[]``。关联笔记的 hash 匹配**一律走
    ``featview``**，本函数不自行实现。
    """
    if feat_store is None:
        return []
    out: List[Dict[str, Any]] = []
    try:
        feats = list(feat_store.all())
    except Exception as e:  # noqa: BLE001
        return out
    for f in feats:
        try:
            out.append(_feat_summary(f))
        except Exception:  # noqa: BLE001 - 单条脏数据不拖垮整包
            continue
    return out


def _feat_summary(f) -> Dict[str, Any]:
    """一条 feat 的摘要（列表项）。"""
    total, reviewed = 0, 0
    try:
        _rc = f.review_counts()
        total, reviewed = _rc.total, _rc.reviewed
    except Exception:  # noqa: BLE001
        pass
    try:
        missing = list(f.missing_required_fields())
    except Exception:  # noqa: BLE001
        missing = []
    return {
        "slug": f.slug,
        "title": f.title or "",
        "kind": f.kind.value,
        "status": f.status.value,
        "stage": f.stage,
        "commit_count": len(f.commits or []),
        "review": [reviewed, total],
        "missing_fields": missing,
    }


def build_feat_detail(feat_store, note_store, doc_dir: str,
                      slug: str) -> Optional[Dict[str, Any]]:
    """单条 Feat 全量（含 ``doc_body`` 与关联笔记）。**纯函数。**

    不存在 → ``None``。设计文档缺失 → ``doc_body=""`` 且
    ``doc_missing=True``。
    """
    if feat_store is None or not slug:
        return None
    try:
        feat = feat_store.get(slug)
    except Exception:  # noqa: BLE001
        return None
    if feat is None:
        return None

    d = _feat_summary(feat)

    # 关联笔记：复用 featview 的匹配（含 >=6 位前缀），不自行 startswith
    from .featview import (  # noqa: PLC0415
        group_notes_by_kind,
        notes_for_feat,
        read_doc_body,
    )

    notes = notes_for_feat(feat, note_store)

    # 设计正文（read_doc_body 读不到时返回固定占位串）
    body, missing = "", False
    if feat.doc:
        try:
            body = read_doc_body(doc_dir, feat.doc)
        except Exception:  # noqa: BLE001
            body = ""
        missing = (not body) or body == _DOC_UNREADABLE
    else:
        missing = True
    if missing:
        body = ""

    d.update({
        "design_note": feat.design_note or "",
        "impl_note": feat.impl_note or "",
        "api": list(feat.api or []),
        "logs": list(feat.logs or []),
        "fallbacks": list(feat.fallbacks or []),
        "data_model": list(feat.data_model or []),
        "samples": list(feat.samples or []),
        "changes": list(feat.changes or []),
        "commits": list(feat.commits or []),
        "discovered": list(feat.discovered or []),
        "doc": feat.doc or "",
        "doc_body": body,
        "doc_missing": bool(missing),
        "stage_reviews": _stage_reviews_dict(feat),
        "review_items": build_review_items(feat),
        "notes": [_note_dict(n) for n in notes],
        "notes_by_kind": [
            [k, [_note_dict(n) for n in items]]
            for k, items in group_notes_by_kind(notes)
        ],
    })
    return d


def _stage_reviews_dict(feat) -> Dict[str, Any]:
    """阶段审核 → 可序列化 dict。"""
    out: Dict[str, Any] = {}
    for stage, rec in (getattr(feat, "stage_reviews", None) or {}).items():
        by = getattr(rec, "by", "") or ""
        at = getattr(rec, "at", None)
        out[stage] = {
            "by": by,
            "at": at.isoformat(sep=" ", timespec="seconds") if at else "",
            "note": getattr(rec, "note", "") or "",
        }
    return out


def _stage_reviews_dict(feat) -> Dict[str, Any]:
    """阶段审核 → 可序列化 dict。"""
    out: Dict[str, Any] = {}
    for stage, rec in (getattr(feat, "stage_reviews", None) or {}).items():
        by = getattr(rec, "by", "") or ""
        at = getattr(rec, "at", None)
        out[stage] = {
            "by": by,
            "at": at.isoformat(sep=" ", timespec="seconds") if at else "",
            "note": getattr(rec, "note", "") or "",
        }
    return out


# ---------------------------------------------------------------------------
# 审查勾选（唯一的写操作；见 doc/feat/web-ui-review.md）
# ---------------------------------------------------------------------------

_REVIEW_FIELDS = {"review": "reviewed", "test": "tested"}


def build_review_items(feat) -> List[Dict[str, Any]]:
    """可审项含勾选态与评论。**纯函数。**

    返回 ``[{"key","label","reviewed","tested","comment"}, ...]``。
    """
    out: List[Dict[str, Any]] = []
    try:
        items = feat.review_items()
    except Exception:  # noqa: BLE001
        return out
    for ref in items:
        key, label = ref.key, ref.label
        rec = feat.review_item(key)
        out.append({
            "key": key,
            "label": label or "",
            "reviewed": bool(getattr(rec, "reviewed", False)),
            "tested": bool(getattr(rec, "tested", False)),
            "comment": (feat.comment(key) or ""),
        })
    return out


def apply_review(feat_store, payload: dict, by: str = "") -> Dict[str, Any]:
    """校验并写入一个勾选位。**唯一写入口，复用 FeatStore.set_reviews。**

    返回响应 dict；错误时带 ``_status``（调用方据此设 HTTP 码）与
    ``error``（**不含内部路径/堆栈**）。
    """
    def err(status: int, msg: str) -> Dict[str, Any]:
        return {"ok": False, "_status": status, "error": msg}

    if feat_store is None:
        return err(403, "未配置 feat store")
    if not isinstance(payload, dict):
        return err(400, "invalid payload")

    slug = payload.get("slug")
    key = payload.get("key")
    field = payload.get("field")
    value = payload.get("value")

    if not isinstance(slug, str) or not slug:
        return err(400, "missing slug")
    if not isinstance(key, str) or not key:
        return err(400, "missing key")
    if field not in _REVIEW_FIELDS:
        return err(400, "field \u53ea\u80fd\u662f review/test")
    if not isinstance(value, bool):
        return err(400, "value \u5fc5\u987b\u662f\u5e03\u5c14")

    feat = feat_store.get(slug)
    if feat is None:
        return err(404, "not found")

    kwargs: Dict[str, Any] = {_REVIEW_FIELDS[field]: bool(value)}
    if field == "review":
        kwargs["by"] = by or ""          # 作者**只**由服务端决定

    try:
        # 复用 CLI 同一条写路径（含 key 校验、原子 update、_prune）
        feat_store.set_reviews(slug, [key], **kwargs)
    except Exception as e:  # noqa: BLE001 - 含 FeatError（非法 key）
        msg = str(e) or "write failed"
        # 非法 key 属客户端错误；其他归 500，且不泄漏内部细节
        status = 400 if "key" in msg or "\u5ba1\u67e5\u9879" in msg else 500
        return err(status, msg if status == 400 else "write failed")

    feat = feat_store.get(slug)
    _rc = feat.review_counts()
    total, reviewed, tested = _rc.total, _rc.reviewed, _rc.tested
    return {
        "ok": True,
        "slug": slug,
        "key": key,
        "reviewed": reviewed,
        "tested": tested,
        "total": total,
        "items": build_review_items(feat),
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
  header .tabs { display: flex; gap: 4px; }
  header .tabs button {
    background: #181825; color: var(--dim); border: 1px solid var(--line);
    border-radius: 4px; padding: 3px 10px; font: inherit; cursor: pointer;
  }
  header .tabs button.on { color: var(--fg); border-color: var(--acc); }
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
  .spec-sec { margin: 8px 0; }
  .spec-sec .h { color: var(--acc); font-weight: 700; margin-bottom: 2px; }
  .spec-sec li { margin-left: -12px; }
  .badge { padding: 0 6px; border-radius: 3px; background: #313244;
           color: var(--fg); font-size: 11px; margin-right: 4px; }
  .badge.miss { background: #f38ba8; color: #111; }
  .check { cursor: pointer; user-select: none; margin-right: 3px;
           font-family: monospace; }
  .check:hover { color: var(--acc); }
  .rev-item { margin: 4px 0; display: flex; gap: 6px; align-items: baseline; }
  .rev-item .lbl { flex: 1; word-break: break-word; }
  pre.body { white-space: pre-wrap; word-break: break-word; }
  .md-h { color: var(--acc); font-weight: 700; margin: 10px 0 4px; }
  .md-code { background: #181825; padding: 6px 8px; border-radius: 4px;
             overflow-x: auto; }
  footer { padding: 6px 12px; border-top: 1px solid var(--line);
           color: var(--dim); font-size: 12px; }
  kbd { background: #181825; border: 1px solid var(--line);
        border-radius: 3px; padding: 0 4px; }
</style>
</head>
<body>
<header>
  <span class="title">✎ PDM</span>
  <span class="tabs">
    <button id="tab-commits" class="on" data-view="commits">提交</button>
    <button id="tab-feats" data-view="feats">Feat</button>
  </span>
  <input id="filter" placeholder="筛选（按 / 聚焦）…" autocomplete="off">
  <span class="meta" id="meta"></span>
</header>
<main>
  <div id="view-commits" style="display:flex;flex:1;min-height:0">
    <div class="col" id="col-commits"></div>
    <div class="col" id="col-notes"></div>
    <div class="col detail" id="col-detail"></div>
  </div>
  <div id="view-feat" style="display:none;flex:1;min-height:0">
    <div class="col" id="col-feats"></div>
    <div class="col detail" id="col-feat-spec"></div>
    <div class="col detail" id="col-feat-notes"></div>
  </div>
</main>
<footer>
  <kbd>j</kbd>/<kbd>k</kbd> 移动 · <kbd>/</kbd> 筛选 · <kbd>R</kbd> 刷新 ·
  <kbd>Tab</kbd> 切换视图 · <kbd>Esc</kbd> 清筛选 · 点击切换
</footer>
<script>
"use strict";
let DATA = {commits: [], notes: {}, feats: []};
let ci = 0;          // 选中的提交下标
let ni = 0;          // 选中的笔记下标
let q = "";          // 筛选词
let VIEW = "commits"; // commits | feats
let fi = 0;          // 选中的 feat 下标
let FEAT = null;     // 当前 feat 详情（按需拉取）

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
  if (VIEW === "feats") { renderFeat(); return; }
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
    `${list.length} 提交 · ${(DATA.feats || []).length} feat · store ${DATA.store_root}`;
}

// --- Feat 视图 ---

function filteredFeats() {
  const all = DATA.feats || [];
  if (!q) return all;
  const k = q.toLowerCase();
  return all.filter(f => (f.slug + " " + f.title + " " + f.status +
                          " " + (f.stage || "")).toLowerCase().includes(k));
}

function stageBadge(f) {
  return f.stage ? `<span class="badge">${escapeHtml(f.stage)}</span>` : "";
}

function renderFeat() {
  const list = filteredFeats();
  if (fi >= list.length) fi = Math.max(0, list.length - 1);
  const cur = list[fi];

  document.getElementById("col-feats").innerHTML = list.length
    ? list.map((f, i) =>
        `<div class="row ${i === fi ? "sel" : ""}" data-f="${i}">` +
        `${escapeHtml(f.slug)} ${stageBadge(f)}` +
        `${escapeHtml(f.title || "")}` +
        `<span class="hash">${escapeHtml(f.status)} ${f.review[0]}/${f.review[1]}` +
        `${f.missing_fields.length ? " ⚠" : ""}</span></div>`).join("")
    : `<div class="empty">（暂无 Feat）</div>`;

  document.getElementById("meta").textContent =
    `${list.length} feat · store ${DATA.store_root}`;

  if (!cur) {
    document.getElementById("col-feat-spec").innerHTML =
      `<div class="empty">选中左侧 Feat 查看规格</div>`;
    document.getElementById("col-feat-notes").innerHTML = "";
    return;
  }
  if (!FEAT || FEAT.slug !== cur.slug) loadFeat(cur.slug);
  else renderFeatDetail(FEAT);
}

function sec(title, items) {
  if (!items || !items.length) return "";
  return `<div class="spec-sec"><div class="h">${title}</div><ul>` +
    items.map(x => `<li>${escapeHtml(String(x))}</li>`).join("") + `</ul></div>`;
}

function renderFeatDetail(f) {
  const miss = (f.missing_fields || []).length
    ? `<div class="spec-sec"><span class="badge miss">缺 ${f.missing_fields.join("、")}</span></div>` : "";
  let h = `<h3>${escapeHtml(f.slug)} — ${escapeHtml(f.title || "")}</h3>`;
  h += `<div class="kv">状态 <b>${f.status}</b>　阶段 <b>${f.stage || "—"}</b>` +
       `　审查 <b>${f.review[0]}/${f.review[1]}</b>　提交 <b>${f.commit_count}</b></div>`;
  h += miss;
  h += `<div class="spec-sec"><div class="h">审查项（点方框勾选）</div>` +
       checkListHtml(f) + `</div>`;
  if (f.design_note) h += `<div class="spec-sec"><div class="h">设计思路</div>${escapeHtml(f.design_note)}</div>`;
  if (f.impl_note) h += `<div class="spec-sec"><div class="h">实现方式</div>${escapeHtml(f.impl_note)}</div>`;
  h += sec("接口", f.api);
  h += sec("日志", f.logs);
  h += sec("兜底", f.fallbacks);
  h += sec("核心数据结构", f.data_model);
  h += sec("样例数据", f.samples);
  h += sec("既有改动", f.changes);
  h += sec("关联提交", (f.commits || []).map(c => c.slice(0, 8)));
  h += sec("发现的异常", f.discovered);
  if (f.doc_missing) h += `<div class="spec-sec"><span class="badge miss">设计文档缺失</span> ${escapeHtml(f.doc || "")}</div>`;
  document.getElementById("col-feat-spec").innerHTML = h;

  // 正文 + 笔记
  let r = "";
  if (f.doc_body) r += `<div class="h md-h">设计正文</div>` + mdLite(f.doc_body);
  const notes = f.notes || [];
  r += `<div class="spec-sec"><div class="h">关联笔记（${notes.length}）</div></div>`;
  r += notes.length
    ? notes.map(n => `<div class="spec-sec"><span class="kind ${n.kind}">${n.kind}</span>` +
        `<b>${escapeHtml(n.title)}</b><div class="kv">${escapeHtml(n.author)}` +
        `${n.severity ? " · " + n.severity : ""}</div></div>`).join("")
    : `<div class="empty">（无关联笔记）</div>`;
  document.getElementById("col-feat-notes").innerHTML = r;
}

// 极简 Markdown（标题/列表/代码块/段落）——不引任何库
function mdLite(src) {
  const lines = String(src).split("\n");
  let out = "", inCode = false;
  for (const ln of lines) {
    if (ln.startsWith("```")) {
      out += inCode ? "</pre>" : "<pre class='md-code'>";
      inCode = !inCode; continue;
    }
    if (inCode) { out += escapeHtml(ln) + "\n"; continue; }
    const m = /^(#{1,4})\s+(.*)$/.exec(ln);
    if (m) { out += `<div class="md-h">${escapeHtml(m[2])}</div>`; continue; }
    if (/^\s*[-*]\s+/.test(ln)) {
      out += `<div class="kv">• ${escapeHtml(ln.replace(/^\s*[-*]\s+/, ""))}</div>`;
      continue;
    }
    if (!ln.trim()) { out += "<div style='height:6px'></div>"; continue; }
    out += `<div>${escapeHtml(ln)}</div>`;
  }
  if (inCode) out += "</pre>";
  return out;
}

async function loadFeat(slug) {
  try {
    const r = await fetch("/api/feat/" + encodeURIComponent(slug));
    if (!r.ok) { FEAT = null;
      document.getElementById("col-feat-spec").innerHTML =
        `<div class="empty">加载失败（${r.status}）</div>`; return; }
    FEAT = await r.json();
    if (VIEW === "feats") renderFeatDetail(FEAT);
  } catch (e) {
    document.getElementById("col-feat-spec").innerHTML =
      `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

// 审查勾选：两个可点方框（[审][测]），点击 POST /api/review
function checkListHtml(f) {
  const items = f.review_items || [];
  if (!items.length) return `<div class="empty">（无可审项）</div>`;
  return items.map(it =>
    `<div class="rev-item">` +
    `<span class="check" data-key="${escapeHtml(it.key)}" ` +
    `data-field="review" title="人工已审">${it.reviewed ? "■" : "□"}</span>` +
    `<span class="check" data-key="${escapeHtml(it.key)}" ` +
    `data-field="test" title="测试通过">[${it.tested ? "■" : "□"}]</span>` +
    `<span class="lbl">${escapeHtml(it.key)}  ${escapeHtml(it.label)}` +
    (it.comment ? `  <span class="kv">// ${escapeHtml(it.comment)}</span>` : "") +
    `</span></div>`).join("");
}

async function toggleReview(key, field, span) {
  if (!FEAT) return;
  const it = (FEAT.review_items || []).find(x => x.key === key);
  if (!it) return;
  const cur = field === "review" ? it.reviewed : it.tested;
  try {
    const r = await fetch("/api/review", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({slug: FEAT.slug, key: key,
                            field: field, value: !cur}),
    });
    const d = await r.json();
    if (!r.ok || !d.ok) { alert("写入失败：" + (d.error || r.status)); return; }
    // 用服务端返回的 items 局部刷新（不做乐观更新）
    FEAT.review_items = d.items;
    FEAT.review = [d.reviewed, d.total];
    renderFeatDetail(FEAT);
    // 同步列表里的审查计数
    const fe = (DATA.feats || []).find(x => x.slug === FEAT.slug);
    if (fe) { fe.review = [d.reviewed, d.total]; renderFeat(); }
  } catch (e) {
    alert("写入失败：" + e.message);
  }
}

document.addEventListener("click", e => {
  const sp = e.target.closest(".check");
  if (!sp || VIEW !== "feats") return;
  toggleReview(sp.dataset.key, sp.dataset.field, sp);
});

function setView(v) {
  VIEW = v;
  document.getElementById("view-commits").style.display =
    v === "commits" ? "flex" : "none";
  document.getElementById("view-feat").style.display =
    v === "feats" ? "flex" : "none";
  document.getElementById("tab-commits").className = v === "commits" ? "on" : "";
  document.getElementById("tab-feats").className = v === "feats" ? "on" : "";
  render();
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

document.getElementById("col-feats").addEventListener("click", e => {
  const row = e.target.closest(".row"); if (!row) return;
  fi = +row.dataset.f; FEAT = null; renderFeat();
});

document.getElementById("tab-commits").addEventListener("click", () => setView("commits"));
document.getElementById("tab-feats").addEventListener("click", () => setView("feats"));

document.getElementById("filter").addEventListener("input", e => {
  q = e.target.value.trim(); ci = 0; ni = 0; fi = 0; render();
});

document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" && e.key !== "Escape") return;
  if (e.key === "j" || e.key === "ArrowDown") {
    if (VIEW === "feats") fi++; else ci++;
    render(); e.preventDefault();
  }
  else if (e.key === "k" || e.key === "ArrowUp") {
    if (VIEW === "feats") fi--; else ci--;
    render(); e.preventDefault();
  }
  else if (e.key === "/") { document.getElementById("filter").focus(); e.preventDefault(); }
  else if (e.key === "R") { load(); }
  else if (e.key === "Tab") { setView(VIEW === "feats" ? "commits" : "feats"); e.preventDefault(); }
  else if (e.key === "Escape") {
    const f = document.getElementById("filter");
    f.value = ""; q = ""; f.blur(); ci = 0; ni = 0; fi = 0; render();
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


def make_handler(data: Dict[str, Any], feat_store=None, note_store=None,
                 doc_dir: str = "doc", by: str = ""):
    """返回一个绑定好数据的 ``BaseHTTPRequestHandler`` 子类。

    传了 ``feat_store`` 时启用 ``GET /api/feat/<slug>``；
    写操作**仅** ``POST /api/review``（其余 POST 仍 405）。
    """
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

        def _feat_detail(self, slug: str) -> None:
            """按需拉取单条 feat（含正文）。"""
            if feat_store is None:
                body = json.dumps({"error": "feat store 未配置"},
                                  ensure_ascii=False).encode("utf-8")
                self._send(404, body, "application/json; charset=utf-8")
                return
            d = build_feat_detail(feat_store, note_store, doc_dir, slug)
            if d is None:
                body = json.dumps({"error": "not found"},
                                  ensure_ascii=False).encode("utf-8")
                self._send(404, body, "application/json; charset=utf-8")
                return
            body = json.dumps(d, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802 - http.server 约定
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, page, "text/html; charset=utf-8")
            elif path == "/api/data":
                self._send(200, payload, "application/json; charset=utf-8")
            elif path.startswith("/api/feat/"):
                slug = path[len("/api/feat/"):].strip("/")
                self._feat_detail(slug)
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        def do_POST(self):  # noqa: N802
            """唯一写路由：``/api/review``。其余一律 405（不扩大写面）。"""
            path = self.path.split("?", 1)[0]
            if path != "/api/review":
                self._send(405, b"read-only", "text/plain; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001
                self._send(400, b'{"error":"invalid json"}',
                           "application/json; charset=utf-8")
                return

            try:
                result = apply_review(feat_store, payload, by=by)
            except Exception as e:  # noqa: BLE001 - 不泄漏堆栈
                import sys
                print(f"审查写入失败：{e}", file=sys.stderr)
                result = {"ok": False, "_status": 500, "error": "write failed"}

            status = 200 if result.get("ok") else int(
                result.get("_status", 400))
            body = {k: v for k, v in result.items() if not k.startswith("_")}
            if not result.get("ok"):
                body.setdefault("error", "failed")
            self._send(status, json.dumps(body, ensure_ascii=False)
                       .encode("utf-8"), "application/json; charset=utf-8")

        do_PUT = do_DELETE = do_PATCH = do_POST

    return Handler


# ---------------------------------------------------------------------------
# IO 层
# ---------------------------------------------------------------------------


def run(store: NoteStore, cwd: str = ".", port: int = 0,
        open_browser: bool = True, stdout=None,
        feat_store=None, note_store=None, doc_dir: str = "doc",
        by: str = "", _serve_forever: bool = True) -> int:
    """起本地 Web 服务；返回退出码。

    只绑 ``127.0.0.1``（不对外暴露）。``port=0`` 时由系统分配空闲端口。
    传了 ``feat_store`` 时启用 Feat 视图（列表 + ``/api/feat/<slug>``）。
    """
    import sys
    import webbrowser

    out = stdout if stdout is not None else sys.stdout

    note_store = note_store if note_store is not None else store
    git = GitRepo(cwd)
    data = build_data(store, git, cwd=str(cwd))
    data["feats"] = build_feats(feat_store, note_store)
    handler = make_handler(data, feat_store=feat_store,
                           note_store=note_store, doc_dir=doc_dir,
                           by=by)

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
    print(f"feat:   {len(data.get('feats', []))} 条")
    if feat_store is not None:
        print(f"""审查写入：开启（作者 {by or '未设置'}）""")
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
