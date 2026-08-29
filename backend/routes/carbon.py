"""AI 碳核算 Agent 接口。
- POST /api/carbon/calculate     提交核算（form 表单 / nl 自然语言两种模式）
- GET  /api/carbon/reports       历史报告列表
- GET  /api/carbon/reports/{id}  单份报告（含 Agent 轨迹）
- GET  /api/carbon/reports/{id}/ledger  报告对应的全流程台账
- POST /api/carbon/reports       手动创建报告（旧接口，同样走 Agent 流水线）
- GET  /api/carbon/factors       排放因子库（含 ID/版本/来源/适用范围）

核算由 agents 包编排：Activity Parser → Factor Selector → Calculation →
Verification → Recommendation → Ledger Writer。
大模型 API 由调用方通过环境变量提供，未配置时自动降级为规则解析。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from agents import ledger_writer, orchestrator
from agents.factor_selector import load_document
from bootstrap import repos
from schemas.carbon import CarbonCalcRequest, CarbonReport, CarbonReportCreate

router = APIRouter(prefix="/api/carbon", tags=["carbon"])


def _default_user_id() -> str:
    users = repos.users.list()
    return users[0].id if users else "anonymous"


@router.post("/calculate", response_model=CarbonReport)
def calculate(payload: CarbonCalcRequest):
    """提交核算：mode=form 用结构化明细，mode=nl 用自然语言。"""
    if payload.mode == "nl":
        if not payload.text or not payload.text.strip():
            raise HTTPException(400, "自然语言模式下 text 不能为空")
    elif not payload.items:
        raise HTTPException(400, "表单模式下 items 不能为空")

    result = orchestrator.run_pipeline(payload)
    report: CarbonReport = result["report"]
    pipeline = result["pipeline"]

    if not report.items:
        raise HTTPException(422, "未能识别出可核算的排放活动，请更具体地描述（含数量与单位）")

    # Ledger Writer：原子保存报告、明细、因子版本与 Agent 轨迹
    ledger = ledger_writer.build_ledger(report.id, pipeline, report.checksum)
    ledger = ledger_writer.write_ledger(repos, ledger)
    report.ledger_id = ledger.id
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


@router.get("/reports/{report_id}/ledger")
def get_report_ledger(report_id: str):
    """返回单份报告的全流程台账（含因子快照、公式、Agent 轨迹与校验哈希）。"""
    report = repos.reports.get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    if report.ledger_id:
        ledger = repos.ledgers.get(report.ledger_id)
        if ledger:
            return ledger
    ledgers = repos.ledgers.list()
    for l in ledgers:
        if l.report_id == report_id:
            return l
    raise HTTPException(404, "该报告尚未生成全流程台账")


@router.post("/reports", response_model=CarbonReport)
def create_report(payload: CarbonReportCreate):
    """手动创建报告（旧接口）：按 amount × factor 计算各项排放并走完整流水线。"""
    req = CarbonCalcRequest(
        user_id=payload.user_id,
        title=payload.title,
        period=payload.period,
        mode="form",
        items=[{
            "activity_type": i.activity,
            "amount": i.amount,
            "unit": i.unit,
        } for i in payload.items],
    )
    result = orchestrator.run_pipeline(req)
    report = result["report"]
    ledger = ledger_writer.build_ledger(report.id, result["pipeline"], report.checksum)
    ledger = ledger_writer.write_ledger(repos, ledger)
    report.ledger_id = ledger.id
    repos.reports.create(report)
    return report


@router.get("/ledgers")
def list_ledgers(limit: int = 20):
    """全流程台账列表（含 Agent 轨迹与校验哈希），用于审计追溯。"""
    ledgers = sorted(repos.ledgers.list(), key=lambda l: l.created_at, reverse=True)
    return ledgers[:max(1, min(limit, 200))]


@router.get("/factors")
def factors():
    """返回排放因子库文档（schema_version + 因子条目，含 ID、数值、版本、来源与适用范围）。"""
    return load_document()
