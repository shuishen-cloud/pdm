# PDM 数据结构与字段总览（现状快照）

> 导出时间：2026-10-14，分支 `feat/web-ui`
> 目的：供重新设计时对照。**本文档只描述"现状"，不评判好坏。**
> 各节末尾的「⚠️ 观察」是导出时发现的事实（非建议），供设计时参考。

---

## 0. 全局约定

| 概念 | 约定 |
|------|------|
| **Actor** | `<kind>:<name>` 字符串，如 `human:lwy` / `ai:claude` / `ci` |
| **commit** | 笔记用短 hash（7~8 位），feat 存完整 40 位；比较时做前缀互匹配（≥6 位） |
| **时间** | ISO8601 带时区，UTC（`_now() = datetime.now(timezone.utc)`） |
| **存储** | 本地 JSON，一实体一文件；`index.json` 是可重建的派生缓存 |

### 存储布局

```
.pdm/
├── notes/
│   ├── index.json            # 派生缓存（count/by_kind/by_status/by_issue/commits）
│   └── by-commit/<hash>.json # 一 commit 一文件，原子写
├── feats/
│   └── by-id/<slug>.json     # 一 feat 一文件
└── docs/                     # 若 doc.dir 指向此（默认指 doc/）
doc/feat/<slug>.md            # 设计正文（默认位置，随代码跟踪）
```

---

## 1. 笔记域 CommitNote

挂在某个 commit 上的一条开发记录。**一篇笔记 = 一次提交里的一件事。**

```jsonc
{
  "commit": "df56554d",          // 关联提交（必填）
  "kind": "pitfall",             // 类型（见下表，必填）
  "title": "一句话摘要",          // 必填
  "detail": "详细描述",           // 可空
  "author": "ai:claude",         // Actor；默认 human:unknown
  "files": ["tests/x.py"],       // 涉及文件，可空
  "severity": "medium",          // low/medium/high/critical，可空
  "status": "noted",             // open/resolved/noted
  "catches": [],                 // controlled-exception 捕获的异常类名
  "verifications": [ ... ],      // 见 §2
  "issue_id": null,              // 升级成的 Issue ID
  "resolves": [],                // 解决了哪些 Issue
  "tags": ["web", "test"],
  "created_at": "2026-10-14T12:44:15+00:00"
}
```

### NoteKind 取值

| 值 | 含义 | 归为 | 派生属性 |
|----|------|------|---------|
| `problem` | 问题 | 资产 | `is_asset` |
| `difficulty` | 难点 | 资产 | `is_asset` |
| `pitfall` | 易错点 | 资产 | `is_asset` |
| `controlled-exception` | 可控异常（已捕获） | 资产 | `is_asset` |
| `bug` | 缺陷 | **负债** | `is_debt` |

**核心二分**：`is_debt`（需限期修复）vs `is_asset`（沉淀的领域知识）。

### NoteStatus 取值

| 值 | 含义 |
|----|------|
| `open` | 还没解决 |
| `resolved` | 已解决 |
| `noted` | 只是记一笔，无需解决（**默认**） |

### 派生属性（不存储，计算得出）

| 属性 | 判据 |
|------|------|
| `promotes_issue` | `issue_id` 非空 |
| `resolves_issue` | `resolves` 非空 |
| `unresolved` | `status == open` |
| `written_by_ai` | `author.is_ai` |
| `is_controlled_exception` | `kind == controlled-exception` |

> ⚠️ **观察**：`unresolved` 的判据只看了 `status`，与 `promotes_issue` 无关；
> 但 `stats.risky` 的定义是"`open` 且从未升级为 Issue"。两处口径需对齐确认。

---

## 2. 验证 Verification

绑在笔记上的一条可执行验证。**三种形态。**

