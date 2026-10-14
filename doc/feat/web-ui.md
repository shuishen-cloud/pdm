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

## 实现与校验结果（收尾）

实现于 `16846213`（`pdev/webui.py` + `pdm ui --web`），
补前端契约测试于 `befdab1e`。

### 交付物

| 文件 | 内容 |
|------|------|
| `pdev/webui.py` | 新模块；`build_data` + `make_handler` + `run` + 内嵌单页 |
| `pdev/cli/parser.py` | `--web` / `--port` / `--no-browser` |
| `pdev/cli/commands.py` | `--web` 分派 |
| `tests/test_webui.py` | 15 例（纯函数 + HTTP + 前端契约 + node 校验 JS） |

**零新增依赖**：`pyproject.toml` 未改，无 Flask/React/npm。

### 分层（沿用 curses 版做法）

```
run()                起 http.server，绑 127.0.0.1
  ↑
make_handler(data)   纯数据 → HTTP 处理器
  ↑
build_data(store, git)   纯函数：store/git → dict
```

`build_data` 不 import http/socket，测试用 `inspect` 断言。

### 交互能力

| 功能 | 状态 |
|------|------|
| 三栏（提交/笔记/详情） | ✅ |
| 点击提交 → 列笔记；点击笔记 → 出详情 | ✅ |
| `j`/`k`、`↑`/`↓` 移动 | ✅ |
| `/` 聚焦筛选框，**前端即时过滤** | ✅ |
| `Esc` 清筛选，`R` 刷新 | ✅ |
| HTML 转义（`escapeHtml`）防注入 | ✅ |

### 验证

| 项 | 结果 |
|----|------|
| 纯函数 + HTTP + 前端契约测试 | ✅ 15 例 |
| 真起服务抓 HTML | ✅ HTTP 200，7377 bytes |
| 真起服务抓 API | ✅ 175 提交 / 73 笔记组 |
| 未知路径 | ✅ 404 |
| 非 GET | ✅ 405（只读） |
| JS 语法 | ✅ `node --check` 通过 |
| 无外部资源引用 | ✅ 正则断言为空（零依赖） |
| 非 TUI 全量回归 | ✅ 全绿 |

实测：`.venv/bin/pdm ui --web --port 8765 --no-browser` 后
`curl /` 与 `/api/data` 均正常，数据为真实 store（175 提交）。

### 本次发现的异常

1. **单页前端需要契约测试**：否则后续加个 CDN 字体就会破坏"零依赖"。
   已加"无外链"断言 + 交互钩子检查 + `node --check`。
2. **测试自身写错**（非实现错误）：短 hash 键按 8 位、空 store 用了
   会返回提交的 git 替身。修测试而非改实现。

### 已知限制（有意不做）

- 只读：无写操作、无跑验证、无审查勾选。
- 无分页：一次全量下发（当前 175 提交无压力，上千后再议）。
- 无暗/亮主题切换（默认暗色）。
- 服务仅绑 `127.0.0.1`，不做认证（本机使用）。
