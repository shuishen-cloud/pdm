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
┌ 提交 ────────────────────────────┬ 笔记 ────────────────┬ 详情 ──────────────────┐
│ 4fd0fec5  feat(tui): 提交面板…   │ ○ [bug] 计数器内存泄 │ 提交  feat(tui): 提交… │
│ ba390f8d  refactor(tui): 筛选…   │ · [controlled-exce… │ 作者  Wsl_Arch_lwy     │
│ 81357e76  feat(tui): 验证过程…   │ · [difficulty] 粒度… │ 提交号 4fd0fec5b1b6… │
│ a9410362  feat(tui): 便捷启动…   │                       │ ──────────────────── │
│ a109a16d  fix(tui): 修正帮助…    │                       │ （该提交暂无笔记）   │
│ ea47bd11  feat(tui): 完整演示…   │                       │                       │
├──────────────────────────────────┴───────────────────────┴───────────────────────┤
│ q 退出  1 提交  2 笔记  3 详情  / 筛选  r 跑验证  R 刷新  p 命令  ? 帮助            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

| 面板 | 内容 |
|------|------|
| **提交** | git 历史里的**全部** commit（新→旧）；**单行**显示 `hash  标题  类型分布` |
| **笔记** | 选中提交的全部笔记，带状态标记与验证聚合符号；无笔记则为空 |
| **详情** | 提交标题/作者/提交号 + 笔记全字段 + 验证条目（方法 / 命令 / 期望 / 脚本） |

类型缩写：`pro` problem、`bug` 缺陷、`pit` 易错点、`dif` 难点、`exc` 可控异常。

### 提交列表：单行 + 自动截断

每条提交只占**一行**（`hash` + 标题 + 类型分布），尽量多显示条目：

```
4fd0fec5  feat(tui): 提交面板接入…              无笔记
ba390f8d  refactor(tui): 筛选弹窗…  bug:1 exc:1
```

- 标题按**显示宽度**截断（CJK 算 2 列），超出用 `…` 结尾
- 宽度不够时优先保留 `hash` 与类型分布，牺牲标题
- **想看全文**：选中后按 `Enter` / `z` 放大提交面板
- 也可在配置里限制每条最大宽度：

```json
{ "ui": { "commit_width": 60 } }
```

`commit_width` 为 `0`（默认）时跟随面板宽度。

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

### 提交来源

提交面板**以 git 历史为主**（`pdev/git.py` 的 `GitRepo.log()`），
所以即使一条笔记都没写，也能看到整个仓库的提交记录；
每条提交叠加显示自己的笔记：

- **有笔记**：显示 `N notes` + 类型分布（`bug:1 exc:2`）
- **无笔记**：显示灰色的`无笔记`，选中后详情面板展示提交信息 +
  `（该提交暂无笔记）`
- **不在 git 里的伪造 hash**（如演示数据 `c0ffee1`、或已 rebase
  掉的提交）：仍会列出，只是拿不到提交标题

未筛选时列出全部 git 提交；一旦应用筛选，则只保留**命中的提交**，
避免在大量无关提交里翻找。

### 只读且安全降级

- 全部为**只读**的 `git log`，不会修改仓库
- 非 git 仓库时 `git.available` 为假，退回"仅笔记驱动"模式
- 结果在进程内缓存（同一 hash 不重复 fork git）

## 快捷键

| 键 | 作用 |
|----|------|
| `1` / `2` / `3` | 直接跳到 提交 / 笔记 / 详情 面板 |
| `Tab` / `Shift+Tab` | 在面板间循环切换 |
| `←` / `→` 或 `h` / `l` | 焦点左移 / 右移（按面板顺序） |
| `j` / `k` | 当前面板内上下移动 |
| `Enter` / `z` | **放大当前面板**（占满宽度）/ 再按还原 |
| `/` | 打开筛选弹窗 |
| `r` | 弹出验证过程窗口并执行 |
| `R` | 重新从磁盘加载数据 |
| `p` / `Ctrl+P` | 命令面板（搜索并执行应用动作） |
| `t` | 循环切换主题（自动保存） |
| `T` | 弹出主题选择器 |
| `?` | 帮助 |
| `q` | 退出 |

> 鼠标点击列表项也可选中；顶部另有 Textual 自带的命令面板：`Ctrl+P`。

## Feat 面板（按 `f` 打开）

仿 lazygit 两栏：左侧 feat 列表，右侧详情。详情可直接查看设计。

| 键 | 作用 |
|----|------|
| `←` / `→` 或 `h` / `l` | 列表 ↔ 详情 切焦点 |
| `↑` / `↓` 或 `j` / `k` | 列表选 feat；焦点在详情时滚动 |
| `PgUp` / `PgDn` | 直接翻右侧详情 |
| `c` | 对当前 feat 跑自约束校验 |
| `r` | 重新加载 |
| `Esc` / `q` | 关闭 |

### 详情视图切换（互斥）

右侧内容区按 `d` / `n` / `v` **互斥切换**，一次只显示一块，
**再按同一个键回默认（规格）视图**：

| 键 | 视图 | 内容 |
|----|------|------|
| `s` | 规格（默认） | api / logs / fallbacks / commit / 异常 / 校验 |
| `d` | 设计文档 | 内联渲染 Markdown 正文 |
| `n` | 关联笔记 | 按 kind 分组，含 detail / files |
| `v` | 验证 | 全部验证命令与上次状态 |

顶部（slug / 标题 / 阶段 / 状态）**固定不动**，切换视图不丢失上下文；
切换时滚动位置重置到顶部。底部状态栏显示当前视图名。

初始视图可用 `.pdm.json` 配置（`doc_body=true` → 初始 `d` 视图，
`notes_detail=true` → 初始 `n` 视图）：

```jsonc
{
  "feat": {
    "view": {
      "doc_body": false,
      "notes_detail": false,
      "notes_grouped": true,
      "doc_max_lines": 0
    }
  }
}
```

对应环境变量：`PDM_FEAT_VIEW_DOC_BODY` 等。

### 弹窗的关闭方式

| 弹窗 | 关闭键 |
|------|--------|
| 筛选 | `Esc` 取消（保持原筛选）；`Enter` 应用；`Ctrl+L` 清除 |
| 主题 | `Esc` / `q` 取消；`Enter` 选中 |
| 帮助 | `Esc` / `q` / `Enter` / `?` |

## 主题（可保存）

内置 21 套主题（Textual 自带）。三种改法，**都会自动写回配置文件**：

| 方式 | 操作 |
|------|------|
| 循环切换 | 按 `t`，逐个试 |
| 选择器 | 按 `T`，列表里 `Enter` 选中 |
| 命令行 | `pdm theme nord` |

写回目标：优先项目 `.pdm.json`，没有则写 `~/.config/pdm/config.json`：

```json
{ "ui": { "theme": "nord", "commit_width": 60 } }
```

查看当前值与全部可选：

```bash
$ pdm theme
可选主题
    ansi-dark
    ...
  ● nord                 # ● 为当前值
    textual-dark

当前：nord；用 `pdm theme <名字>` 设置
```

主题名拼错会报错并给出相近建议（不会静默忽略）：

```bash
$ pdm theme catpp
未知主题：catpp
是否想要：catppuccin-frappe, catppuccin-latte, catppuccin-macchiato, catppuccin-mocha
```

> 改主题只改外观，不影响存储。若主题名无效（如手动编辑配置写错），启动时回退 `textual-dark`。

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

按 `/` 打开，紧凑单屏显示，字段留空表示不限制：

| 字段 | 说明 | 示例 |
|------|------|------|
| 类型 | `problem` / `difficulty` / `pitfall` / `controlled-exception` / `bug` | `bug` |
| 状态 | `open` / `resolved` / `noted` | `open` |
| 文件 | 支持 gitignore 风格 glob | `src/auth/**` |
| 全文 | 匹配标题 / 详情 / 标签 / catches | `竞态` |

```
┌──────────────────────────────────────────────────┐
│  类型    ▊ problem / difficulty / pitfall / ...  │
│  状态    ▊ open / resolved / noted               │
│  文件    ▊ src/auth/** （支持 glob）             │
│  全文    ▊ 关键字                                │
│                                                  │
│  Enter 应用   ·   Esc/q 取消   ·   Ctrl+L 清除    │
└──────────────────────────────────────────────────┘
```

| 键 | 作用 |
|----|------|
| `Enter` | 校验并应用（非法值会提示并留在弹窗） |
| `Esc` | 取消，**保持原有筛选** |
| `Ctrl+L` | 清除全部筛选 |
| `q` | 只能输入字符（焦点总在输入框）；不会误关 |

筛选在**提交层面**收敛：只要某提交里有一条笔记命中，该提交就保留，随后笔记面板显示它的全部笔记。

导航：`Tab` / `Shift+Tab` 在四个字段间切换。

## 执行验证

选中带验证的笔记，按 `r` 弹出**验证过程窗口**，逐条实时显示：

```
验证  ba6c9e57  锁在异常路径未释放导致后续刷新全部超时
$ pytest test_auth_token.py::test_lock_released_on_error -q
  方法  制造刷新失败，断言锁被释放
  → ✓ 通过

$ pytest test_auth_token.py::test_refresh_safe_single_flight -q
  方法  20 次并发断言只产生一个 token
  → ✓ 通过

共 2 条：通过 2，失败 0
Esc / q 关闭
```

- 命令与参数实时追加；失败/出错时会展开**最后 15 行输出**
- 执行期间 `Esc`/`q` 不会关闭（提示"验证进行中"），完成后才可关闭
- 结果回写存储，关闭后详情面板立即刷新
- `manual` 类型的验证自动跳过

## 代码高亮

详情面板里的测试脚本用 **Pygments**（Textual 自带依赖）做 Python 语法高亮，
配色为 monokai。脚本来源优先级：`script` 字段 > 从 `target` 用 AST 抽取。

## 命令面板

按 `p` 或 `Ctrl+P` 打开，可直接搜索并执行所有应用动作：

| 命令 | 说明 |
|------|------|
| 提交面板 / 笔记面板 / 详情面板 | 跳转 |
| 放大 / 还原 | 撑满当前面板 |
| 筛选 | 打开筛选弹窗 |
| 跑验证 | 弹出验证过程窗口 |
| 切换主题 / 选择主题 | 改外观（自动保存） |
| 刷新 / 帮助 / 退出 | — |

输入关键字模糊匹配，回车执行。

## 状态标记

| 标记 | 含义 |
|------|------|
| 笔记 `·` / `○` / `●` | noted / open / resolved |
| 验证 `✓` / `✗` / `!` / `-` / `·` | 通过 / 失败 / 出错 / 人工 / 未跑 |

## 结构

```
pdev/tui/
├── __init__.py     # 延迟导入，未装 textual 时可安全 import
├── app.py          # PDMApp 主应用、绑定、筛选/验证/主题动作
├── commands.py     # 命令面板 Provider（Ctrl+P / p）
├── panels.py       # CommitList / NoteList / DetailPane（含语法高亮、单行截断）
├── screens.py      # FilterScreen / VerifyScreen / ThemeScreen / HelpScreen
└── app.tcss        # 样式
```

设置写回由 `pdev/config.py` 的 `save_config()` 负责：

- **深合并**，只覆盖传入的键，文件里其它设置不动
- 输出始终是缩进 2 的**严格 JSON**（可读、可 diff）
- 优先写项目 `.pdm.json`；找不到则写用户配置
- `github.token` 拒绝落盘

TUI 与 CLI 平级，都依赖内核（`pdev.*`），互不依赖。

## 无头测试

TUI 有 17 个测试，用 Textual 自带的 `run_test` 驱动，无需真实终端：

```bash
.venv/bin/python -m pytest tests/test_tui.py -v
```