```jsonc
{
  "kind": "test",                // test / command / manual
  "target": "tests/x.py::test_y",// test 的用例标识
  "command": "",                 // 显式命令；test 可省略自动拼
  "method": "验证思路（一句话）",
  "script": "",                  // 内联脚本，优先于从 target 抽取
  "expected": "passed",          // 期望结果说明
  "note": "",                    // 补充说明
  "cwd": "",                     // 工作目录（相对 git.repo）

  // --- 执行状态（verify run 回写）---
  "last_run_at": "2026-10-14T20:50:01+08:00",
  "last_status": "passed",       // unknown/passed/failed/error/skipped
  "last_output": "..."
}
```

### VerificationKind

| 值 | 含义 | `runnable` |
|----|------|:---:|
| `test` | 绑定测试用例 | ✅ |
| `command` | 任意命令 | ✅ |
| `manual` | 人工步骤 | ❌ |

### VerificationStatus

`unknown`（默认）/ `passed` / `failed` / `error`（命令本身出错）/ `skipped`（人工未执行）

### 派生

- `effective_command`：`command` 优先；否则 test 自动拼 `pytest <target> -q`
- CLI `--verify` 语法：`test=<用例>` / `cmd=<命令>` / `manual=<步骤>`，
  可加 `;method=...;expected=...;note=...`

> ⚠️ **观察**：`target` 与 `command` 职责有重叠（target 描述"是什么"，
> command 描述"怎么跑"），但 test 形态下二者都会参与拼命令。

---

## 3. Feat（开发记录）

一次功能开发，**横跨多个 commit**。是"流程"的载体。

```jsonc
{
  "slug": "review-query",        // 唯一标识；小写/数字/连字符
  "title": "列出未审查 / 未测试项",
  "kind": "feat",                // feat/fix/refactor/doc/test
  "status": "closed",            // draft/testing/integrated/fixing/closed
  "doc": "feat/review-query.md", // 设计正文路径（相对 doc.dir）

  // --- 规格三栏 ---
  "api": ["unreviewed_items(feats, *, tested=False) -> List[tuple]"],
  "logs": ["不新增日志；清单直接打印"],
  "fallbacks": ["无 feat -> 打印提示，退出码 0"],

  // --- 五项设计字段（新 feat 必填）---
  "design_note": "设计思路（为什么这么做）",
  "impl_note": "实现方式（怎么落地）",
  "data_model": ["结构: 类型 —— 说明"],
  "samples": ["该结构的真实实例"],
  "changes": ["文件::符号 —— 说明"],

  // --- 关联 ---
  "commits": ["完整40位hash", ...],
  "notes": [],                   // ⚠️ 见下方观察
  "discovered": ["fix 阶段发现的异常"],

  // --- 阶段游标 ---
  "stage": "close",              // doc/test/script/feat/fix/close/null

  // --- 审查（键空间 = 可审项）---
  "reviews": { "api:0": { ...ReviewItem } },
  "comments": { "api:0": "人写的评论" },

  // --- 阶段审核（键空间 = 阶段）---
  "stage_reviews": { "doc": { ...StageReview } },

  "created_at": "...",
  "updated_at": "..."
}
```

### FeatKind

`feat` / `fix` / `refactor` / `doc` / `test`

### FeatStatus（流程里程碑，单向）

| 值 | order | 含义 |
|----|:---:|------|
| `draft` | 0 | doc 阶段：设计规格已定 |
| `testing` | 1 | 按 doc 写测试 |
| `integrated` | 2 | 已模块化接入系统 |
| `fixing` | 3 | Code Review / 修 Bug 中 |
| `closed` | 4 | 完成，异常已回填 |

**由 `pdm feat set` 推进，`advance()` 禁止倒退。**

### stage（提交阶段游标，与 status 独立）

`doc` → `test` → `script`（可选）→ `feat` → `fix` → `close`

**由 `pdm feat commit` 强制顺序，提交前拒绝乱序。**

> ⚠️ **观察（重要）**：`status` 与 `stage` 是**两套并行机制**，
> 但 21 条 feat 呈现 `(closed, close)` 的同步关系。设计上明确写了
> "二者独立"，实际常同步。是否冗余需设计时定夺。

### Feat.notes 字段

> ⚠️ **观察（事实）**：39 条 feat 中 `notes` **全部为空**。
> 真实笔记关联走 `commit hash`（`featview.notes_for_feat`）。
> 该字段仅被 `commands.py` 的一处读取，且空段被过滤，**无实际作用**。

