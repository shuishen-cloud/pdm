# 补完 Ledger 门面（ledger-complete）

> 先于实现编写。把"需要凑环境"的操作收进 **一个入口对象**。
> **只做门面（方案 A）**，底层内核函数全部保留不动。

## 问题

`pdev/api.py` 的 `Ledger` 已能记录笔记、管 feat，但**只覆盖一半**：

```python
# 想校验一个 feat，现在要这样：
from pdev.store import NoteStore
from pdev.feat import FeatStore
from pdev.git import GitRepo
from pdev.check import check_one
ns = NoteStore(".pdm/notes")
fs = FeatStore(".pdm/feats")
git = GitRepo(".")
check_one(fs, "web-ui", git, note_store=ns)    # ← 凑了 4 个对象
```

**根因**：门面只包了"笔记"与"feat 列表"，**校验 / 审查 / 验证 / 追溯**
仍要求使用者自己 `import` 4 个模块、`new` 3 个对象、凑对参数。

**另一个问题**：`api.py` 把路径**写死** `.pdm`，**不读 config**
（见 `Ledger.__init__`）。而项目其他地方都通过 `config` 解析路径。

## 规范

### 范围：只加门面，不动内核（方案 A）

| 做什么 | 不做什么 |
|--------|---------|
| ✅ 新增 `LedgerV2(Ledger)` 子类 | ❌ 不动 `check.py`/`review.py` 等内核 |
| ✅ 内部委托现有函数 | ❌ 不搬方法（不做方案 B） |
| ✅ `Ledger.__init__` 改为读 `config` | ❌ 不改任何内核公开签名 |
| ✅ 按**子门面**分区组织 | ❌ 不把 18 个方法塞进一个类 |

**判据**：做完之后，`LedgerV2` 是**唯一需要构造的对象**；
其余依赖（`NoteStore`/`FeatStore`/`GitRepo`/`doc_dir`）都在它内部。

### 变更策略：继承隔离 → 验证后合入（路线 ③）

**目的**：隔离变动，保留回退点。

```
第一步（本 feat）：
  class Ledger: ...                  ← 旧代码几乎不动
  class LedgerV2(Ledger): ...        ← 新功能全在此，可随时删掉回退

第二步（后续，验证过后）：
  把子门面属性合入 Ledger            ← 只搬 4~5 个属性，不搬 18 个方法
```

**哪个可以直接改、哪个必须隔离**：

| 改动 | 性质 | 处理 |
|------|------|------|
| `__init__` 读 config | 小、明确、是 bug | ✅ **直接改**（无需隔离） |
| 18 个新方法 | 大、试验性 | ✅ **放子类**（可回退） |

**关键**：合入时搬的是**子门面属性**（4~5 个），**不是** 18 个方法——
否则会重新变成“上帝对象”。

### 单条操作用「子门面 + 传 slug」形式

```python
ledger.checks.of("web-ui")                      # 校验
ledger.reviews.mark("web-ui", "api:0")          # 审查（写）
ledger.reviews.counts("web-ui")                 # 审查（读）
ledger.trace.doc_body("web-ui")                 # 追溯
```

**不引入 `FeatHandle`**——理由是：
- 子门面已经做到了“按职责分区”，再多一层 handle 反而增重
- 与 CLI 风格一致（`pdm feat review <slug> --item <key>`）
- 少一个类型、少一层间接

### Ledger 的完整方法集

**已有（保留）**：

```python
ledger.record(commit=..., kind=..., title=...)   # 记笔记
ledger.notes()                                   # 全部笔记
ledger.notes_of(commit)                          # 某提交的笔记
ledger.features                                # FeatureAPI（见下）
ledger.overview() -> NoteStats                   # 笔记总览
```

**新增 —— 校验**：

```python
ledger.check(slug) -> List[CheckIssue]           # 委托 check_one
ledger.check_all() -> List[CheckIssue]           # 委托 check_feats
ledger.summary(issues) -> CheckSummary           # 委托 summarize
```

**新增 —— 审查**：

```python
ledger.reviews(slug) -> List[ReviewItemRef]      # 某 feat 的可审项
ledger.counts(slug) -> ReviewCounts              # 审查计数
ledger.review_overview() -> ReviewScore          # 全部 feat 的评分
ledger.mark_reviewed(slug, key, by="") -> Feat   # 置 [审]
ledger.mark_tested(slug, key, ...) -> Feat       # 置 [测]
```

**新增 —— 验证**：

```python
ledger.pending_verifications(commit=None) -> List[CommitNote]  # 委托 pick_notes
ledger.verify(note) -> List[RunResult]                          # 委托 run_note
ledger.verify_commit(commit) -> List[RunResult]                 # 便捷：某提交全部
```

**新增 —— 追溯**：

