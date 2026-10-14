# 审查覆盖率评分与低覆盖告警（review-score）

> 先于实现编写。基于每条 Feat 的双勾选位（review-model），跨全部 Feat
> 汇总出「项目代码掌握程度」，并对**人工审核覆盖率过低**的仓库发出告警。
> 本 feat 只做纯计算 + 配置，不做 CLI / TUI。

## 问题

`review-model` 只把勾选位存进了每条 Feat，但没有任何**汇总视图**：

- 想知道「我到底审了多少」，得手动数 22 个 `by-id/*.json`；
- 无法回答「整个项目里，有多大概率是我真看过的代码」；
- 没有任何机制把「长期不审」这件事**暴露出来**——这正是要防的风险：
  代码量涨，人工确认的占比却在跌，最后没人掌握。

根因：勾选数据是**逐条**的，缺一个**跨条目的汇总与阈值判定**层。

## 规范

### 统计口径

设全部 Feat 的可审项集合为 U（每条 Feat 的 `review_items()` 取并集）；
对每个可审项，它在**自己所属 Feat** 上的勾选位决定计数：

```
items    = Σ 各 feat 的可审项数           # 分母
reviewed = Σ 各 feat 中 reviewed 为真的项数
tested   = Σ 各 feat 中 tested   为真的项数
```

- 分母是**所有未删除**的可审项（含 `closed` 的 feat；已关闭不代表免审）。
- 孤儿记录（规格项已删）不计入——沿用 `review_counts()` 的口径。
- 空仓库（`items == 0`）不告警（没有可审的东西，无从要求）。

### 覆盖率与评分

```
review_coverage = reviewed / items        # 人工审核覆盖率（关键指标）
test_coverage   = tested   / items        # 测试通过覆盖率
score           = 0.6 * review_coverage + 0.4 * test_coverage
```

- 人工审核权重更高（0.6）：**没被人看过的测试通过不算掌握**。
- `items == 0` 时三者均为 `0.0`，`level = "none"`，不告警。

### 掌握程度分档

`level` 由 `score` 落档（文字用于 CLI 展示）：

| level | 区间 | 含义 |
|-------|------|------|
| `none` | items == 0 | 无可审内容 |
| `poor` | score < 0.3 | 基本没掌握 |
| `fair` | 0.3 ≤ score < 0.6 | 掌握有限 |
| `good` | 0.6 ≤ score < 0.9 | 大体掌握 |
| `excellent` | score ≥ 0.9 | 掌握良好 |

### 告警规则（只看「过低」）

| code | level | 触发条件 | 含义 |
|------|-------|----------|------|
| `no-review` | warning | `items > 0 and reviewed == 0` | 完全不审查 |
| `low-review` | warning | `items > 0 and review_coverage < min_coverage` | 人工审核覆盖率过低 |
| `untested` | warning | `items > 0 and tested == 0` | 完全没有测试通过记录 |

- **不设「过高告警」**：审得多不是问题。
- `no-review` 与 `low-review` **可同时出现**（`reviewed == 0` 必然也低于阈值），
  按独立规则各报一条；`no-review` 信息更具体，用于强调。

### 阈值配置

`config.review.min_coverage`（默认 `0.6`）决定 `low-review` 的线。
所有规则也接受 `ReviewPolicy` 显式覆盖，便于单测与临时严格模式。

## 接口

```python
# pdev/review.py（新）

@dataclass
class ReviewPolicy:
    """告警阈值。"""
    min_coverage: float = 0.6     # 人工审核覆盖率下限
    warn_no_review: bool = True   # 是否报 no-review
    warn_untested: bool = True    # 是否报 untested

@dataclass
class ReviewScore:
    """跨 Feat 汇总结果。"""
    items: int = 0
    reviewed: int = 0
    tested: int = 0
    feats: int = 0                # 贡献了可审项的 feat 数
    review_coverage: float = 0.0
    test_coverage: float = 0.0
    score: float = 0.0
    level: str = "none"
    warnings: List[ReviewWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """无告警即 ok。"""

@dataclass
class ReviewWarning:
    code: str        # no-review | low-review | untested
    level: str       # warning
    message: str

def compute_review(feats: Iterable[Feat],
                   policy: ReviewPolicy | None = None) -> ReviewScore
    """汇总一批 Feat 的审查覆盖率、评分与告警。

    feats 为 None 或空 → items=0、level='none'、无告警。
    """

def format_score(s: ReviewScore) -> str
    """渲染成人类可读的多行文本（供 CLI stats/review 复用）。"""
```

配置（`pdev/config.py`）：

```python
@dataclass
class ReviewConfig:
    min_coverage: float = 0.6

# Config 增字段： review: ReviewConfig
# _SEGMENTS 增："review": ReviewConfig
```

## 日志

- 纯计算，**不打日志**；结果由调用方（CLI）渲染。

## 兜底

- **空输入**（无 feat / 无可审项）→ `items=0`、`score=0.0`、`level="none"`、
  无告警；`format_score` 输出「（无可审内容）」而非除零。
- **`items == 0` 时不做除法**：覆盖率直接取 0.0，避免 `ZeroDivisionError`。
- **阈值越界**（如 `min_coverage=2.0`）→ 照常比较，不抛错（低了就报）。
- **单个 feat 抛错**不应拖垮整体：遍历时按 `review_counts()` 取值，
  该方法本身不抛；不做额外 try（保持纯函数可预测）。
- **`score` 浮点** → 展示时保留两位小数，内部不四舍五入。

## 实现与校验结果（收尾）

- **实现**：新增 `pdev/review.py`（`ReviewPolicy` / `ReviewWarning` /
  `ReviewScore` / `compute_review` / `format_score`）；`pdev/config.py` 新增
  `ReviewConfig` 并注册进 `_SEGMENTS`，同时补上 `_coerce` 的 `float` 分支。
- **提交**：`doc` f2ec374、`test` ad59735、`feat` 47daa03、`fix` c8fc7a9e。
- **测试**：`tests/test_review.py` 新增 27 个用例，`tests/test_config.py`
  新增 4 个用例；全仓 693 个用例通过。
- **实测抓出的问题**：`fix` 阶段发现 `pdev.config._coerce` 没有 `float`
  分支，JSON 里把 `min_coverage` 写成字符串时会被原样保留为 `str`，
  后续与阈值比较会出错；已补 `float` 分支 + `_FLOAT_KEYS` 并加回归。
- **结论**：设计成立。权重 0.6/0.4 让「只审不测」不至于是满分（封顶
  0.6 → good）；分档基于 `score`（非单一覆盖率）在 `test_level_buckets`
  中得到参数化验证。
