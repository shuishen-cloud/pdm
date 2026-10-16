# feat edit 命令 + 新设计字段 + 严格度开关（feat-edit-fields）

> 先于实现编写。本 feat 补三处缺口，它们共同支撑后续的
> 「Feat 详情页 Design/Review 分标签」界面（见 `tui-feat-design`）。

## 问题

### 1. 字段只能新建时设置，无法编辑

```
$ pdm feat new --help
  --design-note / --impl-note / --data-model / --sample / --change
$ pdm feat edit --help
  （无此命令）
```

`pdm feat` 有 `new / list / show / set / link / commit / unlink / check /
found / review / comment / stage-review`，**唯独没有 `edit`**。

后果：`--change` 写错格式（缺 `::`）后无法修正，只能手改
`.pdm/feats/by-id/<slug>.json`；而 `.pdm/` 在 `.gitignore` 里，
**修正只存在于本地**，别人 clone 看不到。这在本仓库已多次发生。

### 2. 设计标签页需要的五项数据不存在

界面（`tui-feat-design`）要展示：设计 / 实现方式 / **测试方式** /
**调试方式** / 数据结构 / 样例值 / **对系统的影响** / **如何扩展** /
**重要性**。

对照现有字段：

| 界面要展示 | 现有 | 状态 |
|-----------|------|------|
| 设计 | `design_note` | ✅ |
| 实现方式 | `impl_note` | ✅ |
| 数据结构 | `data_model` | ✅ |
| 样例值 | `samples` | ✅ |
| 对系统的影响 | `changes`（只记"改了哪个符号"） | ⚠️ 语义不同 |
| 测试方式 | — | ❌ |
| 调试方式 | — | ❌ |
| 如何扩展 | — | ❌ |
| 重要性 | — | ❌ |

另注：`pdev/feat.py` 的 `_LEGACY_IGNORED` 里有 `debug` / `fixtures`，
说明历史上曾有过类似字段后被废弃——本次是**重新引入并明确语义**。

### 3. 严格度不可配、字段审查不告警

- 现有 `pdev/check.py::_fields_enforced` 用**时间切点**
  `FIELDS_SINCE = "2026-10-14T11:16:00+00:00"` 自动豁免历史 feat。
  用户无法控制：既不能让历史 feat 也受约束，也不能一键放过。
- 现有审查类规则只有 `review-none`（完全没审）/ `review-low`
  （覆盖率低），**不报"某个具体字段没被审"**。

## 规范

### 一、`pdm feat edit <slug>`

**只有 `edit` 能改字段**；`status` / `stage` / `slug` **不允许**改
（分别由 `feat set` / `feat commit` 管；`slug` 是文件名，改了要重命名）。

| 形式 | 作用 | 适用 |
|------|------|------|
| `--add-<field> VALUE` | 追加一条 | 列表字段（`api`/`logs`/`fallbacks`/`data_model`/`samples`/`changes`） |
| `--remove-<field> IDX` | 删除第 IDX 条 | 同上，索引从 **0** 起 |
| `--set-<field> VALUE` | 整体替换（可多次） | 同上 |
| `--<field> VALUE` | 覆盖 | 单值字段（`title`/`doc`/`design_note`/`impl_note`/新增四项） |
| 不带修改参数 | 打印当前字段值 | 预览 |

示例：

```bash
pdm feat edit token-cache --add-change "pdev/x.py::Cache —— 新增缓存类"
pdm feat edit token-cache --remove-change 1
pdm feat edit token-cache --set-api "run(x) -> int"
pdm feat edit token-cache --importance high
pdm feat edit token-cache --debug-note "断点打在 parse() 入口"
```

#### 改内容 = 撤销该条审查

**规范**：编辑**可审项**（`api:0`、`changes:1` 等）的内容后，该条的
`[审]` 位**自动撤销**，并打印提示。

理由：审查是对**已定稿内容**的确认；内容变了，旧确认不再成立。
不改审查位的字段（`title`/`design_note` 等整块文本）只更新
`updated_at`。

### 二、五个新字段

| 字段 | 类型 | `feat new` 必填 | 说明 |
|------|------|:---:|------|
| `test_note` | `str` | **是** | 测试方式（怎么验证的） |
| `impact` | `str` | **是** | 对现有系统的影响 |
| `importance` | `FeatImportance` | **是** | 重要性枚举 |
| `debug_note` | `str` | 否 | 调试方式 |
| `extend_note` | `str` | 否 | 如何扩展 |

必填三项的理由：测试方式缺失的功能不该立项（与项目"先写测试"一致）；
影响面是决策依据；重要性填一个词成本极低。
选填两项：不是每个改动都有运行时行为或扩展点。

