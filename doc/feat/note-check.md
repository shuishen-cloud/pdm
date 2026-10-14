# 笔记与验证自约束（note-check）

> 先于实现编写。把 `pdm feat check` 的护栏从「feat/commit」扩展到
> 「note（笔记）」与「verify（验证）」，堵住本轮暴露的两个盲区。

## 问题

现状 `pdev/check.py` **完全不引用 note / verify**（引用数为 0），
导致以下违规无人发现：

1. `feat(` / `fix(` 提交没记笔记 —— 违背「看不到就是没记」
2. 测试/实现提交的笔记**没有绑定可执行验证**（`verifications` 为空）
3. 绑定的验证从未跑过、或上次失败，也无告警

本轮 `feat-scroll` 的开发中，这三类问题**全部真实发生过**：
先提交后回填 note、测试 note 未绑 verify、verify 因环境问题失败。

## 新增两条规则

| code | level | 规则 |
|------|-------|------|
| `commit-no-note` | warning | `feat(` / `fix(` 前缀的 commit 没有对应笔记 |
| `note-no-verify` | warning | 该 commit 的笔记全部未绑定验证（`verifications` 全空） |

### `commit-no-note` 的判定

- 仅检查 **`feat(` / `fix(` 前缀**的 commit（`classify_stage` 可识别）；
  `doc(` / `test(` 提交豁免 —— 文档无需笔记，测试本身即验证。
- 该 commit 在 `NoteStore` 中查不到任何笔记（含短 hash 前缀互匹配）→ 告警。
- 需要 `NoteStore`；非 git 或无 note_store 时跳过。

### `note-no-verify` 的判定

- 对该 commit 的**每一条**笔记：若**全部笔记**的 `verifications` 均为空 → 告警。
- 只要有一条笔记绑定了验证，即视为通过（不要求每条都绑）。
- 目的是提醒「记了坑，却没登记怎么复现/验证」。

## 接口变更

`NoteStore` 需注入规则层：

```python
def check_one(store, slug, git=None, note_store=None) -> List[CheckIssue]
def check_feats(store, git=None, *, include_orphans=True,
                note_store=None) -> List[CheckIssue]
def _check_feat(feat, git, note_store=None) -> List[CheckIssue]
```

新增辅助：

```python
def _note_for(note_store, commit) -> List[CommitNote]
    """按 commit（前缀互匹配，≥6 位）取笔记"""

def check_notes(feat, git, note_store) -> List[CheckIssue]
    """commit-no-note / note-no-verify 两条规则"""
```

## CLI 变更

`cmd_feat_check` 把 `ctx.store`（NoteStore）传入 `check_*`。

## 日志

- 无（沿用「TUI/check 不打日志」约定）

## 兜底

- `note_store is None` → 两条规则整体跳过，不报错（保持向后兼容）
- git 不可用 → 跳过（无法读取 commit 前缀）
- 某 commit 查不到 → 跳过该 commit（`commit-missing` 已另行告警）
- note 的 commit 存任意长度短 hash → 用 ≥6 位前缀互匹配，避免短串误配

## 为何是 warning 而非 error

`feat(` 提交无笔记在**历史仓库**中大量存在（真实欠账）；
若定为 error 会让 `feat check` 对既有仓库一律退出码 1，过于激进。
沿用 `missing-stage` 的做法：warning 暴露欠账，`--strict` 才导致失败。

## 实现与校验结果（收尾）

实现于 commit 1ec71a9，测试于 3c4d4e3。

### 实现

- `check_one` / `check_feats` / `_check_feat` 新增 `note_store` 参数
- 新增 `check_notes(feat, git, note_store)` 与辅助 `_note_for()`
- `cmd_feat_check` 传入 `ctx.store`（NoteStore）

### 实测效果

上线后 `pdm feat check` 立即抓出历史真实欠账：

- **15+ 条 `commit-no-note`**：bootstrap / feat-check / tui-polish /
  feat-storage 等多个 `feat(` / `fix(` 提交确实没有笔记
- `feat-scroll` 的提交**未**告警 —— 因为它已被补过笔记，
  证明短 hash 前缀匹配与阶段豁免均工作正常

### 本次发现的异常

1. 两条新规则必须定为 **warning**：历史仓库普遍缺失笔记，
   定为 error 会让 `feat check` 对既有仓库一律退出码 1，
   规则反而被绕过（沿用 `missing-stage` 策略）。
2. `check.py` 原先完全不引用 note/verify，加规则必须先注入
   `NoteStore`，这是本次唯一的结构性改动点。
