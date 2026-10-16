# ProjectDevelopManager

跟踪项目开发中的**问题、难点、易错点与可控异常**，并与测试、验证、文档版本串联的工具。

- **笔记**是记录（发生了什么），**Issue** 是流程（要解决什么），**文档版本**是快照（当前逻辑是什么）
- 三者通过 commit 连接，数据本地存储、git 友好
- 提供 CLI 与仿 lazygit 的 TUI 两种交互方式

## 设计立场

这个工具的形态由以下六条立场决定。**它们是设计的前提，不是待办项。**
（详细展开见 [`doc/DESIGN_OBSERVATIONS.md`](doc/DESIGN_OBSERVATIONS.md)）

### 1. 主数据是 commit，feat 是视图

> "我最开始的设计就是只要关注一个 Commit 即可，有完整的真实即可
> （如果要检验就切换到那个 Commit 复现代码）"

每个 commit 应当**自洽完整**；要复现/检验，切到那个 commit 即可。
`feat` 只负责把相关 commit 串起来，**不是**必须依赖的第二份真相。

### 2. 质量是设计出来的，不是事后补的

> "代码质量不是后来改进的，而是本来就最小优化后的，不能积攒问题"

不接受"先欠着、以后修"。据此：warning 不应长期堆积；
`check` 的规则要么可行动、要么不报。

### 3. 人工审核有两个目的

> "后期在其中穿插人工验收与审核也是为了获得对于代码的掌握能力，
> 以及产生必要的警告"

**掌握能力**（人对代码的认知）与**门禁**（流程阻断）是两件事，
不应混为一套结构。

### 4. doc 流程是为了追溯

> "借助那些之前的 doc 一系列流程，可以很快追溯到一个功能的设计与历史
> （如果是从头就开始就进行管理的话，并且有 Feat 抽象连接多个 Commit）"

追溯是 doc 流程的**目的**；`Feat` 的作用是连接多 commit。
追溯**双向**才有意义。

### 5. 初衷是减少反复

> "我设计这个项目的初衷是因为 AI 加速开发流程，查看设计以及验收
> 还有整理文档是一件颇为反复的事情"

每个信息只应维护**一处**，入口应**唯一**。

### 6. 主要使用形式是命令行约束 Agent

> "最主要的使用形式乃至最后的使用形式，是使用 pdm 的命令行形式
> 来约束 Agent，实现对于 Agent 十分强大的约束"

**CLI 是主要接口**，用于约束 Agent。约束的关键在**门禁**
（提交前拒绝），而非事后审计。

## 快速开始

```bash
# 1. 虚拟环境（推荐）
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,tui]"

# 2. 记一条笔记（绑定到某次提交）
./run.sh note add abc123 -k pitfall -t "token 刷新有竞态" \
    -F src/auth/token.py -T auth -p high \
    --verify 'test=tests/test_token.py::test_refresh_concurrent;method=200 并发断言只刷新一次'

# 3. 查询
./run.sh query -k pitfall -f 'src/auth/**'
./run.sh verify show abc123          # 看验证方法与脚本

# 4. 图形界面
./run.sh ui                          # 或 ./run.sh ui demo-notes
```

`./run.sh` 会自动使用项目内的 `.venv`，无需先激活。也可 `source .venv/bin/activate` 后直接用 `pdm`。

## 文档

| 文件 | 内容 |
|------|------|
| [doc/使用方法以及效果.md](doc/使用方法以及效果.md) | 全流程使用说明（Feat 生命周期 + 审查 + 笔记/查询/验证） |
| [doc/feat/](doc/feat/) | 各 Feat 的设计文档（每功能一份） |
| [doc/TUI使用说明.md](doc/TUI使用说明.md) | lazygit 风格界面、快捷键 |
| [doc/配置文件说明.md](doc/配置文件说明.md) | `.pdm.json`、环境变量、优先级 |
| [doc/DATA_MODEL.md](doc/DATA_MODEL.md) | 数据结构定义 |

## 数据模型概要

```python
CommitNote(
    commit="abc123",              # 关联提交
    kind=NoteKind.PITFALL,        # problem / difficulty / pitfall
                                  # controlled-exception / bug
    title="token 刷新有竞态",
    detail="...",
    author=Actor("human:lwy"),
    files=["src/auth/token.py"],
    tags=["auth"], severity=Priority.HIGH,
    status=NoteStatus.OPEN,       # open / resolved / noted
    catches=[],                   # 可控异常捕获的异常类型
    verifications=[               # 可执行的验证
        Verification(kind=VerificationKind.TEST,
                     target="tests/x.py::test_y",
                     method="并发断言只刷新一次",
                     expected="passed"),
    ],
    issue_id=None, resolves=[],   # 与 Issue 的双向关联
)
```

## 命令一览

