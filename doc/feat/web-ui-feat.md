# Web UI 增加 Feat 视图（web-ui-feat）

> 先于实现编写。给 `pdm ui --web` 增加 **Feat 视图**：列表 / 规格 / 设计正文 /
> 关联笔记。**保持只读与零依赖**，复用 `featview` 纯函数。

## 问题

`web-ui` 只展示"提交 → 笔记"，但**本项目的主流程是 Feat**
（`doc → test → script → feat → fix → close`）。打开网页看不到：

- 有哪些 feat、各自到什么阶段、是否缺字段；
- 某条 feat 的设计规格（api/logs/fallbacks/数据结构/样例/改动）；
- 它的设计正文（`doc/feat/<slug>.md`）；
- 它关联的 commit 与笔记。

TUI 已有 `FeatScreen` 提供这些，但**只能在终端看**，且鼠标不可用。

**根因**：Web 版信息面只覆盖了"笔记"这一半，缺"流程"这一半。

## 规范

### 零依赖与只读不变（硬约束）

- 不新增任何依赖；`pyproject.toml` 不改。
- 仍只绑 `127.0.0.1`；仍只允许 `GET`。
- 前端仍是内嵌原生 JS，无框架、无构建。

### 复用既有纯函数（不重造）

| 需求 | 复用 |
|------|------|
| 读设计正文 | `featview.read_doc_body(doc_dir, feat_doc)` |
| 关联笔记 | `featview.notes_for_feat(feat, note_store)` |
| 笔记分组 | `featview.group_notes_by_kind(notes)` |

**关键**：hash 前缀匹配（笔记 ↔ feat 的 commit）逻辑**已在
`notes_for_feat` 里且带回归测试**，Web 版必须复用它，
**不得在前端或本模块重写**——避免重蹈 `notes_for_feat` 短串误匹配的覆辙。

### 接口扩展

`build_data` 增加 `feats` 字段（列表）；新增单条详情路由。

| 路径 | 返回 |
|------|------|
| `GET /api/data` | 增加 `"feats": [...]`（**不含正文**，保持响应小） |
| `GET /api/feat/<slug>` | 单条 feat 全量（含 `doc_body` 与 `notes`）；未知 slug → 404 JSON |

**为什么不把正文塞进 `/api/data`**：37 条 feat 的正文合起来体积大，
而用户一次只看一条。列表轻量、详情按需拉取。

### Feat 字段（列表项）

```jsonc
{
  "slug": "web-ui",
  "title": "零依赖本地 Web UI",
  "kind": "feat",
  "status": "closed",
  "stage": "close",              // 可能为 null（尚未开始）
  "commit_count": 5,
  "review": [8, 11],             // [已审, 可审]；便于显示 8/11
  "missing_fields": [],          // 缺哪些必填字段（来自 missing_required_fields）
}
```

### Feat 详情（`/api/feat/<slug>`）

在列表项基础上增加：

```jsonc
{
  "design_note": "...", "impl_note": "...",
  "api": ["..."], "logs": ["..."], "fallbacks": ["..."],
  "data_model": ["..."], "samples": ["..."], "changes": ["..."],
  "commits": ["abc1234...", ...],
  "doc": "feat/web-ui.md",
  "doc_body": "# 零依赖本地 Web UI\n...",   // 读不到则为 ""
  "doc_missing": false,                       // true 表示文档缺失
  "discovered": ["fix 阶段发现的异常", ...],
  "stage_reviews": {"doc": {"by": "human:lwy", "at": "..."}},
  "notes": [ {同 note_dict}, ... ],
  "notes_by_kind": [["pitfall", [note, ...]], ...]
}
```

### 前端交互

顶部加**视图切换**：`提交` / `Feat`。

| 视图 | 三栏 |
|------|------|
| 提交 | 提交 / 笔记 / 详情（现状不变） |
| **Feat** | **Feat 列表 / 规格+正文 / 关联笔记** |

- 点 Feat 列表项 → 拉 `/api/feat/<slug>` → 渲染中右两栏。
- 规格栏分区显示：设计思路、实现方式、接口、日志、兜底、数据结构、
  样例、既有改动、关联提交、阶段审核。
- 正文栏渲染 Markdown **极简子集**（标题/列表/代码块/段落），
  **不引 Markdown 库**（保持零依赖）。
- 筛选框在 Feat 视图下过滤 Feat（按 slug/title/正文）。

**不做**（保持范围）：

- ❌ 审查勾选、评论、写操作（只读）
- ❌ 完整 Markdown 渲染（只做标题/列表/代码/段落）
- ❌ 新窗口/深链接路由（单页内切换即可）

## 接口

```python
# pdev/webui.py

def build_feats(feat_store, note_store) -> List[dict]:
    """Feat 列表（不含正文）。**纯函数。** 无 feat_store → []。"""

def build_feat_detail(feat_store, note_store, doc_dir: str,
                      slug: str) -> Optional[dict]:
    """单条 Feat 全量（含 doc_body 与关联笔记）。不存在 → None。"""

def make_handler(data, feat_store=None, note_store=None,
                 doc_dir: str = "doc"):
    """/api/feat/<slug> 由后三个参数支撑；缺省时该路由 404。"""

def run(store, cwd=".", port=0, open_browser=True,
        feat_store=None, note_store=None, doc_dir="doc", stdout=None) -> int:
    """签名扩展；缺省参数时行为与之前一致（feats 为空）。"""
```

CLI：`cmd_ui` 的 `--web` 分支构造 `FeatStore`（按 `config.feat.store`）
并传入。

## 日志

- 启动：打印 feat 数量（如 `feat: 37 条`）。
- 未知 slug：访问日志静默，响应 404 JSON。

## 兜底

| 情况 | 处理 |
|------|------|
| 无 feat store / 目录不存在 | `feats: []`，前端显示"暂无 Feat" |
| slug 不存在 | 404 + `{"error": "..."}` |
| 设计文档缺失 | `doc_body: ""`、`doc_missing: true`，前端提示 |
| 单条 feat JSON 损坏 | `FeatStore._load` 已跳过（既有行为） |
| 正文含 `</script>` 等 | JSON 传输 + 前端 `escapeHtml`，不注入 |
| 笔记匹配 | **一律走 `notes_for_feat`**，不自行 `startswith` |

## 验证方法

```
test=tests/test_webui_feat.py::test_build_feats_shape
test=tests/test_webui_feat.py::test_build_feat_detail_includes_doc_body
test=tests/test_webui_feat.py::test_build_feat_detail_unknown_slug_none
test=tests/test_webui_feat.py::test_api_feat_route_and_404
test=tests/test_webui_feat.py::test_feat_notes_use_featview_matching
cmd=.venv/bin/pdm ui --web
manual=切到 Feat 视图，点一条 feat，看规格与正文；筛选框输入 slug
expected=规格分区完整；正文渲染；未知 slug 不影响页面
```