**允许"无"但必须写明**（沿用 `feat-fields` 约定）：
`--debug-note "无：纯配改，无运行时行为"`。

`importance` 取值（枚举，单一真相）：

```python
class FeatImportance(str, Enum):
    CRITICAL = "critical"   # 关键
    HIGH = "high"           # 高
    MEDIUM = "medium"       # 中
    LOW = "low"             # 低
```

`impact` 与 `changes` 的区别：`changes` 是**改动清单**
（`文件::符号 —— 说明`，逐条），`impact` 是**影响面叙述**
（这次改动对既有行为/兼容性/数据的影响）。两者并存，不替代。

### 三、严格度开关

**新 feat 永远严格**（与开关无关）：

- `feat new` 缺必填字段 → 报错退出码 2；
- `feat check` 缺字段 → `missing-fields` 告警；
- 字段未被 `[审]` 勾选 → **新增 `missing-review` 告警**。

**历史 feat** 由开关决定：

```jsonc
// .pdm.json（项目级，随 git 走）
{ "feat": { "loose_history": false } }
```

| `loose_history` | 历史 feat 的缺字段/未审查 |
|---|---|
| `false`（默认） | 一律告警 |
| `true` | **不告警**（放过） |

CLI 可临时覆盖：`pdm feat check --loose-history`。

**"历史"的判据**：沿用现有时间切点 `FIELDS_SINCE`（feat 创建时间），
即 `_fields_enforced` 的判据保留，只是从"自动豁免"改为"由开关决定
是否报"。

### 新增 check 规则

```
missing-review   某可审项未被 [审] 勾选（warning）
```

与现有规则的边界：

| 规则 | 含义 | 关系 |
|------|------|------|
| `review-none` | **完全**没有任何可审项被审 | 已有，保留 |
| `review-low` | 审查覆盖率低于阈值 | 已有，保留 |
| `missing-review` | **逐个**列出未审的可审项 | **新增** |

### 四、整块文本字段纳入可审项（行为变更）

`doc/feat/feat-fields.md` 当初刻意把 `design_note` / `impl_note`
排除在 `review_items()` 之外（理由：“整块文本，不进可审项”）。

本 feat **改变这一决定**：把设计类整块文本改为**可审项**，
使 Review 页能对它们逐项勾审（用户需求：“在 Review 页面添加
对其的审核”）。

| 字段 | key | 是否可审 |
|------|-----|:---:|
| `design_note` | `design_note` | ✅ 新纳入 |
| `impl_note` | `impl_note` | ✅ 新纳入 |
| `test_note` | `test_note` | ✅ |
| `debug_note` | `debug_note` | ✅（非空时） |
| `extend_note` | `extend_note` | ✅（非空时） |
| `impact` | `impact` | ✅ |
| `importance` | `importance` | ✅ |

规则：**非空的整块文本字段各产生一个可审项**（key = 字段名），
值为空则不产生（与 `doc` 的处理一致）。

影响：现有 feat 的可审项数量会上升（新增 2~5 项），
审查覆盖率分母变大——这是**有意为之**（本来就应该审设计）。

## 接口

```python
# pdev/feat.py

class FeatImportance(str, Enum):
    CRITICAL = "critical"; HIGH = "high"; MEDIUM = "medium"; LOW = "low"

@dataclass
class Feat:
    test_note: str = ""
    debug_note: str = ""
    extend_note: str = ""
    impact: str = ""
    importance: Optional[FeatImportance] = None

    def missing_required_fields(self) -> List[str]:
        """扩展：含 test_note / impact / importance。"""

    def set_list_field(self, name: str, values: List[str]) -> None:
        """整体替换某个列表字段。"""

    def set_text_field(self, name: str, value: str) -> None:
        """覆盖某个单值字段。"""

# pdev/cli/commands.py
def cmd_feat_edit(ctx, args) -> int:
    """编辑 feat 字段。返回 0/2。"""

# pdev/check.py
def _fields_enforced(feat, loose: bool) -> bool:
    """是否约束该 feat 的字段（loose=true 时历史 feat 不约束）。"""

def _check_missing_review(feat) -> List[CheckIssue]:
    """missing-review：逐个列出未审的可审项。"""

# pdev/config.py
@dataclass
class FeatConfig:
    loose_history: bool = False
```

## 日志

- 编辑成功：`已修改 <slug>：<字段>（<动作>）`；撤销审查时追加
  `（已撤销 changes:1 的审查）`
- 预览（无修改参数）：直接打印各字段当前值
- 非法输入：stderr 提示 + 退出码 2

## 兜底

