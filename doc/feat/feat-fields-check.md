# 五项设计字段的校验（feat-fields-check）

> 先于实现编写。`feat-fields` 把五栏写进了 Feat，但只有 `feat new` 拦得住
> 缺字段；已存在的 feat 缺栏、`changes` 写得太糊、`samples` 语义跑偏，都没人管。
> 本 feat 给 `pdm feat check` 补规则，并**明确 `samples` 的语义**。

## 问题

上一轮（feat-fields）之后暴露三个缺口：

1. **缺失无人管**：`feat new` 拦住新建，但手工改 JSON、或旧 feat 缺栏时，
   `pdm feat check` 一声不吭。要靠 `check` 做兜底提示。
2. **`changes` 写得糊**：约定 `文件::符号 —— 说明`，但只写「改了 pdev/feat.py」
   这种不带符号的写法也照收，定位不到具体方法/变量。
3. **`samples` 语义模糊**（上轮实测踩到）：`feat-fields` 自己的 `samples`
   被我填成了 CLI 用法，而非「数据样例」。设计文档只说「每条一个例子」，
   没说清「例子 = 数据结构的实例」。

## 规范

### 三项 check 规则（均 warning）

| code | 触发 | 含义 |
|------|------|------|
| `missing-fields` | `missing_required_fields()` 非空 | 五项必填有缺 |
| `vague-change` | `changes` 某条既无 `::` 也无 `.` | 改动没定位到符号 |
| `empty-sample` | `samples` 某条长度 < 3 或只含占位词 | 样例过于敷衍 |

- 只对**有 `stage` 游标**的 feat 报 `missing-fields`（历史豁免，方案 A）。
- `vague-change` / `empty-sample` 对**有该字段内容**的 feat 都报（补填即消失）。

### `samples` 的语义（明确）

- `data_model` 记**类型/结构定义**：`Cache: dict[str, int] —— key→计数`。
- `samples` 记**该结构的真实实例**：`{"k": 1}`、`by-id/x.json 片段：{...}`。
- **不是**命令行用法、不是接口签名。
- check 只做粗筛（长度、占位词），语义靠文档与展示引导。

### 展示引导

`pdm feat show` 的两个分区标题改为带提示：

```
核心数据结构
  [ ][ ] · Cache: dict[str,int] —— 计数
样例数据（结构的实例，非用法）
  [ ][ ] · {"k": 1}
```

## 接口

```python
# pdev/check.py
CODES = (..., "missing-fields", "vague-change", "empty-sample")

def _check_fields(feat) -> List[CheckIssue]
    """五项字段相关规则；不依赖 git/note_store。"""

# 触发 missing-fields 时，message 列出缺失项（复用 missing_required_fields）
# 历史豁免判据：feat.stage is None → 跳过 missing-fields
```

## 日志

- 不新增日志；走既有 `format_issue` 渲染。

## 兜底

- **`stage is None`（历史 feat）** → 跳过 `missing-fields`，但 `vague-change`
  / `empty-sample` 仍按内容检查（有内容才可能违反）。
- **`changes` 为空列表** → 不报 `vague-change`（空是缺字段的事，不重复报）。
- **`samples` 为空** → 不报 `empty-sample`。
- **占位词判定**：长度 `< 3`，或整条去掉空白后属 `{"无", "none", "n/a", "tbd"}`。
  注意：允许写「无：纯计算无外部数据」（含说明），只有**光秃秃的占位词**才报。
- **`--strict`** → 新规则是 warning，行为与既有 warning 一致。

## 实现与校验结果（收尾）

**在 close 阶段补写**。
