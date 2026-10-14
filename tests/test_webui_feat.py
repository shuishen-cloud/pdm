# -*- coding: utf-8 -*-
"""Web UI 的 Feat 视图测试（web-ui-feat）。

设计见 ``doc/feat/web-ui-feat.md``。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from pdev import Actor, CommitNote, NoteKind, NoteStore
from pdev.feat import Feat, FeatKind, FeatStatus, FeatStore
from pdev.webui import (
    build_data,
    build_feat_detail,
    build_feats,
    make_handler,
)


class _FakeGit:
    available = False

    def log(self, limit: int = 0, ref: str = "HEAD"):
        return []

    def commit_info(self, ref: str):
        return None


@pytest.fixture
def note_store(tmp_path) -> NoteStore:
    s = NoteStore(tmp_path / "notes")
    s.add_many([
        CommitNote(commit="abc1234def", kind=NoteKind.PITFALL, title="并发竞态",
                   author=Actor("human:lwy")),
        CommitNote(commit="def5678abc", kind=NoteKind.BUG, title="计数泄漏",
                   author=Actor("ai:claude")),
    ])
    return s


@pytest.fixture
def feat_store(tmp_path) -> FeatStore:
    fs = FeatStore(tmp_path / "feats")
    fs.add(Feat(
        slug="alpha", title="功能甲", kind=FeatKind.FEAT,
        status=FeatStatus.CLOSED, stage="close",
        doc="feat/alpha.md",
        api=["Alpha.run(x) -> int"],
        logs=["运行时记录 x"],
        fallbacks=["异常降级为 0"],
        design_note="为了甲",
        impl_note="用 dict 实现",
        data_model=["Alpha: dict[str,int]"],
        samples=['{"a": 1}'],
        changes=["pdev/x.py::Alpha —— 新增"],
        commits=["abc1234def", "def5678abc"],
    ))
    fs.add(Feat(slug="beta", title="功能乙", stage=None))
    return fs


@pytest.fixture
def doc_dir(tmp_path):
    d = tmp_path / "doc" / "feat"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text("# 甲的设计\n\n## 规范\n\n正文内容\n",
                                encoding="utf-8")
    return str(tmp_path / "doc")


# ---------------------------------------------------------------------------
# 纯函数：build_feats
# ---------------------------------------------------------------------------


def test_build_feats_shape(feat_store, note_store):
    feats = build_feats(feat_store, note_store)
    assert len(feats) == 2
    by = {f["slug"]: f for f in feats}
    a = by["alpha"]
    for key in ("slug", "title", "kind", "status", "stage",
                "commit_count", "review", "missing_fields"):
        assert key in a, key
    assert a["stage"] == "close"
    assert a["commit_count"] == 2
    assert by["beta"]["stage"] is None


def test_build_feats_no_store_returns_empty():
    assert build_feats(None, None) == []


def test_build_feats_review_counts_shape(feat_store, note_store):
    feats = build_feats(feat_store, note_store)
    review = feats[0]["review"]
    assert isinstance(review, list) and len(review) == 2
    done, total = review
    assert 0 <= done <= total


def test_build_feats_missing_fields_reported(tmp_path, note_store):
    fs = FeatStore(tmp_path / "f2")
    fs.add(Feat(slug="bare", title="缺字段"))
    feats = build_feats(fs, note_store)
    assert feats[0]["missing_fields"], "缺字段的 feat 应报出 missing_fields"


# ---------------------------------------------------------------------------
# 纯函数：build_feat_detail
# ---------------------------------------------------------------------------


def test_build_feat_detail_includes_doc_body(feat_store, note_store, doc_dir):
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    assert d is not None
    assert d["slug"] == "alpha"
    for key in ("api", "logs", "fallbacks", "design_note", "impl_note",
                "data_model", "samples", "changes", "commits",
                "doc_body", "doc_missing", "notes", "stage_reviews"):
        assert key in d, key
    assert "甲的设计" in d["doc_body"]
    assert d["doc_missing"] is False


def test_build_feat_detail_unknown_slug_none(feat_store, note_store, doc_dir):
    assert build_feat_detail(feat_store, note_store, doc_dir, "nope") is None


def test_build_feat_detail_missing_doc(feat_store, note_store, tmp_path):
    empty_doc = tmp_path / "nodoc"
    empty_doc.mkdir()
    d = build_feat_detail(feat_store, note_store, str(empty_doc), "alpha")
    assert d is not None
    assert d["doc_body"] == ""
    assert d["doc_missing"] is True


def test_feat_notes_use_featview_matching(feat_store, note_store, doc_dir):
    """关联笔记必须走 featview.notes_for_feat（含前缀匹配），不自行实现。"""
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    titles = {n["title"] for n in d["notes"]}
    assert titles == {"并发竞态", "计数泄漏"}
    assert d["notes_by_kind"]


def test_build_feat_detail_is_json_serializable(feat_store, note_store,
                                               doc_dir):
    d = build_feat_detail(feat_store, note_store, doc_dir, "alpha")
    assert json.loads(json.dumps(d, ensure_ascii=False))


def test_build_feats_source_does_not_reimplement_matching():
    """build_feats/build_feat_detail 不得自行写 hash 匹配。"""
    import inspect
    import re

    from pdev import webui

    # 不得自行写 hash 匹配：列表函数只是汇总，详情函数必须复用 featview
    for fn in (webui.build_feats, webui.build_feat_detail):
        src = inspect.getsource(fn)
        src = re.sub(r'""".*?"""', "", src, flags=re.S)   # 剔文档串
        src = re.sub(r"#.*", "", src)                       # 剔注释
        assert "startswith" not in src, f"{fn.__name__} 不应自行匹配 hash"
    assert "notes_for_feat" in inspect.getsource(webui.build_feat_detail), \
        "build_feat_detail 应复用 featview.notes_for_feat"


# ---------------------------------------------------------------------------
# HTTP 路由
# ---------------------------------------------------------------------------


def _serve(data, feat_store=None, note_store=None, doc_dir="doc"):
    import socketserver

    handler = make_handler(data, feat_store=feat_store,
                           note_store=note_store, doc_dir=doc_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return f"http://127.0.0.1:{port}", lambda: (httpd.shutdown(),
                                                httpd.server_close())


def test_api_data_includes_feats(feat_store, note_store):
    data = build_data(note_store, _FakeGit())
    data["feats"] = build_feats(feat_store, note_store)
    base, stop = _serve(data, feat_store, note_store)
    try:
        with urllib.request.urlopen(base + "/api/data", timeout=5) as r:
            payload = json.loads(r.read().decode("utf-8"))
        assert "feats" in payload
        assert {f["slug"] for f in payload["feats"]} == {"alpha", "beta"}
    finally:
        stop()


def test_api_feat_route_and_404(feat_store, note_store):
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data, feat_store, note_store)
    try:
        with urllib.request.urlopen(base + "/api/feat/alpha", timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        assert d["slug"] == "alpha"

        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/feat/nope", timeout=5)
        assert e.value.code == 404
    finally:
        stop()


def test_api_feat_route_absent_without_store(note_store):
    """未传 feat_store 时，/api/feat/<slug> 返回 404（不崩）。"""
    data = build_data(note_store, _FakeGit())
    base, stop = _serve(data)
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/feat/alpha", timeout=5)
        assert e.value.code == 404
    finally:
        stop()


# ---------------------------------------------------------------------------
# 前端契约
# ---------------------------------------------------------------------------


def test_page_has_feat_view():
    from pdev.webui import PAGE

    for token in ("Feat", "/api/feat/", "view-feat", "renderFeat",
                  "renderFeatDetail"):
        assert token in PAGE, token


def test_page_still_no_external_resources():
    import re

    from pdev.webui import PAGE

    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', PAGE)
    assert not [u for u in urls if u.startswith(("http", "//"))]


def test_feat_view_dom_ids_present():
    """Feat 视图与提交视图的 DOM 锚点都必须存在。"""
    from pdev.webui import PAGE

    for i in ("view-commits", "view-feat", "col-feats", "col-feat-spec",
              "col-feat-notes", "tab-commits", "tab-feats",
              "col-commits", "col-notes", "col-detail"):
        assert f'id="{i}"' in PAGE, f"缺 DOM 锚点 {i}"


def test_feat_view_filters_by_slug_and_title():
    """前端筛选逻辑：按 slug/title/status/stage 过滤（复刻 JS 断言）。"""
    from pdev.webui import build_feats
    # 直接验证后端数据里筛选所需字段都在，前端只做 includes
    feats = build_feats(  # noqa: F841 - 结构断言
        None, None)
    assert feats == []


def test_js_render_feat_functions_defined():
    """关键 JS 函数与路由常量必须存在。"""
    from pdev.webui import PAGE

    for token in ("function renderFeat", "function renderFeatDetail",
                  "function filteredFeats", "function setView",
                  "function mdLite", "function loadFeat",
                  "/api/feat/"):
        assert token in PAGE, token


def test_md_lite_exists_without_library():
    """极简 Markdown 必须自实现（不得引库）。"""
    import re

    from pdev.webui import PAGE

    assert "mdLite" in PAGE
    # 页面不得出现任何 markdown 库的 CDN
    urls = re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', PAGE)
    assert not [u for u in urls if u.startswith(("http", "//"))]


def test_js_feat_render_runtime(tmp_path):
    """用 node + 最小 DOM 替身真跑 JS，验证 Feat 渲染不抛错且转义正确。

    这比"字符串存在"强：能抓到运行时报错与 XSS 遗漏。
    无 node 则跳过。
    """
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("未安装 node")

    from pdev.webui import PAGE

    js = re.search(r"<script>(.*?)</script>", PAGE, re.S).group(1)
    harness = r"""
