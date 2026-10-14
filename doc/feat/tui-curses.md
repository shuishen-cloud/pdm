# curses 版只读浏览 TUI（tui-curses）

> 先于实现编写。用**标准库 curses** 重做一个**最小可用**的三栏浏览界面，
> 零第三方依赖、行为可预测。**第一步只做只读浏览**，验证方向后再谈扩展。

## 问题

现有 TUI 基于 Textual 8.2.8（第三方，29 个 import 面，2097 行）。
回顾 5 个历史 bug，**3 个是框架特有**：

| bug | 根因 | 是否框架特有 |
|-----|------|:---:|
| 点击 item 崩溃 | 自定义消息名撞 `ListView.Selected` | ✅ |
| 弹窗 `q` 连带退出 App | 全局 `Binding` 向 ModalScreen 冒泡 | ✅ |
| Ctrl+C 退出终端乱码 | 框架接管 raw mode，退出路径未恢复 | ✅ |
| hash 前缀匹配不显示 | 数据身份不清（7/8/40 位混用） | ❌ |
| `notes_for_feat` 短串误匹配 | 同上 | ❌ |

**根因**：抽象层厚 + 全局状态（Binding/消息/终端模式），使边界行为难以预测。
curses 是标准库，**无全局 Binding、无消息系统、无 widget 树**，退出只需
`endwin()`——前 3 类 bug 在结构上不存在。

> 注意：后 2 类（数据身份）**换任何前端都要解决**，本 feat 不处理它们
> （见「不做的事」），避免范围膨胀。

## 规范

### 范围：只做只读浏览（明确边界）

**做**：

- 三栏：提交 / 笔记 / 详情（复用现有信息层次）
- 上下移动选择，`Tab` 或 `1/2/3` 切栏
- `q` 退出
- CJK 宽度正确（复用纯函数）
- 终端过小给出提示而**不崩**

**不做**（留给后续，避免膨胀）：

- ❌ 筛选弹窗、命令面板、主题切换
- ❌ 跑验证、写笔记、任何**写操作**
- ❌ Feat 视图、Review 视图
- ❌ 改动 `pdev/tui/`（Textual 版保持原样，可并行存在）

### 依赖：零新增

- 只用 `curses`（标准库）+ 现有 `pdev.store` / `pdev.git`。
- **不改 `pyproject.toml`**，不加 `[project.optional-dependencies]`。
- Windows 不支持（`curses` 不在其标准库）；检测到不可用 → 提示并退出 2。

### 分层：渲染与 IO 分离（便于单测）

这是本 feat 的**稳定性核心**，直接针对"边界 bug"：

```
run(store, cwd)          ← 唯一碰 curses/终端的地方（IO 层）
      │
      ▼
render_view(view, h, w)  ← 纯函数：数据 → 每行字符串（可无终端单测）
      │
      ▼
build_view(store, git, selection)  ← 纯函数：store/git → CursesView
```

- `build_view` / `render_view` **不 import curses**，可用普通 pytest 断言。
- 终端相关（`initscr`、`addstr`、`getch`）只出现在 `run` 里。
- 这样"选中变化 → 详情内容"的逻辑**不需要启动终端就能测**，避免重蹈
  Textual 版"必须 `run_test` 才能验证"的覆辙。

### 布局与渲染

| 栏 | 宽度 | 内容 |
|----|------|------|
| 提交 | 左 1/3 | `短hash  标题`（截断按显示宽度） |
| 笔记 | 中 1/3 | `标记 [kind] 标题` |
| 详情 | 右 1/3 | 选中笔记的字段与验证 |

- 中间分隔用 `│`，选中项用反色（`curses.A_REVERSE`）。
- 标题行显示 store 路径与当前选中；底部一行显示快捷键提示。
- **最小尺寸**：宽 < 60 或高 < 10 → 只显示一行提示，不画三栏。

### 键位（最小集）

| 键 | 作用 |
|----|------|
| `q` | 退出（返回 0） |
| `j` / `↓` | 下移 |
| `k` / `↑` | 上移 |
| `Tab` / `1` / `2` / `3` | 切换焦点栏 |

**没有全局 Binding 机制**——键全部在 `run` 的主循环里显式 `if` 分发，
不存在"冒泡到别处"的可能。

## 接口

```python
# pdev/tui_curses.py

@dataclass
class CommitRow:
    commit: str          # 完整 hash
    label: str           # 已截断的显示文本

@dataclass
class CursesView:
    commits: List[CommitRow]      # 提交栏全部行
    notes: List[str]              # 笔记栏行
    detail: List[str]             # 详情栏行
    focus: int                    # 当前焦点栏 0/1/2
    cursor: List[int]             # 每栏光标位置 [c, n, d]

def build_view(store, git, selection: Selection) -> CursesView:
    """纯函数：把数据转成待渲染视图。不 import curses。"""

def render_view(view: CursesView, height: int, width: int) -> List[str]:
    """纯函数：视图 → 每行一个字符串（含边框与选中反色标记）。
    返回行数 == height；过小尺寸返回单行提示。"""

def run(store, cwd: str = ".", config=None) -> int:
    """启动 curses 界面；返回退出码。非 tty 或 curses 不可用 → 2。"""
```

`pdev/cli/parser.py` 与 `commands.py`：

```
pdm ui-curses [store]     # 或复用 pdm ui --curses
```

本 feat 在 `ui` 上加一个 `--curses` 开关，**不改默认行为**
（默认仍是 Textual 版，避免破坏现有使用）。

## 日志

- 正常退出：**不打印**（终端已被 curses 接管，打印会污染）。
- 非 tty / curses 不可用：向 stderr 打印一行提示，返回 2。

## 兜底

| 情况 | 处理 |
|------|------|
| stdout 非 tty | 提示 + 退出 2（不进入 curses） |
| `curses` 导入失败（如 Windows） | 提示 + 退出 2 |
| 终端过小 | 单行提示，不画三栏，不崩 |
| store 为空 / 非 git 仓库 | 正常显示空栏与提示，不崩 |
| 运行中抛异常 | `curses.wrapper` 保证 `endwin()`，异常原样上抛 |
| 笔记 JSON 损坏 | 由 store 层跳过（既有行为），UI 不特殊处理 |

**关键**：用 `curses.wrapper(...)` 而非裸 `initscr/endwin`——它自带
`try/finally` + `endwin()`，**终端恢复不依赖我们记得写**。

## 验证方法

```
test=tests/test_tui_curses.py::test_render_view_three_columns
test=tests/test_tui_curses.py::test_render_view_small_terminal
test=tests/test_tui_curses.py::test_build_view_pure_no_curses
cmd=.venv/bin/pdm ui --curses --help
manual=在真实终端运行 pdm ui --curses，上下移动、切栏、q 退出后终端正常
expected=纯函数测试通过；真实终端退出后无乱码
```

「退出无乱码」的实测沿用 `tui-signal-restore` 的教训：**必须确证进程真的
结束**（而非等超时），且退出后终端可正常输入。
