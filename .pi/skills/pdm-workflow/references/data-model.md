# 数据结构与设计思想

## 三类数据，靠 commit 连接

```
笔记 CommitNote ──┐
                  ├── commit hash ── 同一把钥匙
Feat ─────────────┘
                  └── Feat.doc → 设计文档（快照）
```

- **笔记**：记录（发生了什么）。一个 commit 可有零到多条。
- **Feat**：流程（要解决什么）。一条 feat 横跨多个 commit（阶段流水线）。
- **Doc**：快照（当前逻辑是什么）。外置 Markdown，Feat 只存路径。

三者不做额外的关系层，`commit hash` 就是外键。所有数据本地存储、git 友好。

## CommitNote（笔记）

```python
CommitNote(
    commit="abc123",
    kind=NoteKind.PITFALL,       # problem/difficulty/pitfall/controlled-exception/bug
    title="token 刷新有竞态",
    detail="...",
    author=Actor("human:lwy"),   # 或 ai:claude
    files=["src/auth/token.py"],
    tags=["auth"], severity=Priority.HIGH,
    status=NoteStatus.OPEN,      # open/resolved/noted
    catches=[],                  # controlled-exception 捕获的异常类型
    verifications=[              # 可执行的验证
        Verification(kind=TEST, target="tests/x.py::test_y",
                     method="200 并发断言只刷新一次", expected="passed"),
    ],
    issue_id=None, resolves=[],  # 与 Issue 的双向关联
)
```

状态标记：`·` noted（记一笔） / `○` open（未解决） / `●` resolved（已解决）。

## Feat（开发记录）

```python
Feat(
    slug="stage-commit",
    title="阶段提交门面",
    kind=FeatKind.FEAT,          # feat/fix/refactor/doc/test
    status=FeatStatus.DRAFT,     # draft→testing→integrated→fixing→closed
    doc="feat/stage-commit.md",  # 设计正文路径
    api=[...], logs=[...], fallbacks=[...],   # 三栏规格
    commits=[...],               # 关联的 commit
    notes=[...], discovered=[...],
    stage="close",               # 阶段提交游标（doc→test→feat→fix→close）
)
```

**两个独立的"阶段"概念，别混淆：**

| 维度 | 字段 | 取值 | 谁推进 |
|------|------|------|--------|
| 流程状态 | `status` | draft/testing/integrated/fixing/closed | `pdm feat set` |
| 提交阶段 | `stage` | doc/test/feat/fix/close | `pdm feat commit` |

`status` 是粗粒度里程碑（单向），`stage` 是提交前缀游标（由 `feat commit`
强制顺序）。二者协作：`close` 阶段可用 `--close` 同时置 `status=closed`。

## Issue（流程）

```jsonc
{
  "id": "0001", "title": "登录超时",
  "status": "open|in_progress|blocked|resolved|closed",
  "priority": "low|medium|high|critical",
  "reporter": "human:lwy|ai:claude|ci",
  "origin_commit": "a1b2c3d",       // 产生问题的 commit
  "origin_fingerprint": "ai:100%",  // 该 commit 的来源指纹
  "fix_commit": "def456",
  "verified_by": "human:lwy|test:unit|unverified",
  "tags": [...], "body": "...", "events": [...]
}
```

笔记与 Issue 的连接靠 `CommitNote.issue_id`（升级）与
`CommitNote.resolves`（解决）。

## 代码来源指纹（commit trailer）

在 commit 里声明代码来源，用于统计 AI 代码 bug 率：

```
Assisted-by: ai:claude | human:lwy | mixed
Generated-by: ai:100% | ai:partial | human
Reviewed-by: human:lwy | (空 = 未审)
Explainability: yes | no
```

**风险项**：`Generated-by: ai:100%` 且 `Reviewed-by` 为空，或
`Explainability: no`。

## 文档版本

`docs/<module>/manifest.yaml` 记录每个版本的 `covers.paths` /
`covers.symbols`；`to_commit..HEAD` 之间有 diff 且触及 symbols → **漂移**。

## 派生指标（工具算，不存储）

- AI 代码 bug 率 = `origin_fingerprint` 含 ai 的 issue 数 / 全部 issue
- `stats.risky` = `open` 且从未升级为 Issue 的笔记数（记了坑没人管）
- 文档漂移、指纹风险项

## 存储布局

```
.pdm/                          # 默认 gitignore
├── notes/by-commit/<hash>.json  # 一 commit 一文件，原子写
├── notes/index.json             # 派生索引，可重建
├── feats/by-id/<slug>.json      # 一 feat 一文件，可 review
└── docs/feat/<slug>.md          # 设计正文
```

`by-commit` 的好处：写入原子、commit 即索引键、与 `git log` 对齐。损坏的
JSON 会被跳过，不影响其余数据。

## 设计取舍（理解这些能少踩坑）

- **commit message 不存进笔记**：它属于 git，rebase/amend 会变——一律运行时
  查 `git log`，无重复存储、无过期风险。
- **阶段顺序由提交门面强制，不靠自觉**：`pdm feat commit` 在提交前拦住
  乱序；`pdm feat check` 只做兜底扫描历史。
- **git 只读**：`pdev/git.py` 只 `git log`/`rev-parse`，唯一写操作是
  `pdm feat commit` 里的 `git commit`。
