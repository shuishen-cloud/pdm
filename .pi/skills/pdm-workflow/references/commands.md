# pdm 命令参考

所有命令通过 `./run.sh <cmd>` 或 `.venv/bin/pdm <cmd>` 执行。
`--json` / `--no-color` 是**顶层选项**，写在子命令**之前**。

## 全局选项

| 选项 | 说明 |
|------|------|
| `--store DIR` | 笔记存储目录（子命令前后皆可） |
| `--json` | JSON 输出（顶层，需在子命令前） |
| `--no-color` | 禁用彩色 |

环境变量：`PDM_STORE` `PDM_AUTHOR` `PDM_FEAT_STORE` `PDM_DOC_DIR`
`PDM_STORE` `PDM_NO_COLOR` `PDM_JSON` 等，优先级
`CLI > PDM_* > .pdm.json > ~/.config/pdm/config.json > 默认`。

---

## pdm note —— 记笔记

### `pdm note add <commit> -k <kind> -t <title> [选项]`

| 参数 | 说明 |
|------|------|
| `-k, --kind` | **必填**：`problem`/`difficulty`/`pitfall`/`controlled-exception`/`bug` |
| `-t, --title` | **必填**，一句话摘要 |
| `-d, --detail` | 详细描述 |
| `-F, --file` | 涉及文件，可重复 |
| `-c, --catches` | 可控异常捕获的异常类型（配合 `-k controlled-exception`） |
| `--verify` | 验证：`test=<用例>` / `cmd=<命令>` / `manual=<步骤>`，可重复；可加 `;method=...;expected=...` |
| `-T, --tag` | 标签，可重复 |
| `-p, --priority` | `low`/`medium`/`high`/`critical` |
| `--status` | `open`/`resolved`/`noted`（默认 `noted`） |
| `-i, --issue` | 升级成的 Issue ID |
| `-r, --resolve` | 该笔记解决了哪个 Issue，可重复 |
| `-a, --author` | `lwy`→`human:lwy`；`ai:claude` 保持原样 |
| `--no-time` | 不记录当前时间 |

```bash
pdm note add abc123 -k pitfall -t "token 刷新有竞态" \
    -d "并发刷新会写出旧 token" -F src/auth/token.py -T auth -p high \
    --verify 'test=tests/test_token.py::test_refresh;method=200 并发断言只刷新一次;expected=passed'
```

### `pdm note list` / `pdm query`

`note list` 与 `query` 完全等价。组合条件：

| 参数 | 说明 |
|------|------|
| `-k, --kind` | 按类型 |
| `-s, --status` | 按状态 |
| `-f, --file` | 按文件，支持 glob（如 `'src/auth/**'`） |
| `-T, --tag` | 按标签 |
| `-x, --text` | 全文搜索（标题/详情/标签） |
| `-C, --commit` | 按提交 |
| `-i, --issue` | 按关联 Issue（升级+解决） |
| `-a, --author` | 按作者种类（如 `ai`） |
| `-n, --limit` | 最多返回条数 |

---

## pdm show <commit>

看某次提交的全部笔记（顶部显示 commit 标题/作者/时间）。

## pdm verify —— 验证

| 命令 | 作用 |
|------|------|
| `pdm verify list` | 列出全部验证条目 |
| `pdm verify show <commit>` | 展开笔记 + 验证详情 + 关联测试脚本源码 |
| `pdm verify run [commit]` | 执行验证并回写结果（`last_status`） |

`--verify` 的三种形式：

- `test=tests/x.py::test_y` —— pytest 用例
- `cmd=make check` —— 任意命令
- `manual=重建集群后登录三次` —— 人工步骤

## pdm stats

总览：总数、覆盖提交/文件、未解决、已升级、已解决、AI 撰写、**风险项**
（`open` 且从未升级为 Issue）。

---

## pdm feat —— 开发记录

### `pdm feat new <slug> --title T [--doc PATH] [--api SIG] [--log TEXT] [--fallback TEXT]`

登记一条 feat。`--api`/`--log`/`--fallback` 均可重复，应写成能直接照着
实现的真实内容。

```bash
pdm feat new token-cache --title "token 缓存层" \
    --doc feat/token-cache.md \
    --api "TokenCache.get(key) -> Optional[str]" \
    --api "TokenCache.put(key, val, ttl) -> None" \
    --log "缓存命中/未命中时记录 key" \
    --fallback "Redis 不可用降级为直连"
```

### `pdm feat list [--status S] [--kind K] [--open]`

### `pdm feat show <slug> [--doc] [--notes] [--verify] [--json] [--debug]`

看 feat 详情；`--doc` 打印设计正文，`--notes`/`--verify` 附关联笔记。

### `pdm feat set <slug> <status>`

推进 `FeatStatus`（单向，不能倒退）：
`draft → testing → integrated → fixing → closed`。

### `pdm feat link <slug> <commit>` / `pdm feat unlink <slug> <commit>`

手动串联/解除 commit（`feat commit` 会自动 link，一般不需要手动）。

### **`pdm feat commit <stage> <slug> -m <msg> [选项]`** —— 阶段提交门面

由 pdm 创建 commit，强制顺序。**首选这个，不要用 git commit。**

| 参数 | 说明 |
|------|------|
| `<stage>` | `doc`/`test`/`feat`/`fix`/`close` 之一 |
| `-m, --message` | **必填**，自动加 `<prefix>(<slug>): ` 前缀 |
| `--body` | 提交正文 |
| `--files PATH` | 只提交这些路径，可重复；新文件自动 `git add` |
| `--close` | `close` 阶段同时置 `closed` |
| `--no-verify` | 跳过 pre-commit 钩子 |
| `--dry-run` | 只预演，不真正提交 |

阶段与生成的前缀：

```
doc   → doc(<slug>): ...
test  → test(<slug>): ...
feat  → feat(<slug>): ...
fix   → fix(<slug>): ...
close → doc(<slug>): ...   # 收尾 doc，前缀仍是 doc(
```

顺序非法（如 feat 后 test）直接拒绝并返回退出码 2，**不产生 commit**。
旧数据无游标时从已有 commit 前缀自动推断。

### `pdm feat check [slug] [--strict] [--json]`

自约束校验。规则（`code` → level）：

| code | level | 含义 |
|------|-------|------|
| `draft-has-commit` | warning | draft 却已串 commit |
| `closed-no-commit` | error | closed 却没串 commit |
| `empty-doc` / `no-api` / `no-fallback` | warning | 字段缺失 |
| `discovered-not-closed` | warning | 有异常但未 closed |
| `commit-conflict` | error | 同一 commit 被多个 feat 认领 |
| `commit-missing` | error | commit 在 git 中不存在 |
| `orphan-commit` | warning | git 里有 commit 未被任何 feat 认领 |
| `stage-prefix` | warning | commit 前缀不是 doc/test/feat/fix |
| `stage-order` | warning | 阶段倒退（如 feat 后 test） |
| `missing-stage` | warning | closed 的 feat 缺 test/fix |
| `commit-no-note` | warning | feat/fix 提交无笔记 |
| `note-no-verify` | warning | 笔记均未绑定验证 |

退出码：有 error → 1；`--strict` 时 warning 也 → 1。

### `pdm feat found <slug> <text>`

记录 fix 阶段发现的异常。

---

## pdm ui / pdm theme

- `pdm ui [store]` —— 仿 lazygit 的 TUI。
- `pdm theme [name]` —— 查看/设置主题（写入用户配置）。
