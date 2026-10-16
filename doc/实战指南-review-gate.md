# 实战指南：用 pdm 流程开发一个新 Feat（review-gate）

> 这是**给人类照着敲的**操作指南：从登记 feat 到收尾闭环，
> 一步一个命令，附预期输出。
>
> 目标功能：**全局审查覆盖率门禁** —— 汇总全部 feat 的审查/测试数目，
> 低于阈值（默认 10%）时，在**开发下一步**（`pdm feat new`）时报警告。

## 0. 准备

确认环境（在仓库根目录）：

```bash
cd /home/lwy/project/ProjectDevelopManger
.venv/bin/pdm --help          # 能打印帮助即正常
.venv/bin/pdm feat list | head -3
```

看一眼当前覆盖率（本功能要管的就是它）：

```bash
.venv/bin/pdm review
```

预期（当前真实输出）：

```
掌握程度：poor  0.01 / 1.00
  可审项    563（来自 50 条 feat）
  人工审查  10  2%
  测试通过  2  0%
  告警
    ! [low-review] 人工审核覆盖率过低：2%（低于 60%）
```

## 1. 改动地图：这个功能要改哪几处

> **先看地图再登记**：`feat new` 的 `--change` 就是填写这份地图的地方，
> 不先搞清楚要动哪几处，那条字段只能瞎写。

### 功能拆成 4 处（按依赖顺序）

| # | 文件 | 位置 | 职责 |
|---|------|------|------|
| 1 | `pdev/review.py` | `compute_review` 旁边 | **新增纯函数** `gate_decision(score, threshold)`：算是否放行 + 警告文案 |
| 2 | `pdev/config.py` | `ReviewConfig`（约 155 行） | 新增 `gate_threshold: float = 0.10` |
| 3 | `pdev/cli/parser.py` | `fnew.add_argument(...)`（约 251 行起） | 新增 `--ignore-gate` 开关 |
| 4 | `pdev/cli/commands.py` | `cmd_feat_new`（约 508 行） | 创建 feat 前调用门禁，低覆盖率时 `print` 到 stderr |

### 调用链（读代码的路径，不需要“调试”）

```
pdm feat new
  → pdev/cli/parser.py        定义参数（251~287 行），
                             第 287 行 fnew.set_defaults(func=commands.cmd_feat_new)
  → pdev/cli/commands.py::cmd_feat_new（508 行）
      → 构造 Feat(...)
      → feat.missing_required_fields()   必填校验
      → _feat_store(ctx).add(feat)        落盘
  ← 返回 0（成）/ 2（参数错）
```

**要插入门禁的位置**：`missing_required_fields` 校验之后、`add(feat)` 之前。

### 可参照的现成实现

`pdev/cli/commands.py::cmd_review`（约 1596 行）已经在做
“取全部 feat → `compute_review` → 格式化输出”，你要的只是把同样的
逻辑搬到 `feat new` 里做一次检查：

```bash
# 看它怎么用 compute_review
grep -n "compute_review" -B 3 -A 8 pdev/cli/commands.py | sed -n '/1596/,/1620/p'

# 看你的目标函数长什么样
grep -n "def compute_review" -A 12 pdev/review.py

# 看 feat new 现有实现
grep -n "def cmd_feat_new" -A 40 pdev/cli/commands.py
```

### 这份地图的归宿

**写进 `--change`**（下一节的 `feat new` 命令里），之后随时可查：

```bash
.venv/bin/pdm feat show <slug>        # “对既有代码的改动”一节
.venv/bin/pdm feat edit <slug>        # 预览全部字段
```

这就是“设计落到代码中”的载体——`changes` 字段要求
`文件::符号 —— 说明` 格式，正是防止设计漂在文档里、找不到对应代码。

## 2. 调试：怎么亲眼看到执行轨迹

> 光看地图不够，想确认“命令到底走了哪些分支”，用调试器。
> 仓库已配好 `.vscode/launch.json`（随 git 走）。

### 一次性准备

```bash
.venv/bin/pip install debugpy          # 已装则可跳过
```

VSCode 里：**左下角选解释器** → `${workspaceFolder}/.venv/bin/python`。

### 可用的调试配置（`F5` 后选）

| 配置名 | 用途 |
|--------|------|
| `pdm <子命令>（改 args）` | **最常用**：改 `args` 就能调任意 pdm 命令 |
| `pdm feat new（新建 feat）` | 已填好八个必填字段，直接跑 `feat new` 全流程 |
| `pdm --help` | 看命令行入口 |
| `pytest 当前文件` | 调当前打开的测试文件 |
| `pytest 新 TUI 全部` | 跑 `tests/tui_new_to_fix/` |
| `TUI 新版（pdm ui --new）` | 调 TUI（需真终端，用 integratedTerminal） |
| `scripts/check_test_exit.py` | 调退出门禁脚本 |

