# 列出未审查 / 未测试项（review-query）

> 先于实现编写。给 `pdm review` 加 `--unreviewed` / `--untested`，
> 让「哪些部分还没审 / 还没测」能一条命令列出来——补上 review-cli
> 只有汇总数字、`feat review <slug>` 需逐条看的缺口。

## 问题

`review-cli` 提供了三个入口，但没有**跨 feat 的待办清单**：

- `pdm review` 只给汇总（「196 项，0% 已审」），**不说是哪些**；
- `pdm feat check` 只到 feat 粒度（「review-check 未审」），不列具体项；
- `pdm feat review <slug>` 有逐项清单，但要一个 feat 一个 feat 地看，
  24 条 feat 就要敲 24 次命令。

根因：缺一个「**按勾选状态过滤、跨全部 feat 展开**」的查询入口。

## 规范

### 两个筛选开关

在 `pdm review` 上新增（均为可选；不给时保持现有汇总行为）：

| 开关 | 含义 |
|------|------|
| `--unreviewed` | 只列 `reviewed == False` 的可审项 |
| `--untested` | 只列 `tested == False` 的可审项 |

- **单独给**：按该位过滤。
- **同时给**：取**交集**（既未审**且**未测）。
- **都不给**：保持现有行为（打印掌握程度汇总），向后兼容。

### 输出格式

按 feat 分组，每组头行是 slug 与该项的勾选标记，空组（无命中）不出现：

```
$ pdm review --unreviewed
review-model
  [ ][ ] api:0        Feat.review_items() -> List[Tuple[str, str]]
  [ ][ ] api:1        Feat.set_reviewed(key, value, by) -> ReviewItem
review-score
  [ ][ ] doc          feat/review-score.md
  ...

未审查：13/13 项（共 2 条 feat）
```

- 行格式复用 `render_review_marks(feat, key)` + key + label，与
  `pdm feat review <slug>` 一致，便于对照。
- 末尾给一行统计：`未审查：N/M 项（共 K 条 feat）`，`未测试` 同理；
  两者同给时写 `未审查且未测试：N/M 项（共 K 条 feat）`。
- 无命中时打印 `（没有未审查的项）`，退出码 0。

### 退出码与 JSON

- **文本模式**：列出待办属**查询**，有未审项**不算失败** → 退出码 **0**
  （与 `pdm review` 汇总模式的「有告警→1」不同，便于直接阅读/管道）。
  > 注：这是有意区分——`pdm review` 不筛选时是**门禁**（告警即失败），
  > 带筛选时是**清单**（正常查看）。
- **`--json`**：输出 `{"filter": "unreviewed"|"untested"|"both",
  "total": M, "count": N, "feats": [{"slug":..., "items":[{key,label,...}]}]}`，
  退出码同样 0。

## 接口

```python
# pdev/cli/parser.py
review.add_argument("--unreviewed", action="store_true", ...)
review.add_argument("--untested", action="store_true", ...)

# pdev/review.py（内核，可单测）
def unreviewed_items(feats, *, tested=False) -> List[tuple]
    """跨 feat 展开未审（可选：且未测）的可审项。

    返回 [(feat_slug, key, label), ...]，按 feat 顺序、项顺序。
    """

# pdev/cli/commands.py
def cmd_review(ctx, args) -> int
    """带 --unreviewed/--untested 时走清单分支；否则走汇总分支。"""
```

## 日志

- 不新增日志；清单直接打印。

## 兜底

- **无 feat / 无可审项** → 打印 `（没有未审查的项）`，退出码 0。
- **某 feat 无可审项** → 不出现该组（空组跳过）。
- **`--unreviewed` 与 `--untested` 同时给** → 交集，且文案标明。
- **`--json` 与筛选同用** → 只输出 JSON，不混人类文案。
- **`ctx.config.json_output`（顶层 `--json`）** → 与 `--json` 等价。
- **筛选开关与既有汇总不冲突**：给了筛选就**不**打印掌握程度汇总，
  避免输出噪声。

## 实现与校验结果（收尾）

- **实现**：`pdev/review.py` 新增 `unreviewed_items(feats, *, tested)`
  （跨 feat 展开未审/未测项）；`pdev/cli/parser.py` 给 `review` 加
  `--unreviewed` / `--untested`；`pdev/cli/commands.py` 的 `cmd_review`
  新增清单分支（`_print_pending` + `_total_items`）。
- **提交**：`doc` a01b38e、`test` e5bfd72、`feat` 26af4bb、`fix` b2e71de。
- **测试**：`tests/test_review.py` 新增 6 个、`tests/test_cli.py` 新增 7 个；
  全仓 748 个用例通过。
- **实测验证**：
  - `pdm review --unreviewed` 列出全仓未审项（按 feat 分组，带 `[ ][ ]`）；
  - `--untested` / 两者同给（交集）/ 空清单 / `--json` 均符合设计；
  - 勾选一项后清单实时减一。
- **结论**：设计成立。加上这个入口后，「哪些部分没审/没测」可一条命令
  看到；筛选模式退出码恒为 0（查询性质），与无筛选时的门禁语义（有告警→1）
  有意区分。
