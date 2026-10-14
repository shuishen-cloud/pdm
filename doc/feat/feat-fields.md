# Feat 五项设计字段（feat-fields）

> 先于实现编写。给 Feat 补五个人填字段：设计思路、实现方式、核心数据结构、
> 样例数据、对既有代码的改动。**全必填**；对**新 feat** 强制，历史 feat 豁免。

## 问题

现在 Feat 的规格只有 `api` / `logs` / `fallbacks` 三栏，回答不了几个关键问题：

- **为什么这么设计**（设计思路）——只散落在设计文档正文里，结构化字段没有；
- **怎么实现的**（实现方式）——同上；
- **核心数据结构长什么样**——`api` 只写签名，写不下"这个 dict 的键值含义"；
- **样例数据**——没有地方记「一条真实数据长什么样」；
- **动了既有代码的哪里**——完全没有，`git diff` 之外无处可查。

根因：Feat 的字段集停留在"接口/日志/兜底"，缺设计与落地面。

## 规范

### 五个新字段

| 字段 | 类型 | 含义 |
|------|------|------|
| `design_note` | `str` | 设计思路（为什么这么做，一段） |
| `impl_note` | `str` | 实现方式（怎么落地的，一段） |
| `data_model` | `List[str]` | 核心数据结构（每个结构一条） |
| `samples` | `List[str]` | 样例数据（每条一个例子） |
| `changes` | `List[str]` | 对既有代码的改动（`文件::符号 —— 说明`） |

- **全部必填**：`feat new` 时缺任一项 → 报错退出码 2。
- **允许"无"但必须说明**：没有样例数据也要写 `--sample "无：纯计算无外部数据"`。
- `changes` 每条应定位到符号（类/方法/变量），格式约定：
  `pdev/feat.py::Feat.comments —— 新增字段`。

### 可审性（复用审查机制）

`data_model` / `samples` / `changes` 均为 `List[str]`，**并入可审项**：
把 `_REVIEW_FIELDS` 扩为
`("api", "logs", "fallbacks", "data_model", "samples", "changes")`。

于是自动获得：`[审][测]` 勾选、条目级评论、批量勾选、评分统计。

`design_note` / `impl_note` 是整块文本，**不**进 `review_items()`；
它们作为整体由 `doc` 之外的展示段呈现（可后续单独评论，本 feat 不做）。

### 必填的强制范围（方案 A）

| 场景 | 行为 |
|------|------|
| `pdm feat new` 缺任一字段 | **报错**，退出码 2 |
| `pdm feat check` 对**有 stage 游标**的 feat 缺字段 | warning（见 feat-fields-check） |
| `pdm feat check` 对**无 stage 游标**的历史 feat | **豁免**，不报 |

- 判据：新流程 feat 必有 `stage`（`pdm feat commit` 会写）；历史 feat 无。
- 本 feat 只做「`feat new` 必填」与「展示」，check 规则留给下一个 feat。

## 接口

```python
# pdev/feat.py

@dataclass
class Feat:
    design_note: str = ""
    impl_note: str = ""
    data_model: List[str] = field(default_factory=list)
    samples: List[str] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)

    # 缺哪几个必填字段，返回字段中文名列表（空 = 齐全）
    def missing_required_fields(self) -> List[str]:
        """新 feat 必填字段检查；返回缺失项的人类可读名，供 CLI 报错。"""

# 序列化：_to_dict / _from_dict 各加 5 项（旧 JSON 缺 → 默认值）

# pdev/cli/parser.py（feat new）
#   --design-note TEXT        （单值）
#   --impl-note TEXT          （单值）
#   --data-model TEXT         （可重复）
#   --sample TEXT             （可重复）
#   --change TEXT             （可重复）

# pdev/cli/commands.py
def cmd_feat_new(ctx, args) -> int
    """校验 missing_required_fields()，缺则报错退出码 2。"""
```

### `feat show` 展示（插在「异常兜底」之后、「关联 commit」之前）

```
设计思路
  · 把评论与勾选彻底分离……
实现方式
  · 复用 review 的 key 空间……
核心数据结构
  [ ][ ] · Feat.comments: dict[str,str] —— 条目级评论
样例数据
  [ ][ ] · {"api:0": "这个签名保持最小"}
对既有代码的改动
  [ ][ ] · pdev/feat.py::Feat.comments —— 新增字段
```

- 列表型字段（后三个）带 `[审][测]` 标记，与现有规格栏一致。
- 文本型字段（前两个）逐行缩进渲染。

## 日志

- 不新增日志；`feat new` 成功后回显已登记的字段条数。

## 兜底

- **缺必填** → `feat new` 报错并列出缺哪些，退出码 2，不落盘。
- **旧 JSON 无新字段** → 默认 `""` / `[]`，读取不报错。
- **`design_note` / `impl_note` 含换行** → 原样保存，展示按行缩进。
- **`changes` 未含 `::` 或 `.`** → 本 feat **不**校验（留给 feat-fields-check）。
- **`feat show --json`** → 自动带出新字段（`_to_dict` 已含）。
- **`review_items()` 新增三类 key** → 旧 feat 无这些字段，自然不产生项，
  不影响既有勾选数据。

## 实现与校验结果（收尾）

**在 close 阶段补写**。
