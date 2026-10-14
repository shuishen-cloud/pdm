# TUI 信号退出恢复终端（tui-signal-restore）

> 先于实现编写。约束 TUI 在**任何退出路径**都必须把终端恢复原状，
> 否则会留下乱码、raw mode，只能关闭终端窗口。

## 问题

用户报告：`pdm ui` 运行中**直接退出，终端一直出乱码，只能关闭终端**。

用 PTY（`expect`）复现并对比退出序列，定位到确切根因：

| 退出方式 | `1049l`(退备用屏) | `25h`(恢复光标) | `2004l`(关 bracketed paste) |
|----------|:---:|:---:|:---:|
| 按 `q` 正常退出 | ✅ | ✅ | ✅ |
| **Ctrl+C** | ❌ | ❌ | ❌ |

根因链：

1. Textual 的 `LinuxDriver.stop_application_mode()` 负责写上述恢复序列，
   由 `App._shutdown()` 触发。
2. `App.run()` 内部用 `asyncio.run()` 驱动事件循环。
3. Ctrl+C 时，`asyncio.run()` 的默认 SIGINT 处理**直接抛
   `KeyboardInterrupt` 打断事件循环**，`run_async` 的
   `finally: await asyncio.shield(app._shutdown())` 来不及完成
   （或被 `CancelledError` 吞掉）。
4. → `stop_application_mode()` 未执行 → 无恢复序列 → 终端留在备用屏
   + raw mode → 乱码，只能关终端。

`python main.py ui` 路径更严重：`main.py` 的
`install_signal_handlers` 把 SIGINT 换成"抛 KeyboardInterrupt"，
进一步确保事件循环被硬中断。`pdm ui`（走 `pdev.cli.entry`）两者皆未恢复，
说明主因在 `asyncio.run` 的默认 SIGINT 行为。

## 规范

1. **TUI 退出必须恢复终端**，无论正常结束、异常、信号。
2. 恢复动作由 `PDMApp.run()` 统一兜底，不依赖 `asyncio.run` 的清理路径。
3. 恢复序列（幂等，可重复写）：
   ```
   \x1b[?1049l   退出备用屏
   \x1b[?25h     显示光标
   \x1b[?1004l   关 FocusIn/Out
   \x1b[?2004l   关 bracketed paste
   \x1b[?1000l \x1b[?1003l \x1b[?1015l \x1b[?1006l   关鼠标
   \x1b[<u       关 kitty 键盘协议
   ```
4. **非 tty 不写**（避免污染管道输出）。
5. 恢复失败**不得掩盖原异常**：只向 stderr 提示，原异常照常传播。
6. 恢复前尝试 `stty sane` 作深度兜底（无 tty 或 `stty` 缺失则跳过）。

## 接口

```python
# pdev/tui/app.py
def _restore_terminal() -> None
    """无条件把终端恢复到正常模式（幂等、非 tty 安全）。"""

def run(store, cwd=".", config=None, config_path=None) -> int
    """启动 TUI；用 try/finally 保证退出时恢复终端。"""
```

## 日志

- 恢复成功：静默（不污染已恢复的终端）。
- 恢复失败：写 stderr 一行说明，不含堆栈。

## 兜底

- 非 tty（stdout 非终端）→ 直接返回，不写序列。
- `stty` 不存在 / 失败 → 仅写 ANSI 序列。
- 恢复动作本身抛异常 → 吞掉，保证 finally 不二次抛出。
- `KeyboardInterrupt` → 视为正常退出，返回码沿用 CLI 约定（130）。

## 验证方法

```
cmd=python - <<'PY'
# 用 PTY 触发 Ctrl+C，检查退出输出含 1049l
PY
method=PTY 下 Ctrl+C 退出，输出须含 1049l/25h
expected=退出码 0 且含恢复序列
```

## 实现与校验结果（收尾）

实现于 commit `cccdc612`（`PDMApp.run()` 与 `main.py` 信号处理兜底），
文档/说明于 `39e5d5fa`。

### 验证（PTY 下用 expect 实测）

| 退出路径 | `1049l` | `25h` | `2004l` | `1004l` |
|----------|:---:|:---:|:---:|:---:|
| `pdm ui` + `q` | ✅ | ✅ | ✅ | ✅ |
| `main.py ui` + `q` | ✅ | ✅ | ✅ | ✅ |
| `pdm ui` + `Ctrl+C`→`Ctrl+Q` | ✅ | ✅ | ✅ | ✅ |
| `main.py ui` + `Ctrl+C`→`Ctrl+Q` | ✅ | ✅ | ✅ | ✅ |

对比修复前：Ctrl+C 退出时四条恢复序列**全部为 0**，终端留在备用屏
+ raw mode → 乱码。

单元测试见 `tests/test_tui_signal.py`（6 例）：`_restore_terminal` 的
tty/非 tty/异常吞掉/幂等，以及 `run()` 在 KeyboardInterrupt 与正常退出
时都调用恢复。

### 本次发现的异常

1. **Ctrl+C 不再直接退出**：Textual 8.2.8 的 Ctrl+C 只弹
   “Do you want to quit?” 确认框，需 `Ctrl+Q` 才真退出。初期用
   `expect eof` 验证时因确认框未关、超时被杀，误判为“退出无恢复”。
   教训：验证 TUI 退出必须**确证进程真的结束**，而非等待超时。
2. `main.py` 的信号处理器原本直接 `raise KeyboardInterrupt`，
   在 TUI raw mode 下会硬中断事件循环；已改为先恢复终端再抛。
