# 测试退出门禁与段错误留证（tui-test-exit-guard）

> 先于实现编写。**本 feat 不修任何已知 bug**——因为无法复现。
> 它建立的是**监控与留证**能力：让偶发问题在复发时立刻可见、可定位。

## 问题

调查 `tests/tui_new_to_fix/test_feat_ui.py` 时发现：

```
$ pytest tests/tui_new_to_fix/test_feat_ui.py
5 passed in 2.11s
（进程以退出码 139 结束 —— SIGSEGV）
```

崩溃发生在**解释器关闭阶段**（pytest 打印完结果之后），因此：

- `-q` 输出看起来全绿，**只有退出码暴露问题** → 长期无人发现；
- CI 若只看输出文本会漏判，若看退出码则全绿时误报失败。

**调查结论（无法复现，故不盲修）**：

| 场景 | 退出码 |
|------|--------|
| 真实使用 `pdm ui --new`（PTY 操作 Feat 面板） | 0 |
| 纯 asyncio 跑 app | 0 |
| 不经 pytest 连续 8 次 app 会话（含写盘+按键） | 0，且线程数恒 1、fd 恒 7 |
| pytest 单个/两个/三个用例 | 0 |
| pytest + **故意失败**的用例 | 1（失败被正确报告） |
| pytest 完整文件（当时） | **139** |
| 清理遗留 `__pycache__/test_zz_*.pyc` 后，工作区与干净 worktree 各 10+ 次 | 0 |

即：崩溃是**间歇性**的，且**不掩盖真实失败**（有失败时退出码为 1）、
**不影响用户**（真实运行不崩）。影响面仅限"CI 全绿时误判"。

**因此本 feat 不做盲修**（没有复现就无法验证修复是否正确），
而是建设两道防线。

## 规范

### 防线一：退出门禁（`scripts/check_test_exit.py`）

以**子进程**方式运行 pytest，**以退出码为准**判定，而不是看输出文本。

| 退出码 | 判定 | 理由 |
|--------|------|------|
| `0` | ok | 全过 |
| `1` | **tests-failed（合法）** | pytest 约定：有用例失败 |
| 其他（如 `139` = SIGSEGV、`2` = 中断） | **exit-guard-failure** | 异常退出，必须暴露 |

- 支持 `--runs N` 重复运行，用于捕捉**间歇性**崩溃。
- 失败时打印：复现命令、实际退出码、`scripts/tui_crash_report.py` 用法。

### 防线二：现场采集（`scripts/tui_crash_report.py`）

复发时一键采集，输出**可直接贴进笔记**的文本块：

| 字段 | 用途 |
|------|------|
| python 版本 / `-X` 开关 / `sys.flags` | 判断是否 dev 模式（曾观察到 `-X dev` 下不崩） |
| textual / pytest / pytest-asyncio 版本 | 版本相关性问题 |
| `gc` 计数与阈值、`gc.garbage` 长度 | 关闭期 GC 是重点怀疑对象 |
| `threading.active_count()` 与线程名 | Textual 驱动线程是否残留 |
| 打开的 fd 数 | 资源泄漏 |
| 复现命令 | 便于他人接续 |

**任一字段取不到时写 `unknown`，绝不中断**（采集脚本本身不能崩）。

### 不做（保持范围）

- ❌ 修改 `pdev/` 下任何生产代码（没有 bug 可修）
- ❌ 给测试加 `gc.collect()` 之类的"安慰剂"（会掩盖而非解决）
- ❌ 引入 `pytest-forked` / `psutil` 等新依赖
- ❌ 猜测性修复（如删掉某个用例"试试看"）

## 接口

```python
# scripts/check_test_exit.py
def classify(code: int) -> str:
    """退出码 -> "ok" / "tests-failed" / "exit-guard-failure"。纯函数。"""

def main(argv=None) -> int:
    """跑 pytest 并判定。返回 0=通过，1=门禁失败，2=用法错误。"""

# scripts/tui_crash_report.py
def collect() -> dict:
    """采集现场信息。任一字段失败写 "unknown"，不抛异常。"""

def render(info: dict) -> str:
    """dict -> 可直接粘贴的报告文本。纯函数。"""

def main(argv=None) -> int:
    """打印报告。"""
```

两者都**只用标准库**，不新增依赖。

## 日志

- 门禁通过：`ok: 3 次运行退出码均为 0`
- 门禁失败：打印每次的退出码序列、复现命令、留证脚本用法
- 采集脚本：直接打印报告，不写日志

