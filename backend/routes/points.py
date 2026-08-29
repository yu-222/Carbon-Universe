"""碳普惠激励系统 —— 打卡减碳行为得积分、查询记录、积分抵扣。

- GET  /api/points/balance   积分余额
- POST /api/points/checkin   打卡（behavior 行为类型）
- GET  /api/points/history   积分变动记录
- POST /api/points/redeem    积分抵扣（扣减积分）

"当前用户" 默认取用户列表第一个；可通过入参 user_id 指定。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bootstrap import repos
from schemas.points import PointsReason, PointsRecord
from schemas.users import User

router = APIRouter(prefix="/api/points", tags=["points"])


# 打卡行为表：行为 key -> (展示名, 积分, 对应 reason)
BEHAVIORS = {
    "walk_commute": {"label": "步行通勤", "points": 50, "reason": PointsReason.LOW_CARBON_TRAVEL},
    "light_off":    {"label": "关灯1小时", "points": 20, "reason": PointsReason.ENERGY_SAVING},
    "own_cup":      {"label": "自带水杯", "points": 15, "reason": PointsReason.RECYCLE},
    "recycle":      {"label": "垃圾分类回收", "points": 30, "reason": PointsReason.RECYCLE},
    "public_transit": {"label": "公共交通出行", "points": 40, "reason": PointsReason.LOW_CARBON_TRAVEL},
}


class CheckinReq(BaseModel):
    user_id: Optional[str] = None
    behavior: str


class RedeemReq(BaseModel):
    user_id: Optional[str] = None
    points: int
    description: Optional[str] = None


def _current_user_id(uid: Optional[str]) -> str:
    if uid and repos.users.get(uid):
        return uid
    users = repos.users.list()
    if not users:
        raise HTTPException(400, "系统暂无用户")
    return users[0].id


def _get_user(uid: str) -> User:
    u = repos.users.get(uid)
    if not u:
        raise HTTPException(404, "用户不存在")
    return u


def _apply(user: User, reason: PointsReason, points: int, description: str) -> PointsRecord:
    record = PointsRecord(user_id=user.id, reason=reason, points=points, description=description)
    repos.points.create(record)  # 积分流水追加，不覆盖历史
    repos.users.update(user.id, {"points_balance": user.points_balance + points})
    return record


@router.get("/behaviors")
def behaviors():
    """返回可打卡行为列表，供前端渲染按钮。"""
    return [{"key": k, "label": v["label"], "points": v["points"]} for k, v in BEHAVIORS.items()]


@router.get("/balance")
def balance(user_id: Optional[str] = None):
    uid = _current_user_id(user_id)
    u = _get_user(uid)
    return {"user_id": u.id, "name": u.name, "points_balance": u.points_balance}


@router.post("/checkin", response_model=PointsRecord)
def checkin(payload: CheckinReq):
    meta = BEHAVIORS.get(payload.behavior)
    if not meta:
        raise HTTPException(400, "未知的打卡行为")
    u = _get_user(_current_user_id(payload.user_id))
    return _apply(u, meta["reason"], meta["points"], f"打卡：{meta['label']}")


@router.get("/history", response_model=List[PointsRecord])
def history(user_id: Optional[str] = None):
    uid = _current_user_id(user_id)
    records = [p for p in repos.points.list() if p.user_id == uid]
    return sorted(records, key=lambda r: r.created_at, reverse=True)


@router.post("/redeem", response_model=PointsRecord)
def redeem(payload: RedeemReq):
    if payload.points <= 0:
        raise HTTPException(400, "抵扣积分必须大于 0")
    u = _get_user(_current_user_id(payload.user_id))
    if u.points_balance < payload.points:
        raise HTTPException(400, f"积分不足（余额 {u.points_balance}，需 {payload.points}）")
    desc = payload.description or "积分抵扣"
    return _apply(u, PointsReason.REDEEM, -payload.points, desc)
