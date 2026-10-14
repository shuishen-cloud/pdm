# 数据结构定义

三个数据源，全部本地、git 原生，本地为唯一真源。

## 1. 代码来源指纹（commit trailer）

```
Assisted-by: ai:claude-opus-4 | human:lwy | mixed
Generated-by: ai:100% | ai:partial | human
Reviewed-by: human:lwy | (空 = 未审)
Explainability: yes | no
Issue: 0001
```

## 2. Issue

```jsonc
// issues/0001-<slug>.md
{
  "id": "0001",
  "title": "登录超时问题",
  "status": "open | in_progress | blocked | resolved | closed",
  "priority": "low | medium | high | critical",

  // 溯源
  "reporter": "human:lwy | ai:claude | ai:review-bot | ci | tool",
  "origin_commit": "a1b2c3d",              // 关联的产生问题的 commit
  "origin_fingerprint": "ai:100%",          // 该 commit 的来源指纹
  "fix_commit": "def456",                   // 修复 commit（可空）
  "verified_by": "human:lwy | test:unit | unverified",

  // GitHub 锚点（可空）
  "external": {
    "github": {
      "repo": "user/repo",
      "number": 42,
      "etag": "W/\"abc\"",
      "last_synced_at": "2025-10-12T10:00:00Z"
    }
  },
  "sync": {
    "direction": "push",
    "state": "synced | dirty | conflict",
    "local_rev": 7,
    "remote_rev": 3
  },

  "tags": ["auth", "backend"],
  "created_at": "2025-10-12T10:00:00Z",
  "updated_at": "2025-10-13T10:00:00Z",
  "body": "问题描述（Markdown 正文）",
  "events": [                               // 事件日志（进展 / 同步 / 远端动作）
    { "at": "2025-10-12T11:00:00Z", "type": "note",       "actor": "human:lwy", "text": "复现成功" },
    { "at": "2025-10-13T09:00:00Z", "type": "gh-comment", "actor": "github:alice", "text": "我也遇到了" },
    { "at": "2025-10-13T10:00:00Z", "type": "gh-close",   "actor": "github:alice" }
  ]
}
```

## 3. 文档版本

```jsonc
// docs/<module>/manifest.yaml
{
  "module": "auth-flow",
  "current": "0003",
  "versions": [
    {
      "id": "0003",
      "file": "0003-token-cache.md",
      "from_commit": "abc123",
      "to_commit": "def456",              // HEAD 表示仍为当前
      "created_at": "2025-10-12T10:00:00Z",
      "reason": "added token cache layer", // 为什么新建而非修改
      "trigger": "interface-change | data-model-change | core-flow-change | invariant-change | detail-update | doc-fix",
      "doc_origin": "ai:100% | human | mixed",
      "reviewed_by": "human:lwy | (空 = 未审)",
      "explainability": "yes | no",
      "status": "current | superseded | archived",
      "covers": {                          // 漂移检测范围
        "paths": ["src/auth/**"],
        "symbols": ["AuthFlow.login", "AuthFlow.refreshToken"]
      }
    }
  ]
}
```

## 派生规则（工具负责计算，不存储）

- **文档漂移**：`covers.paths` 在 `to_commit..HEAD` 之间有 diff，且触及 `covers.symbols` → 漂移。
- **风险项**：`Generated-by: ai:100%` 且 `Reviewed-by` 为空，或 `Explainability: no`。
- **冲突**：`local_rev > 已同步的 local_rev` 且 `etag != 已同步的 etag`。
- **统计**：AI 代码 bug 率 = `origin_fingerprint` 含 ai 的 issue 数 / 全部 issue 数。

## 4. Feat（开发记录）

一条 feat 一个文件：`.pdm/feats/by-id/<slug>.json`。

```jsonc
{
  "slug": "token-cache",
  "title": "token 缓存层",
  "kind": "feat | fix | refactor | doc | test",
  "status": "draft | testing | integrated | fixing | closed",
  "stage": "doc | test | feat | fix | close | null",   // 阶段提交游标
  "doc": "feat/token-cache.md",                        // 正文外置（doc/<dir>）

  // 规格三栏
  "api":       ["TokenCache.get(key) -> Optional[str]"],
  "logs":      ["缓存未命中时记录 key 与回源耗时"],
  "fallbacks": ["Redis 不可用降级为直连 DB，记 warning"],

  // 五项设计字段（feat new 必填）
  "design_note": "热点 key 读多写少，加内存缓存即可",
  "impl_note":   "LRU dict + TTL 时间戳",
  "data_model":  ["Cache: dict[str, tuple[str, float]] —— key→(值, 过期时刻)"],
  "samples":     ["{\"tok-1\": (\"abc\", 1730000000.0)}"],
  "changes":     ["pdev/cache.py::TokenCache —— 新增类"],

  // 审查：只记录被操作过的 key（未操作不落盘）
  "reviews": {
    "api:0": {
      "reviewed": true, "reviewed_by": "human:lwy",
      "reviewed_at": "2025-10-14T10:00:00Z",
      "tested": true, "test_command": "pytest tests/test_cache.py",
      "test_status": "passed", "tested_at": "2025-10-14T10:01:00Z"
    }
  },
  // 条目级人工评论（可留空；空串即删除）
  "comments": { "api:0": "签名保持最小，不做泛化" },

  // 关联
  "commits":    ["a1b2c3d", "..."],
  "notes":      [],
  "discovered": [],                                    // fix 阶段发现的异常

  "created_at": "2025-10-14T09:00:00Z",
  "updated_at": "2025-10-14T11:00:00Z"
}
```

### 可审项 key 规范

由列表字段展开：`doc`（设计文档单项）、`api:i` / `logs:i` / `fallbacks:i` /
`data_model:i` / `samples:i` / `changes:i`（i 从 0 起）。
`reviews` 与 `comments` 共用这套 key；两项勾选位**互相独立**。

### 派生规则

- **人工审核覆盖率** = `reviewed 项数 / 全部可审项数`；
  **掌握程度** `score = 0.6 × 审核覆盖率 + 0.4 × 测试覆盖率`。
- **低覆盖告警**：覆盖率 < `review.min_coverage`（默认 0.6）。
- **孤儿记录**：key 对应的规格项已删除 → JSON 保留、不计入统计。
