"""Orchestrator Agent —— 编排整个 AI 碳核算流水线。

链路：
    用户输入
      → Activity Parser    （LLM 一次调用完成解析与建议素材 / 规则降级）
      → Factor Selector    （按地区·行业·年份·单位匹配因子，含单位换算）
      → Calculation Service（确定性 amount × factor，不依赖 LLM 心算）
      → Verification Agent （缺失项 / 单位 / 异常值 / 适用范围 / 低置信）
      → Recommendation     （LLM 建议或规则库）
      → Ledger Writer      （原子保存报告与全流程 Agent 轨迹）

状态与重试：
    - 每一步记录 agent / status / duration_ms / detail，写入 trace
    - LLM 调用失败自动降级到规则解析，不阻断整条链路
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents import activity_parser, calculation, factor_selector, ledger_writer, recommendation_agent, verification_agent
from schemas.carbon import CarbonItem, CarbonReport

REPORT_VERSION = "1.0"


def _trace_step(agent: str, status: str, started: float, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "agent": agent,
        "status": status,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "detail": detail or {},
    }


def run_pipeline(payload) -> Dict[str, Any]:
    """执行一次完整核算，返回可直接落库的 CarbonReport 及其流水线上下文。

    参数 payload：schemas.carbon.CarbonCalcRequest
    """
    started = time.perf_counter()
    trace: List[Dict[str, Any]] = []
    tool_calls: List[str] = []

    # 0) 输入上下文
    input_type = payload.mode if payload.mode in ("form", "nl") else "form"
    raw_input = payload.text if input_type == "nl" else None
    if input_type == "form" and payload.items:
        raw_input = "; ".join(
            f"{i.activity_type} {i.amount} {i.unit or ''}".strip() for i in payload.items
        )

    # 1) Activity Parser
    t0 = time.perf_counter()
    parsed = activity_parser.parse_activities(
        payload.text if input_type == "nl" else None,
        form_items=payload.items if input_type == "form" else None,
    )
    items = parsed["items"]
    if parsed["llm_used"]:
        tool_calls.append(f"chat.completions({parsed['model']})")
    trace.append(_trace_step(
        "activity_parser",
        "ok" if items else "warning",
        t0,
        {
            "items_count": len(items),
            "llm_used": parsed["llm_used"],
            "prompt_version": parsed["prompt_version"],
            "duration_ms": parsed["duration_ms"],
        },
    ))

    # 2) Factor Selector + 3) Calculation Service（逐项）
    matches: List[Optional[Dict[str, Any]]] = []
    calcs: List[Optional[Dict[str, Any]]] = []
    t0 = time.perf_counter()
    for item in items:
        match = factor_selector.select(item)
        matches.append(match)
        if match is None:
            calcs.append(None)
            continue
        calc = calculation.calculate(
            amount=item.amount,
            factor_value=match["factor_value"],
            activity_unit=item.unit,
            factor_unit=match["factor_unit"],
        )
        calcs.append(calc)
    trace.append(_trace_step(
        "factor_selector",
        "ok" if any(m for m in matches) else "warning",
        t0,
        {"matched": sum(1 for m in matches if m), "total": len(items)},
    ))
    trace.append(_trace_step(
        "calculation",
        "ok" if any(c for c in calcs) else "error",
        t0,
        {"formula_count": sum(1 for c in calcs if c)},
    ))

    # 4) Verification
    t0 = time.perf_counter()
    verify_result = verification_agent.verify({
        "items": items,
        "matches": matches,
        "calcs": calcs,
        "llm_used": parsed["llm_used"],
        "fallback_reason": parsed.get("fallback_reason"),
    })
    trace.append(_trace_step(
        "verification",
        verify_result["status"],
        t0,
        {"warnings_count": len(verify_result["warnings"]), "confidence": verify_result["confidence"]},
    ))

    # 5) Recommendation
    t0 = time.perf_counter()
    suggestions = recommendation_agent.recommend({
        "items": items,
        "calcs": calcs,
        "llm_suggestions": parsed.get("llm_suggestions", []),
    })
    trace.append(_trace_step(
        "recommendation",
        "ok",
        t0,
        {"suggestions_count": len(suggestions)},
    ))

    # 组装 CarbonItem 与报告
    carbon_items: List[CarbonItem] = []
    for idx, item in enumerate(items):
        match = matches[idx] if idx < len(matches) else None
        calc = calcs[idx] if idx < len(calcs) else None
        factor = match["factor"] if match else None
        carbon_items.append(CarbonItem(
            category=factor["category"] if factor else "未分类",
            activity=item.activity,
            amount=item.amount,
            unit=item.unit or (match["factor_unit"] if match else ""),
            factor=calc["factor_value"] if calc else 0.0,
            emission=calc["emission"] if calc else 0.0,
            region=item.region,
            period=item.period,
            industry=item.industry or (factor.get("industry", "") if factor else ""),
            boundary=item.boundary,
            factor_id=factor["id"] if factor else None,
            factor_version=factor["version"] if factor else None,
            factor_source=factor["source"] if factor else None,
            factor_scope=factor["scope"] if factor else None,
            factor_confidence=float(factor["confidence"]) if factor else None,
            factor_unit=match["factor_unit"] if match else None,
            formula=calc["formula"] if calc else None,
            result_unit="kgCO₂e",
            confidence=min(getattr(item, "confidence", 0.8), float(factor["confidence"]) if factor else 0.8),
        ))
    total_emission = round(sum(i.emission for i in carbon_items), 6)

    # 摘要
    if carbon_items:
        top = max(carbon_items, key=lambda i: i.emission)
        summary = (
            f"本次核算共 {len(carbon_items)} 项活动，合计排放约 {total_emission} kgCO₂e，"
            f"其中「{top.activity}」为主要排放项（{top.emission} kg，占比 "
            f"{round(top.emission / total_emission * 100, 1) if total_emission else 0}%）。"
        )
    else:
        summary = "未识别到有效的排放活动，请补充活动类型与数量后重试。"

    # 6) Ledger Writer
    t0 = time.perf_counter()
    duration_ms = int((time.perf_counter() - started) * 1000)
    pipeline = {
        "items": items,
        "matches": matches,
        "calcs": calcs,
        "trace": trace,
        "raw_input": raw_input,
        "input_type": input_type,
        "model_name": parsed.get("model") or "rule-based",
        "prompt_version": parsed.get("prompt_version"),
        "tool_calls": tool_calls,
        "duration_ms": duration_ms,
        "status": verify_result["status"],
        "confidence": verify_result["confidence"],
        "warnings": verify_result["warnings"],
        "report_version": REPORT_VERSION,
        "llm_suggestions": parsed.get("llm_suggestions", []),
    }

    report = CarbonReport(
        user_id=payload.user_id or _default_user_id(),
        title=payload.title or ("自然语言核算" if input_type == "nl" else "碳足迹核算"),
        period=payload.period or "即时核算",
        items=carbon_items,
        total_emission=total_emission,
        ai_summary=summary,
        suggestions=suggestions,
        source=input_type,
        raw_input=raw_input,
        input_type=input_type,
        region=",".join(sorted({i.region for i in items})) or None,
        model_name=parsed.get("model") or "rule-based",
        prompt_version=parsed.get("prompt_version"),
        duration_ms=duration_ms,
        pipeline_status=verify_result["status"],
        warnings=verify_result["warnings"],
        confidence=verify_result["confidence"],
        report_version=REPORT_VERSION,
        trace=trace,
    )
    # 计算校验哈希（含报告核心内容）
    report.checksum = ledger_writer.checksum_of({
        "user_id": report.user_id,
        "title": report.title,
        "period": report.period,
        "items": [i.model_dump() for i in report.items],
        "total_emission": report.total_emission,
        "pipeline_status": report.pipeline_status,
        "report_version": report.report_version,
    })
    return {"report": report, "pipeline": pipeline}


def _default_user_id() -> str:
    from bootstrap import repos
    users = repos.users.list()
    return users[0].id if users else "anonymous"
