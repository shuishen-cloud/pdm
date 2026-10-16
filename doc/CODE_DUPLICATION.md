# 代码复用与冗余清单

> 实测扫描，**只出清单，不改代码**。时间：2026-10-15。
>
> 分三类：
> - **A. 真重复**（同一逻辑写两遍，会分叉）
> - **B. 假重复**（同名但语义不同，**不该合并**）
> - **C. 未复用**（该复用却各写一份）

---

## A. 真重复：同一逻辑写两遍

### A1. `_VERIFY_MARK` 两处，且**值不一致**

```python
# pdev/tui/panels.py
_VERIFY_MARK = {
    VerificationStatus.PASSED: "✓",
    VerificationStatus.FAILED: "✗",
    VerificationStatus.ERROR: "!",
    VerificationStatus.SKIPPED: "-",
    VerificationStatus.UNKNOWN: "·",     # ← 中点
}

# pdev/cli/commands.py
_VERIFY_MARK = {
    VerificationStatus.PASSED: "\u2713",  # ✓（转义写法）
    VerificationStatus.FAILED: "\u2717",  # ✗
    VerificationStatus.ERROR: "!",
    VerificationStatus.SKIPPED: "-",
    VerificationStatus.UNKNOWN: "?",      # ← 问号！不一致
}
```

**问题**：`UNKNOWN` 在 TUI 是 `·`，在 CLI 是 `?`。**同一状态两种显示。**
（转义写法 `\u2713` vs 直接 `✓` 也是无谓差异，但不算 bug。）

**危害**：用户对照 CLI 与 TUI 时会困惑；改一处忘另一处。

### A2. `_STATUS_MARK` 两处，值相同

```python
# pdev/tui/panels.py 与 pdev/tui_curses.py 完全相同
_STATUS_MARK = {
    NoteStatus.OPEN: "○",
    NoteStatus.RESOLVED: "●",
    NoteStatus.NOTED: "·",
}
```

**问题**：纯复制。**改一处必须记得改另一处。**

### A3. `check.py` 的 `LEVEL_MARK` 是第三个"标记表"

```python
# pdev/check.py
LEVEL_MARK = {"error": "✗", "warning": "!"}
```

**问题**：与上面两个表**同性质**（状态 → 符号），但独立定义。
`✗` 还和 `_VERIFY_MARK[FAILED]` 重复。

**三个标记表本可共用一套"符号表"。**

### A4. `_commit_infos` 两处，实现不同

```python
# pdev/cli/commands.py  —— 自己找 git 仓库
def _commit_infos(ctx, notes) -> dict:
    commits = list({n.commit for n in notes})
    for base in (str(ctx.cwd), str(ctx.store.root)):
        git = GitRepo(base)
        if git.available:
            return git.commit_infos(commits)
    ...

# pdev/tui_curses.py  —— 收一个 git 对象
def _commit_infos(git, commits) -> dict:
    if git is None or not git.available:
        return {}
    ...
```

**问题**：**同一目的**（批量取 commit 信息），**参数与逻辑都不同**。
且 `GitRepo.commit_infos()` **本来就存在**（内核已有），
两处**都在重造轮子**。

---

## B. 假重复：同名但**语义不同**（不该合并）

### B1. 两个 `_KIND_SHORT` —— 名字撞车，含义不同

```python
# pdev/cli/parser.py  —— 输入别名（用户可打的简写，一个 kind 可有多个）
_KIND_SHORT = {NoteKind.PITFALL: ["pit"], NoteKind.BUG: ["b"], ...}

# pdev/tui_curses.py  —— 显示缩写（屏幕上印的字，一个 kind 只有一个）
_KIND_SHORT = {NoteKind.PITFALL: "pit", NoteKind.BUG: "bug", ...}
```

**判定**：**不该合并**——一个管"怎么输入"，一个管"怎么显示"。
**但名字撞车**导致看起来像重复。**该改名**（如 `_KIND_ALIASES` / `_KIND_LABEL`）。

### B2. 两个 `is_ai` —— 不同类上的同名属性

```python
# pdev/common.py::Actor
def is_ai(self): return self.kind == "ai"

# pdev/fingerprint.py::Generated
def is_ai(self): return self in (Generated.AI_FULL, Generated.AI_PARTIAL)
```

