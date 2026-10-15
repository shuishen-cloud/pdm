# 接口可读性审计（pdev/）

> 导出时间：2026-10-14。**只出清单，不改代码。**
> 判据：**看签名能否知道"要什么、给什么、会怎样"**。
> 读不懂 = 必须打开实现才能正确调用。

判据分四级：

| 级 | 含义 |
|:--:|------|
| **A** | 一眼读懂，无需看实现 |
| **B** | 稍想一下能懂（可接受） |
| **C** | 需看实现才知道返回什么 |
| **D** | 需看实现且**极易调用错** |

---

## 一、总览：按问题类型归类的清单

共审计 **19 个模块、163 个函数/方法**。发现的问题分布：

| 问题类型 | 数量 | 涉及模块 |
|---------|:---:|---------|
| ① 返回裸容器（`tuple`/`dict`/`list`） | **31** | check, feat, webui, store, featview, fingerprint, scripts |
| ② 同名跨层（`Feat` vs `FeatStore`） | **5 组** | feat |
| ③ 一词多义（`review` 家族） | **12+** | feat, check, review |
| ④ 返回类型不一致 | **3 处** | feat, store |
| ⑤ 布尔参数无关键字保护 | **4** | check, store, tui_curses |
| ⑥ 参数含义需猜（`key`/`target`/`item`） | **9+** | feat, check, verify |

---

## 二、D 级：极易调用错（优先处理）

### D1. `review_counts() -> tuple` —— 顺序靠记

```python
# pdev/feat.py:313
def review_counts(self) -> tuple:
    """返回 ``(items, reviewed, tested)``，孤儿记录不计入。"""
```

**问题**：
- 三个 `int`，**顺序只能看 docstring**
- docstring 写 `(items, reviewed, tested)`，但**变量名在调用处常写成 `total`**
- **已实际造成 bug**：本轮开发中按 `(reviewed, total)` 解包 → `ValueError`

**读不懂点**：`counts[0]` 是什么？`a, b, c = counts` 谁是总数？

**建议形态**：

```python
@dataclass(frozen=True)
class ReviewCounts:
    total: int
    reviewed: int
    tested: int

def review_counts(self) -> ReviewCounts: ...
```

---

### D2. `review_items() -> List[tuple]` —— 元组元素含义不明

```python
# pdev/feat.py:248
def review_items(self) -> List[tuple]:
    """展开可审项，返回 ``[(key, label), ...]``。"""
```

**问题**：`(key, label)` 只在 docstring 里。调用处：

```python
for key, label in feat.review_items()   # 必须记得顺序
keys = [k for k, _ in targets]          # 到处解包
```

**读不懂点**：`item[0]` 是 key 还是 label？

**建议形态**：

```python
@dataclass(frozen=True)
class ReviewItemRef:
    key: str        # "api:0"
    label: str      # 显示文本

def review_items(self) -> List[ReviewItemRef]: ...
```

---

### D3. `commented_items() -> List[tuple]` —— **三个** str，更糟

```python
# pdev/feat.py
def commented_items(self) -> List[tuple]:
    """返回 ``[(key, label, comment), ...]``，只含**非空**评论。"""
```

**问题**：三元组。`t[0]`/`t[1]`/`t[2]` 全靠记。

**建议**：复用 D2 的 `ReviewItemRef`，加 `comment` 字段。

---

### D4. `summarize(issues) -> dict` —— dict 键未知

```python
# pdev/check.py
def summarize(issues: List[CheckIssue]) -> dict: ...
```

**问题**：返回什么键？`{"error": n, "warning": m}`？还是别的？**必须读实现**。

**建议**：`-> CheckSummary` 或至少 `-> Dict[str, int]` + docstring 列键。

---

### D5. `build_data(store, git) -> Dict[str, Any]` —— `Any` 是放弃类型

```python
# pdev/webui.py
def build_data(store: NoteStore, git, cwd: str = ".") -> Dict[str, Any]:
```

**问题**：`Any` 意味着**没有类型信息**。实际返回 5 个键
（`commits`/`notes`/`store_root`/`git_available`/`warnings`），但类型上看不出。

**连锁**：`build_feats -> List[Dict[str, Any]]`、
`build_review_items -> List[Dict[str, Any]]`、
`apply_review -> Dict[str, Any]` —— **整个 webui 模块都是 `Any`**。

**建议**：定义 `WebData` / `FeatSummary` / `ReviewItemView` dataclass，
`to_dict()` 只在 HTTP 边界调用。

---

### D6. `parse_target(target: str) -> tuple[str, list[str]]`

```python
# pdev/scripts.py
def parse_target(target: str) -> tuple[str, list[str]]: ...
```

**问题**：`str` 是什么？`list[str]` 是什么？**无 docstring 提示**。

**建议**：`-> ParsedTarget` dataclass，或至少加 docstring。

---

## 三、C 级：需看实现才知道

### C1. 全部 31 处裸容器