| 命令 | 作用 |
|------|------|
| `pdm note add` | 记笔记（可绑定验证） |
| `pdm note list` / `pdm query` | 组合查询 |
| `pdm show <commit>` | 某次提交的全部笔记 |
| `pdm verify list` / `show` / `run` | 验证的查看与执行 |
| `pdm feat new/list/show/set/link/check` | 开发记录（设计→测试→实现）；`new` 必填设计思路/实现方式/数据结构/样例/既有改动 |
| `pdm feat commit <stage> <slug>` | 阶段提交：由 pdm 创建 commit，强制 doc→test→feat→fix→close 顺序 |
| `pdm feat review <slug>` | 逐项人工审查 / 测试勾选（`[审][测]` 双勾选位） |
| `pdm feat comment <slug> --on <KEY> -m <TEXT>` | 给某条目写人工评论（可留空，多行） |
| `pdm review` | 项目代码掌握程度与低覆盖告警（有告警退出码 1） |

### 阶段提交（推荐用法）

不用手敲 `git commit`，改用 pdm 门面：顺序不对会被**提交前拒绝**，
而不是事后由 `pdm feat check` 发现。

```bash
pdm feat new demo --title "演示" --doc feat/demo.md \
    --design-note "为什么这么设计" --impl-note "怎么落地" \
    --data-model "Cache: dict[str,int] —— 计数" \
    --sample '{"k": 1}' \
    --change "pdev/x.py::Cache —— 新增类"   # 五项均必填（没有也要写明「无」）
pdm feat commit doc   demo -m "写设计"      # 自动生成 doc(demo): 写设计（提交 doc/feat/demo.md）
pdm feat commit test  demo -m "写测试"
pdm feat commit feat  demo -m "实现" --files pdev/x.py
pdm feat commit fix   demo -m "修 bug"
pdm feat commit close demo -m "收尾文档" --close   # 收尾并置 closed
```

- 阶段流水线：`doc → test → script → feat → fix → close`（`close` 前缀仍是 `doc(`）
- 允许停留在当前阶段重复提交，禁止回退（feat 之后不能再 test）
- `--dry-run` 预演，`--no-verify` 跳过 pre-commit 钩子
- 旧数据无游标时，从已有 commit 前缀自动推断
| `pdm feat show <slug> --doc/--notes/--verify` | 查看设计正文与关联笔记 |
| `pdm ui` | TUI（仿 lazygit） |
| `pdm stats` | 总览（含负债 / 资产 / 验证覆盖 / 掌握程度） |

### Feat 审查

给每条 Feat 的可审信息项（`doc` / `api` / `logs` / `fallbacks`）加**两个
独立勾选位**：`[审]` 人工审查、`[测]` 测试通过，逐项勾选；再由全部 Feat
的审查结果算出「项目代码掌握程度」，**人工审核覆盖率过低**时告警。

```bash
pdm feat review review-cli                       # 列出可审项与 [审][测] 状态
pdm feat review review-cli --item api:0 --review --by human:lwy
pdm feat review review-cli --item api:0 --test --cmd "pytest tests/x.py"
pdm feat review review-cli --item api:0 --unreview
pdm feat review review-cli --all --review           # 整条 feat 一次勾完
pdm feat review review-cli --item api --review      # 只勾 api 一片（前缀匹配）
pdm feat comment review-cli --on api:0 -m "接口保持最小，不做泛化"  # 条目级评论
pdm feat stage-review review-cli doc --by human:lwy                     # 阶段级人工审核
pdm feat stage-review review-cli --list                                 # 看各阶段审核状态
pdm feat comment review-cli                      # 列出已写评论
pdm review                                       # 全局掌握程度 + 告警（有告警退出码 1）
pdm review --unreviewed                          # 列出全仓未人工审查的项
pdm review --untested                            # 列出全仓未测试通过的项
pdm review --unreviewed --untested               # 既未审且未测（交集）
pdm review --json                                # 机器可读
```

掌握程度：`score = 0.6 × 人工审核覆盖率 + 0.4 × 测试通过覆盖率`，
分档 `none / poor / fair / good / excellent`；告警只在**过低**时发出
（`no-review`、`low-review`、`untested`）。阈值由 `review.min_coverage`
（默认 `0.6`）控制。`pdm feat show` 的规格栏与 `pdm stats` 末尾也会
显示勾选状态与掌握程度。

`pdm feat check` 同步联动：未审的 feat 会报 `review-none` / `review-low`
（warning，不阻断），使「关了却没审」一眼可见；五项设计字段缺失报
`missing-fields`（仅对 `feat-fields` 之后新建的 feat），改动未定位到符号
报 `vague-change`，样例敷衍报 `empty-sample`。

另可用 `pdm feat comment <slug> --on <KEY> -m <文本>` 给每个条目写**人工评论**
（人手动填，可留空，支持多行），记录「为什么这么定」。评论与 `[审][测]`
勾选**独立**，共用同一套 key（`doc` / `api:0` / `logs:1` …）。

分阶段落地（每条 Feat 独立走 doc→test→feat→fix→close）：

