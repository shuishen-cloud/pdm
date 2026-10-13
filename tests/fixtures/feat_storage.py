# -*- coding: utf-8 -*-
"""feat-storage 的 Mock 数据。

对应 `pdm feat show feat-storage` 里 "Mock 数据" 一节声明的路径。
供 tests/test_feat.py 使用，保证测试数据集中、可复用。
"""

from __future__ import annotations

# 一条字段齐全的 feat，覆盖 Feat 的全部字段
FULL_FEAT = {
    "slug": "demo-feat",
    "title": "演示功能",
    "kind": "feat",
    "status": "draft",
    "design": "实现方式示例",
    "api": ["pdm demo run"],
    "data_model": "Demo{a, b}",
    "fixtures": ["tests/fixtures/feat_storage.py"],
    "fallbacks": ["非法输入报错"],
    "touches": ["pdev/demo.py"],
    "follows": ["JSON 分片存储"],
    "logs": ["demo.created"],
    "debug": "pdm demo --debug",
}

# 最小可用的 feat（只有必填）
MINIMAL_FEAT = {"slug": "minimal", "title": "最小"}

# 非法 slug 样例
BAD_SLUGS = ["Bad", "has_underscore", "-lead", "trail-", "", "有空 格"]