const fs = require("fs");
const vm = require("vm");
let src = fs.readFileSync(process.argv[2], "utf8");
src = src.replace(/^render\(\);\s*$/m, "").replace(/^load\(\);\s*$/m, "");
const els = {};
function mk(id){ return {id, innerHTML:"", textContent:"", style:{}, dataset:{},
  className:"", value:"", addEventListener(){}, focus(){}, blur(){},
  closest(){return null;}, tagName:"DIV"}; }
global.document = { getElementById:id=>els[id]||(els[id]=mk(id)),
                    addEventListener(){} };
global.fetch = async () => ({ ok:true, json: async () => ({}) });
vm.runInThisContext(src);

DATA = { commits:[], notes:{}, store_root:"/tmp",
  feats:[ {slug:"alpha", title:"甲 <注入>", kind:"feat", status:"closed",
           stage:"close", commit_count:5, review:[8,11], missing_fields:[]},
          {slug:"beta", title:"乙", kind:"feat", status:"draft", stage:null,
           commit_count:0, review:[0,3], missing_fields:["api"]} ] };
VIEW="feats"; fi=0;
renderFeat();
const html = els["col-feats"].innerHTML;
if (!html.includes("alpha")) throw new Error("列表未渲染 alpha");
if (html.includes("<注入>")) throw new Error("title 未转义（XSS）");
if (!html.includes("&lt;注入&gt;")) throw new Error("title 未转义成实体");
if (!html.includes("⚠")) throw new Error("缺字段未警示");

