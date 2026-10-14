# 审查勾选的命令行入口（review-cli）

> 先于实现编写。把 `review-model`（数据）与 `review-score`（评分）接到
> CLI 上，让「逐项勾选」与「看掌握程度」真正可用：`pdm feat review` 勾选，
> `pdm review` 看全局，`pdm feat show` / `pdm stats` 展示勾选状态。

## 问题

`review-model` 只有存储、`review-score` 只有计算，**都没有用户入口**：

- 想勾一个 `[审]`，得手改 `.pdm/feats/by-id/<slug>.json`；
- 想看掌握程度，得写 Python 调 `compute_review`；
- `pdm feat show` 的规格三栏看不到勾选状态。

根因：内核已就绪，缺**命令层**（参数解析 + 渲染 + 调用内核）。

## 规范

### 三个入口

| 命令 | 作用 |
|------|------|
| `pdm feat review <slug>` | 列出该 feat 的可审项与 `[审][测]` 状态 |
| `pdm feat review <slug> --item <key> --review/--test/...` | 勾选单项 |
| `pdm review [--json]` | 全仓掌握程度 + 告警 |

并让 `pdm feat show` 的规格三栏前带 `[审][测]` 标记、`pdm stats` 末尾附掌握程度。

### 勾选命令（逐项）

```
pdm feat review <slug> --item <key> [动作]
```

- `<key>`：可审项键，如 `api:0` / `logs:1` / `doc`。非法 key 报错退出码 2。
- 可省略 `<key>` 时（只 `--list`）列出清单。
- **动作**（互斥，缺省为 `--list`）：

| 动作 | 效果 |
|------|------|
| `--review` | 置 `[审]`，记录 `reviewed_by`（取 `--by`／配置 `default_author`） |
| `--unreview` | 清 `[审]` |
| `--test` | 置 `[测]`（需 `--cmd` 或 `--verify-ref` 说明如何验证） |
| `--untest` | 清 `[测]` |

- 两个位**独立**：允许只 `--review` 不 `--test`。
- 勾选后打印该键的新状态与全 feat 覆盖率，便于连续操作。

### 测试位的「实际执行」

勾 `[测]` 时应体现**真的跑过**。本 feat 采用「**记录证据**」而非「内联执行」：

- `--cmd "pytest tests/x.py::test_y"`：登记实际执行的命令（字符串）；
- `--status passed|failed|error`：登记该次执行结果（默认 `passed`）；
- 二者存入 `ReviewItem.test_command` / `test_status`。

> 复用 `pdm verify run` 做真正执行是后续增强；本 feat 只负责**登记证据**，
> 保证数据结构与展示先跑通，避免在 CLI 里再造一套执行器。

### 掌握程度命令

```
pdm review [--json]
```

- 文本：`format_score(compute_review(feats, policy))`。
- `--json`：`ReviewScore` 序列化为 JSON（含 warnings 数组）。
- 退出码：**有告警返回 1**，否则 0——可直接用于 CI 门禁。
- policy 来自 `config.review`（`min_coverage` / `warn_no_review` / `warn_untested`）。

### 展示（`feat show` 与 `stats`）

- `pdm feat show` 的 `交付接口` / `会打的日志` / `异常兜底` 每行前加
   `[审][测] `（勾上为 `x`），并附一行覆盖率小结。
- `pdm stats` 文本末尾附 `format_score(...)`；`--json` 增 `"review"` 字段。

## 接口

```python
# pdev/cli/parser.py
#
#   feat review <slug> [--item KEY]
#                     [--review|--unreview|--test|--untest]
#                     [--by WHO] [--cmd CMD] [--status S] [--json]
#   review [--json]

# pdev/cli/commands.py
def cmd_feat_review(ctx: AppContext, args) -> int
    """列出或勾选某 feat 的审查项。"""

def cmd_review(ctx: AppContext, args) -> int
    """全仓掌握程度与告警；有告警返回 1。"""

def render_review_marks(feat, key: str = "") -> str
    """生成 "[x][ ] " 前缀（供 show/CLI 复用）。"""

# pdev/cli/commands.py 内的渲染工具
def _review_lines(feat) -> List[str]
    """把 feat 的可审项渲染成 "[x][ ] api:0  f() -> int" 列表。"""
```

- `cmd_feat_review` 走 `FeatStore.set_reviewed / set_tested`，落盘后回显。
- `cmd_review` 走 `pdev.review.compute_review` + `format_score`。
- `--by` 缺省取 `ctx.config.default_author`。

## 日志

- CLI 层不额外打日志；结果直接打印到 stdout。
- `--json` 时**只**输出 JSON，不混人类文案（便于管道）。

## 兜底

- **slug 不存在** → 打印错误，退出码 2。
- **`--item` 键非法**（不在 `review_items()` 中）→ 捕获 `FeatError`，
  打印可选键提示，退出码 2，**不落盘**。
- **同时给多个动作**（如 `--review --test`）→ 参数层互斥组直接拒绝。
- **`--test` 未给 `--cmd`** → 允许（`test_command` 留空），但提示
  「建议用 --cmd 记录验证命令」；不阻断。
- **无 feat / 无可审项** → `pdm review` 输出「无可审内容」，退出码 0。
- **`--json` 与告警同存** → JSON 仍完整输出，退出码照旧反映告警。

## 实现与校验结果（收尾）

- **实现**：`pdev/cli/parser.py` 新增 `feat review` 与顶层 `review`
  两个子命令（动作互斥组 `--review/--unreview/--test/--untest`）；
  `pdev/cli/commands.py` 新增 `cmd_feat_review` / `cmd_review` /
  `render_review_marks` / `_review_lines` / `_review_snapshot`，并让
  `cmd_feat_show` 的规格栏带 `[审][测]` 标记、`cmd_stats` 附掌握程度。
- **提交**：`doc` d372082、`test` ed9bde4、`feat` b6a62ac、`fix` 5c27644。
- **测试**：`tests/test_cli.py` 新增 21 个用例；全仓 714 个用例通过。
- **实测抓出的问题**：
  1. `feat show` 为了让 review 标记匹配上，一度把设计文档栏改成显示
     `feat.doc` 原文，破坏了「按 doc.dir 解析后显示」的既有语义；
     修正为 `(display, match)` 二元组，显示解析后路径、匹配用原值。
  2. `--item` 多次书写时 argparse 只保留最后一条，故此命令一次只勾
     一项，需逐项调用；已在文档/测试中固定这一语义。
  3. 端到端测试中笼统断言 `"100%" in out` 会误命中「测试通过 100%」行，
     改为定位「人工审查」行再断言。
- **结论**：设计成立。三个入口（逐项勾选 / 全局评分 / 展示标记）均已跑通，
  `pdm review` 退出码可直接用作 CI 门禁（有告警→1）。真正执行测试命令
  （复用 `pdm verify run`）留作后续增强，本 feat 只负责登记证据。
