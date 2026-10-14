# Feat 审查项数据模型（review-model）

> 先于实现编写。给每条 Feat 的可人工审核信息项（doc / api / logs /
> fallbacks）附加**两个独立勾选位**：`[审]` 人工审查、`[测]` 测试通过。
> 本 feat 只做数据结构与持久化，不做评分、不做 UI。

## 问题

现状 `pdm feat check` 能校验「字段是否为空」「阶段是否齐全」，但**无法记录
人是否真的看过**这些字段：

- `feat.api` / `logs` / `fallbacks` 是 `pdm feat new` 时一次写入的静态文本，
  之后没有任何「我审过了 / 这条测试跑通了」的痕迹；
- 想知道「这个 feat 的规格有没有被人工确认」，只能靠 issue 或笔记间接猜；
- 没有数据，后续的「低覆盖率告警」与「掌握程度评分」无从谈起。

根因：Feat 只有**描述性**字段，缺**过程性**字段（谁在何时确认了什么）。

## 规范

### 可审项（review items）

一条 Feat 的可审项由其**规格字段**展开而来，顺序固定：

| 来源 | 键（key） | 说明 |
|------|-----------|------|
| `feat.doc` 非空 | `doc` | 设计文档路径（一条） |
| `feat.api` 第 i 条 | `api:i` | i 从 0 开始 |
| `feat.logs` 第 i 条 | `logs:i` | i 从 0 开始 |
| `feat.fallbacks` 第 i 条 | `fallbacks:i` | i 从 0 开始 |

- 键**只由字段类型 + 序号构成**，不含内容——内容改动不应丢失勾选状态。
- `doc` 为空时不产生该项；`api`/`logs`/`fallbacks` 为空列表时同理。
- 全部可审项的数量记为 `items`，是评分分母。

### 勾选位

每个可审项有**两个独立布尔位**：

| 位 | 含义 | 谁置位 |
|----|------|--------|
| `reviewed` | 有人工看过并确认 | 人（TUI 空格 / CLI `--review`） |
| `tested` | 关联测试已实际执行并通过 | 测试执行器回写 |

两者**互不蕴含**：可以只审不测，也可以只测未审（如 CI 先跑）。

### 存储结构

`Feat.reviews` 为 dict，键是可审项 key，值是 `ReviewItem`：

```python
@dataclass
class ReviewItem:
    reviewed: bool = False
    reviewed_by: str = ""        # "human:lwy"，复用 Actor 的字符串形式
    reviewed_at: Optional[datetime] = None
    tested: bool = False
    test_command: str = ""       # 实际执行的命令，如 "pytest tests/x.py::test_y"
    test_status: str = ""        # passed / failed / error（取 VerificationStatus）
    tested_at: Optional[datetime] = None
```

- 只有**被操作过**的 key 才落盘；未勾选的项不写入 JSON（保持文件精简）。
- 勾选状态与内容解耦：key 存在但该项已从 `api` 删除时，视为**孤儿记录**，
  读取时保留、参与统计时忽略。

## 接口

```python
# pdev/feat.py

@dataclass
class ReviewItem:
    reviewed: bool = False
    reviewed_by: str = ""
    reviewed_at: Optional[datetime] = None
    tested: bool = False
    test_command: str = ""
    test_status: str = ""
    tested_at: Optional[datetime] = None

@dataclass
class Feat:
    # 新增字段（默认空 dict，兼容旧数据）
    reviews: dict = field(default_factory=dict)

    def review_items(self) -> List[Tuple[str, str]]:
        """展开可审项，返回 [(key, label), ...]。

        label 供 CLI/TUI 直接显示，如 ("api:0", "Foo.bar() -> int")。
        顺序：doc → api → logs → fallbacks。
        """

    def review_item(self, key: str) -> Optional[ReviewItem]:
        """取某 key 的勾选记录；未记录返回 None。"""

    def set_reviewed(self, key: str, value: bool = True,
                     by: str = "") -> ReviewItem:
        """置/清 `[审]` 位；value 为真时记录 by 与时间。"""

    def set_tested(self, key: str, value: bool = True,
                   command: str = "", status: str = "") -> ReviewItem:
        """置/清 `[测]` 位；value 为真时记录命令、状态与时间。"""

    def review_counts(self) -> Tuple[int, int, int]:
        """返回 (items, reviewed, tested)，供评分与 check 使用。

        - items：当前可审项总数
        - reviewed：其中 reviewed 为真的数量
        - tested：其中 tested 为真的数量
        孤儿记录（key 已不存在）不计入。
        """

class FeatStore:
    def set_reviewed(self, slug: str, key: str, value: bool = True,
                     by: str = "") -> Feat
    def set_tested(self, slug: str, key: str, value: bool = True,
                   command: str = "", status: str = "") -> Feat
        """透传 Feat 的同名方法并落盘；slug 不存在抛 FeatError。"""
```

序列化：`_to_dict` 增 `"reviews"`，`_from_dict` 读 `d.get("reviews") or {}`，
逐条构造 `ReviewItem`（时间用 `datetime.fromisoformat`，非法则置 None）。
**旧 JSON 无该键 → 空 dict，不报错。**

## 日志

- 本层为纯数据操作，**不打日志**。
- 勾选结果只体现在 `Feat.reviews` 与 `updated_at` 的变化上，
  由 CLI/TUI 在交互层回显。

## 兜底

- **旧数据无 `reviews` 键** → 空 dict，读取不报错。
- **key 非法**（如 `api:999` 超出范围）→ `set_*` 抛 `FeatError`，
  不写入；避免落一批永不生效的孤儿记录。
- **时间字段非法** → `_from_dict` 静默置 None，不阻断整条 feat 加载。
- **`reviews` 值类型不对**（非 dict）→ 视为空，忽略。
- **孤儿记录**（key 对应的规格项已删除）→ 保留在 JSON 中，
  `review_counts` 不计入；这样用户撤回一次 `api` 编辑不会丢勾选。

## 实现与校验结果（收尾）

- **实现**：`pdev/feat.py` 新增 `ReviewItem` dataclass、`Feat.reviews` /
  `review_items` / `review_item` / `set_reviewed` / `set_tested` /
  `review_counts`，以及 `FeatStore.set_reviewed` / `set_tested` 与
  `_review_to_dict` / `_review_from_dict` 序列化。
- **提交**：`doc` 66f18db、`test` e7ae36a、`feat` 9d48b5a、`fix` 5b5425f。
- **测试**：`tests/test_feat.py` 新增 19 个用例，全仓 632 个用例通过。
- **实测抓出的问题**：`fix` 阶段发现 `set_reviewed(key, False)` 会对
  从未勾选的 key 写入一条全空记录，违反「未操作不落盘」约定；
  已加 `ReviewItem.is_empty` + `_prune` 修正，并补两个回归用例。
- **结论**：设计成立。key 用「字段+序号」经受住了内容编辑场景；
  孤儿记录保留但不计入统计的策略在 `test_review_counts_ignore_orphans`
  中得到验证。
