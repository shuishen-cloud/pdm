# 批量审查勾选（review-batch）

> 先于实现编写。`pdm feat review` 现在一次只勾一项，13 项要敲 13 次。
> 补 `--all`（整条 feat）与前缀匹配（`--item api`），把重复劳动压成一次。

## 问题

`review-cli` 的勾选粒度是**单个 key**：

```bash
pdm feat review a --item api:0 --review
pdm feat review a --item api:1 --review   # 想勾完 api 得逐条敲
...
```

一个 13 项可审的 feat，全勾一遍要 13 条命令；「整条 feat 我已通读」
这种场景更是纯体力活。且每条都要单独写盘一次（`FeatStore.update`）。

根因：勾选动作只支持**精确 key**，缺「一片」的表达。

## 规范

### 两种扩大匹配的方式

| 写法 | 含义 |
|------|------|
| `--all` | 该 feat 的**全部**可审项 |
| `--item api`（不带 `:序号`） | 匹配 `api:0` / `api:1` …（前缀） |
| `--item api:0` | 仍按精确 key（**向后兼容**） |

- `--all` 与 `--item` **互斥**（同给报错）。
- 前缀匹配规则：`--item <field>` 匹配所有 `f"{field}:"` 开头的 key。
  若 `<field>` 本身就是一个合法 key（如 `doc`），按**精确**处理；
  若既是前缀又是合法 key 不冲突（`doc` 无 `doc:` 子项）。
- 匹配不到任何项 → 报错退出码 2，不落盘。

### 批量动作

`--review` / `--unreview` / `--test` / `--untest` 都支持批量：

```bash
pdm feat review a --all --review --by human:lwy
pdm feat review a --item api --review
pdm feat review a --all --test --cmd "pytest tests/x.py"
pdm feat review a --item fallbacks --untest
```

- 一次动作，**一次落盘**（避免 N 次写文件）。
- `--test` 的 `--cmd` / `--status` 对每个命中项写入相同值。

### 输出

批量时逐行列出命中的 key 及新状态，末尾给汇总：

```
$ pdm feat review a --item api --review
a  api:0  [x][ ]  f() -> int
a  api:1  [x][ ]  g() -> str
已审查 2 项（api）：审查 2/5，测试 0/5
```

- 命中 1 项时保持原有单条输出格式（兼容既有调用方与测试）。
- 命中多项时用上面两行式；总数取该 feat 当前 `review_counts()`。

## 接口

```python
# pdev/feat.py
class FeatStore:
    def set_reviews(self, slug: str, keys, *, reviewed=None,
                    tested=None, by: str = "", command: str = "",
                    status: str = "") -> Feat
        """批量置位：对每个 key 调 set_reviewed / set_tested，只落盘一次。"""

    def resolve_keys(self, slug: str, item: str = "",
                     all_items: bool = False) -> List[tuple]
        """把 --item / --all 展开成 [(key, label), ...]。

        - all_items=True → 全部可审项
        - item 是精确 key → 该项
        - item 是字段前缀（如 "api"）→ 所有 "api:*"
        - 无匹配 → 抛 FeatError
        """

# pdev/cli/parser.py
#   --item KEY 改为可省略（与 --all 二选一）
#   --all 新增

# pdev/cli/commands.py
def cmd_feat_review(ctx, args) -> int
    """按 --all/--item 展开后批量勾选，逐行回显。"""
```

## 日志

- 不新增日志；回显在 stdout。

## 兜底

- **`--all` 与 `--item` 同给** → 报错退出码 2。
- **无 `--all` 也无 `--item`** → 保持原行为（列出清单）。
- **前缀无匹配**（如 `--item nope`）→ 报错退出码 2，不落盘。
- **feat 无可审项** → `--all` 报「无可审项」，退出码 2。
- **单条命中** → 沿用原有单条输出，保证兼容。
- **批量中途某项非法** → 展开阶段就校验完，全部合法才落盘（**全有或全无**）。

## 实现与校验结果（收尾）

- **实现**：`pdev/feat.py` 新增 `FeatStore.resolve_keys`（把 `--item` /
  `--all` 展开为命中项）与 `set_reviews`（批量置位、只落盘一次）；
  `parser.py` 加 `--all`；`cmd_feat_review` 改走展开 + 批量路径。
- **提交**：`doc` b5e6454、`test` bdeb853、`feat` ba0a14a、`fix` 831ce55。
- **测试**：`tests/test_feat.py` 新增 10 个、`tests/test_cli.py` 新增 10 个；
  非 TUI 全量通过。
- **实测抓出的问题**：
  1. 批量分支漏接 `--json`，`--all --json` 仍打印人类文本，破坏「--json 只输出
     JSON」约定；已补 JSON 出口 + 回归。
  2. 「未命中项未被勾选」不能用 `not item.reviewed` 断言——未操作时
     `review_item()` 返回 `None`，应容忍 None。
- **结论**：设计成立。一次动作只写一次盘；单条命中仍走原输出，既有调用
  方与测试无需改动；`--all` 与 `--item` 互斥由命令层直接拒绝。
