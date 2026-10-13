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

## 纪律：note 随 commit 即时记录

每个 commit 完成后**立即**记录它的 note，而不是事后回头补：

```bash
git commit -m "test(feat-x): ..."        # 1. 先提交
pdm note add <刚提交的 hash> -k ... -t ... # 2. 立刻记这一步的坑/难点
```

**为什么不能事后回填**：

- note 的价值在于**开发当下的真实记录**（踩了什么坑、卡在哪、怎么绕）,
  事后回忆会丢细节，且 `created_at` 会与 commit 时间严重脱节。
- 「回头补 note」这个动作**本身又是一个 commit**,那个 commit 又需要再补——
  陷入无限套娃（本仓库真实发生过：`dac9538` → `d042b67` → …）。
- 与「看不到就是没记」（见 `feat-ui.md`）同源：提交当时不记，就等于没记。

**判定滞后**：`pdm query` 里看 `created_at` 与 `git log` 的 commit 时间，
若普遍晚于 commit，说明在事后回填。