### 断点位置（调试 `pdm feat new` 时）

按执行顺序打这三个：

| 顺序 | 行内位置 | 看什么 |
|:--:|----------|--------|
| 1 | `pdev/cli/parser.py:287` | `fnew.set_defaults(func=commands.cmd_feat_new)` —— 按 `F11` 进入实现 |
| 2 | `pdev/cli/commands.py:508` | `cmd_feat_new` 第一行 —— 看 `args` 里八个必填是否都在 |
| 3 | `pdev/cli/commands.py:533` | `missing = feat.missing_required_fields()` —— **你要插入门禁的位置就在附近**（校验之后、`add(feat)` 之前） |

> ⚠️ 行号会随代码变动漂移。**以函数名/代码特征为准**：
> 用 `grep -n "missing_required_fields" pdev/cli/commands.py` 重新定位。

### 你想加功能的观察点

```python
# pdev/review.py:91         compute_review 的第一行
#   → 看它的 feats 参数、返回值 s 的 total/reviewed/coverage

# pdev/cli/commands.py:1604  cmd_review 里调 compute_review 的地方
#   → 这是“参照实现”：它已在做“取全部 feat → 算覆盖率 → 格式化”
```

### 调试操作速查

| 键 | 作用 |
|----|------|
| `F5` | 启动 / 继续 |
| `F9` | 在当前行切换断点 |
| `F10` | 单步跳过 |
| `F11` | 单步进入（进函数） |
| `Shift+F11` | 跳出当前函数 |
| `Shift+F5` | 停止 |

变量面板在左侧，也可以在**调试控制台**里敲 `p feat`、`p args.design_note` 查看值。

### 不用 VSCode 的替代方案

```bash
# 命令行调试器
.venv/bin/python -m pdb main.py feat show feat-edit-fields
#   n=下一行  s=进入  c=继续  p <expr>=打印  q=退出

# 最粗暴：临时打印（记得删）
#   在 pdev/cli/commands.py::cmd_feat_new 里加：
#   print("DEBUG args:", vars(args), file=sys.stderr)
```

### 一个坑：debugpy 与 frozen modules

首次用 `debugpy` 可能看到：

```
Debugger warning: It seems that frozen modules are being used, which may
make the debugger miss breakpoints.
```

**症状**：断点不生效。**规避**：若遇到，把调试配置的 `program` 换成
用 `python -Xfrozen_modules=off` 包装，或改用 `pdb`。
（本仓库实测断点正常，仅作备注。）

## 3. 登记 feat（`pdm feat new`）

**八项字段全必填**（缺一即报错退出码 2）：

```bash
.venv/bin/pdm feat new review-gate \
    --title "全局审查覆盖率门禁：低于阈值时在开发下一步警告" \
    --doc feat/review-gate.md \
    --design-note "现在 pdm review 能算出全局覆盖率，但只会'事后报告'，不会拦截。结果是 563 个可审项只审了 2%，而新 feat 照常开工，债务持续累积。本 feat 把覆盖率变成'下一步的门槛'：新建 feat 时先汇总全部 feat 的审查/测试数目，低于阈值（默认 10%）就打印警告并提示如何补。之所以只在 new 时警告而不阻断：历史遗留的 2% 是既有事实，硬阻断会让所有人都无法开工。" \
    --impl-note "pdev/review.py 已有 compute_review 能算出全局 ReviewScore（含 total/reviewed/tested/coverage）。新增纯函数 gate_decision(score, threshold) 返回 (是否放行, 警告文本)；cmd_feat_new 在写入前调用它，低覆盖率时 print 到 stderr 但**仍继续创建**（退出码 0）。阈值可配：.pdm.json 的 review.gate_threshold，默认 0.10。CLI 加 --ignore-gate 可跳过检查。" \
    --data-model "GateDecision: dataclass(ok: bool, coverage: float, total: int, reviewed: int, tested: int, message: str)；ReviewPolicy 扩一个 gate_threshold: float = 0.10" \
    --sample '{"ok": false, "coverage": 0.02, "total": 563, "reviewed": 10, "tested": 2, "message": "全局审查覆盖率 2% 低于 10%"}' \
    --change "pdev/review.py::gate_decision —— 新增纯函数：算是否放行与警告文案" \
    --change "pdev/cli/commands.py::cmd_feat_new —— 创建前调用门禁并打印警告" \
    --change "pdev/config.py::ReviewConfig —— 新增 gate_threshold 配置项" \
    --api "gate_decision(score, threshold) -> GateDecision" \
    --api "cmd_feat_new(ctx, args) -> int" \
    --log "覆盖率低于阈值时 print 到 stderr 一行警告 + 补齐命令提示" \
    --test-note "纯函数测 gate_decision 的三态（高于/低于/刚好等于阈值，以及 total=0）；CLI 层测 feat new 在低覆盖率时仍返回 0 但 stderr 有警告" \
    --impact "只加一层非阻断警告，不改既有行为；feat new 的成功退出码与落盘结果不变；阈值可配可跳过" \
    --importance medium \
    --debug-note "无：纯计算 + 一次 print，没有可调试的运行时状态；靠 pytest 断言 stderr 内容" \
    --extend-note "要改成硬阻断：gate_decision 返回 ok 时让 cmd_feat_new 提前 return 2；要做成按 feat 粒度而非全局：把 compute_review 的输入换成单个 feat 的 review_items"
```

