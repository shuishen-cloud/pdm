# TUI 重写（tui-new-to-fix）

> 先于实现编写。约束新 TUI 的两件事：**绝不为一个异常整屏退出**、
> **测试必须快到能每次都跑**。

## 背景：旧 TUI 的两个问题

1. **使用中直接退出**。Textual 的 `App._handle_exception()` 语义是
   *any unhandled exception panics the app*：只要某个 action / worker /
   事件回调里漏了一个异常，整个 app 立即 `panic()` 退出
   （`return_code=1`），终端还可能留在 raw mode。
   复现见 `tests/tui_new_to_fix/`（对旧 app 的对照用例）。
2. **测试太贵**。旧 `tests/test_tui.py` 100 个用例，每个都 `run_test()`
   起一次完整事件循环，耗时数十秒且时序敏感、偶发核心转储，
   因此被 `-m 'not tui'` 默认排除 → **平时等于没跑**。
   花了成本却没有反馈，是最坏的一种测试。

## 规范

### A. 异常处理（不退出）

1. 所有 action / 消息回调 / 定时任务**必须**走 `guard()` 装饰器。
2. `guard()` 捕获 `Exception`（不捕 `BaseException`，让 Ctrl+C 正常工作），
   转成 `notify(..., severity="error")` 并记录到 `app.errors`。
3. 出错的 action 返回 `None`，**app 继续运行**。
4. 必须有一条测试断言：*action 抛异常后 `app.is_running` 仍为 True*。

### B. 测试预算（硬指标）

| 层 | 文件 | 上限 | 说明 |
|----|------|------|------|
| 纯函数 | `tests/tui_new_to_fix/test_core.py` | **< 0.2s** | 不 import textual |
| 冒烟 | `tests/tui_new_to_fix/test_smoke.py` | **< 3s** | 一个 app 实例 + 参数化键位 |
| 总计 | `tests/tui_new_to_fix/` | **< 5s** | 进默认 CI，不带 `tui` 标记 |

规则：

1. **默认跑**。新测试**不加** `tui` 标记，`pytest` 直接执行。
2. **一个 app 一次启动**：冒烟用例共用一个 `app` fixture（function 内
   只 `run_test` 一次，用参数化在同一上下文里跑多组断言）。
   禁止"每个键位一个 `async with run_test`"。
3. 每个测试文件结尾**必须**有时间预算断言（见 `test_budget.py`），
   超时直接失败，防止回归成慢测试。
4. 渲染细节（截断、宽字符、颜色）一律下沉到纯函数测，
   不在 app 层重复测。
5. 禁止 `asyncio.sleep` 式的等待；用 `pilot.pause()`。

## 接口

```python
# pdev/tui_new_to_fix/core.py —— 无 textual 依赖，可直接单测
def display_width(text: str) -> int
def ellipsize(text: str, width: int) -> str
def kind_counts(notes) -> dict          # {kind: n}，按 kind.value 排序
def commit_line_parts(commit, info, notes, width) -> tuple
def note_line_parts(note, width) -> tuple

# pdev/tui_new_to_fix/guard.py
def guard(fn) -> fn                     # 异常 -> notify + 记录, 不抛出

# pdev/tui_new_to_fix/app.py
class PDMApp(App):
    errors: list[str]                   # 被 guard 吞掉的异常摘要
def run(store, cwd=".", config=None) -> int
```

## 启动方式

```bash
pdm ui --new          # 重写版（试验）
pdm ui                # 旧 Textual TUI（未变）
pdm ui --curses       # 标准库 curses 版
```

验证充分后把 `--new` 提升为默认，再删旧 `pdev/tui/`。

## 实测数据（Textual 8.2.8，本机）

| 项 | 旧 TUI | 新 TUI |
|----|--------|--------|
| 代码量 | 2013 行 | ~720 行 |
| 测试用例 | 100（默认不跑，偶发核心转储） | 27（默认跑） |
| 测试耗时 | 几十秒 | **~2.2s** |
| 异常行为 | panic 退出，`return_code=1` | 提示 + 记入 `app.errors`，继续运行 |

## 实现中实际抓到的 bug

### 1. 换提交后详情面板不更新（运行时）

原因：`NoteList.clear()` 会触发一个携带**旧 item** 的
`ListView.Highlighted`，该消息排在 `_select()` 写好的详情之后到达，
把详情又刷回上一条笔记的内容。
修法：`on_note_list_picked` 里校验 note 是否属于当前提交
（`_owns()`），不属于就丢弃。
测试：`test_boot_and_navigate`。

### 2. 一条笔记被两条提交重复显示（巡检发现）

原因：`core.commit_entries()` 的 `_pick` 每条提交都从头扫全部笔记，
没有排除已认领的。当一条笔记的短 hash 同时是多条长 hash 的
前缀时（如 `abc123` 对 `abc1234…` 与 `abc1235…`），会被认领两次。
修法：`_pick` 接收 `claimed` 集合并跳过已认领的。
测试：`test_commit_entries_ambiguous_prefix_claimed_once`。

### 3. `on_mount` 未包 guard（巡检发现）

原因：只记得给 `action_*` 和消息回调加 `guard`，漏了 `on_mount`。
它抛异常同样会被 Textual 判为 panic 退出——**这正是“启动就挂”的路径**。
修法：`on_mount` 也加 `@guard`。
测试：`test_boot_failure_is_contained`（启动时数据层就抛异常）。

### 4. 测试后门（巡检发现）

首版在正式 `BINDINGS` 里留了 `x` → `action_boom`（自毁键），
还定义了没人用的 `RUNNABLE_ACTIONS`、`_notify_safe`。
修法：全部删除；测试改用 `guard` 直接包装注入的故障，
并用 `test_bound_action_is_guarded` 防止将来漏包。

## 自检清单（改动本包时逐条过）

1. 每个 `action_*` 与 `on_*` 回调是否都有 `@guard`？
   （`test_bound_action_is_guarded` + `test_boot_failure_is_contained`）
2. 新增按键是否真的必要？每多一个键 ≈ 0.12s 测试开销。
3. 渲染逻辑是否下沉到 `core.py`（可纯函数测）？
4. 是否引入了新的 `run_test`？全局不得超过 6 次。
5. 时间预算断言是否仍通过？
