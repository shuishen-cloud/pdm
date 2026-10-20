# 新 TUI 的主题选项（tui-theme）

> 先于实现编写。让重写版 TUI（`pdev/tui_new_to_fix/`）**读配置主题**，
> 并能在界面内切换、持久化；默认主题 = **Catppuccin Macchiato**。

## 问题

旧 TUI（`pdev/tui/app.py`）早就有主题支持：

- 启动时 `_apply_theme(self._configured_theme())` 读 `config.ui.theme`；
- `t` 循环切换、`T` 弹选择器，都走 `_persist_ui("theme", ...)`
  写**用户配置**；
- `pdm theme [名字]` 列出 / 设置主题。

新 TUI **完全没有**读 `config.ui.theme`：`PDMApp` 只有默认 CSS
（`$primary` / `$surface` 等取自 Textual 默认 `textual-dark`），
所以两个 TUI 主题不一致——`pdm ui --new` 看起来像换了另一个程序。
`pdm theme nord` 对新 TUI 也毫无效果。

## 规范

### 1. 默认主题

`ui.theme` 的默认值已是 `catppuccin-macchiato`（见 `pdev/config.py::UIConfig`）。
本 feat 只需保证：

- 新 TUI 启动时**应用**该值；
- 配置缺失 / 名字无效 → 回退到 `catppuccin-macchiato`（不报错、不退出）；
- 名字大小写 / 连字符写法差异（`Catppuccin Macchiato`）也要认。

### 2. 主题名归一化（纯函数，可毫秒级测）

```python
# pdev/tui_new_to_fix/theme.py —— 不 import textual
DEFAULT_THEME = "catppuccin-macchiato"
def normalize(name, names) -> str
    # 大小写不敏感 + '_'/' ' 视同 '-'；匹配不到返回 DEFAULT_THEME
def is_known(name, names) -> bool
def next_theme(current, names) -> str     # 循环切换
```

**为什么单独成模块**：归一化逻辑要能被测试覆盖，而 `import textual`
在纯函数层是被禁止的（见 `doc/tui-new-to-fix.md` 的测试预算）。
模块只接字符串列表，不碰 textual。

### 3. 应用与持久化（app 层）

| 时机 | 行为 |
|------|------|
| `on_mount` | `theme = normalize(config.ui.theme, available_themes)`，**静默**不 notify |
| `t` | 循环到下一个主题，写入**用户配置**，notify 提示 |
| `T` | 弹出 `ThemeScreen` 选择器（列表 + 回车），选中后持久化 |

- 应用到 `App.theme`；`ThemeScreen` 复用旧 TUI 的设计
  （`● 当前` 标记 + 高亮当前项），但**放在新包内**，不 import `pdev/tui/`
  （旧包将来要删）。
- 持久化失败（只读 HOME 等）只 `notify(warning)`，不中断。
- 所有 action / 回调包 `@guard`——`doc/tui-new-to-fix.md` 硬约束。

### 4. 与 `pdm theme` 的一致性

`pdm theme` 已经是唯一写 `ui.theme` 的 CLI 入口，本 feat 不改它；
只要新 TUI 读同一份用户配置，两边自动一致。

## 接口

```python
# pdev/tui_new_to_fix/theme.py
DEFAULT_THEME: str
normalize(name, names) -> str
is_known(name, names) -> bool
next_theme(current, names) -> str

# pdev/tui_new_to_fix/app.py::PDMApp
action_cycle_theme() -> None       # t
action_pick_theme() -> None        # T
persist_ui(key, value) -> str|None # 写用户配置，失败返回 None

# pdev/tui_new_to_fix/screens.py::ThemeScreen
ThemeScreen(current: str)          # dismiss -> 主题名 | None
```

## 数据模型

无新数据结构。仅复用 `config.ui.theme`（`pdev/config.py::UIConfig`）
与用户配置 `~/.config/pdm/config.json` 的 `ui.theme` 字段。

## 样例

```python
normalize("Catppuccin Macchiato", ["catppuccin-macchiato"])  # -> "catppuccin-macchiato"
normalize("nope", ["nord"])                                  # -> "catppuccin-macchiato"
next_theme("nord", ["dracula", "nord"])                      # -> "dracula"（越界回绕）
```

## 日志

- 切换成功：`notify("主题：nord  (已保存)")`
- 持久化失败：`notify("保存设置失败：...", severity="warning")`
- 启动应用主题：不提示（避免每次启动弹消息）

## 兜底

- `config.theme` 不是字符串 / 为空 / 不在主题表 → 用默认主题，不抛。
- `textual` 未安装：`theme.py` 纯字符串逻辑仍可测；app 层不加载。
- 写用户配置抛异常 → 只提示，主题仍在本会话生效。

## 变更点

- `pdev/tui_new_to_fix/theme.py` —— 新增（纯函数）
- `pdev/tui_new_to_fix/app.py::PDMApp` —— 启动应用主题 + `t`/`T` 两个 action
- `pdev/tui_new_to_fix/screens.py::ThemeScreen` —— 新增主题选择器
- `pdev/tui/app.py::action_pick_theme` —— 改为调用新选择器之外保持行为不变
  （不做，两包各自独立）

## 测试

| 文件 | 内容 | 预算 |
|------|------|------|
| `tests/tui_new_to_fix/test_theme.py` | `normalize` / `next_theme` / `is_known` 纯函数 | < 0.2s |
| `tests/tui_new_to_fix/test_theme_ui.py` | 一次 `run_test`：启动读配置主题落后；`t` 切换并写库 | < 2.5s |

## 影响面

只动 `pdev/tui_new_to_fix/`（新增 `theme.py`、改 `app.py` / `screens.py`）；
旧 TUI、CLI、数据模型均不变；不新增依赖。

## 实现中实际抓到的问题

### 1. `next_theme` 首版对未知当前主题返回“默认主题的下一个”

设计写的是“从默认主题往后取一个”，但实测按 `t` 会直接跳到
`catppuccin-mocha`（默认主题的下一个），与“回退到默认主题”的直觉不符。
改成：**当前主题未知 → 直接返回默认主题**；只有默认主题也不在表里
才退到列表首项。测试：`test_next_theme_unknown_starts_from_default`。

### 2. 测试预算断言假失败（6.85s）

首版 `test_theme.py` / `test_theme_ui.py` 用**模块级** `_T0` 计时，
混在全仓跑时把 import 与其它测试的耗时算进来，budget 断言必挂。
改为 autouse fixture 累加本文件用例耗时（与 `test_smoke.py` 一致）。

### 3. 手敲写法静默失效

`Catppuccin Macchiato` / `catppuccin_macchiato` 在
`App.available_themes` 里查不到，直接 `self.theme = name` 是静默
no-op（用户看到“配置了却没生效”）。`theme._key()` 统一小写并把
`_` / 空格 / `.` 视作 `-` 后再比较。

## 验证结果

```
pytest -q tests/tui_new_to_fix/            # 88 passed
pytest -q                                  # 全仓通过
HOME=/tmp/fakehome pdm theme nord           # CLI 写用户配置
→ 新 TUI 启动主题 = nord（实测）
pytest tests/tui_new_to_fix/test_theme.py  # 15 用例，< 0.2s
```

## 已知边界

- 若 Textual 版本里没有 `catppuccin-macchiato`（当前 8.2.8 有），
  `normalize` 会退回列表首项；此时**不会**提示用户——刻意保持静默，
  因为启动时弹通知太吵。
- 主题切换只影响本进程的 `App.theme`；不用 `App.register_theme`，
  所以无法使用 Textual 主题表之外的自定义主题（不在本 feat 范围）。
