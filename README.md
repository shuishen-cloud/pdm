# ProjectDevelopManager

跟踪项目开发中的**问题、难点、易错点与可控异常**，并与测试、验证、文档版本串联的工具。

- **笔记**是记录（发生了什么），**Issue** 是流程（要解决什么），**文档版本**是快照（当前逻辑是什么）
- 三者通过 commit 连接，数据本地存储、git 友好
- 提供 CLI 与仿 lazygit 的 TUI 两种交互方式

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
| [doc/使用方法以及效果.md](doc/使用方法以及效果.md) | CLI 全部命令与实测输出 |
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
| `pdm feat new/list/show/set/link/check` | 开发记录（设计→测试→实现） |
| `pdm feat show <slug> --doc/--notes/--verify` | 查看设计正文与关联笔记 |
| `pdm ui` | TUI（仿 lazygit） |
| `pdm stats` | 总览（含负债 / 资产 / 验证覆盖） |

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

tests/               289 个测试
scripts/seed_demo.py 模拟数据生成
doc/                 文档
```

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
