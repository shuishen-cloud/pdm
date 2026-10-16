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

登记一条 feat。**八项设计字段必填**（缺一报错，退出码 2）；`--api`/`--log`/
`--fallback` 均可重复，应写成能直接照着实现的真实内容。

| 参数 | 必填 | 说明 |
|------|:---:|------|
| `-t, --title` | ✔ | 一句话标题 |
| `-k, --kind` | | `feat`/`fix`/`refactor`/`doc`/`test`（默认 `feat`） |
| `--doc PATH` | | 设计正文路径（如 `feat/token-cache.md`） |
| `--design-note TEXT` | ✔ | 设计思路（为什么这么做） |
| `--impl-note TEXT` | ✔ | 实现方式（怎么落地） |
| `--data-model TEXT` | ✔ | 核心数据结构（可重复） |
| `--sample TEXT` | ✔ | 样例数据＝结构的实例，**非用法**（可重复） |
| `--change TEXT` | ✔ | 对既有代码的改动，`文件::符号 —— 说明`（可重复） |
| `--test-note TEXT` | ✔ | 测试方式（没有写「无：原因」） |
| `--impact TEXT` | ✔ | 对现有系统的影响 |
| `--importance S` | ✔ | `critical`/`high`/`medium`/`low` |
| `--debug-note TEXT` | | 调试方式（选填） |
| `--extend-note TEXT` | | 如何扩展（选填） |
| `--api SIG` | | 接口签名（可重复） |
| `--log TEXT` | | 会打什么日志（可重复） |
| `--fallback TEXT` | | 异常兜底（可重复） |

- 必填**允许填“无”，但必须说明**：`--sample "无：纯计算无外部数据"`。
- 新建后可随时用 **`pdm feat edit`** 修改（唯一的字段修改入口）。
- `samples` 语义：`data_model` 记类型（`Cache: dict[str,int]`），
  `samples` 记实例（`{"k": 1}`）；**不是**命令行用法。
- `changes` 每条应定位到符号：`pdev/feat.py::Feat.comments —— 新增字段`。

```bash
pdm feat new token-cache --title "token 缓存层" \
    --doc feat/token-cache.md \
    --design-note "缓存层隔离后端抖动，避免调用方写重试" \
    --impl-note "dict + 过期时间戳，读时懒过期" \
    --data-model "TokenCache: dict[str, tuple[str, float]] —— key→(值, 过期时刻)" \
    --sample '{"t1": ("abc", 1730000000.0)}' \
    --change "pdev/auth.py::TokenCache —— 新增类" \
    --api "TokenCache.get(key) -> Optional[str]" \
    --api "TokenCache.put(key, val, ttl) -> None" \
    --log "缓存命中/未命中时记录 key" \
    --fallback "Redis 不可用降级为直连" \
    --test-note "pytest tests/test_auth.py::test_cache_hit" \
    --impact "新增类，不改既有调用链" \
    --importance high
```

### `pdm feat list [--status S] [--kind K] [--open]`

### `pdm feat show <slug> [--doc] [--notes] [--verify] [--json] [--debug]`

看 feat 详情；`--doc` 打印设计正文，`--notes`/`--verify` 附关联笔记。

### **`pdm feat edit <slug> [选项]`** —— 编辑字段（**唯一的修改入口**）

不带任何修改参数时 = 预览当前字段值。

| 形式 | 作用 |
|------|------|
| `--add-<f> VALUE` | 列表字段追加一条（`api`/`logs`/`fallbacks`/`data_model`/`samples`/`changes`） |
| `--set-<f> VALUE` | 列表字段整体替换 |
| `--remove-<f> IDX` | 删除第 IDX 条（**从 0 起**） |
| `--<field> VALUE` | 单值字段覆盖（`title`/`doc`/`design_note`/`impl_note`/`test_note`/`debug_note`/`extend_note`/`impact`/`importance`） |

```bash
pdm feat edit token-cache --add-change "pdev/x.py::Cache —— 新增缓存类"
pdm feat edit token-cache --remove-change 1
pdm feat edit token-cache --importance high     # critical/high/medium/low
```

**改内容 = 撤销该条审查**：编辑可审项（如 `changes:0`）后，
它的 `[审]` 位自动撤销（审查是对已定稿内容的确认）。

**不允许改**：`status`（用 `feat set`）、`stage`（用 `feat commit`）、
`slug`（是文件名）。

### `pdm feat set <slug> <status>`

推进 `FeatStatus`（单向，不能倒退）：
`draft → testing → integrated → fixing → closed`。

### `pdm feat link <slug> <commit>` / `pdm feat unlink <slug> <commit>`

手动串联/解除 commit（`feat commit` 会自动 link，一般不需要手动）。

### **`pdm feat commit <stage> <slug> -m <msg> [选项]`** —— 阶段提交门面

由 pdm 创建 commit，强制顺序。**首选这个，不要用 git commit。**

流水线：`doc → test → script → feat → fix → close`（`script` 可选，可跳过）。

