# -*- coding: utf-8 -*-
"""代码来源指纹：附加在 commit message trailer 上的溯源信息。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from .common import Actor


class Generated(str, Enum):
    """代码 / 文档由谁生成。"""

    AI_FULL = "ai:100%"        # 完全由 AI 生成
    AI_PARTIAL = "ai:partial"  # AI 参与但非全部
    HUMAN = "human"

    @property
    def is_ai(self) -> bool:
        """是否含 AI 生成成分。"""
        return self in (Generated.AI_FULL, Generated.AI_PARTIAL)


@dataclass
class Fingerprint:
    """附加在 commit message trailer 上的来源指纹。

    ::

        Assisted-by: ai:claude-opus-4 | human:lwy | mixed
        Generated-by: ai:100% | ai:partial | human
        Reviewed-by: human:lwy | (空 = 未审)
        Explainability: yes | no
        Issue: 0001
    """

    assisted_by: str = ""
    generated_by: Generated = Generated.HUMAN
    reviewed_by: Optional[Actor] = None
    explainability: str = "yes"
    issue: str = ""

    @property
    def is_ai_generated(self) -> bool:
        """是否含 AI 生成成分。"""
        return self.generated_by.is_ai

    @property
    def fully_ai_generated(self) -> bool:
        """是否完全由 AI 生成。"""
        return self.generated_by is Generated.AI_FULL

    @property
    def reviewed(self) -> bool:
        """是否已被人审查。"""
        return self.reviewed_by is not None and self.reviewed_by.is_human

    @property
    def explainable(self) -> bool:
        """人能否解释该改动。"""
        return self.explainability != "no"

    @property
    def risky(self) -> bool:
        """是否构成风险项：完全由 AI 生成且未审，或不可解释。"""
        if not self.explainable:
            return True
        return self.fully_ai_generated and not self.reviewed

    @property
    def trailers(self) -> List[Tuple[str, str]]:
        """渲染为 git trailer 键值对，供写入 commit message。"""
        out: List[Tuple[str, str]] = []
        if self.assisted_by:
            out.append(("Assisted-by", self.assisted_by))
        out.append(("Generated-by", self.generated_by.value))
        if self.reviewed_by is not None:
            out.append(("Reviewed-by", str(self.reviewed_by)))
        out.append(("Explainability", self.explainability))
        if self.issue:
            out.append(("Issue", self.issue))
        return out
