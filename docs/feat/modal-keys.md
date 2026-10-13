# 弹窗按键规范（modal-keys）

> 本文件**先于代码**编写，是实现的指导与约束。
> 发现动机：FeatScreen 按 `q` 时把整个 App 一起退掉了（bug）。

## 问题

Textual 的 `App` 有全局 `Binding("q", "quit")`。弹窗（`ModalScreen`）
若只用 `key_q()` 返回 `True`，事件仍会冒泡到 App，导致**关弹窗的同时退出应用**。

## 规范（所有弹窗必须遵守）

1. **关闭键要在弹窗自己的 `BINDINGS` 里显式声明**
   （`escape`、`q`），把它们消耗在弹窗层，不冒泡到 App。
2. **不要用 `key_q()` 返回值来"拦截"** —— 声明式 Binding 更可靠。
3. **需要输入文本的弹窗例外**：`q` 必须是普通字符输入，
   此时仅用 `escape` 关闭（如 `FilterScreen`）。
4. 关闭统一走 `action_close()` → `dismiss(None)`（或携带结果）。

## 各弹窗现状

| 弹窗 | 关闭键 | 说明 |
|------|--------|------|
| FilterScreen | `escape` / `Ctrl+L` 清除 | 有输入框，`q` 是字符 |
| VerifyScreen | `escape` / `q` | 无输入框 |
| HelpScreen | `escape` / `q` / `enter` / `?` | 无输入框 |
| ThemeScreen | `escape` / `q` | 无输入框 |
| FeatScreen | `escape` / `q` | 无输入框 |

## 接口

```python
# 弹窗基类约定（各 ModalScreen 自行实现 action_close）
action_close(self) -> None
```

## 兜底

- 弹窗未声明 `q` Binding 却有 `key_q` → 视为违规（会冒泡退 App）
- `dismiss` 后 App 应保持 `is_running == True`
