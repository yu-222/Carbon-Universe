"""Carbon Universe 碳宇 —— FastAPI 入口。
包含 CORS 配置、全局错误处理、启动填充模拟数据、所有路由注册。
运行： uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from store import store, seed_if_empty
from models import User, UserCreate
from routes import carbon, exchange, points, export

app = FastAPI(title="Carbon Universe 碳宇 API", version="1.0.0")

# --- CORS：MVP 阶段允许全部来源，方便前端 CDN 页面直接联调 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 全局错误处理：统一返回 {"error": "描述"} ---
@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    # 取第一条校验错误，转成友好中文提示
    err = exc.errors()[0] if exc.errors() else {}
    loc = " -> ".join(str(x) for x in err.get("loc", []) if x != "body")
    msg = err.get("msg", "请求参数有误")
    return JSONResponse(status_code=422, content={"error": f"参数错误：{loc} {msg}".strip()})


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": f"服务器内部错误：{exc}"})


@app.on_event("startup")
def _startup() -> None:
    seed_if_empty()


@app.get("/")
def root():
    return {"app": "Carbon Universe 碳宇", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/overview")
def overview():
    """首页数据概览：总核算次数、总交易量(金额)、总积分。"""
    reports = store.col("reports")
    trades = store.col("trades")
    total_calc = len(reports)
    total_trade_volume = round(sum(t["price"] * t["quantity"] for t in trades.values()), 2)
    total_trade_count = len(trades)
    total_points = sum(u.get("points_balance", 0) for u in store.col("users").values())
    total_emission = round(sum(r.get("total_emission", 0) for r in reports.values()), 3)
    return {
        "total_calc": total_calc,
        "total_emission": total_emission,
        "total_trade_count": total_trade_count,
        "total_trade_volume": total_trade_volume,
        "total_points": total_points,
    }


# --- 用户接口（基础，供各模块引用）---
@app.get("/api/users")
def list_users():
    return list(store.col("users").values())


@app.post("/api/users", response_model=User)
def create_user(payload: UserCreate):
    user = User(**payload.model_dump())
    store.put("users", user.id, user.model_dump())
    return user


# --- 业务路由注册 ---
app.include_router(carbon.router)
app.include_router(exchange.router)
app.include_router(points.router)
app.include_router(export.router)
