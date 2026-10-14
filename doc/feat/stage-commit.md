# 阶段提交门面（stage-commit）

> 先于实现编写。把「doc → test → feat → fix → doc」的**顺序**从
> 事后审计升级为**提交前强制**：提交由 pdm 创建，不再手敲 git。

## 问题

现有 `check_stages` 用 `set` 收集阶段，只校验 test/fix 是否**出现过**：

- 顺序完全没检查（`feat` 之后又 `test` 也放过）；
- 收尾 `doc` 与开头 `doc` 无法区分；
- 违规只能**提交后**由 `pdm feat check` 发现，拦不住。

根因：提交是 Git 做的，pdm 只事后认领 hash，天然缺失时序与刹车点。

## 规范

一条 feat 的生命周期是一条**单向阶段流水线**：

```
doc → test → feat → fix → doc(收尾)
```

- 每个阶段由 `pdm feat commit <stage> <slug> -m <msg>` 创建一次 git commit，
  pdm 同时自动 `link_commit`，并推进阶段游标。
- 阶段必须**按序推进**：只能前进到「下一个允许的阶段」，或**停留在当前
  阶段重复提交**（如连续两次 `fix(`）。
- 回退（feat 之后又 test）由 pdm **在提交前直接拒绝**（退出码 2），
  不产生 commit。

| 阶段 | 前缀 | 允许进入的条件 |
|------|------|----------------|
| `doc`   | `doc(`   | 首阶段，或已到收尾位（feat/fix 之后） |
| `test`  | `test(`  | 已过 `doc` |
| `feat`  | `feat(`  | 已过 `test` |
| `fix`   | `fix(`   | 已过 `feat` |
| `close` | `doc(`   | 已过 `fix`（收尾 doc，可用 `--close` 同时关闭） |

游标存于 `Feat.stage`（新字段，缺省由历史 commit 推断，兼容旧数据）。

## 提交信息

pdm 生成的首行固定为：

```
<stage>(<slug>): <message>
```

与 `stage-prefix.md` 的 `classify_stage` 对齐，`check` 能直接识别。

## 接口

```python
# pdev/stage.py
STAGE_SEQUENCE = ("doc", "test", "feat", "fix", "close")

class StageError(ValueError): ...

def next_stages(current: str | None) -> list[str]
    """当前阶段下允许进入的下一阶段（含停留在当前）。"""

def infer_stage(commits: list[str], git) -> str | None
    """由已关联 commit 的前缀推断当前所处阶段。"""

def commit_stage(git_runner, feat, stage, message, *, allow_close) -> str
    """校验顺序 -> git commit -> 返回 hash（调用方负责 link）。"""
```

```python
# FeatStore
def commit_stage(slug, stage, message, git, *, cwd) -> Feat
    """在 FeatStore 上封装：校验 + 真正提交 + link + 更新 stage 游标。"""
```

## 日志

- 拒绝时打印：当前阶段、允许的阶段、你请求的阶段。
- 成功时打印新 commit 短 hash 与阶段迁移（如 `doc → test`）。

## 兜底

- **非 git 仓库**：拒绝提交，提示先 `git init`（不静默降级，因为门面的
  全部价值就是提交）。
- git 命令失败：原样返回 stderr，退出码非 0，**不更新** stage 游标。
- 旧数据无 `stage` 字段：用 `infer_stage` 从 commit 前缀推断；推断不出
  视为首阶段，允许 `doc`。
- `--dry-run`：只打印将执行的提交信息与阶段迁移，不真正提交。
- `--no-verify`：跳过 pre-commit 钩子（透传 `git commit --no-verify`）。

## 与 check 的关系

`pdm feat check` 保留，作为**兜底**：门面拦得住新提交，check 负责扫描
历史欠账与绕过门面的提交。新增 `stage-order` 规则（顺序式）与既有
`missing-stage`（集合式）并存。