### 必填字段校验

`_REQUIRED_FIELDS` = `design_note` / `impl_note` / `data_model` / `samples` / `changes`

**只在 `pdm feat new` 时强制（退出码 2）**；`check` 中为 warning 且**历史豁免**。

### 可审项（review_items 的展开规则）

```python
_REVIEW_FIELDS = ("api", "logs", "fallbacks",
                  "data_model", "samples", "changes")
```

- `doc` 非空时产生一项 `key="doc"`
- 每个字段的每个元素产生 `key="<field>:<index>"`，如 `api:0`
- 空字段 / 空列表**不产生**可审项

---

## 4. 审查项 ReviewItem

一个可审项的**双勾选位**记录。**只有被操作过的 key 才落盘。**

```jsonc
{
  "reviewed": true,              // [审] 人工已看
  "reviewed_by": "human:lwy",
  "reviewed_at": "...",
  "tested": false,               // [测] 测试通过
  "test_command": "",
  "test_status": "",
  "tested_at": null
}
```

### 规则

- `reviewed` 与 `tested` **互相独立**，不蕴含
- `is_empty`（两位都清）→ 从 dict 移除（`_prune`），保持 JSON 精简

### 条目评论 comments

`{key: str}`，**与 reviews 共用同一 key 空间**（都是可审项 key）。

> ⚠️ **观察（耦合）**：`reviews` 与 `comments` 的 key 同源
> （都由 `review_items()` 决定）。`doc` 路径一改，key 变化，
> **两个 dict 的旧 key 同时变孤儿**。

---

## 5. 阶段审核 StageReview

一个**阶段**的人工审核记录。**键空间是不同的维度（阶段名，非可审项）。**

```jsonc
{
  "by": "human:lwy",
  "at": "...",
  "note": "审核备注"
}
```

存于 `Feat.stage_reviews: {doc: {...}, test: {...}}`。

### 门禁语义

进入阶段 T 前，要求 **T 的前一个阶段**已审：

| 进入 | 要求已审 |
|------|---------|
| `test` | `doc` |
| `feat` | `test` |
| `fix` | `feat` |
| `close` | `fix` |

- 首次进入（`doc`）无前序，不要求
- 只查**上一个**阶段，不回溯全部前序
- `config.stage_review.enabled`（默认 false）为真时 `feat commit` 硬阻断；
  否则仅 `check` 告警
- `require_human`（默认 true）：审核人必须是 `human:` 前缀

> ⚠️ **观察（耦合）**：`reviews` / `comments` / `stage_reviews` 三者
> 都叫 "review"，但 `stage_reviews` 的 key 是**阶段**而非**可审项**，
> 语义与另外两个**完全不同维度**，却存放在同一 Feat 内。

---

## 6. Issue（问题流程）

> ⚠️ **观察**：完整定义在 `pdev/issue.py`，但**当前无独立 CLI 子命令**
> （`pdm issue ...` 不存在）。仅通过笔记的 `issue_id` / `resolves` 软引用。

```jsonc
{
  "id": "0001",
  "title": "登录超时",
  "status": "open",              // open/in_progress/blocked/resolved/closed
  "priority": "medium",          // low/medium/high/critical

  "reporter": "human:lwy",       // 谁报的
  "origin_commit": "a1b2c3d",    // 产生问题的 commit（溯源）
  "origin_fingerprint": "ai:100%",// 该 commit 的来源指纹
  "fix_commit": "def456",
  "verified_by": "human:lwy",    // 或 test:unit / 空=unverified

  "external": {                  // GitHub 锚点（可空）
    "repo": "owner/name", "number": 12,
    "etag": "", "last_synced_at": null
  },
  "sync": { "direction": "push", "state": "synced",
            "local_rev": 0, "remote_rev": 0 },

  "tags": [],
  "created_at": "...", "updated_at": "...",
  "body": "...",
  "events": [ { "at": "...", "type": "note", "actor": "...", "text": "" } ]
}
```

