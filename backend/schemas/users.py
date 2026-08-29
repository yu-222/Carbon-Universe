"""用户与组织主体。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from schemas.common import BaseRecord


class User(BaseRecord):
    name: str
    email: Optional[str] = None
    carbon_balance: float = 1000.0  # 持有碳信用（单位）
    cash_balance: float = 100000.0  # 法币余额（元）
    points_balance: int = 0         # 碳普惠积分


class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
