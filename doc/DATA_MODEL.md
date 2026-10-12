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
