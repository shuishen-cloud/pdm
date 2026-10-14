# Feat 视图内核 + CLI 对等（feat-cli-parity）

> 先于实现编写。让 CLI 具备 TUI 已有的 feat 展示能力，并修掉分层倒置。

## 动机

上一轮给 TUI 的 Feat 面板加了「内联设计正文 + 复用笔记」，但这三个
函数（`read_doc_body` / `notes_for_feat` / `group_notes_by_kind`）
**定义在 `pdev/tui/screens.py`**：

1. **CLI 无法复用**——`pdm feat show` 只显示 doc 路径、不含关联笔记，
   与 TUI 能力不对等。
2. **分层倒置**——若让 CLI import TUI 模块，会让「运行时零依赖」的
   CLI 依赖 textual。

## 目标

1. 把三个视图函数**上移到内核**（新模块 `pdev/featview.py`），
   CLI 与 TUI 共享，`tui` 不再独占
2. `pdm feat show` 新增 `--doc` / `--notes` / `--verify`，默认值取自
   配置 `feat.view`，与 TUI 四开关对齐
3. 保持 CLI 运行时零依赖（不 import textual）

## 内核模块 `pdev/featview.py`

```python
def read_doc_body(doc_dir: str, feat_doc: str, max_lines: int = 0) -> str
    """读设计文档正文（相对 doc.dir 解析；缺失→标记；可截断）"""

def notes_for_feat(feat, note_store) -> List[CommitNote]
    """该 feat 关联 commit 上的全部笔记（≥6 位前缀互匹配）"""

def group_notes_by_kind(notes) -> List[Tuple[str, List[CommitNote]]]
    """笔记按 kind 分组，保持首次出现顺序"""
```

- 纯函数，只依赖 `pdev.config` / `pdev.note`，**不依赖 textual**
- `pdev/tui/screens.py` 改为从内核 import（保留同名再导出，避免破坏测试）

## CLI 变更

```
pdm feat show <slug> [--doc] [--notes] [--verify]
```

| 选项 | 作用 | 默认来源 |
|------|------|----------|
| `--doc` | 打印设计文档正文（纯文本，Markdown 原文） | `feat.view.doc_body` |
| `--notes` | 附「关联笔记」（按 kind 分组，含 detail/files） | `feat.view.notes_detail` |
| `--verify` | 附每条笔记的验证命令与上次状态 | `feat.view.verify` |

- 未指定任何 flag 时，走**配置默认**（`feat.view`），与 TUI 一致
- `--json` 时在 JSON 里附 `doc_body` / `related_notes` 字段（可选）

## 兜底

- 文档不可读 → 打印「（设计文档不可读）」，不崩
- 该 feat 无关联笔记 → 打印「（该 feat 暂无笔记）」
- `max_lines>0` → 截断并提示
- 非 git / 无 note_store → 跳过相关区块

## 验收

- `pytest` 全绿（新增内核测试 + CLI 测试）
- `pdm feat show <slug> --doc` 能打印正文
- `pdm feat show <slug> --notes` 能聚合笔记
- `pdev/tui/screens.py` 不再定义这三个函数（仅 import/转发）
- CLI 不 import textual（`test_cli.py` 可验证）

## 实现与校验结果（收尾）

实现于 480b941，测试于 2eb8860。

### 落地结果

- 新建 `pdev/featview.py`：三个纯函数，**不 import textual**
- `pdev/tui/screens.py` 改为转发内核实现（保留同名导出）
- `pdm feat show --doc / --notes / --verify` 全部生效，默认取 `feat.view`
- 笔记输出按 kind 分组，含 detail / files / 验证命令与状态

### 验证

- 全量测试通过（含 11 个新测试）
- **CLI 零依赖验证**：子进程 `import pdev.cli`，`textual` 不在 `sys.modules`
- 实测 `pdm feat show note-check --doc --notes --verify`：
  正确输出设计正文 + 分组笔记 + 验证状态

### 与 TUI 的能力对齐

| 能力 | TUI | CLI |
|------|-----|-----|
| 设计正文 | `d` 键（Markdown 渲染） | `--doc`（纯文本原文） |
| 关联笔记 | `n` 键 | `--notes` |
| 验证方法 | `v` 键 | `--verify` |
| 规格字段 | `s` 键 | 默认显示 |

两者共享 `pdev/featview.py` 内核，默认值均取 `feat.view` 配置。

### 本次发现的异常

1. 内核上移时采用「转发」而非删本地定义，保住 `test_tui` 的旧 import。
2. `_flag` 的默认值需区分：`verify` 内置默认 `True`，
   而 `doc_body` / `notes_detail` 默认 `False`，不能一刀切。
3. 迁移测试时须连「数据前提」一起搬——照搬断言会因
   实现分支（如 `nc == c` 完全相等匹配）导致误判。
