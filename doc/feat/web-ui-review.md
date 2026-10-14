# Web UI 增加 Review 勾选（web-ui-review）

> 先于实现编写。给 Web UI 的 Feat 详情加 `[审]` / `[测]` 两个**可点勾选框**。
> 这是 Web UI 的**首个写操作**，因此本文档的重点是**约束与风险**，不是功能。

## 问题

Web UI 至此全是只读：`do_POST` 一律 405。缺 Review 勾选意味着：

- 网页只能"看"审查进度（`8/11`），不能像 TUI 那样勾；
- 且**写操作一旦引入，就打破了"只读"这一既有安全假设**——之前所有
  "绑 127.0.0.1 就够安全"的论证都只适用于读。

**根因**：不是缺按钮，而是缺一套**针对写操作的约束设计**。

## 规范

### 安全约束（本 feat 的核心）

| 约束 | 做法 | 理由 |
|------|------|------|
| 仅本机 | 仍只绑 `127.0.0.1` | 局域网不可达 |
| 仅最小面 | 只有 **一个** POST 路由 `/api/review` | 不开放通用写/删除 |
| 仅两个字段 | 只允许改 `reviewed` / `tested` 布尔位 | 不允许改标题、正文、状态 |
| 白名单校验 | `field ∈ {review,test}`、`value` 必须 bool | 拒绝任意字段注入 |
| 不接受任意路径 | `slug` 只用于查 store，**不拼文件路径** | 防路径穿越 |
| 校验可审项 | `key` 必须 ∈ `feat.review_items()` | 防写脏 key |
| 无堆栈泄漏 | 出错只回 `{"error": "..."}` | 不暴露内部路径 |
| 无 CSRF 面 | 只绑 localhost + 无 cookie/凭据 | 同机同用户模型 |

**显式声明**：本 UI **不做认证**。它与 TUI 同级——任何能在本机跑命令的人
都能改 `.pdm/`。引入认证是另一个层面的需求，本文档不含。

### 单点写入（复用既有实现）

**不得**在 `webui.py` 里直接改 JSON 或调 `feat.set_reviewed()` 后自行落盘。
统一走：

```
FeatStore.set_reviews(slug, keys, reviewed=..., tested=...,
                      by=..., command=..., status=...)
```

理由：该方法已是 CLI 的唯一写入口，具备

- 一次性 `update()` 落盘（原子写，避免半写）；
- `_prune` 清理空记录（保持 JSON 精简）；
- key 合法性由 `_review_slot` 兜底校验。

Web 端复用它 = 与 CLI **行为完全一致**，不会出现"网页勾了但 CLI 行为不同"。

### 接口

| 方法 | 路径 | 行为 |
|------|------|------|
| `POST` | `/api/review` | 改一个勾选位；成功 `200` + 新计数 |
| `POST` | 其他 | 仍 `405`（不扩大写面） |
| `GET` | 不变 | 只读 |

请求体（JSON）：

```jsonc
{"slug": "web-ui", "key": "api:0", "field": "review", "value": true}
```

响应：

```jsonc
{"ok": true, "slug": "web-ui", "key": "api:0",
 "reviewed": 9, "tested": 0, "total": 11,
 "items": [ {"key": "api:0", "label": "...", "reviewed": true,
             "tested": false, "comment": ""}, ... ]}
```

`items` 回传是为了让前端**局部重渲染**，不必整页重拉。

### 作者（`by`）

取 `config.default_author`（默认 `human:lwy`），由**服务端**决定，
**不接受前端传入**——避免伪造审查者（`stage-review` 要求 `human:` 前缀，
审查位也应一致）。

### 前端

- Feat 详情每个可审项前渲染 `[审]` `[测]` 两个方框（`□`/`■`）。
- 点击 → `fetch("/api/review", {method:"POST", ...})` → 用返回的 `items`
  局部更新方框与顶部计数。
- **不做乐观更新**：等服务器确认再改 UI，避免失败时显示假的勾。

**不做**（保持范围）：

- ❌ 阶段级审核（`stage-review`）勾选
- ❌ 条目评论编辑（`feat comment`）
- ❌ 写笔记 / 跑验证 / 改状态
- ❌ 多用户 / 认证 / 审计日志

## 接口

```python
# pdev/webui.py

def build_review_items(feat) -> List[dict]:
    """可审项含勾选态与评论。**纯函数。**
    返回 [{"key","label","reviewed","tested","comment"}, ...]。"""

def apply_review(feat_store, payload: dict, by: str = "") -> dict:
    """校验并写入一个勾选位。返回响应 dict（含错误）。

    - payload 非法 → {"ok": False, "error": ..., "_status": 400}
    - slug 不存在 → 404；feat_store 为 None → 403
    - 成功 → {"ok": True, "reviewed": ..., "tested": ..., "total": ...,
              "items": [...]}
    """
```

`build_feat_detail` 增加 `"review_items"` 字段。
`make_handler` 增加 `POST /api/review`；需新增 `by` 参数。

## 日志

- 成功：静默（前端已更新）。
- 失败：stderr 一行 `审查写入失败：<原因>`；HTTP 响应体只含简短 error。

## 兜底

| 情况 | 处理 |
|------|------|
| `feat_store` 为 None | 403，不尝试写入 |
| JSON 解析失败 | 400 `invalid json` |
| `field` 不在白名单 | 400 |
| `value` 非 bool | 400 |
| `slug` 不存在 | 404 |
| `key` 非可审项 | 400（由 `FeatStore` 抛 `FeatError` 转 400） |
| 写入 IO 失败 | 500，stderr 记录，响应不泄漏路径 |
| 并发点击 | `FeatStore.update` 每次重读-写，最后写胜；**单机单用户可接受** |

## 验证方法

```
test=tests/test_webui_review.py::test_build_review_items_shape
test=tests/test_webui_review.py::test_apply_review_sets_reviewed
test=tests/test_webui_review.py::test_apply_review_rejects_bad_field
test=tests/test_webui_review.py::test_apply_review_unknown_slug_404
test=tests/test_webui_review.py::test_apply_review_by_comes_from_server
test=tests/test_webui_review.py::test_post_review_route_writes
test=tests/test_webui_review.py::test_other_post_still_405
cmd=.venv/bin/pdm ui --web 然后点勾选框
manual=勾一个 [审]，刷新页面确认持久；用 CLI pdm feat review <slug> 验证一致
expected=网页与 CLI 看到同一状态
```
