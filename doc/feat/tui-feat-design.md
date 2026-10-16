# Feat 详情页分标签：Design（可折叠条目）与 Review（tui-feat-design）

> 先于实现编写。给 FeatScreen 的详情区加**标签页**：
> Design 展示这项功能的设计类内容（可折叠条目），Review 保留现有的
> 可审项勾选与评论。

## 问题

`FeatScreen` 的详情区是一块平铺文本：slug、标题、15 个可审项
（`[□][□] design_note …`）、评论缩进。信息密度低且**没有主次**：

- 想看「这项功能为什么这么设计」要在一堆 `[□][□]` 勾选框里找；
- 想看「审查进度」又要翻过整块字段文本。

且可审项数量在 `feat-edit-fields` 后从 8 涨到 **13~16**
（整块文本字段纳入可审项），平铺的问题被放大。

## 规范

### 双标签

| 标签 | 内容 | 操作 |
|------|------|------|
| **Review**（默认） | 可审项 + 勾选态 + 评论 | `空格` 勾 `[审]`、`t` 勾 `[测]`、`c` 写评论 |
| **Design** | 设计类条目（见下表） | `空格` 展开/收起、`j`/`k` 移条目光标 |

**默认停在 Review**：保持既有行为不变（`空格` = 勾审），
避免用户升级后被静默改变习惯。

### Design 页的条目（12 项，顺序即展示顺序）

| # | 条目 | 来源字段 |
|---|------|---------|
| 1 | 设计思路 | `design_note` |
| 2 | 实现方式 | `impl_note` |
| 3 | 测试方式 | `test_note` |
| 4 | 调试方式 | `debug_note` |
| 5 | 如何扩展 | `extend_note` |
| 6 | 影响面 | `impact` |
| 7 | 重要性 | `importance`（显示 `high（高）`） |
| 8 | 数据结构 | `data_model` |
| 9 | 样例值 | `samples` |
| 10 | 交付接口 | `api` |
| 11 | 日志 | `logs` |
| 12 | 异常兜底 | `fallbacks` |

### 折叠规则

- **默认全部收起**：只显示 `▸ 标题  (N 行)`，看不到正文。
- `空格` 展开当前条目 → `▾ 标题` + 缩进正文；再按收起。
- **空条目**显示 `▸ 标题  （未填）`，**不参与光标**：展开空内容
  无意义，让光标停在那里会导致"按空格没反应"。
- 光标 `▶` 只落在**有内容的**条目上。

### 按键

| 键 | 作用 |
|----|------|
| `d` | 切到 Design |
| `n` | 切到 Review |
| `空格` | **按当前标签分派**：Review = 勾审 / Design = 展开收起 |
| `j` / `k` | 焦点在左列 = 切 feat；焦点在详情 = 移条目光标（Design）或可审项（Review） |
| `←/→` `h/l` `Tab` | 列表 ↔ 详情 切焦点 |
| `Enter` / `z` | 放大左侧列表 |
| `Esc` / `q` | 关闭 |

**切到 Design 时自动把焦点交给详情**：Design 的操作对象是条目而非
左列 feat；否则用户按 `j` 只会切 feat，以为"移动没反应"。

### 光标行为（实测中确定）

1. **循环**：到底再按 `j` 回顶部，到顶再按 `k` 去底部
   （`(cursor + delta) % len(filled)`）。Review 页同样改为循环，
   保持两页一致。
2. **自动滚动**：移动后把当前条目**起始行**滚入视野。
   注意**不能**拿条目**末尾**行号做 `scroll_to(y=end)`——那会把
   条目滚出视野（实测踩过：`span=(11,21)`、视口高 8，`scroll_to(21)`
   后可见区变成 `[21,28]`，条目反而看不见了）。

### 不做（保持范围）

- ❌ 编辑 Design 字段（写操作归 `pdm feat edit` / 未来的 TUI 编辑）
- ❌ 折叠状态持久化（记在屏幕实例上，关闭即重置）
- ❌ 设计文档正文内联渲染（旧 TUI 的 `d` 视图）
- ❌ 第三个标签

## 接口

```python
# pdev/tui_new_to_fix/feat_core.py —— 纯函数，无 textual 依赖

def design_lines(feat, folded=None, cursor=None) -> List[List[tuple]]:
    """Design 页行模型。``folded`` = {section_key: 是否收起}；
    ``cursor`` = 当前高亮条目 key。"""

def design_cursor_span(feat, folded=None, cursor=None) -> Optional[Tuple[int, int]]:
    """当前条目的行范围 (start, end)，用于滚动。"""

def _design_sections(feat) -> List[tuple]:
    """条目定义 [(key, 标题, 值)] —— **单一真相**：
    design_lines 与 design_cursor_span 共用，避免行号漂移。"""

# pdev/tui_new_to_fix/screens.py

class FeatScreen(ModalScreen):
    _tab: str              # "design" | "review"，默认 "review"
    _folded: Dict[str, bool]
    _design_cursor: int

    def _design_filled_keys(feat) -> List[str]:
        """有内容的 Design 条目 key（光标只在这些之间移动）。"""

    def _scroll_design_cursor_into_view(self) -> None: ...
```