| 参数 | 说明 |
|------|------|
| `<stage>` | `doc`/`test`/`script`/`feat`/`fix`/`close` 之一 |
| `-m, --message` | **必填**，自动加 `<prefix>(<slug>): ` 前缀 |
| `--body` | 提交正文 |
| `--files PATH` | 只提交这些路径，可重复；新文件自动 `git add` |
| `--close` | `close` 阶段同时置 `closed` |
| `--no-verify` | 跳过 pre-commit 钩子 |
| `--dry-run` | 只预演，不真正提交 |

阶段与生成的前缀：

```
doc    → doc(<slug>): ...
test   → test(<slug>): ...
script → script(<slug>): ...   # 可选：可跳过直达 feat
feat   → feat(<slug>): ...
fix    → fix(<slug>): ...
close  → doc(<slug>): ...   # 收尾 doc，前缀仍是 doc(
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
| `status-skipped` | error | 状态推进跳跃（非线性） |
| `orphan-commit` | warning | git 里有 commit 未被任何 feat 认领 |
| `stage-prefix` | warning | commit 前缀不是 doc/test/script/feat/fix |
| `stage-order` | warning | 阶段倒退（如 feat 后 test） |
| `missing-stage` | warning | closed 的 feat 缺 test/fix（**不查 script**） |
| `commit-no-note` | warning | feat/fix 提交无笔记 |
| `note-no-verify` | warning | 笔记均未绑定验证 |
| `review-none` | warning | 完全无人工审查记录 |
| `review-low` | warning | 人工审查覆盖率过低 |
| `missing-fields` | warning | 五项必填字段有缺（历史豁免） |
| `vague-change` | warning | `changes` 没定位到符号（无 `::`） |
| `empty-sample` | warning | `samples` 过于敷衍（短/占位词） |
| `stage-unreviewed` | warning | 进入下一阶段但上一阶段未审 |

退出码：有 error → 1；`--strict` 时 warning 也 → 1。

### `pdm feat found <slug> <text>`

记录 fix 阶段发现的异常。

### `pdm feat review <slug> [--item KEY] [--all] [--by WHO] [--cmd CMD] [--status S]`

逐项人工审查 / 测试勾选（`[审][测]` 双勾选位，**可独立**）。可审项 =
`api`/`logs`/`fallbacks`/`data_model`/`samples`/`changes` 的每一条。

| 参数 | 说明 |
|------|------|
| `--item KEY` | 可审项键：`api:0` / `logs:1` / `doc`，或字段前缀 `api`（匹配整片） |
| `--all` | 作用于该 feat 全部可审项 |
| `--by WHO` | 审查者（默认取配置 `default_author`） |
| `--cmd CMD` | `--test` 时登记实际执行的命令 |
| `--status` | `--test` 时结果：`passed`/`failed`/`error`（默认 `passed`） |
| 动作（四选一） | `--review` 置 [审] / `--unreview` 清 [审] / `--test` 置 [测] / `--untest` 清 [测] |

```bash
pdm feat review token-cache                       # 列出可审项与 [审][测] 状态
pdm feat review token-cache --item api:0 --review --by human:lwy
pdm feat review token-cache --item api:0 --test --cmd "pytest tests/test_token.py"
pdm feat review token-cache --all --review        # 整条一次勾完
```

### `pdm feat comment <slug> --on KEY [-m TEXT | --clear]`

条目级人工评论（人手写，可留空）。`--on` 指定对象（`api:0` / `logs:1` /
`doc`）。**缺 `-m` 则查看**，空串则清除；`--clear` 显式清除（与 `-m` 互斥）。

```bash
pdm feat comment token-cache --on api:0 -m "接口保持最小，不做泛化"
pdm feat comment token-cache --on api:0            # 只看该条评论
```

### `pdm feat stage-review <slug> [stage] [--by WHO] [--note TEXT] [--clear] [--list]`

阶段级人工审核：进入下一阶段前要求**上一阶段已审**。

| 参数 | 说明 |
|------|------|
| `<stage>` | 要标记已审的阶段（`doc`/`test`/`script`/`feat`/`fix`/`close`） |
| `--by WHO` | 审核人（**必须 `human:` 前缀**，否则拒绝） |
| `--note TEXT` | 审核备注 |
| `--clear` | 撤销该阶段的审核 |
| `--list` | 列出各阶段审核状态 |

- 门禁默认**只告警**（`check` 报 `stage-unreviewed`）；
  开 `config.stage_review.enabled=true` 后 `feat commit` **硬阻断**。
- 只查**上一个**阶段，不回溯全部前序。
- 历史 feat（`created_at` 早于 `FIELDS_SINCE`）默认也报；
  用 `--loose-history` 或配置 `feat.loose_history=true` 放过。

```bash
pdm feat stage-review token-cache doc --by human:lwy
pdm feat stage-review token-cache --list
```

---

## pdm ui / pdm theme

- `pdm ui [store]` —— 仿 lazygit 的 TUI。
- `pdm theme [name]` —— 查看/设置主题（写入用户配置）。

## pdm review —— 掌握程度

汇总全部 feat 的可审项，算「项目代码掌握程度」，覆盖率过低告警（退出码 1）。

| 参数 | 说明 |
|------|------|
| `--unreviewed` | 只列未人工审查的可审项 |
| `--untested` | 只列未测试通过的可审项（与 `--unreviewed` 同给取交集） |
