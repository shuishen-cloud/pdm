# 接口问题完整清单（扩展到全部维度）

> 补充 `INTERFACE_AUDIT.md`（那份只审计了**返回类型**）。
> 本文件覆盖**全部可读性维度**，实测数据，**不改代码**。
>
> 时间：2026-10-15

---

## 总览：8 个维度

| 维度 | 问题 | 重灾区 | 严重度 |
|:--:|---|---|:---:|
| A | 参数无注解 | `cli/commands.py`(28) `webui.py`(12) | 中 |
| B | 字段标注只有裸容器 | `feat.py`(3) `featview.py` | **高** |
| C | 函数重名（45 组） | 全库 | 中 |
| D | 同一概念多套表示 | `_COLOR`×3 `_MARK`×4 `_KIND_SHORT`×2 | **高** |
| E | 同义不同名的参数 | `commit`/`ref`/`refs`；`key`/`item`/`target` | 中 |
| F | 同一规则写两处 | 覆盖率算法、阶段序列 | **高** |
| G | magic 值散落 | `0.6` ×6 | 中 |
| H | 返回裸容器（上次已测） | 18 个 | **高** |

---

## A. 参数无注解：55 处

```
cli/commands.py   28 处
webui.py          12 处
check.py           7 处
featview.py        3 处
tui_curses.py      3 处
feat.py            1 处
stage.py           1 处
```

**典型**：

```python
def apply_review(feat_store, payload: dict, by: str = "") -> Dict[str, Any]
#                ^^^^^^^^^^^ 无注解 —— 是什么？FeatStore 还是别的？
```

**影响**：IDE 无补全、读者不知传什么。

---

## B. 字段标注只有裸容器：5 处

```python
# pdev/feat.py
reviews: dict = field(default_factory=dict)        # 里面是 ReviewItem
comments: dict = field(default_factory=dict)       # 里面是 str
stage_reviews: dict = field(default_factory=dict)  # 里面是 StageReview

# pdev/featview.py
buckets: dict = {}

# pdev/check.py
seen: set = set()
```

**最严重的是 `reviews`/`comments`/`stage_reviews`**：

| 字段 | 标注 | 实际元素 | 读者能知道吗 |
|---|---|---|---|
| `reviews` | `dict` | `ReviewItem` | ❌ 且 `ReviewItem` **未在顶层导出** |
| `comments` | `dict` | `str` | ❌ |
| `stage_reviews` | `dict` | `StageReview` | ❌ 同上 |

**应为**：`Dict[str, ReviewItem]` / `Dict[str, str]` / `Dict[str, StageReview]`

**注意**：这正是上次审计发现的"`Feat.reviews` 看不出元素类型"的**代码侧根因**。

---

## C. 函数重名：45 组

### 危险重名（跨模块，语义不同）

| 名字 | 出现在 | 问题 |
|---|---|---|
| `validate` | `doc.py` `feat.py` `issue.py` `note.py` | 4 个域各一个，**签名不同** |
| `risky` | `doc.py` `fingerprint.py` `note.py` | 3 个不同判据 |
| `ok` | `review.py` `scripts.py` `verify.py` | 3 个不同含义 |
| `add` | `check.py` `feat.py` `store.py` | 参数完全不同 |
| `run` | `tui_curses.py` `webui.py` `app.py` | 3 个不同入口 |
| `is_ai` | `common.py` `fingerprint.py` | 两处实现 |

### 跨层重名（`Feat` vs `FeatStore`，5 组）

```python
Feat.set_reviewed(key, value=True, by="")
FeatStore.set_reviewed(slug, key, value=True, by="")
#                    ^^^^ 只差一个 slug
```

同名 5 个：`set_reviewed` / `set_tested` / `set_comment` /
`review_stage` / `unreview_stage`

### 框架重名（可能冲突）

| 名字 | 出现 | 说明 |
|---|---|---|
| `compose` | app.py + panels.py + screens.py ×5 | Textual 约定，**可接受** |
| `on_mount` | app.py + screens.py ×2 | 同上 |
| `_move` | `tui_curses.py` + `panels.py` ×2 | 自实现，**易混** |

---

## D. 同一概念多套表示（最严重的架构问题）

### D1. kind 的展示信息散在 6 处

```
pdev/note.py            → "debug"            （值）
pdev/cli/parser.py      → ["dbg","db"]       （别名）
pdev/cli/commands.py    → "33"               （ANSI 色）
pdev/tui/panels.py      → "magenta"          （Textual 色）
pdev/tui_curses.py      → "dbg"              （缩写）
pdev/webui.py           → --dbg + .kind.debug（CSS，2 行）
```

### D2. 表格重名但语义不同

| 表 | 文件 | 内容 |
|---|---|---|
| `_KIND_SHORT` | `cli/parser.py` | **输入别名**（列表） |
| `_KIND_SHORT` | `tui_curses.py` | **显示缩写**（字符串） |

**同名不同义** → 看起来冗余 → 但合并不了。

### D3. `_MARK` 系列：4 个文件各有一套

```
pdev/check.py        _MARK         （check level 标记）
pdev/tui/panels.py   _STATUS_MARK + _VERIFY_MARK
pdev/tui_curses.py   _STATUS_MARK
pdev/cli/commands.py _MARK + _VERIFY_MARK
```

**`_STATUS_MARK` 在 2 个文件重复，`_VERIFY_MARK` 在 2 个文件重复。**

### D4. 颜色有 4 套表示

```
CLI    → ANSI 数字码     "33"
TUI    → Textual 名      "magenta"
curses → curses 常量     （另有）
web    → CSS 十六进制    "#f9e2af"
```

**同一语义（"debug 用黄色"）4 种写法。**