```python
ledger.doc_body(slug) -> str                     # 委托 read_doc_body
ledger.notes_of_feat(slug) -> List[CommitNote]   # 委托 notes_for_feat
```

### FeatureAPI 的扩展

```python
ledger.features.new(slug, title, **fields) -> Feat    # 已有
ledger.features.get(slug) -> Optional[Feat]           # 已有
ledger.features.list() -> List[Feat]                  # 已有
ledger.features.open() -> List[Feat]                  # 已有
ledger.features.reviews(slug) -> List[ReviewItemRef]  # 新增（转发）
```

> `mark_reviewed` 等放 `Ledger` 而非 `FeatureAPI`，
> 因为它们**会写盘**，放在顶层更显眼。

### config 解析（修正写死路径）

```python
def __init__(self, root=None, cwd=".", config=None):
    cfg = config or load_config()
    self._notes = NoteStore(路径来自 cfg.store)
    self._feats = FeatStore(路径来自 cfg.feat.store)
    self._doc_dir = cfg.doc.dir
    self._author = cfg.default_author
    self._git = GitRepo(cwd)
```

**兼容**：`open_ledger(root=...)` 传了 `root` 时，仍按
`<root>/notes`、`<root>/feats` 布局（保持现测试通过）。

## 接口

```python
# pdev/api.py

class CheckAPI:                       # 子门面：校验
    def of(self, slug: str) -> List[CheckIssue]: ...
    def all(self) -> List[CheckIssue]: ...
    def summary(self, issues) -> CheckSummary: ...

class ReviewAPI:                      # 子门面：审查
    def list(self, slug: str) -> List[ReviewItemRef]: ...
    def counts(self, slug: str) -> ReviewCounts: ...
    def overview(self) -> ReviewScore: ...
    def mark(self, slug, key, value=True, by="") -> Feat: ...
    def mark_tested(self, slug, key, value=True, command="", status="") -> Feat: ...

class VerifyAPI:                      # 子门面：验证
    def pending(self, commit=None) -> List[CommitNote]: ...
    def run(self, note) -> List[RunResult]: ...
    def commit(self, commit) -> List[RunResult]: ...

class TraceAPI:                       # 子门面：追溯
    def doc_body(self, slug: str) -> str: ...
    def notes(self, slug: str) -> List[CommitNote]: ...

class Ledger:
    # 已有（本 feat 不动）
    def record(...) -> CommitNote: ...
    def notes(self) -> List[CommitNote]: ...
    def notes_of(self, commit) -> List[CommitNote]: ...
    @property
    def features(self) -> FeatureAPI: ...
    def overview(self) -> NoteStats: ...

class LedgerV2(Ledger):               # 新增：可回退的子类
    @property
    def checks(self) -> CheckAPI: ...
    @property
    def reviews(self) -> ReviewAPI: ...
    @property
    def verify(self) -> VerifyAPI: ...
    @property
    def trace(self) -> TraceAPI: ...

def open_ledger(root=None, cwd="", config=None) -> LedgerV2: ...
```

**`open_ledger` 返回 `LedgerV2`**；`Ledger` 保留供回退（如需）。

## 日志

无新增日志（门面不打日志，与内核一致）。

## 兜底

| 情况 | 处理 |
|------|------|
| `config` 读取失败 | 回退默认 `.pdm` 布局，不抛 |
| git 不可用 | `checks.of()` 仍可跑（`git=None`，`check_one` 已容忍） |
| feat 不存在 | 抛 `FeatError`（与内核一致） |
| 无 feat / 无笔记 | `checks.all()` 返回 `[]`，不报错 |
| `verify.run` 遇不可执行的验证 | 由 `run_note(only_runnable=True)` 处理 |
| 子门面 API 出错 | 删 `LedgerV2` 即可回退到 `Ledger` |

## 验证方法（测试即用法说明书）

测试重点**不是单个方法**，而是**怎么组合使用**：

```
test=tests/test_ledger.py::test_usage_record_and_overview
     —— 记笔记 → 看总览（最小闭环）
test=tests/test_ledger.py::test_usage_full_review_flow
     —— 建 feat → 看可审项 → 勾审 → 看计数（审查闭环）
test=tests/test_ledger.py::test_usage_check_and_fix
     —— 校验 → 拿 issue → 知道该做什么
     （校验闭环）
test=tests/test_ledger.py::test_usage_trace_from_code_to_design
     —— 从文件追溯 → 拿 feat → 读设计正文（追溯闭环）
test=tests/test_ledger.py::test_usage_verify_flow
     —— 列待验证 → 跑验证 → 看结果（验证闭环）
test=tests/test_ledger.py::test_ledger_reads_config
test=tests/test_ledger.py::test_no_kernel_signature_changed
cmd=.venv/bin/pytest -q
manual=用 open_ledger() 完成五个闭环，全程不 import 内核模块
expected=全绿；内核签名未变；可用例当成说明书读
```
