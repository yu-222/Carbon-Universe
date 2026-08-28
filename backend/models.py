"""数据模型定义 —— 使用 Pydantic
包含：用户、碳核算报告、挂单、成交、积分记录
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field


def _uid() -> str:
    return uuid4().hex[:12]


def _now() -> str:
    return datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class OrderSide(str, Enum):
    BUY = "buy"     # 买入
    SELL = "sell"   # 卖出


class OrderStatus(str, Enum):
    OPEN = "open"           # 挂单中
    PARTIAL = "partial"     # 部分成交
    FILLED = "filled"       # 完全成交
    CANCELLED = "cancelled" # 已撤单


class PointsReason(str, Enum):
    LOW_CARBON_TRAVEL = "low_carbon_travel"   # 低碳出行
    RECYCLE = "recycle"                       # 回收
    ENERGY_SAVING = "energy_saving"           # 节能
    TRADE_REWARD = "trade_reward"             # 交易奖励
    REDEEM = "redeem"                         # 兑换消耗


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------
class User(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    email: Optional[str] = None
    carbon_balance: float = 1000.0  # 持有碳信用 (单位)，初始分配 1000
    cash_balance: float = 100000.0  # 法币余额 (元)，初始分配
    points_balance: int = 0         # 碳普惠积分
    created_at: str = Field(default_factory=_now)


class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None


# ---------------------------------------------------------------------------
# 碳核算报告
# ---------------------------------------------------------------------------
class CarbonItem(BaseModel):
    """单项排放活动数据"""
    category: str                   # 类别，如 电力/交通/差旅
    activity: str                   # 活动描述
    amount: float                   # 活动量
    unit: str                       # 单位，如 kWh/km/L
    factor: float                   # 排放因子 (kgCO2e/unit)
    emission: float = 0.0           # 计算后的排放 (kgCO2e)


class CarbonReport(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    title: str
    period: str                     # 核算周期，如 2026-Q1
    items: List[CarbonItem] = []
    total_emission: float = 0.0     # 总排放 (kgCO2e)
    ai_summary: Optional[str] = None
    suggestions: List[str] = []     # 减碳建议
    source: str = "form"            # 数据来源：form / nl
    created_at: str = Field(default_factory=_now)


class CarbonReportCreate(BaseModel):
    user_id: str
    title: str
    period: str
    items: List[CarbonItem] = []


# --- AI 智能核算请求 ---
class CalcFormItem(BaseModel):
    """表单模式单项输入：活动类型 + 数量 + 单位"""
    activity_type: str              # 用电 / 出行 / 餐饮 / 办公
    amount: float
    unit: Optional[str] = None      # 缺省时由后端按类型推断


class CarbonCalcRequest(BaseModel):
    user_id: Optional[str] = None
    mode: str = "form"              # form | nl
    title: Optional[str] = None
    period: Optional[str] = None
    items: List[CalcFormItem] = []  # mode=form 时使用
    text: Optional[str] = None      # mode=nl 时使用（自然语言）


# ---------------------------------------------------------------------------
# 挂单 / 成交
# ---------------------------------------------------------------------------
class Order(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    side: OrderSide
    price: float                    # 单价 (元/吨)
    quantity: float                 # 数量 (吨)
    filled: float = 0.0             # 已成交数量
    status: OrderStatus = OrderStatus.OPEN
    created_at: str = Field(default_factory=_now)


class OrderCreate(BaseModel):
    user_id: str
    side: OrderSide
    price: float
    quantity: float


class Trade(BaseModel):
    id: str = Field(default_factory=_uid)
    buy_order_id: str
    sell_order_id: str
    price: float
    quantity: float
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# 积分记录
# ---------------------------------------------------------------------------
class PointsRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: str
    reason: PointsReason
    points: int                     # 正数为获得，负数为消耗
    description: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class PointsCreate(BaseModel):
    user_id: str
    reason: PointsReason
    points: int
    description: Optional[str] = None
