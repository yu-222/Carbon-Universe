"""碳核算相关模型：活动明细、报告、核算请求与全流程台账。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from schemas.common import BaseRecord


class CarbonItem(BaseModel):
    """单项排放活动数据（Agent 链路产出）。"""
    category: str                   # 类别，如 电力/交通/工业
    activity: str                   # 活动描述
    amount: float                   # 活动量
    unit: str                       # 单位，如 kWh/km/L/t
    factor: float                   # 排放因子 (kgCO2e/unit)
    emission: float = 0.0           # 计算后的排放 (kgCO2e)
    # —— Agent 扩展字段（记录完整溯源）——
    region: Optional[str] = None    # 地区
    period: Optional[str] = None    # 时间
    industry: Optional[str] = None  # 行业
    boundary: Optional[str] = None  # 核算边界
    factor_id: Optional[str] = None         # 排放因子 ID
    factor_version: Optional[str] = None    # 因子版本
    factor_source: Optional[str] = None     # 因子来源
    factor_scope: Optional[str] = None      # 因子适用范围
    factor_confidence: Optional[float] = None  # 因子置信度
    factor_unit: Optional[str] = None       # 因子库原始单位
    formula: Optional[str] = None           # 计算公式
    result_unit: str = "kgCO₂e"             # 结果单位
    confidence: float = 0.8                 # 该项综合置信度


class CarbonReport(BaseRecord):
    user_id: str
    title: str
    period: str                     # 核算周期，如 2026-Q1 / 即时核算
    items: List[CarbonItem] = []
    total_emission: float = 0.0     # 总排放 (kgCO2e)
    ai_summary: Optional[str] = None
    suggestions: List[str] = []     # 减碳建议
    source: str = "form"            # 数据来源：form / nl
    # —— Agent 扩展字段（全流程可追溯）——
    raw_input: Optional[str] = None        # 原始输入
    input_type: str = "form"               # 输入类型：form / nl
    region: Optional[str] = None           # 核算地区汇总
    model_name: Optional[str] = None       # LLM 模型名 / rule-based
    prompt_version: Optional[str] = None   # Prompt 版本
    duration_ms: Optional[int] = None      # 全流程耗时
    pipeline_status: str = "ok"            # 流水线状态：ok/warning/error
    warnings: List[str] = []               # 校验警告
    confidence: float = 0.8                # 整体置信度
    report_version: str = "1.0"            # 报告版本
    checksum: Optional[str] = None         # 校验哈希 (sha256)
    ledger_id: Optional[str] = None        # 关联台账记录
    trace: List[Dict[str, Any]] = []       # Agent 轨迹


class EmissionLedger(BaseRecord):
    """核算全流程台账：报告 + 明细 + 因子版本 + Agent 轨迹 + 校验哈希。"""
    report_id: str
    raw_input: Optional[str] = None
    input_type: str = "form"
    activities: List[Dict[str, Any]] = []   # 结构化活动项
    factors: List[Dict[str, Any]] = []      # 因子版本快照
    formulas: List[str] = []                # 计算公式
    total_emission: float = 0.0
    result_unit: str = "kgCO₂e"
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    tool_calls: List[str] = []              # 工具调用记录
    duration_ms: int = 0
    status: str = "ok"
    confidence: float = 0.8
    warnings: List[str] = []
    human_edited: bool = False              # 人工修改标记
    report_version: str = "1.0"
    checksum: str = ""                      # 校验哈希
    trace: List[Dict[str, Any]] = []        # Agent 轨迹


class CarbonReportCreate(BaseModel):
    user_id: str
    title: str
    period: str
    items: List[CarbonItem] = []


class CalcFormItem(BaseModel):
    """表单模式单项输入：活动类型 + 数量 + 单位。"""
    activity_type: str              # 用电 / 出行 / 餐饮 / 办公 / 电力 ...
    amount: float
    unit: Optional[str] = None      # 缺省时由后端按类型推断
    region: Optional[str] = None    # 地区，缺省 中国
    period: Optional[str] = None    # 时间，缺省 2026 年


class CarbonCalcRequest(BaseModel):
    user_id: Optional[str] = None
    mode: str = "form"              # form | nl
    title: Optional[str] = None
    period: Optional[str] = None
    region: Optional[str] = None    # 默认地区（nl 模式兜底）
    items: List[CalcFormItem] = []  # mode=form 时使用
    text: Optional[str] = None      # mode=nl 时使用（自然语言）
