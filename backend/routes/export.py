"""导出接口 —— 将碳核算报告导出为 CSV / JSON，供下载归档。"""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from store import store

router = APIRouter(prefix="/api/export", tags=["export"])


def _current_user_id(uid):
    if uid and uid in store.col("users"):
        return uid
    users = list(store.col("users").keys())
    return users[0] if users else None


@router.get("/summary")
def summary(user_id: str = None):
    """当前用户的台账汇总：用户信息 + 碳核算 + 交易 + 积分。"""
    uid = _current_user_id(user_id)
    user = store.col("users").get(uid)
    if not user:
        raise HTTPException(404, "用户不存在")

    # 碳核算
    reports = [r for r in store.col("reports").values() if r["user_id"] == uid]
    total_emission = round(sum(r.get("total_emission", 0) for r in reports), 3)

    # 交易记录：用户作为 maker（自己的订单）或 taker（taker:<uid> 标记）
    my_order_ids = {o["id"] for o in store.col("orders").values() if o["user_id"] == uid}
    tag = "taker:" + uid
    my_trades = []
    for t in store.col("trades").values():
        if (t["buy_order_id"] in my_order_ids or t["sell_order_id"] in my_order_ids
                or t["buy_order_id"] == tag or t["sell_order_id"] == tag):
            my_trades.append(t)
    my_trades.sort(key=lambda t: t["created_at"], reverse=True)
    trade_volume = round(sum(t["price"] * t["quantity"] for t in my_trades), 2)

    # 积分
    point_records = [p for p in store.col("points").values() if p["user_id"] == uid]
    point_records.sort(key=lambda p: p["created_at"], reverse=True)
    points_earned = sum(p["points"] for p in point_records if p["points"] > 0)
    points_redeemed = -sum(p["points"] for p in point_records if p["points"] < 0)

    return {
        "user": {
            "id": user["id"], "name": user["name"], "email": user.get("email"),
            "carbon_balance": user.get("carbon_balance", 0),
            "cash_balance": user.get("cash_balance", 0),
            "points_balance": user.get("points_balance", 0),
        },
        "carbon": {
            "report_count": len(reports),
            "total_emission": total_emission,
            "reports": sorted(reports, key=lambda r: r.get("created_at", ""), reverse=True),
        },
        "trade": {
            "trade_count": len(my_trades),
            "trade_volume": trade_volume,
            "trades": my_trades,
        },
        "points": {
            "balance": user.get("points_balance", 0),
            "earned": points_earned,
            "redeemed": points_redeemed,
            "records": point_records,
        },
    }


@router.get("/report/{report_id}.json")
def export_json(report_id: str):
    raw = store.col("reports").get(report_id)
    if not raw:
        raise HTTPException(404, "报告不存在")
    return JSONResponse(
        content=raw,
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.json"'},
    )


@router.get("/report/{report_id}.csv")
def export_csv(report_id: str):
    raw = store.col("reports").get(report_id)
    if not raw:
        raise HTTPException(404, "报告不存在")

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
