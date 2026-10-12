# TUI 使用说明

仿 [lazygit](https://github.com/jesseduffield/lazygit) 的三栏界面，用于浏览提交笔记、查看验证方法与脚本、直接执行验证。

## 安装与启动

```bash
# 首次：建虚拟环境并安装
python3 -m venv .venv
.venv/bin/pip install -e ".[tui]"

.venv/bin/pdm ui                       # 用配置里的 store
.venv/bin/pdm ui --store demo-notes    # 指定存储目录
.venv/bin/python main.py ui            # 等价入口
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
│ q 退出  h 左移  l 右移  / 筛选  r 跑验证  R 刷新  ? 帮助                  │
└──────────────────────────────────────────────────────────────────────────┘
```

| 面板 | 内容 |
|------|------|
| **提交** | 有笔记的 commit，按 hash 降序；显示笔记数与类型分布缩写 |
| **笔记** | 选中提交的全部笔记，带状态标记与验证聚合符号 |
| **详情** | 笔记全字段 + 验证条目（方法 / 命令 / 期望 / 脚本） |

类型缩写：`pro` problem、`bug` 缺陷、`pit` 易错点、`dif` 难点、`exc` 可控异常。

## 快捷键

| 键 | 作用 |
|----|------|
| `Tab` / `Shift+Tab` | 在面板间循环切换 |
| `h` / `l` | 焦点左移 / 右移（Vim 风格，按面板顺序） |
| `j` / `k` | 当前面板内上下移动 |
| `/` | 打开筛选弹窗 |
| `r` | 对当前笔记执行验证并回写结果 |
| `R` | 重新从磁盘加载数据 |
| `?` | 帮助 |
| `q` | 退出 |

> 顶部另有 Textual 自带的命令面板：`Ctrl+P`。

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
