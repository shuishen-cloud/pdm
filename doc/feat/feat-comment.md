# Feat 条目级人工评论（feat-comment）

> 先于实现编写。给 Feat 的每个可审条目挂一段**人手动填写的评论**，
> 记录「这一条为什么这么定」的决策。条目粒度与 `feat review --item`
> 完全一致，评论与 `[审][测]` 勾选**互相独立**。

## 问题

`feat review` 提供了 `[审][测]` 两个勾选位，但只能表达「看过没有」，
**表达不了决策内容**：

- `api:0` 被审了，但为什么选这个签名、为什么不泛化，没处记；
- `logs:1` 为什么只在这种时机打，没处记；
- 现有 `CommitNote` 挂在 **commit** 上（记录坑/难点），不是挂在
  **Feat 的某个条目**上，语义不对口。

根因：缺一个「Feat 条目 → 人的决策文本」的轻量载体。

## 规范

### 评论对象（key）

沿用 `feat review --item` 的 key，即 `feat.review_items()` 产出的键：

| key | 对应 |
|-----|------|
| `doc` | 设计文档路径 |
| `api:0` / `api:1` … | 第 i 条交付接口 |
| `logs:0` … | 第 i 条日志 |
| `fallbacks:0` … | 第 i 条兜底 |

- **只允许合法 key**（不在 `review_items()` 中则抛 `FeatError`，不写入）。
- 与 `reviews` 共用同一套 key 空间，便于对照。

### 存储

`Feat.comments: dict[str, str]`，键为 key，值为**人写的评论文本**。

- **留空即不落盘**：清除评论（或写入空串）时从 dict 移除，
  保持 JSON 精简（与 `reviews` 的「未操作不落盘」一致）。
- 评论**独立于** `[审][测]`：写评论不等于勾选，勾选也不要求有评论。
- **多行文本允许**（`\n` 原样保存，展示时按行缩进）。

### 与审查的关系

- 评论**不参与** `review_counts` / 评分 / `pdm review` 告警。
- 评论**不参与** `pdm feat check` 规则。
- 二者仅共享 key 空间。

## 接口

```python
# pdev/feat.py

@dataclass
class Feat:
    comments: dict = field(default_factory=dict)   # {key: 文本}

    def comment(self, key: str) -> str:
        """取某条目的评论；没有返回 ""。"""

    def set_comment(self, key: str, text: str) -> None:
        """写/清某条目的评论；text 为空即清除。非法 key 抛 FeatError。"""

    def commented_items(self) -> List[tuple]:
        """返回 [(key, label, comment), ...]，只含**非空**评论，按项顺序。"""

class FeatStore:
    def set_comment(self, slug: str, key: str, text: str) -> Feat
        """透传并落盘；slug 不存在抛 FeatError。"""
```

序列化：`_to_dict` 增 `"comments"`；`_from_dict` 读
`d.get("comments") or {}`（只保留 `str` 值，丢弃其他类型）。旧 JSON 无该键 → 空 dict。

```python
# pdev/cli/parser.py
#
#   feat comment <slug> [--on KEY] [-m TEXT] [--clear] [--json]

# pdev/cli/commands.py
def cmd_feat_comment(ctx: AppContext, args) -> int
    """查看 / 写 / 清某条目的评论；无条件列全部已写评论。"""
```

### CLI 行为

| 调用 | 行为 |
|------|------|
| `pdm feat comment <slug>` | 列出该 feat 全部**非空**评论（key + label + 文本） |
| `... --on api:0` | 查看 `api:0` 的评论（含空） |
| `... --on api:0 -m "文本"` | 写入（覆盖） |
| `... --on api:0 --clear` | 清空 |
| `... --json` | 机器可读 |

- `--on` 缺省 + `-m` → 报错（必须指明对象）。
- `--on` 与 `--clear` 同给 → 清空该条。
- `-m` 与 `--clear` 互斥。

### 展示

`pdm feat show` 在每个可审条目**下一行**缩进显示其评论（`💬 ` 前缀），
无评论则不显示：

```
交付接口
  [x][ ] · Foo.bar() -> int
    💬 这个签名保持最小，不做泛化
  [ ][ ] · Foo.baz() -> str
```

- 多行评论按行缩进，首行带 `💬`，续行对齐。
- `--json` 的 `_to_dict` 已含 `comments`，无需额外改。

## 日志

- 不新增日志；写/清评论后在 stdout 回显新状态。

## 兜底

- **slug 不存在** → 错误 + 退出码 2。
- **`--on` key 非法** → 捕获 `FeatError`，提示可选 key，退出码 2，不落盘。
- **`-m` 为空串** → 视为清除（等同 `--clear`）。
- **`comments` 值非 str** → `_from_dict` 丢弃该条，不报错。
- **旧 JSON 无 `comments`** → 空 dict。
- **`--on` 指向的条目已删除**（孤儿 key）→ 保留在 JSON 中，但
  `commented_items()` 不返回（与 `reviews` 的孤儿处理一致）。
- **`feat show --json`** → 直接带出 `comments`。

## 实现与校验结果（收尾）

- **实现**：`pdev/feat.py` 新增 `Feat.comments` / `comment()` /
  `set_comment()` / `commented_items()` 与 `FeatStore.set_comment`，
  及序列化（非 str 值丢弃）；`pdev/cli/parser.py` 加 `feat comment`
  子命令（`--on` / `-m` / `--clear`，后两者互斥）；`pdev/cli/commands.py`
  加 `cmd_feat_comment`，并让 `cmd_feat_show` 在每个条目下缩进显示评论。
- **提交**：`doc` 89e0bf3、`test` cf61126、`feat` 8680f72、`fix` 18a7545。
- **测试**：`tests/test_feat.py` 新增 12 个、`tests/test_cli.py` 新增 11 个；
  非 TUI 全量通过。
- **实测抓出的问题**：写入回显与 `feat show` 各写一份多行渲染逻辑，
  一个每行都带 `💬`、一个只首行带；已统一为「首行 `💬`、续行 3 空格对齐」
  并加回归测试。
- **结论**：设计成立。评论与 `[审][测]` 完全独立（不参与评分与 check），
  空评论不落盘，孤儿 key 保留但不列出；`--on` 与 `pdm feat review --item`
  共用 key 空间，无需记两套标识。