预期：

```
已创建 feat：review-gate [draft] 全局审查覆盖率门禁：低于阈值时在开发下一步警告
下一步：按本 doc 编写测试（pdm feat set <slug> testing）
```

**踩坑点**：`--change` 每条必须带 `::` 或 `.`（定位到符号），否则
`feat check` 会报 `vague-change`。

## 4. doc 阶段：先写设计文档

写 `doc/feat/review-gate.md`，内容建议包含：

- **问题**：为什么需要门禁（覆盖率只报不拦，债务累积）
- **规范**：阈值默认值、何时警告、警告什么、是否阻断
- **接口**：`gate_decision()` 的签名与返回
- **兜底**：`total=0`、配置缺失、`--ignore-gate`
- **验证方法**：测试用例名 + 手工步骤

提交（**只提交文档**）：

```bash
.venv/bin/pdm feat commit doc review-gate -m "设计规格：非阻断警告 + 阈值可配" \
    --files doc/feat/review-gate.md
```

预期：

```
✓ review-gate （未开始） → doc  <hash>
下一步：按本 doc 编写测试（pdm feat set <slug> testing）
```

## 5. test 阶段：先写测试

新建 `tests/test_review_gate.py`。**先只写测试，实现可以是空**：

```python
# 建议覆盖
def test_gate_blocks_below_threshold(): ...     # 覆盖率 2% < 10% → 警告
def test_gate_passes_above_threshold(): ...     # 覆盖率 50% > 10% → 放行
def test_gate_passes_exactly_at_threshold(): ...  # 边界：等于阈值
def test_gate_with_no_items(): ...              # total=0 不除零
def test_feat_new_warns_but_still_creates(): ...  # CLI：退出码 0 + stderr 有警告
def test_feat_new_ignore_gate_flag(): ...       # --ignore-gate 无警告
```

提交：

```bash
.venv/bin/pdm feat commit test review-gate -m "按设计写测试：门禁三态 + CLI 警告不阻断" \
    --files tests/test_review_gate.py
```

**此时跑测试应该是红的**（实现还没写）：

```bash
.venv/bin/python -m pytest tests/test_review_gate.py -q
```

## 6. feat 阶段：实现

改 `pdev/review.py`、`pdev/cli/commands.py`、`pdev/config.py`、`pdev/cli/parser.py`。

跑测试变绿：

```bash
.venv/bin/python -m pytest tests/test_review_gate.py -q
.venv/bin/python -m pytest -q                        # 全仓，别破坏别的
```

提交：

```bash
.venv/bin/pdm feat commit feat review-gate -m "实现 gate_decision 与 feat new 前置警告" \
    --files pdev/review.py --files pdev/cli/commands.py \
    --files pdev/config.py --files pdev/cli/parser.py
```

**提交后立刻记笔记**（规范要求 feat/fix 提交必须有笔记）：

```bash
.venv/bin/pdm note add <刚提交的 hash> \
    -k pitfall -t "一句话说清这个坑" \
    -d "详细：现象、根因、怎么发现的、怎么修的" \
    -F pdev/review.py -T review -p high \
    --verify 'test=tests/test_review_gate.py::test_gate_blocks_below_threshold;method=怎么验证;expected=passed'
```

## 7. fix 阶段：集成中发现的问题

手工实测（见第 9 节），有问题就在这一步修并提交：