### 派生

- `caused_by_ai`：`origin_fingerprint.is_ai`
- `reported_by_ai`：`reporter.is_ai`
- 指标：`ai_cause_rate = ai_caused / total`

### EventType

`note` / `gh-comment` / `gh-close` / `gh-open` / `push`

### SyncState

`synced` / `dirty` / `conflict`

---

## 7. 代码来源指纹 Fingerprint

附加在 **commit message trailer** 上，用于统计 AI 代码问题率。

```
Assisted-by: ai:claude-opus-4 | human:lwy | mixed
Generated-by: ai:100% | ai:partial | human
Reviewed-by: human:lwy | (空 = 未审)
Explainability: yes | no
Issue: 0001
```

| 字段 | 取值 | 派生 |
|------|------|------|
| `assisted_by` | 自由文本 | — |
| `generated_by` | `ai:100%` / `ai:partial` / `human` | `is_ai_generated` / `fully_ai_generated` |
| `reviewed_by` | Actor 或空 | `reviewed`（human 才算） |
| `explainability` | `yes` / `no` | `explainable` |
| `issue` | Issue ID | — |

**`risky` 判据**：不可解释，**或**（完全 AI 生成 且 未审）

---

## 8. 文档版本（Manifest / Version / Cover）

> ⚠️ **观察**：定义在 `pdev/doc.py`，**当前无独立 CLI 入口**。
> 设计意图是检测"文档漂移"（代码改了但文档没改）。

```jsonc
// docs/<module>/manifest.yaml
{
  "module": "auth",
  "current": "v2",
  "versions": [
    {
      "id": "v2",
      "file": "auth-v2.md",
      "from_commit": "abc1234",
      "to_commit": "HEAD",       // HEAD 表示仍为当前
      "created_at": "...",
      "reason": "接口变更",
      "trigger": "interface-change",
      "doc_origin": "human",     // ai:100%/ai:partial/human
      "reviewed_by": "human:lwy",
      "explainability": "yes",
      "status": "current",       // current/superseded/archived
      "covers": {
        "paths": ["src/auth/**"],// glob，gitignore 风格
        "symbols": ["TokenCache.refresh"]
      }
    }
  ]
}
```

### Trigger（为何新建版本）

| 值 | 必须新建版本？ |
|----|:---:|
| `interface-change` | ✅ |
| `data-model-change` | ✅ |
| `core-flow-change` | ✅ |
| `invariant-change` | ✅ |
| `detail-update` | ❌ 可原地改 |
| `doc-fix` | ❌ |

**漂移判据**：`to_commit..HEAD` 之间有 diff 且触及 `covers.symbols` → 漂移。

---

## 9. 配置 Config

```jsonc
{
  "store": ".pdm/notes",         // 笔记存储目录
  "default_author": "human:unknown",
  "color": true,
  "json_output": false,
  "editor": "",

  "git":   { "repo": ".", "auto_commit": false },
  "note":  { "default_status": "noted", "require_detail": false },
  "query": { "default_limit": null },
  "issue": { "store": "issues" },
  "doc":   { "dir": "doc" },     // 设计文档根目录（相对路径）

  "feat": {
    "store": ".pdm/feats",
    "view": {                    // TUI 展示开关
      "doc_body": false, "notes_detail": false, "verify": true,
      "specs": true, "notes_grouped": true, "doc_max_lines": 0
    }
  },

  "review": {                    // 覆盖率告警阈值
    "min_coverage": 0.6,
    "warn_no_review": true, "warn_untested": true
  },
  "stage_review": {              // 阶段门禁
    "enabled": false, "require_human": true
  },

  "ui": { "theme": "catppuccin-macchiato",
          "commit_width": 0, "show_footer": true },

  "github": { "repo": "", "token": "", "auto_push": false }
}
```

**优先级**：`CLI > PDM_* 环境变量 > .pdm.json > ~/.config/pdm/config.json > 默认`

---

## 10. 校验与汇总结构

### CheckIssue

