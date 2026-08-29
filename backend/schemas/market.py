"""虚拟碳资产交易所模型：挂单、成交。"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from schemas.common import BaseRecord


class OrderSide(str, Enum):
    BUY = "buy"     # 买入
    SELL = "sell"   # 卖出


class OrderStatus(str, Enum):
    OPEN = "open"           # 挂单中
    PARTIAL = "partial"     # 部分成交
    FILLED = "filled"       # 完全成交
    CANCELLED = "cancelled" # 已撤单


class Order(BaseRecord):
    user_id: str
    side: OrderSide
    price: float                    # 单价（元/吨）
    quantity: float                 # 数量（吨）
    filled: float = 0.0             # 已成交数量
    status: OrderStatus = OrderStatus.OPEN


class OrderCreate(BaseModel):
    user_id: str
    side: OrderSide
    price: float
    quantity: float


class Trade(BaseRecord):
    buy_order_id: str
    sell_order_id: str
    price: float
    quantity: float
