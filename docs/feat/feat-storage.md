# Feat 存储

把 pdev 的开发流程（doc→test→feat→fix→doc）本身索引化，供 Agent 用命令检索，
不必扫描代码库。

## 是什么

Feat 是**一次开发的索引卡**，横跨多个 commit。它不存长正文，只做两件事：

- **约束**：这次开发的设计规格（接口签名 / 日志 / 兜底）
- **检索**：slug、状态、关联的 commit 与 note

## 为什么不是文档仓库

正文（设计与实现）放在本文件里，保持简短。Feat 只存 `doc` 路径。
这样文档由 AI/人维护，pdev 只管**规范化与检索**。

## 与 commit 的关系

一个 feat 通常对应多个 commit（doc→test→feat→fix→doc 各阶段）。
通过**手动** `pdm feat link <slug> <commit>` 串联，可 `unlink` 解除。
`FeatStore.by_commit()` 支持反向查询「这个 commit 属于哪个 feat」。

## 状态机

```
draft → testing → integrated → fixing → closed
```

不可倒退；每步带 `next_step` 提示下一步该做什么。
