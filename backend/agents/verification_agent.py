"""Verification Agent —— 检查缺失项、单位冲突、异常值、适用范围与低置信结果。

对每个核算项执行以下检查，汇总为 warnings 列表并给出整体置信度：
    - 缺失：活动名 / 数量非正 / 单位缺失 / 未匹配到因子
    - 单位冲突：因子单位与活动单位不一致且无法换算
    - 异常值：活动数量超出该活动类型的典型上限
    - 适用范围：活动年份与所采用因子年份差距过大
    - 低置信：LLM 解析置信度低 / 因子自身置信度低 / 规则降级解析
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 各活动的典型数量上限（用于异常值判断，按标准单位）
TYPICAL_LIMIT: Dict[str, float] = {
    "kWh": 1_000_000.0, "km": 200_000.0, "人·km": 2_000_000.0,
    "L": 1_000_000.0, "m³": 500_000.0, "t": 100_000.0, "kg": 100_000_000.0,
    "MJ": 10_000_000.0, "GJ": 10_000.0, "小时": 200_000.0, "餐": 100_000.0, "份": 100_000.0,
}

# 因子年份与活动年份的最大允许差距
MAX_YEAR_GAP = 3


def _year_of(period: Optional[str]) -> Optional[int]:
    if not period:
        return None
    m = re.search(r"(20\d{2})", str(period))
    return int(m.group(1)) if m else None


def verify(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    """对整条流水线结果做校验。

    入参 pipeline 至少包含：
        items: List[ActivityItem]
        matches: List[factor_selector.select() 结果或 None]
        calcs: List[calculation.calculate() 结果或 None]
        llm_used: bool
    返回：
        {
          "warnings": List[str],
          "confidence": float,       # 0-1，所有项的平均置信度加权
          "status": "ok" | "warning" | "error",
        }
    """
    warnings: List[str] = []
    items = pipeline.get("items", [])
    matches = pipeline.get("matches", [])
    calcs = pipeline.get("calcs", [])

    if not items:
        return {"warnings": ["未解析到任何有效的排放活动"], "confidence": 0.0, "status": "error"}

    confidences: List[float] = []
    for idx, item in enumerate(items):
        match = matches[idx] if idx < len(matches) else None
        calc = calcs[idx] if idx < len(calcs) else None

        # 1) 缺失项
        if not item.activity:
            warnings.append(f"第 {idx + 1} 项：缺少活动名称，已跳过")
            continue
        if not item.amount or item.amount <= 0:
            warnings.append(f"「{item.activity}」：数量必须大于 0（当前 {item.amount}）")
        if not item.unit:
            warnings.append(f"「{item.activity}」：缺少单位，已按因子默认单位计算")

        # 2) 因子匹配
        if match is None:
            warnings.append(f"「{item.activity}」：未找到适用排放因子，该活动不参与计算")
            confidences.append(0.0)
            continue
        factor = match["factor"]

        # 3) 单位冲突
        if match["converted"]:
            warnings.append(
                f"「{item.activity}」：{match['conv_note']}"
            )
        elif "未换算" in match["conv_note"]:
            warnings.append(
                f"「{item.activity}」：{match['conv_note']}，结果按原单位近似"
            )

        # 4) 异常值
        limit = TYPICAL_LIMIT.get(item.unit)
        if limit and item.amount > limit:
            warnings.append(
                f"「{item.activity}」：数量 {item.amount} {item.unit} 超过典型上限（{limit:,.0f}），请确认输入"
            )

        # 5) 适用范围（因子年份 vs 活动年份）
        activity_year = _year_of(item.period)
        factor_year = match["year"]
        if activity_year and abs(activity_year - factor_year) > MAX_YEAR_GAP:
            warnings.append(
                f"「{item.activity}」：活动年份 {activity_year} 与因子版本 {factor_year} 差距 {abs(activity_year - factor_year)} 年，可能不适用"
            )

        # 6) 低置信
        item_conf = getattr(item, "confidence", 0.8) or 0.8
        factor_conf = float(factor.get("confidence", 0.8))
        if item_conf < 0.6:
            warnings.append(f"「{item.activity}」：解析置信度低（{item_conf:.2f}），请核对结构化结果")
        if factor_conf < 0.7:
            warnings.append(
                f"「{item.activity}」：因子「{factor['id']}」置信度低（{factor_conf:.2f}），结果仅供参考"
            )
        confidences.append(min(item_conf, factor_conf))

    # 规则降级提示
    if not pipeline.get("llm_used", False) and pipeline.get("fallback_reason"):
        if pipeline.get("fallback_reason") == "llm_not_configured":
            warnings.append("未配置大模型 API，已使用规则解析；配置后可在 .env 开启智能解析")
        elif pipeline.get("fallback_reason") == "llm_unavailable_or_empty":
            warnings.append("大模型调用不可用或未返回有效结果，已降级为规则解析")
        elif pipeline.get("fallback_reason") == "form":
            pass

    if not confidences:
        confidences = [0.0]
    confidence = round(sum(confidences) / len(confidences), 3)
    status = "ok"
    if warnings:
        status = "warning"
    if not any(calcs):
        status = "error"
    return {"warnings": warnings, "confidence": confidence, "status": status}
