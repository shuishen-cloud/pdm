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

# pdev/cli/context.py 或新 helper
def resolve_doc_path(ctx, feat_doc: str) -> Path
    """把 feat.doc 解析成项目内实际路径（兼容旧格式）"""

# pdev/cli/commands.py
def cmd_feat_new(...):
    # --doc 传了 → 相对项目根原样存
    # 未传 → 空（不变）
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

（待实现后回填）
