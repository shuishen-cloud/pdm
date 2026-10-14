# script 子阶段：先脚本、再接入（script-stage）

> 先于实现编写。在 `test` 与 `feat` 之间插入一个 **可选** 阶段 `script`：
> 先把 MVP 脚本跑通，再逐步接入正式代码。可选 = 允许从 `test` **跳过**
> 它直接进 `feat`。

## 问题

现在的 `feat` 阶段是「一次性实现到位」，但真实开发常分两步：

1. 先写个**一次性脚本**验证思路（`scripts/try_x.py`）；
2. 思路验证后，再**逐步接入**正式模块（`pdev/x.py`）。

现状下这只能都塞进 `feat` 提交，或手动拆两次 `feat`——
流程上看不出"先脚本后接入"，`check` 也无从校验。

根因：`doc → test → feat → fix → close` 少了"脚本验证"这一环。

## 规范

### 新的阶段序列

```
doc → test → script → feat → fix → close
```

`script` 落在 `test` 与 `feat` 之间：先有测试，再写脚本打通，最后接入。

| 阶段 | 前缀 | 是否必须 |
|------|------|---------|
| `doc` | `doc(` | 必须（首） |
| `test` | `test(` | 必须 |
| **`script`** | **`script(`** | **可选** |
| `feat` | `feat(` | 必须 |
| `fix` | `fix(` | 视需要 |
| `close` | `doc(` | 必须（尾） |

### 「可选」的语义

`script` 可跳过：从 `test` 既允许进 `script`，**也允许**直接进 `feat`。

`stage.next_stages` 需支持这一点：

| 当前 | 允许进入 |
|------|---------|
| `test` | `test`（停留）、`script`、**`feat`** |
| `script` | `script`（停留）、`feat` |

实现：给 `STAGE_SEQUENCE` 配一个「可选阶段」集合，
`next_stages` 对可选阶段**多放行一跳**。

```python
STAGE_SEQUENCE = ("doc", "test", "script", "feat", "fix", "close")
OPTIONAL_STAGES = frozenset({"script"})
```

### 受影响的硬编码点

| 位置 | 现状 | 改法 |
|------|------|------|
| `stage.STAGE_SEQUENCE` | 5 元组 | 插入 `script` |
| `stage.STAGE_PREFIX` | 无 `script` | 加 `"script": "script"` |
| `stage._PREFIX_TO_STAGE` | 无 `script` | 加 `"script"` |
| `stage._subject_prefix` | 硬编码 4 前缀 | 改从 `STAGE_PREFIX` 派生 |
| `check.STAGES` | 4 元组 | 加 `script` |
| `check._PIPELINE` | 4 元组 | 加 `script` |
| `check` 的 `missing-stage` | 只查 `test`/`fix` | **不变**（`script` 可选，不查） |
| `parser` 两处 `choices` | 硬编码 | 改为从 `STAGE_SEQUENCE` 派生 |

### `missing-stage` 的口径

`script` **可选**，因此：

- `missing-stage` 仍只查 `("test", "fix")`，**不因缺 `script` 告警**；
- 但若**出现过 `script`**，则它必须位于 `test` 之后、`feat` 之前
  （由 `stage-order` 兜底，`_PIPELINE` 加进 `script` 即自动生效）。

## 接口

```python
# pdev/stage.py
STAGE_SEQUENCE = ("doc", "test", "script", "feat", "fix", "close")
OPTIONAL_STAGES = frozenset({"script"})
STAGE_PREFIX = {..., "script": "script"}
_PREFIX_TO_STAGE = {..., "script": "script"}

def next_stages(current): ...
    """可选阶段多放行一跳：test → script|feat。"""

def _subject_prefix(subject): ...
    """从 STAGE_PREFIX 的值集合派生，不再硬编码。"""

# pdev/check.py
STAGES = ("doc", "test", "script", "feat", "fix")   # classify_stage 识别
_PIPELINE = ("doc", "test", "script", "feat", "fix")  # 顺序判定

# pdev/cli/parser.py
choices=list(STAGE_SEQUENCE)   # feat commit 与 stage-review 两处
```

## 日志

- 不新增日志。

## 兜底

- **既有 feat 的游标**（如 `feat`/`close`）→ `_index` 仍有效，不受插入影响。
- **旧数据推断**（`infer_stage`）→ `_PREFIX_TO_STAGE` 增 `script`，
  旧 commit 无 `script(` 前缀 → 推断结果不变。
- **`stage-order`**：`_PIPELINE` 加 `script` 后，`feat` 后出现 `script`
  会被判倒退（正确）。
- **`script` 停留在原地** → 允许（同其他阶段）。
- **从未提交过 `script`** → 一切正常，与旧流程等价。

## 实现与校验结果（收尾）

**在 close 阶段补写**。
