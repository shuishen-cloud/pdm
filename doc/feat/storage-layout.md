# 存储布局统一到 `.pdm/`（storage-layout）

> 先于实现编写。目标是方便分发代码：开发过程数据默认不随代码上传，
> 但允许用户显式配置到可跟踪目录。

## 动机

当前开发过程数据散落在项目根：`notes/`、`feats/`、`docs/`，
且**全部被 git 跟踪**。分发代码时会把这些"本地开发过程"一起带上，
既无必要，也暴露过程细节。

## 目标

1. 三类数据统一收进 **`.pdm/`**：`.pdm/notes/`、`.pdm/feats/`、`.pdm/docs/`
2. `.pdm/` **整体 gitignore**（默认不跟踪、不随代码分发）
3. `doc.dir` 配置**真正生效**：作为 feat 设计文档的根目录
4. 用户可把 `doc.dir` 配到**可跟踪目录**（如 `docs`），使设计文档随代码走
5. 单条 feat 可用 `--doc <path>` 覆盖（相对项目根，原样存）

## 关键决策

### `feat.doc` 存**相对 `doc.dir` 的相对路径**

- 现状：`feat.doc = "docs/feat/feat-scroll.md"`（字面全路径，pdev 不解析）
- 改为：`feat.doc = "feat/feat-scroll.md"`（相对 `doc.dir`）
- 好处：改一次 `doc.dir` 配置，全部 feat 的文档根随之切换

### 兼容读取（不破坏历史）

读取时若 `doc` 以已知根前缀开头（`docs/`、`.pdm/docs/`），
视为"旧格式、已含根"，**不再拼接** `doc.dir`。保证旧 json 可读。

### 配置变更

```jsonc
{
  "store": ".pdm/notes",
  "feat": { "store": ".pdm/feats" },
  "doc":  { "dir": ".pdm/docs" }      // 默认值由 "docs" 改为 ".pdm/docs"
}
```

`.gitignore` 追加 `.pdm/`。

## 接口

新增/修改：

```python
# pdev/config.py
DocConfig.dir: str = ".pdm/docs"        # 默认值变更

def resolve_doc_path(doc_dir: str, feat_doc: str) -> str
    """把 feat.doc（相对 doc.dir）解析成项目内实际路径。

    - feat_doc 为空 → 返回 ""
    - feat_doc 已是旧格式（以 docs/ 或 .pdm/docs/ 开头）→ 原样返回
    - 否则 → 拼成 <doc_dir>/<feat_doc>
    """
```

## 兜底

- `doc.dir` 为空 → 视作 `.pdm/docs`
- `feat.doc` 为空 → 不解析（现状）
- 旧格式（含 `docs/` 前缀）→ 直接返回，不拼接
- 目标文件不存在 → 显示时原样打印路径，不报错

## 迁移

一次性脚本 `scripts/migrate_storage.py`：

1. `git mv` 或 `mv`：`notes/`→`.pdm/notes/`，`feats/`→`.pdm/feats/`，
   `docs/feat/`→`.pdm/docs/feat/`（`doc/` 不动）
2. 规范化每个 feat 的 `doc` 字段为相对 `doc.dir`
3. `git rm -r --cached` 旧路径，`.gitignore` 加 `.pdm/`

**注意**：旧 git 历史中这些文件仍存在；本次只保证**新 clone 不含**。

## 实现与校验结果（收尾）

实现于 ae8adcb，迁移于 0947a36。

### 落地结果

- `.pdm/{notes,feats,docs}` 收纳全部开发过程数据，整体 gitignore
- `resolve_doc_path()` 生效：`feat.doc` 存相对路径（`feat/x.md`），
  按 `doc.dir`（默认 `.pdm/docs`）解析为 `.pdm/docs/feat/x.md`
- `Config.store` / `FeatConfig.store` 默认值同步改到 `.pdm/` 下
- `git rm --cached` 旧路径：新 clone 不再旧带开发过程数据

### 验证

- 全量测试通过
- 实际仓库实测：`pdm feat list` / `pdm feat show` / `pdm stats`
  均从新路径正确读取；`feat show` 解析出 `.pdm/docs/feat/storage-layout.md`
- 12 个 feat 的 doc 解析后路径全部真实存在

### 本次发现的异常

1. `git mv feats .pdm/feats` 在 `.pdm/feats/by-id` 已存在时会把目录
   嵌套成 `.pdm/feats/feats/by-id`；须先确保目标目录不存在，
   或改用普通 `mv` + `git add -A` 重建索引。
2. 规范化 `doc` 字段的基准易搞错：去掉的是 `docs/`（根），
   不是 `docs/feat/`；正确结果应是 `feat/x.md`，
   否则解析成 `.pdm/docs/x.md`（错位）。
3. `git rm -r --cached` 前若工作区与索引不一致（改了 doc 字段），
   会报错拒删，须先 `git add -A` 对齐。