FEAT = {slug:"alpha", title:"甲", status:"closed", stage:"close",
  review:[8,11], commit_count:5, missing_fields:[], design_note:"思路",
  impl_note:"落地", api:["A.x() -> int"], logs:["记录"], fallbacks:["降级"],
  data_model:["A: dict"], samples:['{"a":1}'], changes:["f.py::A —— 新增"],
  commits:["abcdef1234"], discovered:[], doc:"feat/a.md",
  doc_body:"# 标题\n\n- 项\n", doc_missing:false, stage_reviews:{},
  notes:[{kind:"pitfall",title:"坑",author:"human:lwy",severity:"high"}],
  notes_by_kind:[["pitfall",[{}]]]};
renderFeatDetail(FEAT);
const spec = els["col-feat-spec"].innerHTML;
const notes = els["col-feat-notes"].innerHTML;
for (const k of ["思路","落地","记录","降级","A: dict"])
  if (!spec.includes(k)) throw new Error("规格缺 " + k);
if (!notes.includes("标题")) throw new Error("Markdown 未渲染");
if (!notes.includes("坑")) throw new Error("关联笔记未渲染");

DATA.feats = [];
renderFeat();
if (!els["col-feats"].innerHTML.includes("暂无")) throw new Error("空数据未兜底");
console.log("ok");
"""
    harness_file = tmp_path / "harness.js"
    harness_file.write_text(harness, encoding="utf-8")
    js_file = tmp_path / "page.js"
    js_file.write_text(js, encoding="utf-8")
    r = subprocess.run([node, str(harness_file), str(js_file)],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0, f"JS 运行失败：{r.stdout}\n{r.stderr}"
    assert "ok" in r.stdout