| 顺序 | slug | 内容 | 状态 |
|------|------|------|------|
| 1 | `review-model` | 审查项数据模型（`ReviewItem` + 双勾选位存储） | ✅ 已完成 |
| 2 | `review-score` | 覆盖率评分与低覆盖告警 | ✅ 已完成 |
| 3 | `review-cli` | `pdm feat review` / `pdm review` 命令 | ✅ 已完成 |
| 4 | `review-check` | `pdm feat check` 联动规则 | ✅ 已完成 |
| 4.5 | `review-query` | `pdm review --unreviewed/--untested` 清单 | ✅ 已完成 |
| 4.6 | `feat-comment` | 条目级人工评论（`pdm feat comment`） | ✅ 已完成 |
| 4.7 | `review-batch` | 批量勾选（`--all` / `--item` 前缀） | ✅ 已完成 |
| 4.8 | `feat-fields` | 五项设计字段（设计思路/实现方式/数据结构/样例/既有改动） | ✅ 已完成 |
| 4.9 | `feat-fields-check` | 五项字段校验 + samples 语义 | ✅ 已完成 |
| 5.0 | `stage-review` | 阶段级人工审核门禁 | ✅ 已完成 |
| 5 | `review-tui-read` | TUI 只读显示 `[审][测]` | ⏸ 搁置（TUI 稳定性问题） |
| 6 | `review-tui-toggle` | TUI 空格勾选 | ⏸ 搁置（TUI 稳定性问题） |

## 目录结构

```
pdev/
├── common.py        Actor、utcnow
├── fingerprint.py   代码来源指纹（人/AI）
├── note.py          CommitNote、Verification
├── issue.py         Issue 流程
├── doc.py           文档版本快照
├── store.py         笔记持久化 + 索引
├── query.py         组合查询
├── verify.py        验证执行器
├── scripts.py       测试脚本 AST 抽取
├── stats.py         派生指标
├── config.py        配置合并
├── cli/             CLI 层
└── tui/             TUI 层（与 cli 平级，均依赖内核）

tests/               测试
scripts/seed_demo.py 模拟数据生成
doc/                 项目文档 + feat 设计文档（doc/feat/<slug>.md，可跟踪）
.pi/skills/           AI 代理技能（pdm-workflow）
```

## 给 AI 代理用（Skill）

本仓库内置技能 `.pi/skills/pdm-workflow/`，让 AI 编码代理自动遵循
**doc → test → script → feat → fix → close** 的开发纪律，并通过 `pdm` 门面提交：

- 只经 `pdm feat commit` 创建提交，不手敲 `git commit`
- 每阶段完成后用 `pdm note add --verify` 沉淀笔记与可执行验证
- 收尾跑 `pdm feat check` 自校验

在 pi 中 `/skill:pdm-workflow` 强制加载，或直接让代理“实现某功能”时
按描述自动触发。脚本 `scripts/pdm` 可从任意子目录定位并执行 pdm。

## 开发

```bash
.venv/bin/python -m pytest -q

# 生成模拟数据体验功能
.venv/bin/python scripts/seed_demo.py --store demo-notes --reset
.venv/bin/pdm ui --store demo-notes
```

### 两个演示脚本的区别

| 脚本 | 产出 | 特点 |
|------|------|------|
| `scripts/seed_demo.py` | 纯笔记数据 | 伪造 hash（`c0ffee1`），无 git、无真测试；适合看统计与筛选 |
| `scripts/setup_demo_project.py` | 完整演示项目 | **真 git 仓库 + 真提交 + 真测试**；笔记绑定真实 commit，能看到提交标题、抽取并运行测试脚本 |

```bash
# 完整演示项目（推荐）
.venv/bin/python scripts/setup_demo_project.py --dir demo-project --reset
cd demo-project
../.venv/bin/pdm ui        # 提交标题、测试脚本、验证执行 全部可用
../.venv/bin/pdm verify run
```

## 故障排查

### 退出 TUI 的按键

- **`q`**：主界面直接退出。
- **`Ctrl+C`**：弹出 “Do you want to quit?” 确认框，需再按 **`Ctrl+Q`**
  确认才会退出（Textual 的默认行为，不是卡死）。
- 弹窗内：`Esc` / `q` 关闭弹窗（不会退出应用）。

### TUI 退出后终端乱码、只能关闭终端

**现象**：`pdm ui` 异常退出后，终端出现乱码、光标消失，只能关闭终端窗口。

**预期**：TUI 无论正常结束、异常还是收到信号，都应恢复终端（退出备用屏、
显示光标、关闭鼠标与 bracketed paste）。

**临时缓解**：在乱码终端执行 `stty sane` 或 `reset` 后按回车。

**根因**：Ctrl+C / 信号触发时，`asyncio.run` 硬中断事件循环，跳过了
Textual 的 `stop_application_mode()`，导致终端未恢复。修复在 `PDMApp.run()`
的 `finally` 与信号处理器中无条件调用 `_restore_terminal()` 兜底。

该问题的根因与修复见 `pdm feat show tui-signal-restore`。
