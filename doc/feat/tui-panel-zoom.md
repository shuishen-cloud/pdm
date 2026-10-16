# 主界面三栏：单行条目 + 任意栏放大（tui-panel-zoom）

> 先于实现编写。给重写版 TUI 的**主界面**（提交 / 笔记 / 详情）加
> 两项能力：列表条目**强制单行**、任意栏可**放大**。

## 问题

主界面沿用三栏固定宽度布局（`pdev/tui_new_to_fix/app.py` 的 CSS）：

```css
#commits { width: 36%; }
#notes   { width: 28%; }
#detail  { width: 1fr;  }
```

由此产生两个问题：

1. **条目会折行**。`CommitItem` / `NoteItem` 都没有锁行高，窄栏里
   长 commit subject、长笔记标题会被 Textual 折成 2~3 行，
   一行内容占掉多行高度，列表一屏只能看几条。
   （Feat 面板刚修过同类问题，根因一样：CSS 漏了 `height: 1`。）
2. **截断后看不全**。为单行而截断的长文本没法还原——
   想看完整 commit subject 只能切到 CLI。

**根因**：列表项缺行高约束 + 缺一个"临时把某栏撑大"的查看手段。

## 规范

### 单行渲染

| 项 | 做法 |
|----|------|
| 行高 | CSS `CommitItem { height: 1; }`、`NoteItem { height: 1; }` |
| 截断 | 按**栏宽**用 `core.ellipsize` 截断（CJK 算 2 列） |
| 纯函数 | 拼接逻辑留在 `core.commit_line_parts` / `core.note_line_parts`，可毫秒级测 |

**只对两个列表生效**：详情栏是阅读区，**不锁单行**（多行是它的本职）。

### 放大（三态互斥）

| 状态 | `#commits` | `#notes` | `#detail` |
|------|-----------|----------|-----------|
| 常规 | 36% | 28% | 1fr |
| 放大提交 | **1fr** | hidden | hidden |
| 放大笔记 | hidden | **1fr** | hidden |
| 放大详情 | hidden | hidden | **1fr** |

- 用容器 class 切换：`#body.zoom-commits` / `.zoom-notes` / `.zoom-detail`，
  三态互斥（同一时刻最多一个 class）。
- 放大态下其余两栏 `display: none`（而不是收窄）——目的是**最大化**
  被截断内容的可视宽度。
- 再按一次还原为常规三栏。

### 按键（与 Feat 面板保持一致）

| 键 | 作用 |
|----|------|
| `Enter` | 放大当前焦点所在栏 / 再按还原 |
| `z` | 同 `Enter`（别名，便于连续操作） |

**必须拦截 `Enter`**：Textual 的 `ListView` 会把 `Enter` 当"选中"吃掉，
App 级绑定收不到（Feat 面板实测 `action_toggle_zoom` 触发 **0** 次）。
做法：在 `CommitList` / `NoteList` 子类里实现 `key_enter()` 并返回 `True`。

### 不做（保持范围）

- ❌ 鼠标拖拽调栏宽
- ❌ 记忆栏宽到配置文件
- ❌ 列宽预设方案
- ❌ 详情栏内部分区放大（如只放大验证脚本块）

## 接口

```python
# pdev/tui_new_to_fix/core.py —— 纯函数
#   commit_line_parts() / note_line_parts() 已存在，本 feat 复用（不新增）

# pdev/tui_new_to_fix/app.py

ZOOM_CLASSES = {"commits": "zoom-commits",
                "notes": "zoom-notes",
                "detail": "zoom-detail"}

class PDMApp(App):
    _zoomed: Optional[str]          # 当前放大的栏 id；None = 常规

    def zoom_target(self) -> Optional[str]:
        """当前焦点落在哪一栏（"commits"/"notes"/"detail"）；不在三栏则 None。"""

    def action_toggle_zoom(self) -> None:
        """放大当前栏 / 再按还原。写 class 并 notify。"""
```

`CSS` 增加三态规则；`CommitList` / `NoteList` 增加 `key_enter`。

## 日志

- 放大：`notify("已放大：<栏名>")`
- 还原：`notify("已还原")`
- 焦点不在三栏：静默 no-op（不报错）

## 兜底

