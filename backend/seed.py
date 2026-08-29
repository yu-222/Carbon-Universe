"""首次运行时填充演示数据（与旧 store.py 的 seed_if_empty 等价）。"""
from __future__ import annotations

from schemas.carbon import CarbonItem, CarbonReport
from schemas.market import Order, OrderSide
from schemas.points import PointsReason, PointsRecord
from schemas.users import User


def seed_if_empty(repos) -> None:
    if repos.users.count() > 0:
        return

    u1 = User(name="绿色科技有限公司", email="demo@carbon.universe",
              carbon_balance=1200.0, points_balance=3600)
    u2 = User(name="低碳出行者", email="rider@carbon.universe",
              carbon_balance=50.0, points_balance=980)
    repos.users.create(u1)
    repos.users.create(u2)

    items = [
        CarbonItem(category="电力", activity="办公用电", amount=120000,
                   unit="kWh", factor=0.581, emission=120000 * 0.581),
        CarbonItem(category="交通", activity="公务车行驶", amount=8000,
                   unit="km", factor=0.203, emission=8000 * 0.203),
    ]
    rpt = CarbonReport(
        user_id=u1.id, title="2026年第一季度碳核算", period="2026-Q1",
        items=items, total_emission=sum(i.emission for i in items),
        ai_summary="（模拟）本季度主要排放来自电力消耗，建议提升绿电采购比例。",
    )
    repos.reports.create(rpt)

    o1 = Order(user_id=u1.id, side=OrderSide.SELL, price=68.5, quantity=100)
    o2 = Order(user_id=u2.id, side=OrderSide.BUY, price=67.0, quantity=30)
    repos.orders.create(o1)
    repos.orders.create(o2)

    p1 = PointsRecord(user_id=u2.id, reason=PointsReason.LOW_CARBON_TRAVEL,
                      points=120, description="地铁通勤")
    repos.points.create(p1)
