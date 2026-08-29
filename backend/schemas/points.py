"""碳普惠积分模型。"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from schemas.common import BaseRecord


class PointsReason(str, Enum):
    LOW_CARBON_TRAVEL = "low_carbon_travel"   # 低碳出行
    RECYCLE = "recycle"                       # 回收
    ENERGY_SAVING = "energy_saving"           # 节能
    TRADE_REWARD = "trade_reward"             # 交易奖励
    REDEEM = "redeem"                         # 兑换消耗


class PointsRecord(BaseRecord):
    user_id: str
    reason: PointsReason
    points: int                     # 正数为获得，负数为消耗
    description: Optional[str] = None


class PointsCreate(BaseModel):
    user_id: str
    reason: PointsReason
    points: int
    description: Optional[str] = None
