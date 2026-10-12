# -*- coding: utf-8 -*-
"""跨域共享的小类型。

只放被多个数据域共用的东西，领域专属的枚举请留在各自模块。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    """一个动作的发出者，格式 ``<kind>:<name>``。

    例：``human:lwy`` / ``ai:claude-opus-4`` / ``ci`` / ``github:alice``。
    """

    raw: str

    @property
    def kind(self) -> str:
        """冒号前的种类；无冒号时返回整个值。"""
        return self.raw.split(":", 1)[0]

    @property
    def name(self) -> str:
        """冒号后的名字；无冒号时返回空串。"""
        return self.raw.split(":", 1)[1] if ":" in self.raw else ""

    @property
    def is_ai(self) -> bool:
        return self.kind == "ai"

    @property
    def is_human(self) -> bool:
        return self.kind == "human"

    def __str__(self) -> str:
        return self.raw
