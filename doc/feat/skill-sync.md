# skill 同步到 pdm 最新进展（skill-sync）

> 先于改动编写。把 `.pi/skills/pdm-workflow` 的命令面与规则，
> 对齐到 **parser 与实现的最新状态**：不新增功能，只消除文档漂移。

## 问题

skill 是人与 AI 操作 pdm 的**唯一入口文档**，但已落后于代码：

| 漂移点 | 代码现状 | skill 现状 |
|--------|---------|-----------|
| 阶段序列 | `doc→test→script→feat→fix→close`，`script` **可选** | 只有 5 段，无 `script` |
| `feat review` | 有（`[审][测]` 双勾选位） | **缺失** |
| `feat comment` | 有（条目级评论） | **缺失** |
| `feat stage-review` | 有（阶段级审核 + 门禁） | **缺失** |
| `feat new` 必填 | 五项设计字段全必填 | 未提 |
| `check` 规则 | 21 个 code（含 `missing-fields` 等） | 只列了 13 个 |
| `stage-prefix` 前缀 | 含 `script(`，另有中性前缀豁免 | 未含 `script` |

**根因**：skill 手写维护，代码演进（`script-stage`、`stage-review`、
`feat-fields`、`feat-comment` 等 feat）落地后没有回头同步 skill。
`tests/test_docs.py` 的一致性测试只覆盖 `README` 与 `doc/`，**未覆盖 skill**。

## 规范

### 范围：只改这三份文档

| 文件 | 改什么 |
|------|-------|
| `SKILL.md` | 阶段流水线序列、`script` 可选语义、四条审查命令的何时用 |
| `references/commands.md` | 补 `feat review/comment/stage-review`、`script` 阶段、`feat new` 五必填、check 全 code |
| `references/data-model.md` | `Feat.stage` 取值补 `script`；补 `stage_reviews`/`comments` 字段 |

**不改**：`references/design-doc.md`（阶段序列为举例，不构成漂移）、
`scripts/pdm`（包装器无变化）、任何代码。

### 事实来源（唯一权威）

一切以实测为准，不凭记忆：

- 命令面 → `.venv/bin/pdm <cmd> --help`
- 阶段序列 → `pdev/stage.py` 的 `STAGE_SEQUENCE` / `OPTIONAL_STAGES`
- check 规则 → `pdev/check.py` 的 `CODES`
- 配置键 → `pdev/config.py`

### `script` 阶段的表述口径

`script` 是**可选**阶段：`test` 之后既可进 `script`，也可**直接进 `feat`**。

- `pdm feat commit` 的 `choices` 已含 `script`（从 `STAGE_SEQUENCE` 派生）。
- `check` 的 `missing-stage` **不查** `script`（缺它不告警）。
- 一旦出现 `script(` 提交，其位置由 `stage-order` 约束（须在 `test` 后、`feat` 前）。

## 接口

无代码接口。交付物是文档内容，验收见下。

## 日志

无。

## 兜底

- 若某命令的 `--help` 与本文描述不符 → **以 `--help` 为准**并改本文档。
- 若发现代码本身缺功能（而非文档漂移）→ **不在本 feat 处理**，
  另行开 feat；本 feat 保持"只同步文档"的边界。

## 验证方法

```
cmd=<逐条核对>
# 命令面：pdm feat --help 的子命令列表 与 commands.md 的标题一一对应
# 阶段序列：stage.py STAGE_SEQUENCE 与 SKILL.md 流水线字符串一致
# check：check.py CODES 与 commands.md 的规则表 code 集合一致
manual=通读 SKILL.md 的标准流程，确认按其中命令能实际跑通
expected=无遗漏、无过时命令
```

## 实现与校验结果（收尾）

实现于 commit `fc6ff229`（三份文档同步 + 新增 `tests/test_skill_sync.py`），
补漏于 `a8a0ef82`（`design-doc.md` 两处旧流水线 + 防漂移断言）。

### 同步了什么

| 文件 | 变化 |
|------|------|
| `SKILL.md` | 流水线加 `script`（可选语义）；`feat new` 五项必填进标准流程；新增「审查」一节（review/comment/stage-review/`pdm review`） |
| `references/commands.md` | 补 `feat review/comment/stage-review` 三个子命令；`feat commit` 的 `script` 阶段；`feat new` 五项必填表；check 规则表由 13 补到 21 个 code |
| `references/data-model.md` | `Feat.stage` 补 `script`；新增 `script` 可选说明与「审查数据（两级）」小节 |
| `references/design-doc.md` | 两处旧流水线改为含 `script` |

### 防复发（本 feat 的重点）

新增 `tests/test_skill_sync.py`（9 例），把 skill 钉在代码上：

- 命令面：SKILL.md 的 `pdm <cmd>` → `build_parser()` 顶层 choices；
  commands.md → `feat` 全部子命令。
- 阶段序列：三份文档都必须含 `STAGE_SEQUENCE` 派生的流水线串。
- 规则表：commands.md 必须覆盖 `check.CODES` 全部代号。
- 必填参数、`script` 可选、`samples` 语义等关键表述。
- **旧流水线禁止串**：任何参考文件不得含缺 `script` 的 `doc → test → feat → fix → close`。

同时把 `tests/test_skill.py::test_body_mentions_pipeline` 从**硬编码字符串**
改为从 `STAGE_SEQUENCE` 派生——原先它等于把漂移固化成测试。

### 本次发现的异常

1. **`design-doc.md` 被误判为"无漂移"**：写设计文档时凭判断排除，实际它
   两处硬编码旧流水线。教训：是否漂移应由**派生串全量 grep** 判定，
   不能靠人眼。已由 `test_no_reference_doc_has_stale_pipeline` 兜住。
2. **旧测试固化了旧事实**：`test_body_mentions_pipeline` 直接断言旧串，
   代码改了它反而拦住正确的更新。文档测试应**从代码派生期望值**。
