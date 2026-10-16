# 新 TUI 的 Feat 面板与手动审查勾选（tui-feat-review）

> 先于实现编写。给重写版 TUI（`pdev/tui_new_to_fix/`）加一个 Feat 面板，
> 在其上提供 `[审]` / `[测]` 两个**可手动勾选**的位。
>
> 这是新 TUI 的**首个写操作**，因此本文档的重点与 `web-ui-review` 一致：
> **约束与风险**，不是功能。

## 问题

新 TUI 目前只有三栏只读浏览（提交 / 笔记 / 详情），看不到 feat，也不能
勾选审查。用户必须切回 CLI 才能勾，而 `pdm feat check` 会因此一直报
`review-none` / `review-low`。

**根因**：不是缺界面，而是新 TUI **尚无写操作的前例**。一旦引入，
就打破了"只读"这一既有假设——此前所有"`_reload()` 不落盘"的论证
都不再适用。

## 状态的存储（既有能力，无需新建）

审查/测试状态**本来就会持久化**，存在
`.pdm/feats/by-id/<slug>.json` 的 `reviews` 字段，随 git 走：

```json
"api:0": {
  "reviewed": true,
  "reviewed_by": "human:lwy",
  "reviewed_at": "2026-10-16T04:18:49.468834+00:00",
  "tested": true,
  "test_command": "pytest -q",
  "test_status": "passed",
  "tested_at": "2026-10-16T04:18:49.529273+00:00"
}
```

`reviewed` 与 `tested` 是**独立布尔位，互不蕴含**（可只审不测），
但**都会落盘**。本 feat 不需要任何新的存储结构。

## 规范

### 安全约束（本 feat 的核心，对齐 `web-ui-review`）

| 约束 | 做法 | 理由 |
|------|------|------|
| 仅本机 | TUI 本就在本机终端跑 | 无网络面，比 Web UI 更小 |
| 仅最小面 | 只加 `空格`(审) / `t`(测) 两个键 | 不开放通用写/删除 |
| 仅两个字段 | 只允许改 `reviewed` / `tested` 布尔位 | 不允许改标题、正文、状态 |
| 不接受任意路径 | `slug` 只用于查 store，**不拼文件路径** | 防路径穿越 |
| 校验可审项 | `key` 必须 ∈ `feat.review_items()` | 防写脏 key |
| 作者不由界面决定 | `by` 取 `config.default_author` | 防伪造审查者（与 Web UI 同） |
| 无堆栈泄漏 | 出错只 `notify` 摘要 + 记入 `app.errors` | 不暴露内部路径 |
| 不做认证 | 与 CLI / Web UI 同级 | 能在本机跑命令的人本就能改 `.pdm/` |

**显式声明**：本 TUI **不做认证**，与 CLI / Web UI 同级。

### 单点写入（复用既有实现）

**不得**在 TUI 里直接改 JSON，也不得调 `feat.set_reviewed()` 后自行落盘。
统一走 CLI 的同一条写路径：

```
FeatStore.set_reviews(slug, [key], reviewed=..., tested=..., by=...)
```

理由与 `web-ui-review` 相同：它是 CLI 的唯一写入口，具备原子
`update()` 落盘、`_prune` 清理空记录、key 合法性兜底校验。
走同一条路径 = 与 CLI **行为完全一致**。

### 界面形态

| 项 | 选择 | 理由 |
|----|------|------|
| 形态 | **ModalScreen**（`f` 打开，`Esc`/`q` 关闭） | 不污染三栏主布局 |
| 布局 | 左 feat 列表 + 右详情（两栏） | 与旧 TUI 一致，用户已熟悉 |
| `空格` | 切换当前高亮可审项的 `[审]` | 空格是勾选的通例 |
| `t` | 切换当前高亮可审项的 `[测]` | `t`=test 好记；新 TUI 无主题切换，键位空闲 |
| 测试命令 | 不做输入框，`--test` 只置 `passed` | 避免引入 Textual 输入事件面 |

**不做**（保持范围，留给后续 feat）：

- ❌ 条目评论编辑（`feat comment`）→ 拆为独立 feat `tui-feat-comment`
- ❌ 阶段级审核（`stage-review`）
- ❌ 跑 `feat check`
- ❌ 设计文档正文内联渲染（旧 TUI 的 `d` 视图）
- ❌ 关联笔记 / 验证视图切换