| 情况 | 处理 |
|------|------|
| 焦点不在三栏（如在 Footer/弹窗内） | `zoom_target()` 返回 None，action 静默 no-op |
| 列表为空 | 放大仍可用（栏照常撑满） |
| `_zoomed` 与 class 不一致（异常路径） | 每次 action 先清掉全部 zoom class 再写目标态，**幂等** |
| 渲染/查询异常 | 走 `@guard`，app 不退出 |

## 验证方法

```
test=tests/tui_new_to_fix/test_core.py::test_note_line_parts_truncates_title
test=tests/tui_new_to_fix/test_smoke.py::test_boot_and_navigate
test=tests/tui_new_to_fix/test_smoke.py::test_exception_in_action_does_not_kill_app
cmd=.venv/bin/pdm ui --new 然后按 Enter / z
manual=选一栏按 Enter 看它撑满、再按还原；用长 subject 的提交验证单行截断
expected=列宽变化正确、条目始终单行
```

## 实现与校验结果（收尾）

实现于 `332edb46`（test `780244d7`、doc `c4a9274b`、
集成回填 `5fdf10be`）。

**状态：已闭环（closed）**。集成期发现的两个缺陷已修并记入笔记；
遗留的 pytest 退出段错误已隔离并转入独立 feat。

### 交付物

| 文件 | 内容 |
|------|------|
| `pdev/tui_new_to_fix/app.py` | CSS 加 `CommitItem/NoteItem { height: 1 }` 与三态 zoom class；`+zoom_target` / `+action_toggle_zoom`；`CommitList` / `NoteList` `+key_enter` |
| `tests/tui_new_to_fix/test_smoke.py` | 单行断言 + 三态放大断言 + 焦点不在栏内时 no-op |
| `doc/feat/tui-panel-zoom.md` | 本文档 |

**零新增依赖**：`pyproject.toml` 未改。

### 实测（`run_test`，尺寸 100x30）

| 状态 | `#commits` | `#notes` | `_zoomed` |
|------|-----------:|---------:|-----------|
| 常规 | 34 | 26 | `None` |
| 放大提交 | **98** | 0 | `commits` |
| 放大详情 | 0 | 0 | `detail` |
| 还原 | 34 | 26 | `None` |

列表项高度断言：`commits` 两条、`notes` 一条，**全部 height=1**（单行生效）。

### 与设计文档的差异

- 文档未提但实现时新增：`zoom_target()` 会**向上找祖先**，
  以支持焦点落在栏内子控件（如详情里的 `Static`）的情况。
- `_zoom_parent(widget)` 辅助函数：沿 `screen` → `app` 找
  `action_toggle_zoom`，不硬编码 `self.app.screen`（弹窗场景下
  screen 不是主界面）。

### 本次发现的异常（已记笔记）

1. **`ListView` 吞掉 `Enter`**（pitfall/high）
   App 级 `Binding("enter", ...)` 收不到，必须在子类 `key_enter()`
   里转发并 `return True`。Feat 面板实测 action 触发 **0** 次。
2. **`zoom_target()` 与 `_zoomed` 是两个不同的量**（pitfall/medium）
   前者答“Enter 会作用于谁”，后者答“现在放大的是哪栏”。
   测试里曾混淆，导致还原后的断言失败。断言状态请用 `_zoomed`。
3. **pytest 退出时段错误（退出码 139）**（bug/high，**独立问题**）
   与本 feat 无关（`git stash` 验证改动前同样崩），
   详见下节。

### 遗留问题（不属本 feat 范围）

跑 `tests/tui_new_to_fix/test_feat_ui.py` 时，pytest 会输出
`5 passed` 但**以退出码 139 结束**——崩溃发生在解释器关闭阶段。

- 范围：仅该文件触发（`test_core` / `test_feat_core` / `test_smoke`
  退出码均为 0）。
- 触发条件：`FeatStore` 写盘 + `pilot.press` 按键路径同时存在。
- 影响：CI 会误判失败，且掩盖真实失败。
- 已记入笔记（bug/high），**需单开 feat 排查**。

### 已知限制（有意不做）

- 不记忆栏宽到配置（每次启动为默认比例）。
- 不支持鼠标拖拽调栏宽。
- 详情栏内不分区放大（只能整栏）。
