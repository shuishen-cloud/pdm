# 拆分 FeatScreen：编排 / 详情视图 / 写操作（tui-featscreen-split）

> 先于实现编写。**纯内部重构**：不改按键、不改数据模型、不改 CLI，
> 输出与交互完全一致。**唯一验收标准是现有测试继续通过**。

## 问题

`pdev/tui_new_to_fix/screens.py` 的 `FeatScreen` 已达 **334 行 / 27 个方法**，
承担至少六类职责：

| 职责 | 相关方法 | 行数 |
|------|---------|-----:|
| 数据加载 | `_feats` / `_load_list` / `_current_feat` | 22 |
| 详情渲染 | `_refresh_detail` / `_append_comment` | 46 |
| 焦点与导航 | `_is_list_focused` / `_detail` / `_move_cursor` / `_focus_*` | 41 |
| 放大 | `action_toggle_zoom` | 11 |
| 审查写入 | `_toggle` / `action_toggle_review` / `action_toggle_test` / `_record_error` | 36 |
| 评论编辑 | `action_edit_comment` | 29 |
| 提示栏 | `_update_hint` | 13 |

### 具体症状

1. **`_move_cursor`（25 行）用 `_is_list_focused()` 分支同时处理两种移动**
   （移动 feat 选中 / 移动可审项光标）。之前修"详情不更新"的 bug 时，
   问题正出在这段。
2. **`_toggle`（24 行）与 `action_edit_comment`（29 行）混合了
   写盘与渲染刷新**，无法脱离 Textual 单测——这是测试成本的主要来源。
3. **下一个功能会雪上加霜**：`tui-feat-design` 要加双标签 + 折叠，
   照现状加完约 450 行、职责更加纠缠。

### 依赖分析（拆分可行性）

用 AST 提取 `FeatScreen` 各方法对 `self.X` 的引用，耦合点只有：

- `_rows` / `_cursor` —— 数据状态
- `query_one(...)` —— 渲染

**没有隐晦的交叉调用**，说明可以按职责切开。

## 规范

### 三层划分

```
FeatScreen  编排（~120 行）
  ├─ compose / on_mount
  ├─ 数据加载：_feats / _load_list / _current_feat
  ├─ 焦点导航：_is_list_focused / _move_cursor / _focus_*
  └─ 按键分派：action_* 转发给下面两层

FeatDetail  详情渲染（~90 行）
  ├─ _refresh_detail / _append_comment / _update_hint
  └─ 放大时的渲染配合

FeatOps     写操作（~80 行）—— **不依赖 Textual**
  ├─ toggle_review / toggle_test
  ├─ edit_comment
  └─ 错误记录
```

### 关键约束

1. **`FeatOps` 必须可脱离 Textual 单测**：
   - 构造参数只接 `feat_store` 与 `by`；
   - 方法**返回 `(ok: bool, message: str)`**，不直接调 `notify`；
   - 由 `FeatScreen` 负责把 message 转成 `notify` / 记入 `app.errors`。

2. **状态归属**：`_rows` / `_cursor` 仍由 `FeatScreen` 持有，
   **以参数传给 `FeatDetail`**（避免共享可变状态）。

3. **行为零变化**：按键、提示文案、落盘结果、审查撤销时机全部不变。
   测试是唯一验收标准——**不新增功能**。

4. **不拆文件**：三层都留在 `pdev/tui_new_to_fix/screens.py`
   （拆文件会牵动 import，收益小于风险；先拆类）。

### 不做（保持范围）

- ❌ 加任何新功能（双标签/折叠留给 `tui-feat-design`）
- ❌ 改按键位
- ❌ 拆成多个文件
- ❌ 改数据模型 / CLI

## 接口

```python
# pdev/tui_new_to_fix/screens.py

class FeatOps:
    """Feat 面板的写操作。**不 import textual 的运行时依赖**：

    构造只接 store 与作者；方法返回 (ok, message)，由调用方提示。
    """
    def __init__(self, feat_store, by: str = "human") -> None: ...

    def toggle_review(self, feat, key: str) -> Tuple[bool, str]:
        """切换 [审]。返回 (成功, 提示文案)。"""

    def toggle_test(self, feat, key: str) -> Tuple[bool, str]:
        """切换 [测]。"""

    def edit_comment(self, feat, key: str, text) -> Tuple[bool, str]:
        """写评论（空串 = 清除）。"""

class FeatDetail(VerticalScroll):
    """详情渲染。无状态：渲染所需数据由参数传入。"""

    def render_detail(self, feat, rows, cursor, zoomed=False) -> None: ...

class FeatScreen(ModalScreen):
    """编排层：数据加载 + 焦点 + 按键分派。"""
```

## 日志

与现状完全一致：仍是 `notify(...)`，只是调用点从 `FeatScreen` 改为
收到 `FeatOps` 返回值后转发。**不改变任何文案**。

## 兜底

| 情况 | 处理 |
|------|------|
| `FeatOps` 写入失败 | 返回 `(False, 原因)`；`FeatScreen` 调 `_record_error` + `notify` |
| 拆分后某处漏接线 | **集成测试会失败**（行为不变是硬约束） |
| `FeatOps` 单测无法构造 | 说明它仍依赖 Textual —— 视为设计失败，回退 |

## 验证方法

```
test=tests/tui_new_to_fix/test_feat_ops.py::test_toggle_review_persists
test=tests/tui_new_to_fix/test_feat_ops.py::test_toggle_test_does_not_touch_review
test=tests/tui_new_to_fix/test_feat_ops.py::test_edit_comment_roundtrip
test=tests/tui_new_to_fix/test_feat_ops.py::test_edit_comment_empty_clears
test=tests/tui_new_to_fix/test_feat_ops.py::test_bad_key_returns_false
test=tests/tui_new_to_fix/test_feat_ui.py::test_feat_panel_toggle_and_persist
test=tests/tui_new_to_fix/test_feat_ui.py::test_feat_comment_roundtrip
test=tests/tui_new_to_fix/test_feat_ui.py::test_feat_list_single_line_zoom_and_focus
cmd=.venv/bin/python -m pytest tests/tui_new_to_fix/ -q
manual=按 f 打开面板，勾审/写评论/放大/切焦点，行为与重构前一致
expected=全部测试通过，且 FeatOps 单测不起 app（毫秒级）
```

## 时间预算（中止条件）

预估：doc 10min + test 15min + 实现 25min + 修集成 20min ≈ 70min。

**若实现阶段超过 40min 仍未能让测试变绿，则中止重构、
删除本分支（`refactor/tui-new/ScreenFeat`），回到 `tui-feat-design` 直接硬加。**
