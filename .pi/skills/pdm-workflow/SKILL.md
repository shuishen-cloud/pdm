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
doc → test → script → feat → fix → close
```

- **doc**：先写设计规格（`doc/feat/<slug>.md`），再动代码。
- **test**：按设计写测试。
- **script**：**可选**，先写一次性脚本验证思路（`scripts/try_x.py`），
  再接入正式代码。可从 `test` **直接跳到 `feat`**，不写脚本也行。
- **feat**：实现（接入正式模块）。
- **fix**：Code Review / 修 Bug / 回填发现的异常。
- **close**：收尾文档，置 `closed`。

`script` 是唯一可选阶段：`pdm feat commit` 的 choices 已含它，
`check` 的 `missing-stage` 不因缺它告警；但一旦有 `script(` 提交，
就必须落在 `test` 之后、`feat` 之前（`stage-order` 约束）。

`pdm feat commit` 会**在提交前**拒绝乱序（如 feat 之后又 test）。允许停留
在当前阶段重复提交（如连续两次 `fix`）。

## 标准流程

记为 `<SLUG>`（小写字母/数字/连字符，如 `token-cache`）。

```bash
# 0. 确认环境：用项目自带启动器或 .venv 里的 pdm
./run.sh --help        # 或 .venv/bin/pdm --help

# 1. 新建 feat，登记设计规格（五项必填，缺一即报错退出 2）
.venv/bin/pdm feat new <SLUG> \
    --title "一句话说明" \
    --doc feat/<SLUG>.md \
    --design-note "为什么这么设计" \
    --impl-note "怎么落地" \
    --data-model "Cache: dict[str,int] —— key→计数" \
    --sample '{"k": 1}' \
    --change "pdev/x.py::Cache —— 新增类" \
    --api "类.方法(参数) -> 返回" \
    --log "会产生什么日志" \
    --fallback "异常兜底策略"
# 没有也要写明「无」，例如 --sample "无：纯计算无外部数据"

# 2. doc 阶段：先写设计文档正文，再提交
#    写 doc/feat/<SLUG>.md（见 references/design-doc.md）
.venv/bin/pdm feat commit doc <SLUG> -m "设计规格" \
    --files doc/feat/<SLUG>.md

# 3. test 阶段：写测试并提交
.venv/bin/pdm feat commit test <SLUG> -m "按设计写测试" \
    --files tests/test_<x>.py

# 4. script 阶段（可选）：先写一次性脚本打通思路
.venv/bin/pdm feat commit script <SLUG> -m "脚本验证思路" \
    --files scripts/try_<x>.py
#    不需要脚本则跳过，直接进 feat

# 5. feat 阶段：实现并提交
.venv/bin/pdm feat commit feat <SLUG> -m "实现" \
    --files pdev/<x>.py

# 6. fix 阶段：修复 / 回填
.venv/bin/pdm feat commit fix <SLUG> -m "修复 <问题>" \
    --files pdev/<x>.py

# 7. close 阶段：在**本 feat 的设计文档**里补写收尾小节，并提交
#    不是改 README——收尾闭环回到 doc/feat/<SLUG>.md 的「实现与校验结果」
.venv/bin/pdm feat commit close <SLUG> -m "收尾文档" \
    --files doc/feat/<SLUG>.md --close

# 8. 自校验
.venv/bin/pdm feat check <SLUG>
```

**注意**：`--files` 每个路径写一次一个 `--files`（是 `action="append"`）；
新文件会被自动 `git add`。设计文档存于 `doc/feat/`（**可跟踪**，随代码走），
所以各阶段都能直接提交设计正文；收尾文档也写回同一份文档（`doc.dir`
控制根目录，默认 `doc`）。

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

## 审查（人工把关，可选但推荐）

三个层级，都作用于 feat：

```bash
# 条目级：给 api/logs/fallbacks/data_model/samples/changes 的每一项打两个勾
# [审] = 人看过，[测] = 测试通过（勾选位置，不进 commit）
.venv/bin/pdm feat review <SLUG>                         # 列出可审项与 [审][测]
.venv/bin/pdm feat review <SLUG> --item api:0 --review --by human:lwy
.venv/bin/pdm feat review <SLUG> --item api:0 --test --cmd "pytest tests/x.py"
.venv/bin/pdm feat review <SLUG> --all --review          # 整条一次勾完
.venv/bin/pdm feat review <SLUG> --item api --review     # 只勾 api 一片（前缀）

# 条目级评论（人写，可留空；缺 -m 则查看，空串则清除）
.venv/bin/pdm feat comment <SLUG> --on api:0 -m "保持最小，不做泛化"
.venv/bin/pdm feat comment <SLUG> --on api:0 --clear

# 阶段级审核：进下一阶段前要求上一阶段已审（默认只告警）
.venv/bin/pdm feat stage-review <SLUG> doc --by human:lwy
.venv/bin/pdm feat stage-review <SLUG> --list            # 看各阶段审核状态

# 汇总：项目代码掌握程度（低覆盖率告警，退出码 1）
.venv/bin/pdm review
.venv/bin/pdm review --unreviewed        # 只看未人工审查的
.venv/bin/pdm review --untested          # 只看未测试通过的
```

**纪律**：

- 审查者必须是 **`human:` 前缀**（防 AI 自审）；AI 用 `ai:` 会被拒。
- 阶段门禁默认**只告警**；开 `config.stage_review.enabled=true` 才硬阻断。
- 历史 feat（`created_at` 早于 `FIELDS_SINCE`）豁免，不被迫补勾。

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
- ❌ commit 前缀用 `doc|test|script|feat|fix` 以外的词：`stage-prefix` 报警
  （`refactor`/`init`/`chore` 等中性前缀例外，不参与阶段判定）。
- ❌ 把 `script` 当必经阶段：它是**可选**的，缺它不告警；但位置错了
  （如 feat 之后又 script）会被 `stage-order` 拦。

## 何时读参考文件

- 完整命令与参数 → `references/commands.md`
- 设计文档该写什么（api/logs/fallbacks 三栏 + 兜底）→ `references/design-doc.md`
- 数据结构、指纹、Issue、Doc 版本 → `references/data-model.md`

> 本 skill 与代码的一致性由 `tests/test_skill_sync.py` 把守：
> 命令面、阶段序列、check 规则表漂移都会直接报错。改代码后若该测试变红，
> **同步改 skill 即可**。

## 运行命令的位置

优先用项目自带启动器 `./run.sh <cmd>`（自动定位 `.venv`）；其次
`.venv/bin/pdm <cmd>`。若在子目录，用 `git rev-parse --show-toplevel`
定位项目根后再执行。

本技能自带包装器 `scripts/pdm`：从任意子目录向上找到项目根（含
`pyproject.toml` 或 `.pdm.json`）后执行，并优先用项目自带的 pdm：

```bash
.pi/skills/pdm-workflow/scripts/pdm feat commit doc <SLUG> -m "设计"
```

若当前项目没有自带 pdm，它会回退到技能所在仓库的 `.venv` 并在 stderr
提示来源，但仍以**当前项目**为操作对象。