## 兜底

| 情况 | 处理 |
|------|------|
| pytest 目标不存在 | 返回 2，提示路径错误 |
| `--runs` 非法（0/负数/非整数） | 返回 2 |
| 采集时字段取不到（如无 `gc.garbage`） | 写 `unknown`，继续 |
| 采集时 import textual 失败 | 该字段写 `unknown`，不中断 |
| 子进程被信号杀死 | 退出码为负数（如 -11），同样判为 exit-guard-failure |

## 验证方法

```
test=tests/test_tui_exit_guard.py::test_classify_codes
test=tests/test_tui_exit_guard.py::test_classify_negative_means_signal
test=tests/test_tui_exit_guard.py::test_crash_report_has_key_fields
test=tests/test_tui_exit_guard.py::test_crash_report_survives_missing
cmd=.venv/bin/python scripts/check_test_exit.py tests/tui_new_to_fix/test_feat_ui.py --runs 5
cmd=.venv/bin/python scripts/tui_crash_report.py
manual=门禁脚本对目标跑多次，观察是否出现非 0/1 的退出码
expected=当前应稳定为 ok；一旦复发，脚本会打印诊断提示
```

## 实现与校验结果（收尾）

实现于 `b6ed69bf`（test `3cff436d`、doc `967a573c`）。

**状态：已闭环（closed）**。本 feat **未修任何 bug**（无可复现的 bug），
交付的是监控与留证能力。收尾于 `b52e319d`。

### 交付物

| 文件 | 内容 |
|------|------|
| `scripts/check_test_exit.py` | 退出门禁：子进程跑 pytest，按退出码判定 |
| `scripts/tui_crash_report.py` | 现场采集：Python/flags/版本/GC/线程/fd/复现命令 |
| `tests/test_tui_exit_guard.py` | 10 例（分类语义 + 采集健壮性 + 用法校验） |
| `doc/feat/tui-test-exit-guard.md` | 本文档 |

**零新增依赖**。

### 实测

退出门禁（5 次）：

```
$ .venv/bin/python scripts/check_test_exit.py tests/tui_new_to_fix/test_feat_ui.py --runs 5
  run 1/5: 退出码 0
  ...
ok: 5 次运行退出码均为 0
```

**门禁自验**（用一个真段错误确认它真能抓到，
否则这脚本只是装饰）：

```
$ .venv/bin/python scripts/check_test_exit.py /tmp/seg_fail.py
退出门禁失败：出现异常退出码（既非 0 也非 1）
  第 1 次：退出码 -11（被信号 11 杀死，如 -11 = SIGSEGV）
  复现命令：... -m pytest /tmp/seg_fail.py -q
  采集现场：.venv/bin/python scripts/tui_crash_report.py
```

现场采集输出（示例）：

```
Python            : 3.13.2 | packaged by Anaconda, Inc.
平台                : Linux-6.6.87.1-microsoft-standard-WSL2-x86_64-with-glibc2.43
sys.flags         : sys.flags.dev_mode=False
# textual 8.2.8 / pytest 9.1.1 / pytest-asyncio 1.4.0
GC                : count=(1692, 0, 1) threshold=(2000, 10, 10) garbage=0
线程                : 1: MainThread
打开 fd 数           : 4
```

### 本次发现的异常（已记笔记）

1. **无法复现的偶发崩溃不应盲修**（difficulty/high）
   清理探针 `.pyc` 后，工作区与干净 worktree 各跑 10+ 次均退出码 0。
   没有复现就没有验收标准，因此转为门禁 + 留证。
2. **删掉源文件后 `__pycache__` 里的 `.pyc` 仍会被 pytest 加载**（pitfall/medium）
   调试期创建的 `test_zz_*.py` 用 `rm` 删除后，其 `.pyc` 残留，
   pytest 仍会加载执行——既污染结果，也误导了我的归因。

### 复发时怎么办

1. 跑 `scripts/check_test_exit.py <目标> --runs 10` 确认是否复发；
2. 若是，跑 `scripts/tui_crash_report.py` 采集现场；
3. 带着两份输出开一个新 feat（届时才有可验证的复现步骤）。

### 已知限制（有意不做）

- 未接入 CI 配置文件（仓库暂无 workflow 目录）；
  需要时把 `check_test_exit.py` 作为 CI 步骤即可。
- 不做自动归因（如自动判断是不是 GC/线程问题）——证据不足时
  自动化只会给出误导结论。