**判定**：**不该合并**——判据不同（Actor 看前缀，Generated 看枚举）。
这是**多态**（同名不同实现），是正常的。

### B3. `Feat` 与 `FeatStore` 的 5 组同名方法

```
set_reviewed / set_tested / set_comment / review_stage / unreview_stage
```

| 层 | 行数 | 做什么 |
|---|---|---|
| `Feat.xxx` | 11~14 行 | 改内存对象 + `touch()` |
| `FeatStore.xxx` | 6~7 行 | `_require()` + 调 `Feat.xxx` + `update()` 落盘 |

**判定**：**Store 层是"转发 + 落盘"，不是重复实现**。
**但**：读者看到 `store.set_reviewed(...)` 与 `feat.set_reviewed(...)`
**分不清该用哪个**（这是**可读性**问题，非冗余）。

---

## C. 未复用：该复用却各写一份

### C1. `GitRepo.commit_infos()` 被绕过两次

**内核已有**：

```python
# pdev/git.py
def commit_infos(self, refs: List[str]) -> Dict[str, CommitInfo]:
```

**但**：
- `cli/commands.py::_commit_infos` 自己写了循环
- `tui_curses.py::_commit_infos` 也自己写了循环

**两处都调的是 `commit_info`（单数），没用 `commit_infos`（复数）。**

### C2. 覆盖率算法两处（**上次已记，仍未合**）

```python
# pdev/check.py::_check_review    → review-none  / review-low
# pdev/review.py::compute_review  → no-review    / low-review
```

**同一算法、不同告警码**。`oop-refactor` 只统一了阈值常量
（`DEFAULT_MIN_COVERAGE`），**算法本身仍是两份**。

### C3. 阶段序列已收敛，但**校验规则仍分两处**

```python
# pdev/check.py —— 21 个 code
CODES = (...)

# pdev/review.py —— 3 个 code（no-review / low-review / untested）
```

**审查相关的告警码在两个模块各有一套**，与 C2 同源。

---

## D. 汇总：按"该不该动"排序

### 该动（真重复，会分叉）

| # | 项 | 危害 | 成本 |
|:--:|---|:---:|:---:|
| **1** | `_VERIFY_MARK` 值不一致（`·` vs `?`） | **高**（显示矛盾） | 低 |
| **2** | `_STATUS_MARK` 两处复制 | 中 | 低 |
| **3** | `_commit_infos` 重造轮子 | 中 | 低 |
| **4** | 覆盖率算法两份（C2/C3） | **高** | 中 |
| **5** | 三个标记表可合一 | 低 | 低 |

### 该改名（假重复）

| # | 项 | 动作 |
|:--:|---|---|
| **6** | 两个 `_KIND_SHORT` | 改为 `_KIND_ALIASES` / `_KIND_LABEL` |

### 不该动

| # | 项 | 理由 |
|:--:|---|---|
| **7** | 两个 `is_ai` | 多态，正常 |
| **8** | `Feat` vs `FeatStore` 同名 | 分层，非重复 |

---

## E. 一个"理想形态"（供参考，不强制）

如果要把 A 类收敛，形态是：

```python
# pdev/note.py 或新的 pdev/display.py —— 符号的单一真相
VERIFY_MARKS = {PASSED: "✓", FAILED: "✗", ERROR: "!",
                SKIPPED: "-", UNKNOWN: "·"}
STATUS_MARKS = {OPEN: "○", RESOLVED: "●", NOTED: "·"}
LEVEL_MARKS  = {"error": "✗", "warning": "!"}
```

四处（`tui/panels.py`、`tui_curses.py`、`cli/commands.py`、`check.py`）
**全部从这一处取**。

**注意**：`check.py` 的 `LEVEL_MARK` 是否该共用 `✗` 需确认——
`error` 用 `✗` 与 `verify failed` 用 `✗` **是同义还是巧合**。

---

## 附：本次扫描命令

```bash
# 重复的表
python -c "扫描模块级字典赋值，找同名"
# 同名函数
python -c "AST 收集所有 FunctionDef，按名分组"
# 逐个对比
sed -n '/_VERIFY_MARK/,/^}/p' pdev/tui/panels.py pdev/cli/commands.py
```
