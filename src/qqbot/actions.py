"""通用动作结果（确定性指令与 LLM 工具共用）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActionResult:
    summary: str
    media: bytes | None = None
