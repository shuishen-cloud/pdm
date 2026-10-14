# Feat 详情视图切换（feat-view-switch）

> 先于实现编写。把 Feat 右侧详情的四开关从「纵向堆叠」改为「互斥切换」，
> 省去长内容上下滚动的时间。

## 问题

现状右侧 `#feat-detail` 把**所有内容纵向堆叠**：
阶段 → 规格字段 → commit → 异常 → 关联笔记 → 校验 →（d 开启时）文档正文。
内容越堆越长，想看文档正文得先滚过一大段笔记，浪费时间。

## 目标

- 右侧内容区按 `d/n/v/s` **互斥切换**：一次只显示一块
- 顶部信息（slug / title / 阶段 / 状态）**固定不动**
- 再按同一个键 → **切回默认视图**（规格字段）
- 长内容仍可滚动（`PgUp/PgDn`、`↑/↓`）

## 视图划分

```
┌ #feat-list ─┐ ┌ #feat-detail ──────────────────┐
│ feat A      │ │ 头部（固定）：slug/标题/阶段/状态 │
│ feat B      │ │ ────────────────────────────── │
│ feat C      │ │ 内容区（互斥）：                 │
│             │ │  默认  规格字段 api/logs/fallback │
│             │ │  d     设计文档正文               │
│             │ │  n     关联笔记详情               │
│             │ │  v     验证                       │
└─────────────┘ └────────────────────────────────┘
```

- `s` = 默认视图（规格字段），再按其它键切走；按 `s` 也回到默认
- `v`（验证）从「笔记的附属」提升为**独立视图**：列出该 feat 全部
  验证命令与上次状态（不依赖笔记详情展开）

## 状态模型

```python
# 单一“当前视图”字符串，取代原四布尔叠加
self._view = "spec"        # "spec" | "doc" | "notes" | "verify"
```

- 按 `d`：`view == "doc"` ? 回 `"spec"` : 设 `"doc"`
- 按 `n` / `v` 同理
- 按 `s`：直接回 `"spec"`
- **初始值**：仍读配置 `feat.view`——若 `doc_body=true` 则初始 `"doc"`，
  `notes_detail=true` 则初始 `"notes"`（保持与配置一致；否则 `"spec"`）

## 渲染

`_feat_detail()` 拆成「头部」+「按视图取内容」：

```python
def _feat_detail(feat, issues, git, note_store, doc_dir, view) -> Text:
    parts = [_feat_header(feat, git)]          # 固定头部
    parts.append(_view_spec(feat, view))       # 或 doc/notes/verify
    return concat(parts)
```

各视图函数：

- `_view_spec`：api / logs / fallbacks / commit / discovered / 校验
- `_view_doc`：Markdown 正文（沿用现有挂载逻辑）
- `_view_notes`：关联笔记（分组，含 detail/files）
- `_view_verify`：遍历笔记的 verifications（命令 + 状态）；无则提示

## 键位（不变）

| 键 | 作用 |
|----|------|
| `d` / `n` / `v` | 切到 文档 / 笔记 / 验证 视图；再按回默认 |
| `s` | 回到默认（规格）视图 |
| `PgUp` / `PgDn` | 滚动当前视图内容 |

状态栏显示当前视图：`[视图: spec]  d 文档  n 笔记  v 验证  s 规格`

## 兜底

- 某视图无内容（无笔记 / 无验证 / 文档不可读）→ 显示占位提示，不崩
- 切换视图时重置滚动位置到顶部（避免停在旧偏移）
- 配置 `feat.view` 的布尔开关退化为「初始视图」的选取

## 实现与校验结果（收尾）

实现于 c4a3ed9，测试于 48e6cc9。

### 落地结果

- `_view` 改为单一字符串（`spec|doc|notes|verify`）
- `d/n/v/s` 互斥切换，再按同键回 `spec`
- `_feat_detail` 拆为固定 `_feat_header` + 四个 `_view_*`
- `verify` 升为独立视图（不依赖笔记详情）
- 切换视图重置滚动到顶部；状态栏显示当前视图
- 配置 `feat.view` 布尔量退化为「选初始视图」（doc 优先于 notes）

### 验证

- 全量测试通过
- 实测：spec→d(doc,挂载Markdown)→n(notes,卸载)→v(verify)→v(回spec)→s

### 本次发现的异常

1. Textual `remove`/`mount` 均异步，切视图会重复挂载同名 widget；
   用自增代次 + `call_after_refresh` 防重。
2. 改 `_feat_detail` 默认行为会波及旧测试的隐式默认，
   需给直接调用处补显式视图。
