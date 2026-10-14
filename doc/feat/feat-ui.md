# Feat 界面重构（feat-ui）

> 先于实现编写，作为界面实现的指导。

## 动机

当前 `FeatScreen` 只显示 feat 列表与详情，看不到"闭环走到哪一步"，
且不展示该 feat 下的笔记。目标是让 Feat 界面成为**开发纪律的驾驶舱**。

## 布局

```
┌ Feat ─────────────────────────────────────────────────┐
│ 左：feat 列表          中：详情            右：阶段     │
│ ● slug  状态 ×N        doc/api/logs        ①doc ✓     │
│                        fallbacks/discovered ②test ✓    │
│                                            ③feat ✓    │
│                                            ④fix ✓     │
│                                            ⑤doc ✓     │
│                        ── 笔记 ──                       │
│                        · [bug] xxx                    │
└───────────────────────────────────────────────────────┘
```

## 阶段闭环显示（核心）

从 `feat.commits` 的提交信息前缀推导 5 个阶段，用符号标出完成情况：

| 阶段 | 前缀 | 未完成 | 完成 |
|------|------|--------|------|
| ① doc  | `doc(`  | `○` | `●` |
| ② test | `test(` | `○` | `●` |
| ③ feat | `feat(` | `○` | `●` |
| ④ fix  | `fix(`  | `○` | `●` |
| ⑤ doc  | `doc(`  | `○` | `●` |

推导复用 `pdev.check.classify_stage`。

## 与笔记的关系

Feat 详情下方展示关联的笔记（按 `commit` 匹配 `NoteStore`）。
解决"提交不带笔记"的可见性问题：**看不到就是没记**。

## 接口

```python
def stage_progress(feat: Feat, git) -> List[Tuple[str, bool]]
    """返回 [("doc", True), ("test", True), ...] 五阶段完成情况"""

def notes_for_feat(feat: Feat, note_store) -> List[CommitNote]
    """该 feat 关联 commit 上的全部笔记"""
```

## 日志

- 打开界面时记录 feat 数量（沿用现有约定，TUI 不打日志）

## 兜底

- git 不可用 → 阶段全部显示 `?`，不崩
- 无 commit → 五阶段均未完成
- 无关联笔记 → 显示"（该 feat 暂无笔记）"

## 实现与校验结果（收尾）

实现于 760c012，修复于 8d84a9b。

### 界面效果

```
feat-ui  [feat / closed]
阶段  ●① 设计 ●② 测试 ●③ 实现 ○④ 修复 ○⑤ 收尾
设计文档  docs/feat/feat-ui.md
...
关联笔记
  · pitfall ×1  pitch
  · difficulty ×1
```

阶段闭环从 `feat.commits` 的提交信息前缀推导，一眼看出流程走到哪一步。

### 为什么此前提交不带笔记

根因：`pdm` 的 **note 与 feat 是两套独立记录**，
`git commit` 不会自动触发 `pdm note add`，Agent 也只用了 feat、忘了 note。
本条 feat 已实际为 3 个关键 commit 补上笔记（difficulty / pitfall / bug）。

对应 feat: feat-ui