## 日志

不弹通知（切标签/折叠是高频操作，`notify` 会刷屏）。
状态变化体现在**底部提示栏**：

```
[DESIGN] Review   design_note 收起   d/n 切标签   空格 展开/收起   ↑/↓ 选条目
```

## 兜底

| 情况 | 处理 |
|------|------|
| 无 feat（列表空） | Design 页显示 `（无 feat）`，光标不存在，`空格` 无副作用 |
| feat 无任何有条目字段 | `_design_cursor_section()` 返回 `None`，`空格`/`j`/`k` 静默 no-op |
| `feat` 对象缺字段 | `getattr` 取默认值，渲染成"（未填）" |
| 详情为空（高度 0） | `scroll_to` 前用 `max(height, 1)`，不除零、不越界 |

## 验证方法

```
test=tests/tui_new_to_fix/test_feat_core.py::test_design_lines_all_sections_collapsed_by_default
test=tests/tui_new_to_fix/test_feat_core.py::test_design_lines_expands_one_section
test=tests/tui_new_to_fix/test_feat_core.py::test_design_lines_covers_all_nine_fields
test=tests/tui_new_to_fix/test_feat_core.py::test_design_lines_marks_empty_section
test=tests/tui_new_to_fix/test_feat_core.py::test_design_cursor_span_matches_render
test=tests/tui_new_to_fix/test_feat_core.py::test_design_cursor_span_unknown_key
test=tests/tui_new_to_fix/test_feat_ui.py::test_feat_list_single_line_zoom_and_focus
cmd=.venv/bin/python -m pytest tests/tui_new_to_fix/ -q
manual=./run.sh ui --new → f → d → j/k（应跟随滚动、到底循环）→ 空格展开收起 → n 回 Review 后空格变勾审
expected=Design 页可浏览全部设计字段，Review 页行为与之前一致
```

## 实现与校验结果（收尾）

实现于 `8f5e2bed`（test `9a36d47e`、doc `647af924`、fix `56c95d0f`）。
**状态：已闭环（closed）**。

### 交付物

| 文件 | 内容 |
|------|------|
| `pdev/tui_new_to_fix/feat_core.py` | `+design_lines` / `+design_cursor_span` / `+design_keys` / `+_design_sections`（单一真相） |
| `pdev/tui_new_to_fix/screens.py` | `+_tab/_folded/_design_cursor`；`+action_primary_action`（空格按标签分派）/`+action_tab_design`/`+action_tab_review`；`+_scroll_design_cursor_into_view`；`_refresh_detail`/`_move_cursor`/`_update_hint` 各加分派 |
| `doc/feat/tui-feat-design.md` | 本文档 |

**零新增依赖**。

### 实测渲染

```
▶ ▸ 设计思路  (2 行)
▸ 实现方式  (1 行)
…
▸ 日志  （未填）

（空格展开后）
▶ ▾ 设计思路
    详情区平铺信息密度低，看设计要在一堆勾选框里找。
    分成 Design 与 Review 两页，Design 用可折叠条目。
```

### 骨架试金石的结论

本 feat 先写骨架验证“重构是否充分”（上一个 feat 的成果）：

| 遇到的问题 | 是否需继续重构 |
|-----------|:---:|
| 默认标签选什么 | 否（改一行，选 Review 保兼容） |
| 空格语义分派 | 否（一个 if） |
| 渲染分派 | 否（3 行） |
| 移动分派 | 否（3 行） |
| 光标停在空条目上 | 否（功能设计缺陷，加 `_design_filled_keys`） |

**结论**：重构是够的，5 个问题里 4 个只需改几行，没有一处需要动
`FeatScreen` 的整体结构；且未改动之前的代码结构（只加分派分支）。

### fix 阶段回填

集成后发现一个**重复定义隐患**：`FeatScreen._DESIGN_KEYS` 与
`feat_core._design_sections` 各维护一份条目顺序，靠人工对比保证一致；
一旦漂移，光标会跳到错条目。

修法：新增 `feat_core.design_keys()` 作为**单一真相**，
`screens.py` 改为派生；补 2 个测试（顺序一致、元组不可变）
与 1 个幂等断言（重复按同一标签键不出错）。

### 本次发现的异常（已记笔记）

1. **滚动跟随不能用条目末尾行号**（pitfall/high）——
   `scroll_to(y=end)` 会把条目滚出视野。
2. **空格含义随标签变化需要“主操作”分派层**（difficulty/medium）——
   否则按键空间冲突；默认标签选 Review 才能保住老行为。

### 遗留问题（不属本 feat）

用户报告 Design 页视图不跟随滚动。无头测试（`size=(100,16)`、
4 项各 10 行全展开）显示滚动逻辑正确（起始行始终在可见区内），
但实际终端仍未复现出“不滚”。已记入笔记（bug/high），
含 4 条待排查方向。

### 已知限制（有意不做）

- 折叠状态不持久化（关闭面板即重置）。
- 不做第三个标签、不做 Design 字段的 TUI 内编辑。
- 不内联渲染设计文档正文。
