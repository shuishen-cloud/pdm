# Feat 自约束校验

让 pdev 能检查自己的流程是否合规，从"记账本"变成"护栏"。

## 是什么

`pdm feat check` 扫描所有 Feat 及其关联的 commit，报告**状态与事实不符**、
**覆盖缺口**、**关联冲突**等问题。

## 校验规则

| code | level | 规则 |
|------|-------|------|
| draft-has-commit | warning | draft 却已串了 commit |
| closed-no-commit | error | closed 却没串任何 commit |
| empty-doc | warning | 没有 doc 路径 |
| no-api | warning | 没有 api |
| no-fallback | warning | 没有 fallbacks |
| discovered-not-closed | warning | 有 discovered 但未 closed |
| commit-conflict | error | 同一 commit 被多个 feat 认领 |
| commit-missing | error | commit 在 git 里不存在 |
| status-skipped | warning | 状态跳步 |
| orphan-commit | warning | git 里有 commit 未被任何 feat 认领 |
| commit-no-note | warning | `feat(` / `fix(` 提交没有笔记（需 note_store） |
| note-no-verify | warning | 该 commit 的笔记全部未绑定验证（需 note_store） |

## 与 git 的关系

`commit-missing` 与 `orphan-commit` 复用 `pdev/git.py` 的 `GitRepo`；
非 git 仓库时自动跳过这两条，不报错。

`commit-no-note` 与 `note-no-verify` 复用 `pdev.store.NoteStore`；
调用方未传 `note_store` 时自动跳过（向后兼容）。

## 退出码

- 0：无 error（有 warning 也算通过）
- 1：有 error；`--strict` 时 warning 也导致 1
