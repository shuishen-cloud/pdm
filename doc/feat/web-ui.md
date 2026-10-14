# 零依赖本地 Web UI（web-ui）

> 先于实现编写。用**标准库 http.server + 原生 JS 单页**做一个可交互的
> 本地网页界面。**零第三方依赖、无构建步骤**，与 curses 版共享纯数据逻辑。

## 问题

终端 TUI 有两条现实约束：

1. **框架风险**：Textual 版 2097 行、77 次 `run_test()` 让测试要 40s+，
   且历史 bug 多来自框架边界（Binding 冒泡、消息命名、raw mode）。
2. **终端约束**：curses 版只能在本机终端看，不能鼠标点、不能长文滚动
   舒服地看、无法分享给同事瞄一眼。

Web 前端天然解决第 2 条：浏览器里能点、能滚、能缩放。
但常见做法（Flask/FastAPI + React/Vue）会**重新引入一大串依赖与构建步骤**，
与项目"零依赖、可审查"的取向冲突。

**根因**：缺一个"能交互、又不引框架"的查看方式。

## 规范

### 零依赖（硬约束）

| 层 | 用什么 | 不许用 |
|----|--------|--------|
| HTTP 服务 | 标准库 `http.server` | Flask/FastAPI/uvicorn |
| 数据序列化 | 标准库 `json` | 任何 ORM/模板引擎 |
| 前端 | 原生 HTML + CSS + JS（内嵌字符串） | React/Vue/npm/webpack |
| 依赖声明 | `pyproject.toml` **不改** | 新增任何依赖 |

### 分层（沿用 curses 版的可测性做法）

```
run()               起 http.server（唯一碰网络的层）
  ↑
make_handler(data)  把纯数据绑成 http 处理器
  ↑
build_data(store, git)   纯函数：store/git → dict（可脱离网络单测）
```

- `build_data` **不 import http.server**，与 curses 版同源做法。
- 测试断言 JSON 结构，**不用起真服务**；另用 1~2 个用例起服务跑通。

### 交互（第一版做什么）

| 功能 | 说明 |
|------|------|
| 三栏布局 | 提交 / 笔记 / 详情 |
| 点击切换 | 点提交 → 中间列出笔记；点笔记 → 右侧详情 |
| 键盘 | `j`/`k` 或上下键在提交间移动，`/` 聚焦筛选 |
| 筛选框 | 按关键字**前端过滤**提交与笔记（不请求后端） |
| 刷新 | `R` 重新 `fetch` 一次 |

**不做**（保持范围可控）：

- ❌ 写操作（改笔记、跑验证、勾审查）
- ❌ 分页/虚拟滚动（数据量小，一次全量下发）
- ❌ 任何前端框架与构建

### 路由

| 路径 | 返回 |
|------|------|
| `GET /` | 内嵌的单页 HTML |
| `GET /api/data` | 一次性全量 JSON（commits + notes + detail 源数据） |
| 其他 | 404 |

**只读**：所有路由仅 `GET`；非 GET → 405。服务只绑 `127.0.0.1`
（不对外网暴露）。

### CLI

```
pdm ui --web [store] [--port N] [--no-browser]
```

- 默认 `port=0`（系统分配随机空闲端口），避免与已有服务冲突。
- 默认尝试打开浏览器（`webbrowser`，标准库）；失败只打印地址。
- 默认行为不变：`pdm ui` 仍是 Textual 版。

## 接口

```python
# pdev/webui.py

def build_data(store, git, cwd=".") -> dict:
    """组装前端所需全部数据。**纯函数，不 import http.server。**

    返回::

        {
          "commits": [{"hash": str, "short": str, "subject": str,
                       "author": str, "note_count": int}, ...],
          "notes": {短hash: [note_dict, ...]},   # 每条含 kind/title/status/...
          "store_root": str, "git_available": bool
        }
    """

def make_handler(data: dict):
    """返回一个 http.server.BaseHTTPRequestHandler 子类。"""

def run(store, cwd=".", port=0, open_browser=True,
        stdout=None) -> int:
    """起服务并阻塞；返回退出码（0 正常，2 端口/环境错误）。"""
```

CLI：`--web` 分派到 `run`；新增 `--port`、`--no-browser`。

## 日志

- 启动：向 stdout 打印 `Web UI: http://127.0.0.1:<port>`（**便于用户手点**）。
- 请求：默认静默（覆盖 `log_message`），避免刷屏。
- 异常：打印一行到 stderr，不抛堆栈给用户。

## 兜底

| 情况 | 处理 |
|------|------|
| 端口被占 | `port=0` 时由系统分配；显式端口冲突 → 报错退出 2 |
| 非 git 仓库 | `build_data` 退回笔记里的 commit，`git_available=false` |
| store 为空 | 返回空数组，前端显示"暂无数据"，不崩 |
| 浏览器打开失败 | 捕获异常，仅打印地址 |
| 请求非 GET | 405 |
| 未知路径 | 404 |
| JSON 序列化失败（脏数据） | 跳过该条并记入 `warnings`，不整包失败 |

## 验证方法

```
test=tests/test_webui.py::test_build_data_shape
test=tests/test_webui.py::test_build_data_pure_no_http_import
test=tests/test_webui.py::test_handler_serves_html_and_api
test=tests/test_webui.py::test_non_get_returns_405
cmd=.venv/bin/pdm ui --web --help
manual=运行 pdm ui --web，浏览器点提交/笔记，筛选框输入关键字
expected=三栏联动正常；筛选即时过滤；刷新不变
```
