"""AI 智能碳足迹核算接口。
- POST /api/carbon/calculate     提交核算（form 表单 / nl 自然语言两种模式）
- GET  /api/carbon/reports       历史报告列表
- GET  /api/carbon/reports/{id}  单份报告
- POST /api/carbon/reports       手动创建报告（保留旧接口）

大模型调用由 mock_carbon_ai() 占位：根据输入关键词返回合理的碳排放估算与明细，
后续替换为真实 LLM 时保持相同的返回结构即可。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from bootstrap import repos
from schemas.carbon import (
    CalcFormItem,
    CarbonCalcRequest,
    CarbonItem,
    CarbonReport,
    CarbonReportCreate,
)

router = APIRouter(prefix="/api/carbon", tags=["carbon"])


# ---------------------------------------------------------------------------
# 排放因子表（kgCO2e / 单位）—— 供 mock AI 与表单核算共用
# ---------------------------------------------------------------------------
FACTORS: Dict[str, Dict[str, object]] = {
    "用电": {"factor": 0.5, "unit": "度", "category": "电力"},
    "出行": {"factor": 0.2, "unit": "km", "category": "交通"},
    "餐饮": {"factor": 1.8, "unit": "餐", "category": "餐饮"},
    "办公": {"factor": 0.6, "unit": "小时", "category": "办公"},
}

# 自然语言关键词 → 活动类型 的映射（按优先级排序）
NL_KEYWORDS: List[Tuple[str, str]] = [
    ("开车", "出行"), ("驾车", "出行"), ("公里", "出行"), ("km", "出行"),
    ("打车", "出行"), ("坐车", "出行"), ("骑", "出行"),
    ("用电", "用电"), ("度电", "用电"), ("度", "用电"),
    ("空调", "办公"), ("办公", "办公"), ("电脑", "办公"), ("加班", "办公"),
    ("外卖", "餐饮"), ("吃", "餐饮"), ("餐", "餐饮"), ("饭", "餐饮"),
]

# 各活动类型的减碳建议
SUGGESTION_BANK: Dict[str, str] = {
    "出行": "尽量选择公共交通、拼车或骑行，可显著降低出行碳排放。",
    "用电": "更换节能电器、随手关灯，并优先采购绿电。",
    "办公": "合理设置空调温度（夏季≥26℃），下班关闭待机设备。",
    "餐饮": "减少一次性餐具与食物浪费，适当增加植物性饮食。",
}


# ---------------------------------------------------------------------------
# 自然语言解析：抽取“数字 + 关键词”片段
# ---------------------------------------------------------------------------
def _parse_nl(text: str) -> List[CalcFormItem]:
    """把自然语言拆成若干 (活动类型, 数量) 片段。
    规则：找到每个数字，在其前后就近窗口内匹配一个活动关键词。
    """
    items: List[CalcFormItem] = []
    # 紧邻数字的单位词，优先级最高（避免被窗口内其它关键词抢占）
    unit_rules: List[Tuple[str, str]] = [
        ("小时", "办公"), ("公里", "出行"), ("km", "出行"),
        ("度", "用电"), ("餐", "餐饮"), ("顿", "餐饮"),
    ]
    for m in re.finditer(r"(\d+(?:\.\d+)?)", text):
        num = float(m.group(1))
        tail = text[m.end(): m.end() + 6]                   # 数字后紧邻片段（判单位）
        window = text[max(0, m.start() - 8): m.end() + 10]  # 数字前后窗口（判动作）
        activity: Optional[str] = None
        # 1) 先按紧邻单位判定
        for kw, act in unit_rules:
            if tail.lower().startswith(kw) or kw in tail:
                activity = act
                break
        # 2) 再按窗口内动作关键词兜底
        if activity is None:
            for kw, act in NL_KEYWORDS:
                if kw in window:
                    activity = act
                    break
        if activity:
            items.append(CalcFormItem(activity_type=activity, amount=num))
    return items


# ---------------------------------------------------------------------------
# 模拟大模型：输入活动明细，输出排放数值 + 分项 + 摘要 + 建议
# ---------------------------------------------------------------------------
def mock_carbon_ai(form_items: List[CalcFormItem]) -> Dict[str, object]:
    """占位版“AI 核算”。返回结构与真实 LLM 对齐：
    { "items": [CarbonItem...], "total": float, "summary": str, "suggestions": [str] }
    TODO: 替换为真实大模型调用（保持返回结构不变）。
    """
    carbon_items: List[CarbonItem] = []
    for fi in form_items:
        meta = FACTORS.get(fi.activity_type)
        if not meta:
            continue
        factor = float(meta["factor"])
        unit = fi.unit or str(meta["unit"])
        emission = round(fi.amount * factor, 3)
        carbon_items.append(CarbonItem(
            category=str(meta["category"]),
            activity=fi.activity_type,
            amount=fi.amount,
            unit=unit,
            factor=factor,
            emission=emission,
        ))

    total = round(sum(i.emission for i in carbon_items), 3)

    if carbon_items:
        top = max(carbon_items, key=lambda i: i.emission)
        summary = (
            f"（模拟AI）本次核算共 {len(carbon_items)} 项活动，"
            f"合计碳排放约 {total} kgCO2e，其中「{top.activity}」占比最高"
            f"（{top.emission} kg）。"
        )
    else:
        summary = "（模拟AI）未识别到有效的排放活动，请补充数量与活动类型。"

    seen = set()
    suggestions: List[str] = []
    for i in carbon_items:
        tip = SUGGESTION_BANK.get(i.activity)
        if tip and tip not in seen:
            seen.add(tip)
            suggestions.append(tip)

    return {
        "items": carbon_items,
        "total": total,
        "summary": summary,
        "suggestions": suggestions,
    }


def _default_user_id() -> str:
    users = repos.users.list()
    return users[0].id if users else "anonymous"


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------
@router.post("/calculate", response_model=CarbonReport)
def calculate(payload: CarbonCalcRequest):
    """提交核算：mode=form 用结构化明细，mode=nl 用自然语言。"""
    if payload.mode == "nl":
        if not payload.text or not payload.text.strip():
            raise HTTPException(400, "自然语言模式下 text 不能为空")
        form_items = _parse_nl(payload.text)
        if not form_items:
            raise HTTPException(422, "未能从文本中识别出可核算的活动，请更具体地描述（含数量）")
    else:
        if not payload.items:
            raise HTTPException(400, "表单模式下 items 不能为空")
        form_items = payload.items

    ai = mock_carbon_ai(form_items)

    report = CarbonReport(
        user_id=payload.user_id or _default_user_id(),
        title=payload.title or ("自然语言核算" if payload.mode == "nl" else "碳足迹核算"),
        period=payload.period or "即时核算",
        items=ai["items"],
        total_emission=ai["total"],
        ai_summary=ai["summary"],
        suggestions=ai["suggestions"],
        source=payload.mode,
    )
    repos.reports.create(report)
    return report


@router.get("/reports", response_model=List[CarbonReport])
def list_reports(user_id: Optional[str] = None):
    reports = repos.reports.list()
    if user_id:
        reports = [r for r in reports if r.user_id == user_id]
    return sorted(reports, key=lambda r: r.created_at, reverse=True)


@router.get("/reports/{report_id}", response_model=CarbonReport)
def get_report(report_id: str):
    report = repos.reports.get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    return report


@router.post("/reports", response_model=CarbonReport)
def create_report(payload: CarbonReportCreate):
    """手动创建报告（保留旧接口）：按 amount * factor 计算各项排放。"""
    report = CarbonReport(**payload.model_dump())
    for item in report.items:
        item.emission = round(item.amount * item.factor, 3)
    report.total_emission = round(sum(i.emission for i in report.items), 3)
    ai = mock_carbon_ai([
        CalcFormItem(activity_type=i.activity, amount=i.amount, unit=i.unit)
        for i in report.items
    ])
    report.ai_summary = ai["summary"]
    report.suggestions = ai["suggestions"]
    repos.reports.create(report)
    return report


@router.get("/factors")
def factors():
    """返回可选活动类型及默认因子，供前端表单下拉。"""
    return FACTORS
