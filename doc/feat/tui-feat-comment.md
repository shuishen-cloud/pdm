# TUI 的 Feat 条目评论编辑（tui-feat-comment）

> 先于实现编写。给重写版 TUI 的 Feat 面板加 **条目评论编辑**：
> 按 `c` 弹出输入框，编辑当前高亮可审项的评论。
>
> 这是新 TUI 的**第二个写操作**（第一个是 `tui-feat-review` 的勾选），
> 也是**第一次引入文本输入**。约束见下。

## 问题

`[审][测]` 两个勾选位只能表达「看过没有」，**表达不了决策内容**：

- `api:0` 被审了，但为什么选这个签名、为什么不泛化，没处记；
- `logs:0` 为什么只在这种时机打，没处记。

CLI 侧已有 `pdm feat comment <slug> --on <KEY> -m <TEXT>`（见
`doc/feat/feat-comment.md`），但 **TUI 里看不到也改不了**——用户必须
切回命令行。

Web UI 明确**不做**评论编辑（见 `doc/feat/web-ui-review.md` 的「不做」），
所以 TUI 是第一个做它的图形界面。

## 规范

### 安全约束（延续 `tui-feat-review`）

| 约束 | 做法 | 理由 |
|------|------|------|
| 仅本机 | TUI 本就在本机终端跑 | 无网络面 |
| 仅最小面 | 只加 `c` 一个键 | 不开放通用写/删除 |
| 仅一个字段 | 只允许改 `comments[key]` | 不允许改标题、正文、状态、勾选位 |
| 不拼路径 | `slug` 只用于查 store | 防路径穿越 |
| 校验可审项 | `key` 必须 ∈ `feat.review_items()` | 沿用 `set_comment` 的校验 |
| 作者不参与 | 评论本身不记 `by`（与 CLI 一致） | 数据模型无该字段 |
| 无堆栈泄漏 | 出错只 `notify` 摘要 + 记入 `app.errors` | 不暴露内部路径 |
| 全部 `@guard` | CommentScreen / FeatScreen 的 action 与回调 | 防止未知异常导致闪退 |

**显式声明**：本 TUI 不做认证，与 CLI / Web UI 同级。

### 单点写入（复用既有实现）

**不得**在 TUI 里直接改 JSON，也不得自行落盘。统一走 CLI 的同一条路径：

```
FeatStore.set_comment(slug, key, text)
```

它是 CLI 的唯一写入口，具备原子 `update()` 落盘、`FeatError` 校验
非法 key、空串即清除（保持 JSON 精简）。走同一条 = 与 CLI 行为一致。

### 输入方式（关键决策）

评论允许 `\n`（见 `feat-comment.md`），因此**必须多行输入**。

| 选择 | 决定 | 理由 |
|------|------|------|
| 控件 | **`TextArea`**（Textual 自带） | 支持多行；`Input` 只能单行 |
| 形态 | **独立 `CommentScreen`（ModalScreen）** | **隔离输入焦点**：文本框的字母/回车不能污染 FeatScreen 的 `j`/`k`/`空格`/`t` |
| 保存键 | **`Ctrl+S`** | 多行输入里回车是换行，不能用作保存 |
| 取消键 | `Esc` | 返回 `None`，**不落盘** |
| 清除 | 保存**空文本** | 与 CLI 的 `--clear` 语义一致（空串即删除该条评论） |
| 外部编辑器 | ❌ 不做 | 挂起 TUI 会离开 Textual 事件循环，正是刚修过的那类终端恢复风险 |

### 交互

| 键 | 作用 |
|----|------|
| `c`（FeatScreen 内） | 编辑当前高亮可审项的评论 |
| `Ctrl+S`（CommentScreen 内） | 保存 |
| `Esc`（CommentScreen 内） | 取消 |

评论与勾选**互相独立**：写评论不等于勾选，勾选也不要求有评论
（沿用 `feat-comment.md` 的立场）。

### 展示

FeatScreen 详情已有「评论」小节（只读）。本 feat 把它保留：

- 有评论的条目，在可审项行下方缩进显示（多行按行缩进）；
- 编辑后立即刷新，无需重开面板。

### 测试策略（延续「测试要简单」）

- **纯函数**（`feat_core.plan_comment`）承担规范化与校验，随便加用例；
- **app 层只加 1 个会话**：`c` 打开弹窗 → 输入 → `Ctrl+S` → 从磁盘复查；
- 不在 app 层重复测多行文本的渲染细节（下沉到纯函数）；
- 时间预算维持现有断言。

## 接口

```python
# pdev/tui_new_to_fix/feat_core.py —— 纯函数，无 textual 依赖

def plan_comment(text) -> Optional[str]:
    """规范化评论文本，供 set_comment 使用。

    - None / 非 str / 全空白 → ""（表示清除该条评论）
    - 其余 → 原样返回（保留内部换行与首尾之外的内容）

    纯函数：不落盘、不抛异常。"""

def comment_rows(feat) -> List[tuple]:
    """带评论的可审项：``(key, label, comment)``。无评论返回 []。"""
```

```python
# pdev/tui_new_to_fix/screens.py

class CommentScreen(ModalScreen):
    """评论编辑弹窗。dismiss 返回 str|None（None=取消）。"""

class FeatScreen(ModalScreen):
    ...  # 新增 c -> action_edit_comment
```

## 日志

- 保存成功：`notify(f"{key} 评论已保存")`（清除时 `... 已清除`）。
- 失败：`notify(..., severity="error")` + `app.errors.append(...)`。
- 打开/取消：静默。

## 兜底

| 情况 | 处理 |
|------|------|
| 无可审项 / 未选中 | `c` 无副作用 |
| `TextArea` 不可用 | 降级：不打开弹窗，`notify` 提示 |
| 非法 key | `set_comment` 抛 `FeatError` → 被 `@guard` 兜住，app 不退出 |
| 保存空文本 | 删除该条评论（不写空串进 JSON） |
| 写入 IO 失败 | `notify` 报错 + 记 `app.errors`，app 继续运行 |
| 评论很长 | `TextArea` 自带滚动；详情侧截断展示 |

## 验证方法

```
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_comment_normalizes
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_comment_empty_means_clear
test=tests/tui_new_to_fix/test_feat_core.py::test_plan_comment_keeps_newlines
test=tests/tui_new_to_fix/test_feat_core.py::test_comment_rows_shape
test=tests/tui_new_to_fix/test_smoke.py::test_feat_comment_roundtrip
cmd=.venv/bin/pdm ui --new 然后按 f、c
manual=按 f 打开面板，c 输入评论，Ctrl+S 保存，Esc 关闭后用 pdm feat comment <slug> 复核
expected=CLI 与 TUI 看到同一状态
```
