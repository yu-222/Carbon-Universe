"""Ledger Writer —— 原子保存报告、明细、因子版本与 Agent 轨迹。

职责：
    1. 生成报告校验哈希（sha256，对报告核心内容排序后序列化）
    2. 组装 EmissionLedger：原始输入、活动项、因子快照、公式、模型信息、
       Agent 轨迹（每步 agent/status/duration_ms）、置信度、警告、报告版本
    3. 通过 JsonStore 原子落盘（临时文件 + os.replace）
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from schemas.carbon import EmissionLedger


def checksum_of(payload: Dict[str, Any]) -> str:
    """对报告核心内容生成 SHA-256 校验哈希（排序序列化，保证稳定）。"""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_ledger(
    report_id: str,
    pipeline: Dict[str, Any],
    report_checksum: str,
) -> EmissionLedger:
    """由流水线上下文组装 ledger 记录。"""
    items = pipeline.get("items", [])
    matches = pipeline.get("matches", [])
    calcs = pipeline.get("calcs", [])
    trace = pipeline.get("trace", [])

    activities = [it.to_dict() for it in items]
    factors: List[Dict[str, Any]] = []
    formulas: List[str] = []
    for idx, item in enumerate(items):
        match = matches[idx] if idx < len(matches) else None
        calc = calcs[idx] if idx < len(calcs) else None
        if match is not None:
            f = match["factor"]
            factors.append({
                "activity": item.activity,
                "region": item.region,
                "factor_id": f["id"],
                "factor_value": match["factor_value"],
                "factor_unit": match["factor_unit"],
                "version": f["version"],
                "source": f["source"],
                "scope": f["scope"],
                "year": f["year"],
                "converted": match["converted"],
            })
        if calc is not None:
            formulas.append(calc["formula"])

    total = round(sum(c["emission"] for c in calcs if c), 6)

    return EmissionLedger(
        report_id=report_id,
        raw_input=pipeline.get("raw_input"),
        input_type=pipeline.get("input_type", "form"),
        activities=activities,
        factors=factors,
        formulas=formulas,
        total_emission=total,
        result_unit="kgCO₂e",
        model_name=pipeline.get("model_name"),
        prompt_version=pipeline.get("prompt_version"),
        tool_calls=pipeline.get("tool_calls", []),
        duration_ms=pipeline.get("duration_ms", 0),
        status=pipeline.get("status", "ok"),
        confidence=pipeline.get("confidence", 0.8),
        warnings=pipeline.get("warnings", []),
        human_edited=False,
        report_version=pipeline.get("report_version", "1.0"),
        checksum=report_checksum,
        trace=trace,
    )


def write_ledger(repos, ledger: EmissionLedger) -> EmissionLedger:
    """原子保存 ledger（底层 JsonStore 写临时文件后 os.replace）。"""
    return repos.ledgers.create(ledger)