```bash
.venv/bin/pdm feat commit fix review-gate -m "修复：<具体问题>" \
    --files pdev/review.py
```

**注意**：`feat` 之后**必须**经过 `fix` 才能 `close`（流程强制）。
即使没有代码修复，也要提交一次回填文档。

## 8. close 阶段：收尾

在本 feat 的设计文档 `doc/feat/review-gate.md` 末尾追加「实现与校验结果」小节：
交付物、实测数据、发现的异常、已知限制。

```bash
.venv/bin/pdm feat commit close review-gate -m "收尾：交付物与实测" \
    --files doc/feat/review-gate.md --close
```

预期：

```
✓ review-gate fix → close  <hash>
  review-gate → [closed]
```

## 9. 手工验证

```bash
# 当前覆盖率 2%（低于 10%）→ 应该警告
.venv/bin/pdm feat new temp-demo --title "临时" ...

# 加 --ignore-gate → 不应警告
.venv/bin/pdm feat new temp-demo2 --title "临时" ... --ignore-gate
```

## 10. 自校验

```bash
.venv/bin/pdm feat check review-gate
```

**必然剩下的告警**（只能人工做，工具的设计意图）：

```
! [review-none] / [review-low] / [missing-review]   逐个可审项勾选
! [stage-unreviewed]                                阶段级审核
```

### 人工勾审查

```bash
# 看有哪些可审项
.venv/bin/pdm feat review review-gate

# 逐项勾「已人工审查」
.venv/bin/pdm feat review review-gate --item api:0 --review
.venv/bin/pdm feat review review-gate --all --review      # 全勾

# 登记测试通过
.venv/bin/pdm feat review review-gate --item api:0 --test \
    --cmd "pytest tests/test_review_gate.py::test_gate_blocks_below_threshold" \
    --status passed
```

### 阶段级审核

```bash
.venv/bin/pdm feat stage-review review-gate doc --by human:lwy
.venv/bin/pdm feat stage-review review-gate test --by human:lwy
.venv/bin/pdm feat stage-review review-gate feat --by human:lwy
.venv/bin/pdm feat stage-review review-gate fix --by human:lwy
.venv/bin/pdm feat stage-review review-gate close --by human:lwy
.venv/bin/pdm feat stage-review review-gate --list        # 看进度
```

## 11. 常用排查命令

| 目的 | 命令 |
|------|------|
| 看字段概览 | `pdm feat show review-gate` |
| 看全部可编辑字段 | `pdm feat edit review-gate`（不带参数=预览） |
| 改字段（追加改动） | `pdm feat edit review-gate --add-change "pdev/x.py::Y —— 说明"` |
| 改字段（覆盖） | `pdm feat edit review-gate --impact "新的影响面"` |
| 看审查进度 | `pdm feat review review-gate` |
| 看全局覆盖率 | `pdm review` |
| 看流程是否合规 | `pdm feat check review-gate` |
| 看某 commit 的笔记 | `pdm show <commit>` |

## 12. 常见报错与处置

| 报错 | 原因 | 处置 |
|------|------|------|
| `缺必填字段：…` | `feat new` 少给了字段 | 补 `--test-note` / `--impact` / `--importance` 等 |
| `阶段顺序不允许：当前 [feat]，只能进入 [feat/fix]` | 想跳阶段 | 先提交 `fix`，再 `close` |
| `commit xxx 没有笔记` | feat/fix 提交后没记笔记 | `pdm note add <hash> ...` |
| `改动未定位到符号` | `--change` 缺 `::` | `pdm feat edit <slug> --set-change "pdev/x.py::Y —— 说明"` |
| `draft 却已串联 N 个 commit` | stage 游标丢失（跨分支开发常见） | 见下节 |

### stage 游标丢失的修复

跨分支 `git stash` / 合并后会丢（`.pdm/` 不跟踪）：

```bash
# 1. 补回 commit 关联（可用命令）
.venv/bin/pdm feat link review-gate <hash>

# 2. stage 游标只能手改 JSON（feat set 只改 status；link 不碰 stage）
.venv/bin/python -c "
import json
p='.pdm/feats/by-id/review-gate.json'
d=json.load(open(p,encoding='utf-8')); d['stage']='feat'
json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)"

# 3. 复查
.venv/bin/pdm feat check review-gate
```

## 13. 完成后

```bash
.venv/bin/pdm feat list | grep review-gate     # 应是 [closed]
git log --oneline -6                            # 应看到 doc/test/feat/fix/close 五条
```

如一切正常，这个 feat 就完整走完了一轮流程。
