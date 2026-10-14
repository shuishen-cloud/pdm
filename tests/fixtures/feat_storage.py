# -*- coding: utf-8 -*-
"""feat-storage 的 Mock 数据。

对应 `pdm feat show feat-storage` 里 doc 声明的 Mock 路径。
供 tests/test_feat.py 使用。

重构后 Feat 字段精简为：slug/title/kind/status/doc/api/logs/fallbacks/
commits/notes/discovered
"""

from __future__ import annotations

# 字段齐全的 feat（api/logs 都是"能直接写进代码"的真实内容）
FULL_FEAT = {
    "slug": "demo-feat",
    "title": "演示功能",
    "kind": "feat",
    "status": "draft",
    "doc": "docs/feat/demo.md",
    "api": [
        "FeatStore.add(feat: Feat) -> None",
        "FeatStore.get(slug: str) -> Optional[Feat]",
    ],
    "logs": [
        "创建时记录 slug 与标题",
        "状态推进时记录 from → to",
    ],
    "fallbacks": ["非法输入抛 FeatError"],
    "commits": [],
}

# 最小可用的 feat（只有必填）
MINIMAL_FEAT = {"slug": "minimal", "title": "最小"}

# 非法 slug 样例
BAD_SLUGS = ["Bad", "has_underscore", "-lead", "trail-", "", "有空 格"]

# 已废弃的字段（旧版塞进 Feat 的"文档正文"，重构后应被忽略）
# 注：data_model 曾属废弃字段，feat-fields 后又复活为真实字段，故移除。
LEGACY_FIELDS = ["design", "fixtures", "touches",
                 "follows", "debug"]


# --- feat-check 的 Mock 数据 ---

# 合规的 feat：closed、有 commit、字段齐全
GOOD_FEAT = {
    "slug": "good-feat", "title": "合规", "status": "closed",
    "doc": "docs/feat/good.md", "api": ["f() -> None"],
    "logs": ["记录调用"], "fallbacks": ["报错"], "commits": ["aaa111"],
    "design_note": "这么设计的原因", "impl_note": "这么实现的",
    "data_model": ["X: int —— 计数"], "samples": ["X=1"],
    "changes": ["pdev/x.py::X —— 新增"],
}

# draft 却已有 commit（draft-has-commit）
DRAFT_WITH_COMMIT = {
    "slug": "draft-commit", "title": "矛盾", "status": "draft",
    "doc": "d.md", "api": ["f()"], "logs": ["l"], "fallbacks": ["f"],
    "commits": ["bbb222"],
}

# closed 却没有 commit（closed-no-commit）
CLOSED_NO_COMMIT = {
    "slug": "closed-empty", "title": "空", "status": "closed",
    "doc": "d.md", "api": ["f()"], "logs": ["l"], "fallbacks": ["f"],
}

# 缺字段（empty-doc / no-api / no-fallback）
BARE_FEAT = {"slug": "bare", "title": "裸", "status": "draft"}
