# 测试提速（test-speedup）

> 先于实现编写。目标：把全量测试从 ~40s 降到 ~15s，**不改变任何断言语义**。

## 问题

全量测试 40s，其中 `tests/test_tui.py` 独占 **36s（90%）**，其余 21 个
文件合计仅 ~4s。定位到三个开销源：

| 因素 | 数量 | 单次开销 | 估算 |
|------|------|---------|------|
| `app.run_test()` 启停 Textual app | 77 | ~190ms | ~14.6s |
| `pilot.pause()` 遍历 widget 树 | 197 | ~22ms | ~4.4s |
| fixture（store/GitRepo）| 100 | <3ms | ~0.3s |

关键事实（读 Textual 源码确认）：

1. `Pilot.press()` 内部**已调用 `_wait_for_screen()`**。因此
   `await pilot.press(...)` 紧跟 `await pilot.pause()` 时，pause 内的
   `_wait_for_screen()` 是**重复等待**（~22ms），绝大多数可删。
2. `_wait_for_screen()` 遍历 `screen.walk_children()` 逐 widget 等消息队列，
   app 越大越慢。
3. 一个测试内多次 `run_test()` = 多次 ~190ms 启停。

## 规范

1. **语义等价**：只删冗余等待、只合并同测试内的 app，**不弱化断言**。
   每个被删 `pause` 的断言点必须在删除后仍通过。
2. `press` 后不紧跟 `pause`，除非：
   - 断言依赖**定时器/动画**推进（需显式 `pause(delay)`）；
   - 后续操作依赖屏幕**重新挂载**（如 remove/mount 异步，见 modal）。
3. 同一测试内需要多个 app 场景时，**优先在单个 app 内完成**（push/dismiss
   screen 复用同一 app），减少 run_test 次数。
4. **不引入随机性/时间竞态**：删 pause 后若出现 flaky，必须恢复该 pause。
5. `pdev/` 生产代码**不改动**（纯测试重构）。

## 接口

不新增生产接口。测试侧新增：

```python
# tests/test_tui.py
@pytest.fixture(scope="session")
def store_factory() -> Callable[[], NoteStore]
    """按需构造独立 store（避免 session 级共享可变状态）。"""

@asynccontextmanager
async def boot(store, cwd=None, size=(110, 40))
    """跑一个 app 并 pause 一次的常用封装。"""
```

## 日志

不适用（测试基础设施）。

## 兜底

- 任何测试变 flaky（重跑 3 次有波动）→ 恢复对应 pause，并在文档记录。
- 提速后若测试数减少，需在文档说明"合并了哪些重复用例"。
- 无法判断某 pause 是否冗余时，**保守保留**。

## 验收标准

| 指标 | 基线 | 目标 |
|------|------|------|
| 全量测试 wall time | ~39.5s | ≤ 15s |
| 测试通过数 | 全绿 | 全绿（不减少覆盖） |
| 重跑 3 次 | 稳定 | 稳定（无 flaky） |

## 实现与校验结果（收尾）

实现于本分支 `refactor/test-speedup`（未合并 master）。

### 实际结果（诚实记录）

| 指标 | 基线 | 结果 |
|------|------|------|
| 全量测试 | ~34.7s | **~35.4s**（波动区间 32-35s）|
| test_tui.py | ~34.7s | **~32.5s** |
| 测试数 | 101 | 101（不减少）|
| 重跑稳定性 | — | 3 次全绿，无 flaky |

*未达到 15s 目标。* 原因见下。

### 已完成

1. **删除 93 处冗余 `press→pause`**（`Pilot.press()` 已内含
   `_wait_for_screen()`）——已重构域内全部清除，守卫阻止回退。
2. **8 个共享 app 测试类**（约 35 个测试）：`TestStartupAndNav` /
   `TestModalClose` / `TestFilter` / `TestZoom` / `TestPanelKeys` /
   `TestArrowNav` / `TestRunAndClick` / `TestCommandPalette`。
3. **守卫测试** `tests/test_speedup_guard.py`：保证测试数不减少、
   共享类内无冗余 pause、无单测试多次 run_test。

### 关键发现（推翻初始估算）

实测（`/tmp` 基准脚本）：

| 操作 | 耗时 |
|------|------|
| 新 app 启动 | **仅 49ms**（非估算的 190ms）|
| 首次 `pause`（首帧渲染）| 95ms |
| 后续 `pause` | 22-52ms |
| `press`（含等待）| ~66ms |
| `reset_app`（去 pause 后）| **3ms** |

**真正瓶颈是测试内的多次 `press`（每次 ~66ms），而非 app 启动。**
共享 app 可摊销启动，但无法减少 press——而 press 是测试内容本身。

因此 15s 目标**不可达**：101 测试 × 多 press ≈ 25-30s 是这类
UI 集成测试的现实下限。强行达标需削减 press/端到端断言，那会
**降低测试价值**，得不偿失。

### 本次发现的异常

1. `ListView.clear()` 返回 `AwaitRemove`，**必须 `await`** 才真正移除子项；
   共享 app 时不 await 会导致列表项叠加（2 变 4）。
2. `reset_app` 里 clear 后的额外 `pause()` 是**多余**的
   （await clear 已足够），去掉后 reset 从 57ms 降至 3ms。
3. pytest-asyncio 的**类级事件循环共享**需要
   `@pytest.mark.asyncio(loop_scope="class")` 加在**类上**；
   仅 `fixture(loop_scope="class")` 不够（测试仍在不同循环，
   await 跨循环 Future 会报 “different loop”）。
4. 依赖精确 UI 坐标的测试（如 `pilot.click(children[1])`）
   **不适合共享 app**（残留选中/滚动状态），保留独立。

### 未完成（后续可选）

剩余 ~40 个独立 app 测试（含 Feat 域、主题域、git 合并域）
未转换。预估全部转换可再省 3-5s（难以达到 15s）。
