# 阶段级人工审核门禁（stage-review）

> 先于实现编写。给 `doc → test → feat → fix → close` 每个阶段加一个
> **人工审核位**；进入下一阶段前要求**上一阶段已审**。默认只告警，
> 配置可升级为**硬阻断**；且审核人必须是人（`human:`）。

## 问题

现有的审查是**条目级**（`api:0` 这种），回答"这条接口审过没有"；但答不了
**"这个阶段整体审过没有"**：

- `doc` 阶段的设计正文写完了，但没人通读过，就可以直接进 `test`；
- `feat` 阶段的实现提交了，没人确认，就直接进 `fix`；
- `pdm feat check` 只看"阶段是否齐全"，不看"阶段是否被人看过"。

根因：审查维度只有「条目」，缺「阶段」这一层。

## 规范

### 审核位

`Feat.stage_reviews: dict[str, StageReview]`，键是**阶段名**（`doc`/`test`/
`feat`/`fix`/`close`），值是审核记录：

| 字段 | 含义 |
|------|------|
| `by` | 审核人（必须是 `human:` 前缀，否则拒绝） |
| `at` | 审核时间 |
| `note` | 可选备注 |

- 只有**审核过**的阶段才落盘（未审不写）。
- 撤销即从 dict 移除。

### 门禁语义

进入阶段 `T` 前，要求 **`T` 的前一个阶段** 已审。

| 进入 | 要求已审 |
|------|---------|
| `test` | `doc` |
| `feat` | `test` |
| `fix` | `feat` |
| `close` | `fix` |

- 首次进入（`doc`）无前序，不要求。
- 只查**上一阶段**（不查全部前序），避免历史 feat 一次被全拦。

### 强制程度（可配）

`config.stage_review`：

| 字段 | 默认 | 含义 |
|------|------|------|
| `enabled` | `false` | 为真时**硬阻断**（提交前拒绝）；为假时仅 `check` 告警 |
| `require_human` | `true` | 审核人必须是 `human:`（防 AI 自审） |

- **默认不阻断**：既有 feat 与正常开发不被卡住。
- 打开 `enabled` 后，`pdm feat commit <stage> <slug>` 会先校验上一阶段已审。

### 历史豁免

与 `feat-fields-check` 同法：`created_at < FIELDS_SINCE` 的 feat 不参与门禁与
`stage-unreviewed` 告警（避免历史全线报错）。

## 接口

```python
# pdev/feat.py

@dataclass
class StageReview:
    by: str = ""
    at: Optional[datetime] = None
    note: str = ""

@dataclass
class Feat:
    stage_reviews: dict = field(default_factory=dict)   # {stage: StageReview}

    def review_stage(self, stage: str, by: str, note: str = "") -> StageReview
        """标记阶段已审；非法阶段名抛 FeatError。"""

    def unreview_stage(self, stage: str) -> None
    def stage_reviewed(self, stage: str) -> bool
    def pending_stage_review(self, target: str) -> Optional[str]
        """进入 target 前还差哪个阶段未审；无需审时返回 None。"""

class FeatStore:
    def review_stage(self, slug, stage, by, note="") -> Feat
    def unreview_stage(self, slug, stage) -> Feat

# pdev/stage.py
def previous_stage(stage: str) -> Optional[str]
    """STAGE_SEQUENCE 中 stage 的前一个；doc 返回 None。"""

# pdev/check.py
#   规则 stage-unreviewed（warning）：有 stage 游标、且有已提交阶段未审。

# pdev/cli/parser.py + commands.py
#   pdm feat stage-review <slug> <stage> [--by WHO] [--note TEXT]
#   pdm feat stage-review <slug> --list
#   pdm feat stage-review <slug> <stage> --clear
```

### CLI

```bash
pdm feat stage-review a doc --by human:lwy        # 审过 doc
pdm feat stage-review a --list                    # 看各阶段审核状态
pdm feat stage-review a doc --clear               # 撤销
```

- `--by` 默认取 `config.default_author`；`require_human` 为真时非 `human:`
  前缀 → 报错退出码 2。
- `--list` 输出每阶段：`✓ doc  human:lwy 2026-10-14` / `· test（未审）`。

### 展示

`pdm feat show` 新增一行**阶段审核摘要**：

```
阶段审核  doc✓ test· feat· fix· close·   （pdm feat stage-review <slug> <阶段> --by human:名字）
审查  审查 2/7  测试 0/7
```

`pdm feat stage-review <slug> --list` 列出每阶段详情：

```
  ✓ doc    human:lwy  2026-10-14 11:49:48
  · test   （未审）
```

### 门禁接入点

`FeatStore.commit_stage` 在 `assert_allowed` 之后、`run_commit` 之前：

```python
assert_allowed(current, stage)
if enabled and _fields_enforced(feat):
    pending = feat.pending_stage_review(stage)
    if pending:
        raise StageError(f"上一阶段 [{pending}] 尚未人工审核（pdm feat stage-review ...）")
```

## 日志

- 不新增日志；审核动作由 CLI 回显。

## 兜底

- **非法阶段名** → `FeatError`，退出码 2。
- **`by` 非 `human:` 且 `require_human`** → 报错退出码 2，不落盘。
- **重复审核同一阶段** → 覆盖（更新 by/at），不报错。
- **`--clear` 未审过的阶段** → 静默无变化。
- **历史 feat（早于 FIELDS_SINCE）** → 不参与门禁与告警。
- **`dry_run`** → 门禁仍校验（提前暴露），但不落盘。
- **`config` 缺 `stage_review` 段** → 视为默认（不阻断）。

## 实现与校验结果（收尾）

- **实现**：`pdev/feat.py` 新增 `StageReview` / `Feat.stage_reviews` /
  `review_stage` / `unreview_stage` / `stage_reviewed` / `pending_stage_review`
  与序列化，`commit_stage` 加 `require_stage_review` 门禁；
  `stage.previous_stage`；`config.StageReviewConfig`；`check` 的
  `stage-unreviewed`；`pdm feat stage-review` 命令；`feat show` 阶段审核行。
- **提交**：`doc` 5dafa71、`test` e5a4070、`feat` e9942fa、`fix` 49c9ec8。
- **实测验证**（临时仓库开 `enabled=true`）：
  - 未审 `doc` 就 `commit test` → 被拒（退出码 2）；
  - `stage-review doc --by human:lwy` 后放行；
  - `--by ai:claude` → 被拒（须 human）；
  - `--list` 正确显示各阶段状态。
- **发现的问题**：
  1. 门禁分支用 `StageError` 但忘了 import（dry_run 路径不触发，真跑才暴露）。
  2. 设计里写「`feat show` 头部阶段行加 ✓」，但 CLI 的 show **没有阶段行**
     （那是 TUI 的 `stage_progress`），已改为新增一行独立摘要。
- **结论**：设计成立。默认不阻断（`enabled=false`），`check` 对已走过阶段
  报 `stage-unreviewed`；历史 feat（早于 `2026-10-14 11:16`）全部豁免。
