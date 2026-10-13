# 提交阶段前缀校验（stage-prefix）

> 先于实现编写。约束"开发纪律"本身：Feat 的 commit 必须体现
> doc → test → feat → fix → doc 的阶段。

## 问题

Feat 已经能把 commit 串联起来，但**没人检查这些 commit 是否走完了流程**。
实际发生过：`modal-keys` 只有 `doc` + `feat` 两个提交，
`test` 与 `fix` 被塞进了 `feat`，收尾 `doc` 缺失——纪律形同虚设。

## 规范

一条 feat 关联的 commit，其信息前缀应体现阶段：

| 阶段 | 前缀 |
|------|------|
| ① doc  | `doc(`
| ② test | `test(`
| ③ feat | `feat(`
| ④ fix  | `fix(`
| ⑤ doc  | `doc(` |

## 校验规则

| code | level | 规则 |
|------|-------|------|
| `stage-prefix` | warning | commit 前缀不是上述之一 |
| `missing-stage` | warning | closed 的 feat 缺少 test 或 fix 阶段 |

`missing-stage` 只在 status == closed 时检查。历史归档（kind == `doc`，
如 bootstrap）豁免，不强制 test/fix 阶段。

## 接口

```python
def classify_stage(subject: str) -> Optional[str]
    """从 commit 信息前缀识别阶段：doc/test/feat/fix/other，识别不出返回 None"""

def check_stages(feat: Feat, git, exempt: bool = False) -> List[CheckIssue]
```

## 日志

- 识别不出阶段时记录 commit hash 与 subject 前缀

## 兜底

- git 不可用 → 跳过（复用现有 `git.available` 判断）
- commit 查不到 subject → 记 `stage-prefix` warning，不崩
- kind == `doc`（历史归档）→ 跳过 `missing-stage`