| 情况 | 处理 |
|------|------|
| `slug` 不存在 | 返回 2，提示可用 slug |
| `--remove-<f> IDX` 越界 | 返回 2，提示该字段条数 |
| `--importance` 非法值 | 返回 2，列出合法取值 |
| 既无修改参数 | 视为预览，打印当前值，返回 0 |
| 配置读不到 | 按**严格模式**（安全默认，不静默放宽） |
| 旧 JSON 无新字段 | `_from_dict` 取默认值，不报错 |

## 验证方法

```
test=tests/test_feat_edit.py::test_add_change_appends
test=tests/test_feat_edit.py::test_remove_change_by_index
test=tests/test_feat_edit.py::test_remove_index_out_of_range
test=tests/test_feat_edit.py::test_edit_reviewable_revokes_review
test=tests/test_feat_edit.py::test_edit_text_field_keeps_review
test=tests/test_feat_edit.py::test_edit_rejects_bad_importance
test=tests/test_feat_edit.py::test_preview_without_changes
test=tests/test_feat_edit.py::test_new_requires_new_fields
test=tests/test_check.py::test_missing_review_reports_each_item
test=tests/test_check.py::test_loose_history_suppresses_old_feat
test=tests/test_check.py::test_strict_by_default
cmd=.venv/bin/pdm feat edit <slug> --debug-note "..." && pdm feat show <slug>
manual=改一个 changes 条目，确认原 [审] 被撤销
expected=字段更新且审查位撤销
```

## 实现与校验结果（收尾）

实现于 `798760dd`（test `5e086b92`、doc `8620d42e`）。
**状态：已闭环（closed）**。

### 交付物

| 文件 | 内容 |
|------|------|
| `pdev/feat.py` | `+FeatImportance`；`Feat` 新增 5 字段；`review_items` 纳入整块文本；`set_list_field`/`set_text_field`/`list_field` |
| `pdev/cli/parser.py` | `feat new` 新增 5 参数；`+feat edit` 子命令；`feat check --loose-history` |
| `pdev/cli/commands.py` | `+cmd_feat_edit`（唯一字段修改入口）、`+_revoke_*`、预览模式 |
| `pdev/check.py` | `_fields_enforced(feat, loose_history)`；`+_is_new_feat`；`+_check_missing_review` |
| `pdev/config.py` | `FeatConfig.loose_history` |
| `tests/test_feat_edit.py` | 24 例 |
| `.pi/skills/pdm-workflow/references/commands.md` | 补 `feat edit` 章节与新字段 |

**零新增依赖**。

### 实测（端到端）

| 场景 | 结果 |
|------|------|
| 缺必填 → `feat new` | ✅ 退出码 2，列出全部 8 项 |
| 勾审 `changes:0` | ✅ `[x][ ] changes:0`，审查 1/9 |
| **改内容 → 自动撤销审查** | ✅ 回到 0/9 |
| 整块文本纳入可审项 | ✅ `design_note`/`impl_note`/`test_note` 等可勾审 |
| `missing-review` | ✅ 逐个列出未审项 |
| `--loose-history` 对新 feat | ✅ **无影响**（永远严格） |
| **给本 feat 自己补字段** | ✅ `missing-fields` 告警消失 |

### fix 阶段回填的缺口

集成后发现**测试未覆盖“改自身已审的整块文本字段”**：
原测试只验了“改 `debug_note` 不影响 `api:0`”，
而未验“改 `design_note` 会撤销它自己的审查”——行为是对的
（`design_note` 已纳入可审项），但**无测试背”**。

补：`test_edit_own_text_field_revokes_its_review` 与
`test_edit_importance_revokes_its_review`。

### 本次发现的异常（已记笔记）

1. **改必填项会连带打爆一批既有测试**（difficulty/high）
   共 12 个失败，分“夹具要更新”与“断言刻画旧行为”两类。
2. **`Feat(**json_dict)` 不会把字符串转成枚举**（pitfall/medium）
   要用 `_from_dict()`（内含 `_importance_of` 容错转换）。

### 行为变更清单（影响既有 feat）

| 变更 | 影响 |
|------|------|
| 必填字段 5 → 8 | 新建时必须多填三项 |
| 可审项纳入整块文本 | 现有 feat 可审项 +2~5，覆盖率分母变大 |
| 历史豁免改为开关 | 默认严格；用 `loose_history` 放过 |
| `check_one`/`check_feats` 签名 +`loose_history` | 调用方需同步（已更新 `test_ledger` 台账） |

### 已知限制（有意不做）

- `edit` 不支持改 `status`/`stage`/`slug`（分别由 `set`/`commit` 管，
  `slug` 是文件名）。
- 不支持批量编辑多个 feat。
- 不提供交互式编辑（`$EDITOR`）—— 会离开事件循环，风险大于收益。
