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
| `vague-change` | `changes` 某条既无 `::` 也无「非扩展名的点」 | 改动没定位到符号 |
| `empty-sample` | `samples` 某条长度 < 3 或只含占位词 | 样例过于敷衍 |

- 只对**创建的 feat 在强制起点之后**的报 `missing-fields`（历史豁免，方案 A）。
  起点取 `FIELDS_SINCE = 2026-10-14 11:16`（feat-fields 落地日）；
  不用 `stage` 游标——走新流程的历史 feat 也有 stage，会误伤。
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

- **`created_at` 早于 `FIELDS_SINCE`（历史 feat）** → 跳过 `missing-fields`，但
  `vague-change` / `empty-sample` 仍按内容检查（有内容才可能违反）。
- **`changes` 为空列表** → 不报 `vague-change`（空是缺字段的事，不重复报）。
- **`samples` 为空** → 不报 `empty-sample`。
- **占位词判定**：长度 `< 3`，或整条去掉空白后属 `{"无", "none", "n/a", "tbd"}`。
  注意：允许写「无：纯计算无外部数据」（含说明），只有**光秃秃的占位词**才报。
- **`vague-change` 的「点」要排除文件扩展名**：`pdev/feat.py` 里的 `.py` 不是
  符号定位，否则「改了 pdev/feat.py」会被误判为合格。判据：含 `::`，或含
  一个点且其后不是常见扩展名（py/md/json/…）。
- **`--strict`** → 新规则是 warning，行为与既有 warning 一致。

## 实现与校验结果（收尾）

- **实现**：`pdev/check.py` 新增 `_check_fields` / `_is_lazy_sample` /
  `_locates_symbol` 与 `FIELDS_SINCE`；`CODES` 增三码；
  `cmd_feat_show` 的「样例数据」标题加语义提示。
- **提交**：`doc` 90d1e61、`test` 2431fa2、`feat` 5d750a3、`fix` 0c6a659。
- **实测抓出的问题**：
  1. `vague-change` 最初判「含 :: 或含 .」，但 `改 pdev/feat.py` 里的 `.py`
     被当成符号定位；改为排除常见扩展名后仍有点才算。
  2. **豁免判据错**：用 `stage` 判历史——但走新流程的旧 feat 也有 stage，
     一上线就误报 8 条；改为按 `created_at >= FIELDS_SINCE` 判定，且分界点
     必须**晚于 feat-fields 的创建时刻**。
- **结论**：设计成立。`doc/feat/feat-fields.md` 中 `samples` 的语义已明确为
  「结构的真实实例，非用法」，并在 `feat show` 分区标题上提示。

> 遗留：`FIELDS_SINCE` 是硬编码时间点，属权宜之计；若后续引入 feat 的
> 「模式版本」字段，可改用它替代时间比较。
