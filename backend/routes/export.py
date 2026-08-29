"""导出接口 —— 将碳核算报告导出为 CSV / JSON，供下载归档。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from bootstrap import repos

router = APIRouter(prefix="/api/export", tags=["export"])


def _current_user_id(uid):
    if uid and repos.users.get(uid):
        return uid
    users = repos.users.list()
    return users[0].id if users else None


@router.get("/summary")
def summary(user_id: str = None):
    """当前用户的台账汇总：用户信息 + 碳核算 + 交易 + 积分。"""
    uid = _current_user_id(user_id)
    user = repos.users.get(uid)
    if not user:
        raise HTTPException(404, "用户不存在")

    # 碳核算
    reports = [r for r in repos.reports.list() if r.user_id == uid]
    total_emission = round(sum(r.total_emission for r in reports), 3)

    # 交易记录：用户作为 maker（自己的订单）或 taker（taker:<uid> 标记）
    my_order_ids = {o.id for o in repos.orders.list() if o.user_id == uid}
    tag = "taker:" + uid
    my_trades = []
    for t in repos.trades.list():
        if (t.buy_order_id in my_order_ids or t.sell_order_id in my_order_ids
                or t.buy_order_id == tag or t.sell_order_id == tag):
            my_trades.append(t)
    my_trades.sort(key=lambda t: t.created_at, reverse=True)
    trade_volume = round(sum(t.price * t.quantity for t in my_trades), 2)

    # 积分
    point_records = [p for p in repos.points.list() if p.user_id == uid]
    point_records.sort(key=lambda p: p.created_at, reverse=True)
    points_earned = sum(p.points for p in point_records if p.points > 0)
    points_redeemed = -sum(p.points for p in point_records if p.points < 0)

    def _report_view(r):
        return {
            "id": r.id, "title": r.title, "period": r.period,
            "total_emission": r.total_emission, "created_at": r.created_at,
        }

    return {
        "user": {
            "id": user.id, "name": user.name, "email": user.email,
            "carbon_balance": user.carbon_balance,
            "cash_balance": user.cash_balance,
            "points_balance": user.points_balance,
        },
        "carbon": {
            "report_count": len(reports),
            "total_emission": total_emission,
            "reports": sorted((_report_view(r) for r in reports), key=lambda r: r["created_at"], reverse=True),
        },
        "trade": {
            "trade_count": len(my_trades),
            "trade_volume": trade_volume,
            "trades": [t.model_dump() for t in my_trades],
        },
        "points": {
            "balance": user.points_balance,
            "earned": points_earned,
            "redeemed": points_redeemed,
            "records": [p.model_dump() for p in point_records],
        },
    }


@router.get("/report/{report_id}.json")
def export_json(report_id: str):
    report = repos.reports.get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    return JSONResponse(
        content=report.model_dump(),
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.json"'},
    )


@router.get("/report/{report_id}.csv")
def export_csv(report_id: str):
    report = repos.reports.get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    raw = report.model_dump()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["类别", "活动", "活动量", "单位", "排放因子", "排放(kgCO2e)"])
    for item in raw.get("items", []):
        writer.writerow([
            item["category"], item["activity"], item["amount"],
            item["unit"], item["factor"], item["emission"],
        ])
    writer.writerow([])
    writer.writerow(["总排放(kgCO2e)", raw.get("total_emission", 0)])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.csv"'},
    )
