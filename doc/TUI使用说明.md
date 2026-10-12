# TUI 使用说明

仿 [lazygit](https://github.com/jesseduffield/lazygit) 的三栏界面，用于浏览提交笔记、查看验证方法与脚本、直接执行验证。

## 安装与启动

```bash
# 首次：建虚拟环境并安装
python3 -m venv .venv
.venv/bin/pip install -e ".[tui]"
```

### 启动方式

| 方式 | 命令 | 说明 |
|------|------|------|
| **便捷脚本** | `./run.sh ui` | 自动使用项目内 `.venv`，无需激活 |
| **便捷脚本 + store** | `./run.sh ui demo-notes` | 位置参数直接指定 store |
| 安装后的入口 | `.venv/bin/pdm ui` | pip 安装时生成 |
| 模块方式 | `.venv/bin/python -m pdev.cli ui` | 不经 console script |
| 主入口 | `.venv/bin/python main.py ui` | 等价 |

激活虚拟环境后可直接用 `pdm`：

```bash
source .venv/bin/activate
pdm ui
deactivate
```

或设为别名（加到 `~/.bashrc`）：

```bash
alias pdm='/path/to/ProjectDevelopManger/run.sh'
```

> TUI 需要交互式终端；`stdout` 不是 tty 时会提示并退出（退出码 2）。
> 未装 textual 时 CLI 其他命令不受影响。

## 界面布局

```
┌ 提交 ────────────┬ 笔记 ──────────────────┬ 详情 ─────────────────────┐
│ c0ffee6  3 notes │ ○ [bug] 计数器内存泄漏  │ [problem] 加分布式锁修复   │
│   bug:1 exc:1    │ · [controlled-except]  │ ────────────────────       │
│   dif:1          │   限流器故障时放行      │ commit    c0ffee3          │
│                  │ · [difficulty] 粒度...  │ author    human:lwy        │
│ c0ffee5  2 notes │                         │ status    resolved         │
│ c0ffee4  4 notes │                         │ files     src/auth/token.py│
│ c0ffee3  2 notes │                         │                            │
│ c0ffee2  4 notes │                         │ 验证                       │
│ c0ffee1  3 notes │                         │ ────────────────────       │
│                  │                         │ · [test] pytest tests/...  │
│                  │                         │     方法  200 并发断言...  │
│                  │                         │     期望  passed           │
├──────────────────┴─────────────────────────┴────────────────────────────┤
│ q 退出  1 提交  2 笔记  3 详情  / 筛选  r 跑验证  R 刷新  ? 帮助           │
└──────────────────────────────────────────────────────────────────────────┘
```

| 面板 | 内容 |
|------|------|
| **提交** | 有笔记的 commit，按 hash 降序；显示提交标题（来自 `git log`）+ 笔记数 + 类型分布缩写 |
| **笔记** | 选中提交的全部笔记，带状态标记与验证聚合符号 |
| **详情** | 提交标题/作者 + 笔记全字段 + 验证条目（方法 / 命令 / 期望 / 脚本） |

类型缩写：`pro` problem、`bug` 缺陷、`pit` 易错点、`dif` 难点、`exc` 可控异常。

### 类型分布染色

提交面板里每个类型的计数用独立颜色，方便扫视：

| 类型 | 缩写 | 颜色 |
|------|------|------|
| `problem` | `pro` | 亮红 |
| `bug` | `bug` | 红 |
| `pitfall` | `pit` | 亮黄 |
| `difficulty` | `dif` | 亮青 |
| `controlled-exception` | `exc` | 亮绿 |

### 标题栏

左上角为应用图标（📓，由 `PDMApp.ICON` 控制），右侧是应用名与当前 store 路径；非 git 仓库时会额外标注 `(非 git 仓库)`。

### 提交标题来源

笔记只存 commit hash，提交标题由 `git log` 实时补齐（`pdev/git.py`）：

- 命中时提交面板显示标题，详情面板顶部也显示标题与作者
- 不在 git 仓库、或 hash 是伪造值（如模拟数据 `c0ffee1`）时，只显示 hash 与笔记统计
- 只读操作，不会修改仓库；结果在进程内缓存

## 快捷键

| 键 | 作用 |
|----|------|
| `1` / `2` / `3` | 直接跳到 提交 / 笔记 / 详情 面板 |
| `Tab` / `Shift+Tab` | 在面板间循环切换 |
| `←` / `→` 或 `h` / `l` | 焦点左移 / 右移（按面板顺序） |
| `j` / `k` | 当前面板内上下移动 |
| `Enter` / `z` | **放大当前面板**（占满宽度）/ 再按还原 |
| `/` | 打开筛选弹窗 |
| `r` | 对当前笔记执行验证并回写结果 |
| `R` | 重新从磁盘加载数据 |
| `?` | 帮助 |
| `q` | 退出 |

> 鼠标点击列表项也可选中；顶部另有 Textual 自带的命令面板：`Ctrl+P`。

### 弹窗的关闭方式

| 弹窗 | 关闭键 |
|------|--------|
| 筛选 | `Esc` 取消；`q` 仅在焦点不在输入框时生效（否则 `q` 是正常输入） |
| 帮助 | `Esc` / `q` / `Enter` / `?` |

## 放大视图

按 `Enter` 或 `z` 把当前焦点面板撑满整个宽度，其余面板隐藏；再按一次还原。

适合看长验证脚本或长详情：

```
┌ 详情（放大）──────────────────────────────────────────┐
│ 提交  feat: 提交笔记与问题追踪工具，含 CLI 与 TUI      │
│ 作者  Wsl_Arch_lwy  2026-10-12 21:27                   │
│ ────────────────────────────────                       │
│ [problem] 加分布式锁修复 token 刷新竞态                │
│ ────────────────────────────────                       │
│ 验证 1: test                                           │
│   方法  200 并发断言 Redis 只被写入一次                │
│   def test_refresh_concurrent():                       │
│       results = run_concurrent(refresh, n=200)         │
└────────────────────────────────────────────────────────┘
```

## 筛选弹窗

按 `/` 打开，字段留空表示不限制：

| 字段 | 说明 | 示例 |
|------|------|------|
| 类型 | `problem` / `difficulty` / `pitfall` / `controlled-exception` / `bug` | `bug` |
| 状态 | `open` / `resolved` / `noted` | `open` |
| 文件 | 支持 gitignore 风格 glob | `src/auth/**` |
| 全文 | 匹配标题 / 详情 / 标签 / catches | `竞态` |

按钮：**应用** 生效、**清除** 重置、**取消** 保持原状。
非法输入（如类型拼错）会提示错误且不关闭弹窗。

筛选在**提交层面**收敛：只要某提交里有一条笔记命中，该提交就保留，随后笔记面板显示它的全部笔记。

## 执行验证

选中带验证的笔记，按 `r`：

- 逐条执行 `effective_command`
- `manual` 类型的验证自动跳过
- 结果（`✓` / `✗` / `!`）回写存储，`R` 刷新后仍可见
- 底部弹通知：`验证：2/3 通过`

无验证时提示 `当前笔记没有可执行的验证`。

## 状态标记

| 标记 | 含义 |
|------|------|
| 笔记 `·` / `○` / `●` | noted / open / resolved |
| 验证 `✓` / `✗` / `!` / `-` / `·` | 通过 / 失败 / 出错 / 人工 / 未跑 |

## 结构

```
pdev/tui/
├── __init__.py     # 延迟导入，未装 textual 时可安全 import
├── app.py          # PDMApp 主应用、绑定、筛选与验证动作
├── panels.py       # CommitList / NoteList / DetailPane
├── screens.py      # FilterScreen / HelpScreen
└── app.tcss        # 样式
```

TUI 与 CLI 平级，都依赖内核（`pdev.*`），互不依赖。

## 无头测试

TUI 有 17 个测试，用 Textual 自带的 `run_test` 驱动，无需真实终端：

```bash
.venv/bin/python -m pytest tests/test_tui.py -v
```
