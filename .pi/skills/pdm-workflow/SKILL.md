---
name: pdm-workflow
description: Use when developing features or fixing bugs in this project (or any repo that uses the `pdm` / ProjectDevelopManager tool). Enforces the doc → test → feat → fix → doc commit discipline, creates commits only through `pdm feat commit`, and persists per-commit notes (pitfalls, difficulties, controlled exceptions) with runnable verification. Trigger when the user asks to implement a feature, fix a bug, refactor, or record a development note, and when commit history discipline matters.
---

# pdm 开发工作流

本项目的开发纪律由 `pdm`（ProjectDevelopManager）强制。**提交一律经
`pdm feat commit`，不要手敲 `git commit`**——手敲会绕过阶段顺序校验。

## 核心心智模型

三类数据通过 **commit** 连接，不额外建关系层：

| 数据 | 是什么 | 命令 |
|------|--------|------|
| **笔记 Note** | 记录：这次提交踩了什么坑/难点/异常 | `pdm note add` |
| **Feat** | 流程：一次功能开发，横跨多个 commit | `pdm feat` |
| **Doc** | 快照：当前逻辑是什么（设计正文外置 Markdown） | 存于 `feat.doc` 路径 |

关键点：**笔记的 commit 与 feat 的 commit 是同一个 hash**——先提交，再用该
hash 记笔记、link 到 feat。

## 阶段流水线（必须遵守）

每条 feat 的 commit 顺序固定为：

```
doc → test → feat → fix → close
```

- **doc**：先写设计规格（`.pdm/docs/feat/<slug>.md`），再动代码。
- **test**：按设计写测试。
- **feat**：实现。
- **fix**：Code Review / 修 Bug / 回填发现的异常。
- **close**：收尾文档，置 `closed`。

`pdm feat commit` 会**在提交前**拒绝乱序（如 feat 之后又 test）。允许停留
在当前阶段重复提交（如连续两次 `fix`）。

## 标准流程

记为 `<SLUG>`（小写字母/数字/连字符，如 `token-cache`）。

```bash
# 0. 确认环境：用项目自带启动器或 .venv 里的 pdm
./run.sh --help        # 或 .venv/bin/pdm --help

# 1. 新建 feat，登记设计规格（api 要能直接照着写代码）
.venv/bin/pdm feat new <SLUG> \
    --title "一句话说明" \
    --doc feat/<SLUG>.md \
    --api "类.方法(参数) -> 返回" \
    --log "会产生什么日志" \
    --fallback "异常兜底策略"

# 2. doc 阶段：先写设计文档正文，再提交
#    写 .pdm/docs/feat/<SLUG>.md（见 references/design-doc.md）
printf '...' > .pdm/docs/feat/<SLUG>.md   # 实际用编辑工具写
.venv/bin/pdm feat commit doc <SLUG> -m "设计规格" \
    --files .pdm/docs/feat/<SLUG>.md

# 3. test 阶段：写测试并提交
.venv/bin/pdm feat commit test <SLUG> -m "按设计写测试" \
    --files tests/test_<x>.py

# 4. feat 阶段：实现并提交
.venv/bin/pdm feat commit feat <SLUG> -m "实现" \
    --files pdev/<x>.py

# 5. fix 阶段：修复 / 回填
.venv/bin/pdm feat commit fix <SLUG> -m "修复 <问题>" \
    --files pdev/<x>.py

# 6. close 阶段：收尾文档，并置 closed
.venv/bin/pdm feat commit close <SLUG> -m "收尾文档" \
    --files README.md --close

# 7. 自校验
.venv/bin/pdm feat check <SLUG>
```

**注意**：`--files` 每个路径写一次一个 `--files`（是 `action="append"`）；
新文件会被自动 `git add`。`.pdm/` 默认被 gitignore，所以设计文档正文不会
进入 commit——若 doc 阶段没有可提交的代码文件，可用 README 等有实际内容
的文件，或先确认项目是否跟踪 `.pdm/`。

## 记录笔记（贯穿各阶段）

每次 **feat/fix 提交**后，把这次的问题/难点/易错点记下来，并把可复现的
验证方法一并登记：

```bash
.venv/bin/pdm note add <COMMIT_HASH> \
    -k pitfall -t "一句话摘要" \
    -d "详细描述" \
    -F pdev/<x>.py -T <模块> -p high \
    --verify 'test=tests/test_x.py::test_y;method=怎么验证;expected=passed'
```

- `-k` 取值：`problem` / `difficulty` / `pitfall` / `controlled-exception` / `bug`
- `--verify` 支持 `test=<用例>` / `cmd=<命令>` / `manual=<步骤>`
- 可控异常加 `-c <ExceptionType>`
- 解决某 Issue 加 `-r <issue_id>`；升级为 Issue 加 `-i <issue_id>`

**纪律**：`feat(` / `fix(` 提交应当有笔记并绑定验证——`pdm feat check` 会
以 `commit-no-note` / `note-no-verify` 提醒。

## 校验与查询

```bash
.venv/bin/pdm feat check <SLUG>      # 阶段顺序、字段完整性、commit 存在性
.venv/bin/pdm feat check             # 全仓库 + 孤儿 commit
.venv/bin/pdm show <COMMIT>          # 某次提交的全部笔记
.venv/bin/pdm query -k pitfall -f 'pdev/**'   # 这个模块有哪些坑
.venv/bin/pdm query -x 关键词         # 全文搜索
.venv/bin/pdm stats                  # 总览 + 风险项（记了坑没人管）
.venv/bin/pdm verify run             # 执行笔记绑定的验证并回写结果
```

## 反模式（不要做）

- ❌ 直接用 `git commit`：绕过阶段顺序强制，`check` 才会事后报错。
- ❌ 把 test/fix 塞进一次 `feat` 提交：违反纪律，`missing-stage` 会报警。
- ❌ 写完代码才补设计文档：doc 必须在 feat 之前。
- ❌ 记了 `-k pitfall --status open` 却不升级 Issue：会成为 `stats` 里的风险项。
- ❌ commit 前缀用 `doc|test|feat|fix` 以外的词：`stage-prefix` 报警
  （`refactor`/`init`/`chore` 等中性前缀例外，不参与阶段判定）。

## 何时读参考文件

- 完整命令与参数 → `references/commands.md`
- 设计文档该写什么（api/logs/fallbacks 三栏 + 兜底）→ `references/design-doc.md`
- 数据结构、指纹、Issue、Doc 版本 → `references/data-model.md`

## 运行命令的位置

优先用项目自带启动器 `./run.sh <cmd>`（自动定位 `.venv`）；其次
`.venv/bin/pdm <cmd>`。若在子目录，用 `git rev-parse --show-toplevel`
定位项目根后再执行。
