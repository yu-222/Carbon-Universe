"""碳核算相关模型：活动明细、报告与请求体。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from schemas.common import BaseRecord


class CarbonItem(BaseModel):
    """单项排放活动数据。"""
    category: str                   # 类别，如 电力/交通/差旅
    activity: str                   # 活动描述
    amount: float                   # 活动量
    unit: str                       # 单位，如 kWh/km/L
    factor: float                   # 排放因子 (kgCO2e/unit)
    emission: float = 0.0           # 计算后的排放 (kgCO2e)


class CarbonReport(BaseRecord):
    user_id: str
    title: str
    period: str                     # 核算周期，如 2026-Q1
    items: List[CarbonItem] = []
    total_emission: float = 0.0     # 总排放 (kgCO2e)
    ai_summary: Optional[str] = None
    suggestions: List[str] = []     # 减碳建议
    source: str = "form"            # 数据来源：form / nl


class CarbonReportCreate(BaseModel):
    user_id: str
    title: str
    period: str
    items: List[CarbonItem] = []


class CalcFormItem(BaseModel):
    """表单模式单项输入：活动类型 + 数量 + 单位。"""
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
