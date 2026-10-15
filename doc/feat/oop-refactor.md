# 接口重构：类型化 + 门面 + 单一真相（oop-refactor）

> 先于实现编写。把审计出的接口问题**按可做性分三批**处理。
> 目标：**接口看签名即懂；同一事实只有一处定义。**

## 问题

本会话审计出 **29 个接口问题**（见 `doc/INTERFACE_ISSUES_FULL.md`）。
按「OOP 能否解决」分类后：

| 类别 | 数量 | OOP 能否解决 |
|---|:---:|:---:|
| A 表达/可读性 | 7 | 大半能 |
| B 结构/真相（重复） | 6 | 小半能（本质是纪律） |
| C 建模/语义 | 5 | 一半 |
| D 流程/意图 | 4 | 基本不能 |

**根因三个**：

1. **没有"概念对象"，只有"容器"** —— 18 个裸容器 + 5 处裸 dict 字段
2. **没有"单一真相"** —— 阶段序列 3 处、kind 展示 6 处、阈值 6 处
3. **命名无唯一性约束** —— `review`/`key`/`target` 各 3 义

**本 feat 处理 1、2 两条根因**（第三条与 D 类流程问题不做）。

## 规范

### 范围：三批，按风险从低到高

#### 批次 1：类型化返回值（低风险）

| 现接口 | 现返回 | 改为 |
|--------|--------|------|
| `Feat.review_counts()` | `tuple` | `ReviewCounts` |
| `Feat.review_items()` | `List[tuple]` | `List[ReviewItemRef]` |
| `Feat.commented_items()` | `List[tuple]` | `List[ReviewItemRef]`（含 comment） |
| `check.summarize()` | `dict` | `CheckSummary` |
| `scripts.parse_target()` | `tuple[str, list[str]]` | `ParsedTarget` |
| `Feat.reviews` 字段 | `dict` | `Dict[str, ReviewItem]` |
| `Feat.comments` 字段 | `dict` | `Dict[str, str]` |
| `Feat.stage_reviews` 字段 | `dict` | `Dict[str, StageReview]` |

**约束**：类型定义后**必须加属性访问**（如 `counts.total`），
**不得**再返回可解包的元组——否则读者仍会解包错。

#### 批次 2：门面对象（中风险）

新增 `pdev/api.py`，提供**任务级入口**：

```python
from pdev.api import open_ledger
ledger = open_ledger()                     # 一个入口
ledger.record(commit="abc1234", kind="pitfall", title="...")
ledger.features.new(slug="x", title="...")
ledger.overview()
```

**约束**：
- 门面**只暴露任务级方法**，不暴露 `Store`/`Enum`/裸 `dataclass`
- **不破坏现有 CLI**——门面是**新增**，不是替换
- 门面内部**只调用现有内核算**，不新写逻辑

#### 批次 3：单一真相 + 测试守卫（中风险）

| 现状 | 收敛为 |
|------|--------|
| `STAGES` / `_PIPELINE` / `STAGE_SEQUENCE` 三处 | **只留 `stage.STAGE_SEQUENCE`**，其余派生 |
| kind 展示散在 6 处 | **`note.KIND_SPECS`** 注册表，各处查表 |
| 阈值 `0.6` 出现 6 次 | **单一常量** |

**关键：加测试守卫**——防止再次分叉。例如：

```python
def test_no_hardcoded_stage_sequence():
    """除 stage.py 外，任何模块不得硬编码阶段序列字面量。"""
```

### 不做的事（明确排除）

- ❌ **事件化改造**（把审查/评论/审核统一成事件流）——风险大，且需先定"审核目的"的产品决策
- ❌ **D 类流程问题**（反向追溯、终点强制、审核防伪）
- ❌ **删除 `Feat.notes` 死字段**——分单独 feat
- ❌ **`webui.py` 的 `Dict[str, Any]` 全部类型化**——工作量大，分单独 feat

### 兼容性要求

1. **旧 JSON 必须全部可读**——新增类型只影响内存表示，落盘格式不变。
2. **CLI 行为不变**——所有命令的输出、退出码保持。
3. **全量测试必须通过**——任何一处破坏，必须修好而非改测试。
4. **`StageManager` 重构并入**——工作区已完成的 `stage.py` 重构
   （`run_commit` → `StageManager` 类）作为批次 0 一并提交。

## 接口

```python
# pdev/feat.py
@dataclass(frozen=True)
class ReviewCounts:
    total: int
    reviewed: int
    tested: int
    @property
    def coverage(self) -> float: ...     # reviewed / total（total=0 时为 0）

@dataclass(frozen=True)
class ReviewItemRef:
    key: str
    label: str
    comment: str = ""
    reviewed: bool = False
    tested: bool = False

# pdev/check.py
@dataclass(frozen=True)
class CheckSummary:
    error: int
    warning: int
    @property
    def total(self) -> int: ...

# pdev/scripts.py
@dataclass(frozen=True)
class ParsedTarget:
    command: str
    args: List[str]

# pdev/note.py
@dataclass(frozen=True)
class KindSpec:
    value: str
    short: str                # 显示缩写
    aliases: Tuple[str, ...]  # 输入别名
    color: str                # 语义色
    is_debt: bool

KIND_SPECS: Dict[str, KindSpec] = {...}

# pdev/api.py
class Ledger:
    def __init__(self, root: str = ".pdm", cwd: str = "."): ...
    def record(self, *, commit, kind, title, **kw) -> CommitNote: ...
    def features(self) -> FeatureAPI: ...
    def overview(self) -> NoteStats: ...

def open_ledger(root=".pdm", cwd=".") -> Ledger: ...
```

## 日志

无新增日志。

## 兜底

| 情况 | 处理 |
|------|------|
| 旧 JSON 缺新类型所需字段 | 构造时给默认值，不报错 |
| `ReviewCounts` 的 `total=0` | `coverage` 返回 `0.0`（不除零） |
| `KIND_SPECS` 查不到的 kind | 返回**默认 spec**（不抛异常） |
| 门面调用不存在的 feat | 抛 `FeatError`（与现有行为一致） |

## 验证方法

```
test=tests/test_oop_refactor.py::test_review_counts_is_named_type
test=tests/test_oop_refactor.py::test_review_items_named_type
test=tests/test_oop_refactor.py::test_check_summary_named_type
test=tests/test_oop_refactor.py::test_parsed_target_named_type
test=tests/test_oop_refactor.py::test_kind_specs_single_source
test=tests/test_oop_refactor.py::test_no_hardcoded_stage_sequence
test=tests/test_oop_refactor.py::test_no_hardcoded_coverage_threshold
test=tests/test_oop_refactor.py::test_ledger_facade_roundtrip
test=tests/test_oop_refactor.py::test_old_json_still_loads
cmd=.venv/bin/pytest -q --ignore=tests/test_tui.py --ignore=tests/test_tui_signal.py
manual=跑 pdm note add / query / stats / feat review，输出与改动前一致
expected=全绿；CLI 行为不变
```