完整清单（`-> tuple` / `-> dict` / `-> List[...]` 但元素无类型）：

| 文件 | 函数 | 返回 |
|------|------|------|
| check.py | `summarize` | `dict` |
| check.py | `_note_for` | `list` |
| config.py | `to_dict` / `_read_json` / `_env_overrides` / `_scrub` | `Dict[str, Any]` |
| feat.py | `review_items` | `List[tuple]` |
| feat.py | `commented_items` | `List[tuple]` |
| feat.py | `review_counts` | `tuple` |
| feat.py | `_review_keys` | `set` |
| feat.py | `_to_dict` / `_review_to_dict` / `_stage_review_to_dict` | `dict` |
| featview.py | `notes_for_feat` | `list` |
| featview.py | `group_notes_by_kind` | `List[Tuple[str, list]]` |
| fingerprint.py | `trailers` | `List[Tuple[str, str]]` |
| store.py | `_counter` | `Dict[str, int]` |
| store.py | `_note_to_dict` / `_verification_to_dict` | `dict` |
| tui_curses.py | `_commit_infos` | `dict` |
| tui_curses.py | `col_lines` | `List[str]`（这个 OK，行文本） |
| webui.py | 全部 8 个 | 见 D5 |

**分级说明**：
- **可接受**：`-> List[str]`（行文本）、`-> Dict[str, CommitInfo]`（值有类型）
- **不可接受**：`-> tuple`、`-> dict`、`-> List[tuple]`、`Dict[str, Any]`

### C2. `group_notes_by_kind(notes) -> List[Tuple[str, list]]`

元组的 `str` 是 kind，`list` 里是 note。**顺序需读 docstring**。

### C3. `trailers() -> List[Tuple[str, str]]`

指纹 trailer 的 `(key, value)`。**无 docstring**，需看实现。

---

## 四、同名跨层：`Feat` vs `FeatStore`（5 组）

**同一份文件里，两个类有 5 个同名方法，签名不同。**

| 方法 | `Feat` 版 | `FeatStore` 版 |
|------|-----------|---------------|
| `set_reviewed` | `(key, value=True, by="")` | `(slug, key, value=True, by="")` |
| `set_tested` | `(key, value=True, command="", status="")` | `(slug, key, value=True, command="", status="")` |
| `set_comment` | `(key, text)` | `(slug, key, text)` |
| `review_stage` | `(stage, by, note="")` | `(slug, stage, by, note="")` |
| `unreview_stage` | `(stage)` | `(slug, stage)` |

**读不懂点**：

```python
feat.set_reviewed("api:0", True)          # Feat 层
store.set_reviewed("web-ui", "api:0", True)  # Store 层
```

**唯一的区别是"多不多 slug"**。读代码时看到 `set_reviewed(...)`，
**必须确认是哪个对象**。

**建议**：Store 层改名加前缀，如 `set_reviewed_for(slug, ...)`，
或统一为 `FeatStore.update_review(slug, key, ...)`。

---

## 五、一词多义：`review` 家族（12+ 处）

**`review` 这一个词承担了三种含义：**

| 含义 | 用法 | 例子 |
|------|------|------|
| **A. 条目勾选** | `reviewed` / `set_reviewed` / `review_items` / `review_counts` | `[审]` 位 |
| **B. 条目评论** | `comments` / `commented_items` | 人写的评语 |
| **C. 阶段审核** | `review_stage` / `unreview_stage` / `stage_reviewed` / `stage_reviews` | 阶段门禁 |

**具体清单**：

```
feat.py:  review_items, review_item, _review_keys, _review_slot,
          set_reviewed, review_counts, review_stage, unreview_stage,
          stage_reviewed, pending_stage_review
check.py: _check_review, _check_stage_reviews
review.py: compute_review, ReviewScore, ReviewPolicy, ReviewWarning
```

**读不懂点**：`feat.review_stage(...)` 和 `feat.review_counts()` 里的
"review" **根本不是一回事**——一个管阶段门禁，一个管条目统计。

**建议**：按维度分名

| 现名 | 建议名 | 理由 |
|------|--------|------|
| `review_stage` | `audit_stage` | 阶段**审核**，与条目勾选区分 |
| `stage_reviewed` | `stage_audited` | 同上 |
| `stage_reviews` | `stage_audits` | 字段名同步 |
| `set_reviewed` | `mark_reviewed` | 动词化，更像"打勾" |

---

## 六、返回类型不一致（3 处）

### 6.1 `FeatStore` 的写方法返回 `Feat`，读方法返回 `None`

```python
def add(self, feat: Feat) -> None        # 写，返回 None
def update(self, feat: Feat) -> None     # 写，返回 None
def set_status(self, slug, status) -> Feat   # 写，返回 Feat
def link_commit(self, slug, commit) -> Feat  # 写，返回 Feat
def set_comment(self, slug, key, text) -> Feat
```

**问题**：**写方法有的返回 `None`，有的返回 `Feat`**，判据不明。
调用方无法预期。

