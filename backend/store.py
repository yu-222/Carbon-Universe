"""内存字典 + JSON 文件持久化的极简数据层。
所有路由共享同一个 store 实例。
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")
_LOCK = threading.Lock()

# 顶层集合结构
_DEFAULT: Dict[str, Any] = {
    "users": {},
    "reports": {},
    "orders": {},
    "trades": {},
    "points": {},
}


class Store:
    def __init__(self, path: str = _DATA_PATH):
        self.path = path
        self.db: Dict[str, Any] = json.loads(json.dumps(_DEFAULT))
        self.load()

    # -- 持久化 ------------------------------------------------------------
    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k in _DEFAULT:
                    self.db[k] = data.get(k, {})
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        with _LOCK:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.db, f, ensure_ascii=False, indent=2)

    # -- 便捷访问 ----------------------------------------------------------
    def col(self, name: str) -> Dict[str, Any]:
        return self.db[name]

    def put(self, name: str, obj_id: str, value: Any) -> None:
        self.db[name][obj_id] = value
        self.save()


store = Store()


def seed_if_empty() -> None:
    """首次运行时填充模拟数据，便于前端联调。"""
    if store.db["users"]:
        return
    from models import User, CarbonReport, CarbonItem, Order, OrderSide, PointsRecord, PointsReason

    u1 = User(name="绿色科技有限公司", email="demo@carbon.universe", carbon_balance=1200.0, points_balance=3600)
    u2 = User(name="低碳出行者", email="rider@carbon.universe", carbon_balance=50.0, points_balance=980)
    for u in (u1, u2):
        store.db["users"][u.id] = u.model_dump()

    items = [
        CarbonItem(category="电力", activity="办公用电", amount=120000, unit="kWh", factor=0.581, emission=120000 * 0.581),
        CarbonItem(category="交通", activity="公务车行驶", amount=8000, unit="km", factor=0.203, emission=8000 * 0.203),
    ]
    rpt = CarbonReport(
        user_id=u1.id, title="2026年第一季度碳核算", period="2026-Q1",
        items=items, total_emission=sum(i.emission for i in items),
        ai_summary="（模拟）本季度主要排放来自电力消耗，建议提升绿电采购比例。",
    )
    store.db["reports"][rpt.id] = rpt.model_dump()

    o1 = Order(user_id=u1.id, side=OrderSide.SELL, price=68.5, quantity=100)
    o2 = Order(user_id=u2.id, side=OrderSide.BUY, price=67.0, quantity=30)
    for o in (o1, o2):
        store.db["orders"][o.id] = o.model_dump()

    p1 = PointsRecord(user_id=u2.id, reason=PointsReason.LOW_CARBON_TRAVEL, points=120, description="地铁通勤")
    store.db["points"][p1.id] = p1.model_dump()

    store.save()
