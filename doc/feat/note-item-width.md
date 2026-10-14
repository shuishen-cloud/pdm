# 笔记列表项按宽度截断（note-item-width）

> 先于实现编写。修「笔记列表中栏 `[difficulty]` 后面空白」的问题。

## 问题

`NoteItem.render()` 直接把 `· [kind] 标题  ✓ severity` 拼成**单行 Text**，
不做宽度处理。而 `NoteList` 宽仅 **40**，`ListItem` CSS 是 `height: 1`
（单行不换行）。

实测：一条 difficulty 笔记渲染 cell 宽度达 **81**，远超 40 →
超宽部分被裁/挤出可视区，表现为 `[difficulty]` 之后**空白**（标题看不见）。

对比 `CommitItem`：它已按可用宽度用 `_ellipsize(subject, avail)` 截断，
所以提交列表没这个问题。

## 目标

`NoteItem.render()` 仿 `CommitItem`：按可用宽度**截断标题**，保证
`· [kind] 标题…  ✓ sev` 始终完整可见。

## 方案

```python
def render(self) -> Text:
    n = self.note
    width = self.size.width or 40      # 脱离 app 时的估值

    # 固定前缀
    mark = _STATUS_MARK.get(n.status, "·")
    kind = f"[{n.kind.value}] "
    # 后缀（验证标记 + severity）
    suffix = ...                        # 计算其 cell 宽度

    prefix_len = len(mark) + 1 + cell_len(kind)
    avail = width - prefix_len - suffix_len - 2
    title = _ellipsize(n.title, max(avail, 4))
    ...拼接...
```

- 只截断**标题**，`[kind]` 与后缀（验证符号、severity）保留
- 沿用 `_ellipsize`（已有辅助）

## 兜底

- `self.size.width == 0`（脱离 app 渲染）→ 用估值 40
- `avail <= 0` → 标题截为 `…` 或空，仍保证 `[kind]` 可见

## 不做

- 不改变列表宽度（用户要求：截断即可）
- 不改详情面板（那里可横向容纳/换行）

## 实现与校验结果（收尾）

实现于 c198425，测试于 e18c22a。

### 落地结果

- `NoteItem.render()` 按 `self.size.width` 计算可用宽度
- 保留 `[kind]` 与后缀（验证符号 / severity），**仅截断标题**
- 实测：81 字符长标题 → `· [difficulty] 数据迁移三坑…  ✓ high`
  （cell_len 37 ≤ 40）

### 验证

- 全量测试通过
- 两个新测试：超长截断（cell_len ≤ 38）、短标题完整

### 本次发现的异常

1. `NoteItem` 无子控件，无法靠 CSS 截断，必须在 `render()` 内自算
   前后缀宽度；中文标题要用 `_display_width` 而非 `len`。
2. 测试勿用 `store.all()`（会混入 fixture 预置笔记），
   应 `by_commit` 精确取。