### 6.2 `Feat` 的写方法返回 `ReviewItem`，`FeatStore` 的返回 `Feat`

```python
Feat.set_reviewed(...) -> ReviewItem         # 返回被改的那一项
FeatStore.set_reviewed(...) -> Feat          # 返回整个 feat
```

**读不懂点**：**同一个方法名，返回的东西粒度不同**。

### 6.3 `verify` 相关：`-> int` vs `-> RunResult`

```python
cmd_verify_run(ctx, args) -> int     # CLI 退出码
verify.run(...) -> ?                 # 内核
```

需确认内核返回什么（`RunResult`）。

---

## 七、布尔参数（4 处）

```python
check.py:392   def check_stages(feat, git, exempt: bool = False)
check.py:109   def format_issue(issue, color: bool = False)
store.py:192   def _counter(self, key, skip_none: bool = False)
tui_curses.py  def col_lines(items, selected, w, focused: bool)
```

**读不懂点**：调用处 `check_stages(feat, git, True)` ——
`True` 是什么？**必须回看签名**。

**建议**：Python 无强制关键字，靠约定——**调用时一律写 `exempt=True`**。
或改成 `mode="exempt"` 这类具名参数。

---

## 八、参数含义需猜（9+ 处）

### 8.1 `key` —— 有时是"可审项 key"，有时是"配置键"

```python
Feat.set_reviewed(key: str, ...)         # key = "api:0"
config._coerce_value(value, declared, key)  # key = 配置项名
store._counter(key, ...)                 # key = by_kind / by_status
```

**同名不同义，且都叫 `key`。**

### 8.2 `target` —— 三种含义

```python
Verification.target = "tests/x.py::test_y"    # 测试用例
scripts.parse_target(target)                   # 待解析的目标
Feat.pending_stage_review(target: str)         # 目标阶段名
```

### 8.3 `item` —— `resolve_keys(item=...)` 里的 item 是 key 或前缀

```python
def resolve_keys(self, slug, item: str = "", all_items: bool = False)
    """item 是精确 key → 该项；item 是字段前缀（如 "api"）→ 所有 api:*"""
```

**读不懂点**：`item` 既可以是 `api:0` 也可以是 `api`，**靠内容猜**。

### 8.4 `ref` vs `commit` vs `refs`

```python
git.commit_info(ref: str)        # ref
git.commit_infos(refs: List[str])
git.log(limit, ref="HEAD")       # ref 是分支名！
store.by_commit(commit: str)     # commit
```

**`ref` 有时是 hash，有时是分支名**（`"HEAD"`）。

---

## 九、汇总：按"建议成本"排序

### 低成本、高收益（建议先做）

| # | 问题 | 改法 | 影响面 |
|:--:|------|------|-------|
| 1 | `review_counts() -> tuple` | 换 `ReviewCounts` 数据类 | 2 处调用 |
| 2 | `review_items() -> List[tuple]` | 换 `ReviewItemRef` | 4 处调用 |
| 3 | `commented_items() -> List[tuple]` | 同上复用 | 2 处调用 |
| 4 | `summarize() -> dict` | 换 `CheckSummary` | 1~2 处 |
| 5 | `parse_target() -> tuple` | 加 docstring 或具名类 | 1 处 |

### 中成本（需设计决策）

| # | 问题 | 需要决定 |
|:--:|------|---------|
| 6 | `review` 一词多义 | 是否重命名阶段审核为 `audit_*` |
| 7 | 跨层同名 5 组 | Store 层是否加后缀 |
| 8 | 写方法返回不一致 | 统一返回 `Feat` 还是统一 `None` |

### 高成本（webui 模块整体）

| # | 问题 | 说明 |
|:--:|------|------|
| 9 | 全部 `Dict[str, Any]` | 整个模块需定义 dataclass，工作量较大 |

---

## 十、一个观察：问题集中在两层交界

读完 163 个接口，**"读不懂"大多出现在两个地方**：

1. **返回值的"形状"** —— 裸容器（tuple/dict）占问题总数 **~60%**
2. **命名的"唯一性"** —— 同名跨层、一词多义占 **~35%**

**而"参数"层面问题相对少**（4 处布尔 + 9 处含义模糊）。

**换句话说**：

> 你的接口**"要什么"基本清楚，"给什么"不清楚。**

这解释了为什么读起来"奇怪但说不上哪奇怪"——
调用语法的样子是对的，但**返回给你一个看不懂的元组**。

---

## 附：分级统计

| 级别 | 数量 | 占比 |
|:--:|:---:|:---:|
| A（一眼懂） | ~110 | 67% |
| B（稍想能懂） | ~20 | 12% |
| C（需看实现） | ~29 | 18% |
| D（易调错） | ~6 | 4% |

**A+B 占 79%** —— 大头是好的。问题集中在 **21% 的 C/D 级**，
而这 21% 恰好是**最核心的数据操作**（review/counts/store/webui）。
