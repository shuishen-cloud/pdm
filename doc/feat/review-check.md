# feat check 的审查联动规则（review-check）

> 先于实现编写。把 `review-model` / `review-score` 接进既有的
> `pdm feat check` 护栏：让「规格字段未审」与「Feat 关闭时审查覆盖率过低」
> 成为 check 能报出的问题，让 `check` 不只查流程，也查掌握度。

## 问题

`pdm feat check` 目前能查：字段是否为空、阶段是否齐全、commit 是否存在、
笔记与验证覆盖。但它**不知道审查勾选**：

- 一条 feat 的 `api`/`logs`/`fallbacks` 全未勾选，`check` 依然报「✓ 通过」；
- feat 已 `closed`，但没人审过一眼，`check` 不吭声；
- 已有的 `pdm review` 能算全局覆盖率，但它**不参与 feat 级护栏**，
  单条 feat 关闭时没有任何闸门。

根因：`check` 的规则集停留在「结构化完整性」，未接上新增的审查维度。

## 规范

### 新增规则

在 `_check_feat` 内新增两条（均为 **warning**，不阻断，沿用现有风格）：

| code | level | 触发条件 | 含义 |
|------|-------|----------|------|
| `review-none` | warning | 有可审项，且 `reviewed == 0` | 规格字段无一项被人工审查 |
| `review-low` | warning | 有可审项，且 `review_coverage < min_coverage` | 人工审核覆盖率过低 |

- `min_coverage` 取 `config.review.min_coverage`（默认 `0.6`）；
  `check` 通过参数接收，不直接读配置（保持 `check` 纯函数）。
- **无（可审项的）feat 不报**：`items == 0` 时跳过。
- `review-none` 与 `review-low` 可同时出现（`reviewed == 0` 必然低于阈值）；
  前者更具体，保留以便一眼看出「一项都没审」。

### 关闭时的严格口径（可选）

`pdm feat check` 已有对 `closed` feat 的规则。本 feat **不**新增
「closed 但未审即 error」——因为那会让历史 24 条 feat 立刻变成 error。

改为：`closed` 且 `items > 0` 且 `reviewed == 0` 时，`review-none`
的 message 追加「（已 closed）」提示，级别仍 warning。

### 接入方式

- `check_one(store, slug, git, note_store, min_coverage=0.6)`：新增可选参数。
- `check_feats(store, git, *, include_orphans, note_store, min_coverage=0.6)`。
- `cmd_feat_check` 从 `ctx.config.review.min_coverage` 取值传入。
- 两条规则仅依赖 `feat.review_counts()`，**不需要 git / note_store**，
  因此在无 git 环境下也能生效。

## 接口

```python
# pdev/check.py

CODES = (..., "review-none", "review-low")

def check_one(store, slug, git=None, note_store=None,
              min_coverage: float = 0.6) -> List[CheckIssue]

def check_feats(store, git=None, *, include_orphans=True,
                note_store=None, min_coverage: float = 0.6) -> List[CheckIssue]

def _check_review(feat, min_coverage: float) -> List[CheckIssue]
    """审查覆盖规则；无 git/note 依赖。"""

# pdev/cli/commands.py
def cmd_feat_check(ctx, args) -> int
    """传入 ctx.config.review.min_coverage。"""
```

## 日志

- 不新增日志；结果经既有 `format_issue` 渲染。

## 兜底

- **`items == 0`** → 不报任何 review 规则（无内容可审）。
- **`min_coverage` 缺失/非法** → 调用方给默认 `0.6`；`check` 不自己兜底。
- **feat 无 `reviews`** → `review_counts()` 已返回 `(items, 0, 0)`，
  正常触发 `review-none`。
- **`--json` 输出** → 新规则自动进 `issues` 数组，无需改序列化。
- **`--strict`** → 新规则是 warning，`--strict` 时会让退出码变 1，
  与既有 warning 行为一致。

## 实现与校验结果（收尾）

**在 close 阶段补写**。