### 测试策略（"测试要简单"）

贵的是 `run_test`（≈0.2s/次），不是断言数量。因此：

- **逻辑全部下沉到 `feat_core.py` 的纯函数**，用真 `Feat` 对象测（不落盘、
  无 textual），可随便加用例；
- **app 层只留 2 个用例**：能打开面板看到列表、按 `空格` 后 JSON 真的变了；
- **不单独测** `next_state`（就是 `not x`，无测试价值）；
- **不重复测**写失败兜底——`@guard` 已被
  `test_boot_failure_is_contained` / `test_exception_in_action_does_not_kill_app`
  覆盖；
- 全部用例纳入现有 `tests/tui_new_to_fix/`，共用时间预算（< 2.5s）。

## 接口

```python
# pdev/tui_new_to_fix/feat_core.py —— 纯函数，无 textual 依赖

def review_rows(feat) -> List[tuple]:
    """可审项拆成 (key, label, reviewed, tested)。

    供列表渲染与断言。无 review_items() 或为空时返回 []（不抛异常）。"""

def plan_toggle(feat, key: str, field: str) -> Optional[dict]:
    """校验并算出 set_reviews 的 kwargs；非法返回 None。

    - field ∉ {"review","test"} → None
    - key 不在该 feat 的可审项中 → None
    - 合法 → {"reviewed": bool} / {"tested": bool}（**取反**当前值）

    纯函数：不落盘、不抛异常。"""
```

```python
# pdev/tui_new_to_fix/screens.py

class FeatScreen(ModalScreen):
    """两栏 feat 浏览 + 审查勾选。按下空格/t 时调 store.set_reviews。"""
```

`app.py` 增加绑定 `f` → `action_show_feats`（走 `@guard`），
在其中构造 `FeatStore` 与 `FeatScreen`。`__init__.py` 的 `__all__` 不变。

### 键盘绑定

| 键 | 作用 |
|----|------|
| `f` | 打开 Feat 面板 |
| `↑`/`↓` 或 `j`/`k` | 选 feat |
| `←`/`→` 或 `h`/`l` / `Tab` | 列表 ↔ 详情 切焦点 |
| `空格` | 切换当前高亮的 `[审]` |
| `t` | 切换当前高亮的 `[测]` |
| `Esc` / `q` | 关闭面板 |

## 日志

- 成功：`notify(f"{key} [审] 已勾选（{n}/{total}）")`。
- 失败：`notify(..., severity="error")` + `app.errors.append(...)`。
- 打开/关闭面板：静默。

## 兜底

| 情况 | 处理 |
|------|------|
| `config` 为 None | `by` 用默认 `"human"`，不报错 |
| feat 目录不存在 | `FeatStore` 自行 mkdir（既有行为） |
| feat 列表为空 | 详情显示 `（无 feat，用 pdm feat new 创建）`，不崩 |
| 无任何可审项 | 列表显示 `（无可审项）`，`空格`/`t` 无副作用 |
| `key` 不合法 | `plan_toggle` 返回 None，不落盘 |
| 写入 IO 失败 | 走 `@guard`：`notify` 报错 + 记 `app.errors`，**app 不退出** |
| 与 CLI 并发修改 | `set_reviews` 每次重读-写，最后写胜；单机单用户可接受 |

## 验证方法

```
test=tests/tui_new_to_fix/test_feat_core.py::test_review_rows_shape
test=tests/tui_new_to_fix/test_feat_core.py::test_review_rows_empty_feat
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_toggle_review_field
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_toggle_test_field
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_toggle_rejects_bad_field
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_toggle_rejects_unknown_key
test=tests/tui_new_to_fix/test_smoke.py::test_feat_screen_opens_and_lists
test=tests/tui_new_to_fix/test_smoke.py::test_feat_screen_space_toggles_review
cmd=.venv/bin/pdm ui --new 然后按 f
manual=按 f 打开面板，空格勾一个 [审]，Esc 关闭后用 pdm feat review <slug> 复核
expected=CLI 与 TUI 看到同一状态
```
