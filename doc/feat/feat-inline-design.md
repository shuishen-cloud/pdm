# Feat 详情内联设计（feat-inline-design）

> 先于实现编写。让 Feat 页面**直接看到设计内容**（数据结构 / 参考值 /
> 实现方式），并**复用已有 CommitNote**，而不是只看一个文档路径。

## 动机

现状 Feat 详情只显示 `api` / `logs` / `fallbacks` 三个结构化字段
和一行文档**路径**，看不到设计正文；关联笔记只显示一行 title。
用户要"查看相应功能的设计（数据结构、参考值、简单实现方式）"时，
必须手动去开文件、翻笔记。

## 目标

1. Feat 详情可**内联渲染设计文档正文**（Markdown）
2. **复用 CommitNote**：展开笔记的 detail / files / 验证方法
3. 显示内容**四个维度独立可控**（按键临时切 + 配置持久默认）
4. 不新增重复存储：doc 正文来自文件，笔记来自 NoteStore

## 四个开关键

在 FeatScreen 现有键位（`j k ← → Tab PgUp PgDn c r q Esc`）之外新增：

| 键 | 开关 | 控制 | 默认 |
|----|------|------|------|
| `d` | doc_body | 内联渲染设计文档正文（Markdown） | 关 |
| `n` | notes_detail | 笔记展开 detail + files | 关 |
| `v` | verify | 每条验证的命令 + 上次状态 | 开 |
| `s` | specs | api / logs / fallbacks 展开 | 开 |

- 均为一键 toggle；底部状态栏实时显示 `[d:on] [n:off] ...`
- `d` 打开正文后，`PgUp/PgDn` 或 `[`/`]` 滚动正文（不抢占 `j/k` 选 feat）

## 配置（持久默认值）

优先级：**按键临时切换 > 配置 > 内置默认**。

```jsonc
// pdev/config.py: FeatConfig 下新增 view 段
{
  "feat": {
    "store": ".pdm/feats",
    "view": {
      "doc_body": false,
      "notes_detail": false,
      "verify": true,
      "specs": true,
      "notes_grouped": true,   // 笔记按 kind 分组
      "doc_max_lines": 0       // 正文截断，0=不限
    }
  }
}
```

环境变量（沿用现有映射风格）：
`PDM_FEAT_VIEW_DOC_BODY` / `PDM_FEAT_VIEW_NOTES_DETAIL` /
`PDM_FEAT_VIEW_VERIFY` / `PDM_FEAT_VIEW_SPECS` /
`PDM_FEAT_VIEW_NOTES_GROUPED` / `PDM_FEAT_VIEW_DOC_MAX_LINES`

## 接口

```python
# pdev/config.py
@dataclass
class FeatViewConfig:
    doc_body: bool = False
    notes_detail: bool = False
    verify: bool = True
    specs: bool = True
    notes_grouped: bool = True
    doc_max_lines: int = 0

@dataclass
class FeatConfig:
    store: str = ".pdm/feats"
    view: FeatViewConfig = field(default_factory=FeatViewConfig)

# pdev/tui/screens.py
class FeatScreen:
    def __init__(self, ..., view=None): self._view = dict(...)
    def action_toggle_doc(self): ...
    def action_toggle_notes(self): ...
    def action_toggle_verify(self): ...
    def action_toggle_specs(self): ...

def read_doc_body(doc_dir, feat_doc, max_lines=0) -> str
    """读设计文档正文（相对 doc.dir 解析）；读取失败返回 ''"""

def group_notes_by_kind(notes) -> list
    """[(kind, [note, ...]), ...]，保持 kind 首次出现顺序"""
```

## 渲染

- 纯文本块（阶段/字段/笔记）→ `Static`
- doc 正文 → `textual.widgets.Markdown`（textual ≥0.80 自带，实测 8.2.8 可用）
- 笔记按 `notes_grouped` 决定是否分组；`notes_detail` 决定是否展开 detail/files
- `verify` 打开时显示每条 verification 的命令与 `last_status`

## 兜底

- 文档路径为空 / 文件不存在 / 读取失败 → 显示「（设计文档不可读）」，
  不崩、不报错
- `max_lines > 0` → 截断并提示「…（已截断，共 N 行）」
- git 不可用 → 阶段显示不变（既有逻辑）
- 开关状态在屏幕内保留（切换 feat 不重置）

## 实现与校验结果（收尾）

实现于 ff7894c，测试于 8479242。

### 落地结果

- `FeatViewConfig`（挂在 `FeatConfig.view`）：6 个字段全部生效
- `_apply_segment` 支持嵌套 dataclass 递归合并
- `read_doc_body()` / `group_notes_by_kind()` 两个纯函数
- `FeatScreen` 四开关键 `d/n/v/s` + 状态栏 `[d:on] [n:off] ...`
- `d` 打开时挂载 `textual.widgets.Markdown` 渲染正文（textual 8.2.8）
- 笔记区复用 `notes_for_feat()`，展开 detail/files/验证

### 验证

- 全量测试通过（含 11 个新测试）
- 无头实测：默认开关、`d` 挂载 Markdown、`n` 展开笔记、状态栏均正常
- `pdm feat check feat-inline-design`：仅缺独立 test/fix 阶段（与既往同因）

### 本次发现的异常

1. `_apply_segment` 原本只处理一层，嵌套 dataclass（`view`）不生效；
   需 `is_dataclass(current)` 判断后递归。
2. 动态挂载 Markdown 用 `query/remove/mount` 三件套，已存在则 `update` 复用；
   开关状态栏需 `_update_hint` 主动刷新，否则用户看不到当前状态。
