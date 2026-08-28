"""虚拟碳资产交易所 —— 挂单、吃单成交、订单簿、成交历史。

设计（MVP，显式吃单）：
- 挂单只入簿，不自动撮合。
- 用户点击对手方订单，调用 /match 全额吃单成交。
- 成交时校验双方碳信用/法币余额，成交后双方余额变动、订单移除、记录成交。

为简化演示，"当前用户" 默认取用户列表第一个；可通过入参 user_id 指定。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models import Order, OrderCreate, OrderSide, OrderStatus, Trade, User
from store import store

router = APIRouter(prefix="/api/exchange", tags=["exchange"])


# --- 请求模型 ---
class PlaceOrderReq(BaseModel):
    user_id: Optional[str] = None
    type: OrderSide            # buy / sell
    amount: float              # 数量（碳信用单位）
    price: float               # 单价（元/单位）


class MatchReq(BaseModel):
    user_id: Optional[str] = None   # 吃单者
    order_id: str                   # 被吃的对手方订单


# --- 工具 ---
def _current_user_id(uid: Optional[str]) -> str:
    if uid and uid in store.col("users"):
        return uid
    users = list(store.col("users").keys())
    if not users:
        raise HTTPException(400, "系统暂无用户")
    return users[0]


def _get_user(uid: str) -> User:
    raw = store.col("users").get(uid)
    if not raw:
        raise HTTPException(404, "用户不存在")
    return User(**raw)


def _save_user(u: User) -> None:
    store.col("users")[u.id] = u.model_dump()


# --- 接口 ---
@router.get("/balance")
def balance(user_id: Optional[str] = None):
    uid = _current_user_id(user_id)
    u = _get_user(uid)
    return {
        "user_id": u.id,
        "name": u.name,
        "carbon_balance": round(u.carbon_balance, 3),
        "cash_balance": round(u.cash_balance, 2),
    }


@router.get("/orders")
def orderbook():
    """返回订单簿：卖单价格升序，买单价格降序（价格优先）。"""
    opens = [Order(**o) for o in store.col("orders").values()
             if o["status"] == OrderStatus.OPEN]
    asks = sorted([o for o in opens if o.side == OrderSide.SELL], key=lambda x: x.price)
    bids = sorted([o for o in opens if o.side == OrderSide.BUY], key=lambda x: -x.price)
    return {"asks": asks, "bids": bids}


@router.get("/trades", response_model=List[Trade])
def list_trades():
    trades = [Trade(**t) for t in store.col("trades").values()]
    return sorted(trades, key=lambda t: t.created_at, reverse=True)


@router.post("/orders", response_model=Order)
def place_order(payload: PlaceOrderReq):
    if payload.amount <= 0 or payload.price <= 0:
        raise HTTPException(400, "数量与单价必须大于 0")
    uid = _current_user_id(payload.user_id)
    u = _get_user(uid)

    # 挂单时冻结校验：卖单需有足够碳信用，买单需有足够法币
    if payload.type == OrderSide.SELL and u.carbon_balance < payload.amount:
        raise HTTPException(400, f"碳信用不足（持有 {u.carbon_balance}，需 {payload.amount}）")
    if payload.type == OrderSide.BUY and u.cash_balance < payload.amount * payload.price:
        raise HTTPException(400, "法币余额不足以支付该买单")

    order = Order(user_id=uid, side=payload.type, price=payload.price, quantity=payload.amount)
    store.put("orders", order.id, order.model_dump())
    return order


@router.post("/match")
def match(payload: MatchReq):
    """吃单成交：taker 与指定对手方订单全额成交。"""
    raw = store.col("orders").get(payload.order_id)
    if not raw:
        raise HTTPException(404, "订单不存在")
    maker_order = Order(**raw)
    if maker_order.status != OrderStatus.OPEN:
        raise HTTPException(400, "该订单已不可成交")

    taker_id = _current_user_id(payload.user_id)
    if taker_id == maker_order.user_id:
        raise HTTPException(400, "不能吃自己的挂单")

    taker = _get_user(taker_id)
    maker = _get_user(maker_order.user_id)

    qty = maker_order.quantity
    price = maker_order.price
    total = round(qty * price, 2)

    # 判定买卖方：maker 是卖单 → taker 买入；maker 是买单 → taker 卖出
    if maker_order.side == OrderSide.SELL:
        buyer, seller = taker, maker
    else:
        buyer, seller = maker, taker

    # 校验双方余额充足
    if seller.carbon_balance < qty:
        raise HTTPException(400, "卖方碳信用不足，无法成交")
    if buyer.cash_balance < total:
        raise HTTPException(400, "买方法币不足，无法成交")

    # 结算：碳信用 卖→买，法币 买→卖
    seller.carbon_balance = round(seller.carbon_balance - qty, 3)
    buyer.carbon_balance = round(buyer.carbon_balance + qty, 3)
    buyer.cash_balance = round(buyer.cash_balance - total, 2)
    seller.cash_balance = round(seller.cash_balance + total, 2)
    _save_user(buyer)
    _save_user(seller)

    # 订单完成并移出订单簿（标记 filled）
    maker_order.filled = qty
    maker_order.status = OrderStatus.FILLED
    store.col("orders")[maker_order.id] = maker_order.model_dump()

    # 记录成交
    trade = Trade(
        buy_order_id=maker_order.id if maker_order.side == OrderSide.BUY else "taker:" + taker_id,
        sell_order_id=maker_order.id if maker_order.side == OrderSide.SELL else "taker:" + taker_id,
        price=price, quantity=qty,
    )
    store.col("trades")[trade.id] = trade.model_dump()
    store.save()

    return {
        "trade": trade,
        "buyer": {"id": buyer.id, "carbon_balance": buyer.carbon_balance, "cash_balance": buyer.cash_balance},
        "seller": {"id": seller.id, "carbon_balance": seller.carbon_balance, "cash_balance": seller.cash_balance},
    }


@router.post("/orders/{order_id}/cancel", response_model=Order)
def cancel_order(order_id: str):
    raw = store.col("orders").get(order_id)
    if not raw:
        raise HTTPException(404, "订单不存在")
    order = Order(**raw)
    if order.status != OrderStatus.OPEN:
        raise HTTPException(400, "订单无法撤销")
    order.status = OrderStatus.CANCELLED
    store.put("orders", order.id, order.model_dump())
    return order
