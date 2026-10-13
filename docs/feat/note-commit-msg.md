# note 显示 commit message（note-commit-msg）

> 先于实现编写，作为实现指导。

## 动机

`pdm note list` 只显示 `commit=8d84a9b`，看不到这次提交干了什么；
作为"约束与检索工具"，检索时缺少一半上下文。

## 原则

**commit message 不存进笔记文件**——它属于 git，rebase/amend 后会变。
一律通过 `pdev/git.py` 运行时查询，无重复存储、无过期风险。

## 命令变更

| 命令 | 现状 | 变更 |
|------|------|------|
| `pdm note list` | 平铺每条笔记 | **按 commit 分组**，message 每组只出现一次 |
| `pdm show <commit>` | 只有笔记 | 顶部加 commit 标题 + 作者/时间 |
| `pdm note add` | 不变 | 不变（不加 --from-head） |

## 输出排版（采用 B：按 commit 分组）

```
★ 8d84a9b  fix(tui): 修正 notes_for_feat 短串误匹配
    ○ [BUG    ] 短 commit 前缀匹配笔记会串号
        pdev/tui/screens.py  #feats

★ 760c012  feat(tui): Feat 界面显示阶段闭环与关联笔记
    ! [PITFALL] commit 未 link 到 feat 时阶段显示全空
    · [PROBLEM] Feat 详情要聚合三处数据源
```

- 无 git / 查不到 subject → 回退到原来的平铺格式，不报错

## 接口

```python
def group_by_commit(notes) -> List[Tuple[str, List[CommitNote]]]
    """按 commit 分组，保持首次出现顺序"""

def print_notes(notes, *, as_json, color, out=None, infos=None)
    """infos: {commit: CommitInfo}；有则分组显示 message，无则平铺"""
```

## 日志

- TUI 不打日志（沿用约定）

## 兜底

- git 不可用 → 平铺（原行为）
- 某 commit 查不到 subject → 该组只显示 hash
- `--json` 不变（仍是笔记数组，不含 message）