---

## E. 同义不同名的参数

### E1. "提交" 有 3 个名字

```python
commit   8 次    store.by_commit(commit)
ref      3 次    git.commit_info(ref)      # ← 有时是 hash，有时是 "HEAD"
refs     1 次    git.commit_infos(refs)
```

**`ref` 最危险**：`commit_info("HEAD")` 与 `commit_info("abc1234")` 都合法。

### E2. "目标" 有 5 个名字

```python
key      17 次   review key "api:0" / 配置键 / 统计键  ← 三种含义
slug     28 次   feat 标识
target    9 次   测试用例 / 待解析目标 / 目标阶段  ← 三种含义
item      5 次   resolve_keys(item=...) 可传 key 或前缀
name      4 次
```

**`target` 和 `key` 各自承担 3 种含义。**

---

## F. 同一规则写两处

### F1. 阶段序列：3 处定义

```python
pdev/stage.py:29    STAGE_SEQUENCE = ("doc","test","script","feat","fix","close")
pdev/check.py:61    STAGES         = ("doc","test","script","feat","fix")      # 少 close
pdev/check.py:441   _PIPELINE      = ("doc","test","script","feat","fix")      # 又一份
```

**`check.py` 里有两份**，且都与 `stage.py` 的不同（少 `close`）。

**风险**：改阶段序列要改 3 处，漏一处则规则不一致。

### F2. 覆盖率算法：2 处实现

```
pdev/check.py    _check_review  → review-none / review-low
pdev/review.py   compute_review → no-review   / low-review
```

**同一算法、不同告警码**（上次审计已记）。

---

## G. magic 值散落

### G1. 覆盖率阈值 `0.6` 出现 5 次

```python
check.py:123   min_coverage: float = 0.6     # 默认参数
check.py:141   min_coverage: float = 0.6
check.py:200   min_coverage: float = 0.6
check.py:365   min_coverage: float = 0.6
review.py:30   ("good", 0.6)                 # 分档下界
```

**外加 `review.py:36  REVIEW_WEIGHT = 0.6`（含义不同，但同值易混）。**

---

## H. 返回裸容器：18 个（上次已测，此处列全）

| 模块 | 接口 | 返回 |
|---|---|---|
| check | `summarize` | `dict` |
| config | `to_dict` | `Dict[str, Any]` |
| feat | `review_items` | `List[tuple]` |
| feat | `review_counts` | `tuple` |
| feat | `commented_items` | `List[tuple]` |
| feat | `commit_stage` | `tuple` |
| feat | `resolve_keys` | `List[tuple]` |
| featview | `group_notes_by_kind` | `List[Tuple[str, list]]` |
| fingerprint | `trailers` | `List[Tuple[str, str]]` |
| git | `commit_infos` | `Dict[str, CommitInfo]` |
| review | `unreviewed_items` | `List[tuple]` |
| scripts | `parse_target` | `tuple[str, list[str]]` |
| webui | `build_data` | `Dict[str, Any]` |
| webui | `build_feats` | `List[Dict[str, Any]]` |
| webui | `build_feat_detail` | `Optional[Dict[str, Any]]` |
| webui | `build_review_items` | `List[Dict[str, Any]]` |
| webui | `apply_review` | `Dict[str, Any]` |
| webui | `err` | `Dict[str, Any]` |

---

## 汇总：重灾区排名

| 排名 | 模块 | 问题数 | 主要问题 |
|:--:|---|:--:|---|
| 1 | **`pdev/feat.py`** | 12+ | 裸 dict 字段(3) + 跨层重名(5) + 裸容器(5) |
| 2 | **`pdev/webui.py`** | 12 | 全 `Any`(6) + 无注解参数(12) |
| 3 | **`pdev/cli/commands.py`** | 30+ | 无注解(28) + `_COLOR`/`_MARK` |
| 4 | **`pdev/check.py`** | 8 | 阶段序列两份 + 阈值(4) + `_MARK` |
| 5 | `pdev/review.py` | 4 | 与 check 重复实现 |
| 6 | `pdev/tui_curses.py` | 5 | `_KIND_SHORT` 撞名 + `_MARK` |

---

## 三个"根因"串联

前面所有维度，归到三个根因：

### 根因 1：**没有"概念对象"，只有"容器"**

```
ReviewCounts  → 不存在，用 tuple 代替
CheckSummary  → 不存在，用 dict 代替
KindSpec      → 不存在，散成 6 处表
WebData       → 不存在，用 Dict[str,Any] 代替
```

**证据**：18 个裸容器 + 5 处裸 dict 字段。

### 根因 2：**没有"单一真相"，同一事实多处存储**

```
阶段序列  → 3 处
覆盖率算法 → 2 处
kind 展示 → 6 处
阈值 0.6  → 5 处
```

**证据**：F/G/D 三个维度。

### 根因 3：**命名没有"唯一性约束"**

```
review  → 3 种含义（勾选/评论/阶段审核）
key     → 3 种含义
target  → 3 种含义
ref     → hash 或分支名
_KIND_SHORT → 2 个不同表
```

**证据**：C/E 两个维度。

---

## 附：各维度可执行核查命令

```bash
# A. 无注解参数
python -c "..."   # 见上文脚本

# B. 裸 dict 字段
grep -n ': dict = \|: list = \|: set = ' pdev/*.py

# D. 概念多套表示
grep -rn '_KIND_SHORT\|_STATUS_MARK\|_VERIFY_MARK' pdev/ --include='*.py'

# F. 同一规则多处
grep -rn 'STAGE_SEQUENCE\|_PIPELINE\|STAGES = ' pdev/*.py
grep -rn 'min_coverage.*=.*0\.6' pdev/*.py
```
