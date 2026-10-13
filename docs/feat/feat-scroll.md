# Feat 界面滚动与焦点（feat-scroll）

> 先于实现编写。约束 Feat 面板的浏览交互。

## 问题

`FeatScreen` 右侧详情是一个 `Static`（`overflow-y: auto`），
**无法获得焦点、也就无法滚动**。详情（接口 / 日志 / 兜底 / commit /
笔记 / 校验）越长越读不完，且 `j/k` 只能移动左侧列表，无法跨面板。

## 目标

- 左右箭头（含 `h`/`l`）在「feat 列表 ↔ 详情」之间切换焦点
- 上下箭头（含 `j`/`k`）：焦点在列表时移动选中；焦点在详情时滚动详情
- `PgUp` / `PgDn`：无论焦点在哪，直接翻右侧详情
- `Tab`：在列表与详情间切换

## 实现

右侧详情由 `Static` 改为可聚焦、可滚动的 `VerticalScroll`：
`#feat-detail`（VerticalScroll）内嵌 `#feat-detail-body`（Static）。

焦点行为由 `FeatScreen` 的绑定分发：

| 键 | action | 行为 |
|----|--------|------|
| `←` / `h` | `focus_list` | 焦点回左侧列表 |
| `→` / `l` | `focus_detail` | 焦点切右侧详情 |
| `Tab` | `focus_toggle` | 在两者间切换 |
| `↓` / `j` | `move_down` | 列表焦点→移动选中；否则→滚动详情 |
| `↑` / `k` | `move_up` | 同上，向上 |
| `PgDn` | `detail_page_down` | 聚焦并翻详情 |
| `PgUp` | `detail_page_up` | 聚焦并翻详情 |

## 接口

```python
def _detail(self) -> VerticalScroll
def _is_list_focused(self) -> bool
def action_focus_list(self) -> None
def action_focus_detail(self) -> None
def action_focus_toggle(self) -> None
def action_move_down(self) -> None
def action_move_up(self) -> None
def action_detail_page_down(self) -> None
def action_detail_page_up(self) -> None
```

## 兜底

- 无 feat：详情显示「（无 feat，用 pdm feat new 创建）」，列表为空，滚动无内容不崩
- `r` 刷新会 recompose，刷新后重新聚焦列表，避免焦点丢失
- 焦点在详情时 `j/k/↑/↓` 由 `VerticalScroll` 自身先处理（滚动），与 Screen 分发一致

## 实现与校验结果（收尾）

实现于 commit dd22ca6，测试于 bc4c416。

新增测试 `test_feat_screen_arrows_switch_focus_and_scroll`：
验证初焦点在列表、`↓`/`k` 改变 `ListView.index`、`→`/`←` 切焦点、
`PgDn` 聚焦详情。全部 TUI 测试通过。

### 本次发现的异常

1. `BINDINGS` 用元组写 `show=False` 会 `SyntaxError`
   （元组形式不支持关键字参数），需改用 `textual.binding.Binding`。
2. 原详情是 `Static`，即便加了 `overflow-y: auto` 也**无法聚焦**，
   故不能滚动——必须换成 `VerticalScroll` 才能承接焦点与翻页。
