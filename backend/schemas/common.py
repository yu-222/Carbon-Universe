"""公共字段与工具：所有记录模型的基类与 ID / 时间戳生成。"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


def _uid() -> str:
    return uuid4().hex[:12]


def _now() -> str:
    return datetime.utcnow().isoformat()


class BaseRecord(BaseModel):
    """所有持久化记录的公共字段。

    - id：稳定 ID（uuid hex 前 12 位）
    - created_at / updated_at：ISO8601 字符串，Repository 层负责填充
    """
    id: str = Field(default_factory=_uid)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
