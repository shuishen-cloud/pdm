# UI 偏好写用户配置（ui-prefs-user-config）

> 先于实现编写。修「切换主题后重启又变回去」的问题。

## 问题

`_persist_ui` 把 TUI 主题（`ui.theme`）写进**项目配置 `.pdm.json`**，
而 `.pdm.json` 是 **git 跟踪文件**。于是：

1. TUI 里 `t` / `T` 切换主题 → 写 `.pdm.json`
2. 之后任何 `git checkout` / `git stash` / 切分支 / `git restore` → `.pdm.json`
   被还原成 git 里的版本，主题选择丢失
3. 用户重启后主题"回到之前的"（被 git 覆盖）

## 目标

- **UI 偏好**（个人口味，不随项目走）写**用户配置** `~/.config/pdm/config.json`
- **团队共享配置**（`store` / `feat` / `doc` 等）仍写**项目 `.pdm.json`**
- 用户配置不进 git，主题持久化不再被冲掉

## 方案

`_persist_ui` 目前一律 `save_config(..., project_config=..., cwd=...)`，
要按 key 路由：

| key | 归属 | 写回目标 |
|-----|------|----------|
| `theme` | 个人偏好 | 用户配置 |
| `commit_width` | 个人偏好 | 用户配置 |
| `show_footer` | 个人偏好 | 用户配置 |

新增 `save_user_config(updates)`（或给 `save_config` 加 `target="user"`），
固定写 `~/.config/pdm/config.json`，**不写项目**。

优先级顺序不变：用户配置是「低优先」来源，但**TUI 改的就是它**——
下次 `load_config` 时用户配置的 `ui.theme` 会生效（除非项目显式覆盖）。

### 验证优先级不冲突

`load_config` 的合并顺序（低→高）：默认 → 用户 → 项目 → 环境 → CLI。
若项目 `.pdm.json` 也写了 `ui.theme`，会**盖过**用户配置。因此
`storage-layout` 之后项目 `.pdm.json` 里的 `ui.theme` 应**移除**
（它本就是个人偏好，不该在项目配置里）。

## 接口

```python
# pdev/config.py
def save_user_config(updates: Mapping[str, Any]) -> Path
    """把 updates 合并写入用户配置（~/.config/pdm/config.json）"""
```

`PDMApp._persist_ui(key, value)` 改为：UI 偏好 key → `save_user_config`。

## 兜底

- 用户目录不可写 → `notify` 警告，不影响使用（沿用现有 try/except）
- 用户配置不存在 → 创建
- 迁移：清掉项目 `.pdm.json` 里已有的 `ui` 段（搬去用户配置）

## 实现与校验结果（收尾）

实现于 60052ca，测试于 abf2cee。

### 落地结果

- 新增 `config.save_user_config()`（固定写用户配置，不碰项目）
- `_persist_ui` 改写用户配置
- 迁移：项目 `.pdm.json` 移除 `ui` 段，主题移入 `~/.config/pdm/config.json`
- 实测 `load_config` 仍读到 `textual-light`（读取链路正常）

### 验证

- 全量测试通过
- 切换主题后写用户配置，`git checkout` 不再影响主题

### 本次发现的异常

1. 根因是 UI 偏好写进了 **git 跟踪**的项目配置；
   修法是分文件——个人偏好→用户配置，团队配置→项目配置。
2. 改持久化目标后，旧测试 `test_cycle_theme_changes_and_persists`
   的断言目标也要改（否则按旧语义假绿）。
