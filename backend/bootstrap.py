"""应用装配：JsonStore 实例 + Repository 注册表（全局单例）。

路由统一从这里拿仓库：from bootstrap import repos
"""
from __future__ import annotations

import os

from repositories.json_repository import JsonRepository
from repositories.registry import Registry
from schemas.carbon import CarbonReport
from schemas.market import Order, Trade
from schemas.points import PointsRecord
from schemas.users import User
from storage.json_store import JsonStore

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# collection(存储文件名) -> Pydantic 模型（加载/写入时校验）
SCHEMAS = {
    "users": User,
    "calculation_reports": CarbonReport,
    "orders": Order,
    "trades": Trade,
    "points_ledger": PointsRecord,
}

store = JsonStore(DATA_DIR, SCHEMAS)

repos = Registry()
repos.register("users", JsonRepository(store, User, collection="users"))
repos.register("reports", JsonRepository(store, CarbonReport, collection="calculation_reports", append_only=True))
repos.register("orders", JsonRepository(store, Order, collection="orders"))
repos.register("trades", JsonRepository(store, Trade, collection="trades", append_only=True))
repos.register("points", JsonRepository(store, PointsRecord, collection="points_ledger", append_only=True))