```jsonc
{
  "slug": "web-ui",        // 哪个 feat；全局问题用 "" 或 "(仓库)"
  "code": "review-low",    // 规则代号
  "level": "warning",      // error | warning
  "message": "人话描述"
}
```

**21 个 code**：`draft-has-commit` `closed-no-commit` `empty-doc` `no-api`
`no-fallback` `discovered-not-closed` `commit-conflict` `commit-missing`
`status-skipped` `orphan-commit` `stage-prefix` `stage-order` `missing-stage`
`commit-no-note` `note-no-verify` `review-none` `review-low` `missing-fields`
`vague-change` `empty-sample` `stage-unreviewed`

### 审查评分（两套并存）

| | `check.py::_check_review` | `review.py::compute_review` |
|---|---|---|
| 覆盖率算法 | `reviewed / items` | `reviewed / items` |
| 告警码 | `review-none` / `review-low` | `no-review` / `low-review` |
| 阈值来源 | `min_coverage` 参数 | `ReviewPolicy.min_coverage` |
| 分档 | 无 | `LEVELS`: excellent/good/.../poor |
| 汇总 | 逐 feat | 跨 feat 聚合 |

> ⚠️ **观察（冗余）**：同一套覆盖率逻辑**实现了两遍**，连告警码命名都不同。

### NoteStats（笔记汇总）

`total` / `by_kind` / `open` / `promoted` / `resolved` / `written_by_ai` /
`risky` / `commits` / `files` / `bugs` / `bugs_open` /
`controlled_exceptions` / `caught_types` / `verified_notes` / `verifications` /
`verification_passed` / `verification_failed` / `needs_verification`

---

## 附：三组"看似重叠"的字段

重新设计时最需要澄清的三处：

### ① `status` ↔ `stage`

- `status`（draft→closed）：**里程碑**，`feat set` 推进
- `stage`（doc→close）：**提交游标**，`feat commit` 强制顺序
- 现状：21 条 feat 呈现同步（closed ↔ close）

### ② `api` ↔ `data_model` ↔ `samples`

- `api`：接口签名（`文件::符号(参数) -> 返回`）
- `data_model`：数据结构定义（`类型: 结构 —— 说明`）
- `samples`：**该结构的真实实例**（非用法、非签名）
- 现状：边界模糊，`samples` 曾被填成 CLI 用法（已在 `feat-fields-check` 记录）

### ③ `reviews` ↔ `comments` ↔ `stage_reviews`

- `reviews` / `comments`：key = **可审项**（`api:0`）
- `stage_reviews`：key = **阶段**（`doc`）
- 现状：三者同名 "review"，但维度不同

---

## 附：全部 Enum 速查

| Enum | 取值 |
|------|------|
| `NoteKind` | problem / difficulty / pitfall / controlled-exception / bug |
| `NoteStatus` | open / resolved / noted |
| `VerificationKind` | test / command / manual |
| `VerificationStatus` | unknown / passed / failed / error / skipped |
| `FeatKind` | feat / fix / refactor / doc / test |
| `FeatStatus` | draft / testing / integrated / fixing / closed |
| `IssueStatus` | open / in_progress / blocked / resolved / closed |
| `Priority` | low / medium / high / critical |
| `EventType` | note / gh-comment / gh-close / gh-open / push |
| `SyncState` | synced / dirty / conflict |
| `Generated` | ai:100% / ai:partial / human |
| `Trigger` | interface-change / data-model-change / core-flow-change / invariant-change / detail-update / doc-fix |
| `VersionStatus` | current / superseded / archived |

---

## 附：阶段流水线

```
doc → test → script（可选）→ feat → fix → close
```

| 阶段 | commit 前缀 | 必须 |
|------|-----------|:---:|
| doc | `doc(<slug>):` | ✅ 首 |
| test | `test(<slug>):` | ✅ |
| script | `script(<slug>):` | 可选 |
| feat | `feat(<slug>):` | ✅ |
| fix | `fix(<slug>):` | 视需要 |
| close | `doc(<slug>):` | ✅ 尾 |

中性前缀（不参与阶段判定）：`refactor` `init` `chore` `style` `perf`
`build` `ci`
