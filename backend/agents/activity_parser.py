"""Activity Parser Agent —— 将自然语言输入解析为结构化活动项。

职责：
    用户输入 → 活动名称 / 数量 / 标准单位 / 地区 / 时间 / 行业 / 核算边界

首版策略：一次 LLM 调用同时产出结构化活动项与减排建议素材；
未配置 LLM 或调用失败时，降级到确定性规则解析（关键词 + 数字抽取），
保证接口在无大模型环境下依然可用。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.llm import chat_completion_json

PROMPT_VERSION = "2026.08.29-v1"

# 单位别名 → 因子库标准单位
UNIT_ALIAS = {
    "度": "kWh", "度电": "kWh", "千瓦时": "kWh", "kwh": "kWh", "KWH": "kWh",
    "度点": "kWh", "电": "kWh",
    "公里": "km", "千米": "km", "km": "km", "里": "km",
    "升": "L", "L": "L", "l": "L", "公升": "L",
    "立方米": "m³", "方": "m³", "立方": "m³", "m3": "m³",
    "吨": "t", "t": "t", "万吨": "万t",
    "千克": "kg", "公斤": "kg", "kg": "kg",
    "人公里": "人·km", "人千米": "人·km", "人次": "人·km", "人·公里": "人·km",
    "小时": "小时", "时": "小时", "h": "小时",
    "餐": "餐", "顿": "餐", "份": "份", "单": "份",
    "兆焦": "MJ", "吉焦": "GJ", "mj": "MJ",
}

# 规则解析：关键词 → 活动类型（按优先级排序，与旧版本对齐）
KEYWORD_RULES: List[tuple] = [
    ("地铁", "地铁"), ("高铁", "地铁"), ("火车", "地铁"), ("轨道交通", "地铁"),
    ("公交", "公交"), ("公共汽车", "公交"),
    ("开车", "开车"), ("驾车", "开车"), ("驾驶", "开车"), ("打车", "开车"), ("坐车", "开车"),
    ("飞机", "飞机"), ("航班", "飞机"), ("航空", "飞机"), ("乘机", "飞机"),
    ("用电", "用电"), ("度电", "用电"), ("度", "用电"), ("电费", "用电"),
    ("天然气", "天然气"), ("燃气", "天然气"),
    ("柴油", "柴油"),
    ("汽油", "汽油"),
    ("钢铁", "钢铁"), ("钢材", "钢铁"), ("粗钢", "钢铁"), ("炼钢", "钢铁"),
    ("水泥", "水泥"),
    ("电解铝", "铝"), ("铝", "铝"),
    ("供热", "供热"), ("供暖", "供热"), ("取暖", "供热"),
    ("蒸汽", "蒸汽"),
    ("外卖", "外卖"), ("点外卖", "外卖"),
    ("办公", "办公"), ("空调", "办公"), ("电脑", "办公"), ("加班", "办公"),
    ("吃饭", "餐饮"), ("餐饮", "餐饮"), ("餐", "餐饮"), ("饭", "餐饮"), ("外卖", "外卖"),
    ("居家", "居家"), ("在家", "居家"),
]

SYSTEM_PROMPT = """你是一个企业碳排放活动解析器。请把用户的描述解析为结构化活动项，并基于主要排放活动给出可执行减排建议。

必须只输出一个 JSON 对象，结构如下：
{
  "activities": [
    {
      "activity": "活动名称（中文，贴合因子库：用电/开车/飞机/公交/地铁/天然气/柴油/汽油/钢铁/电炉钢/水泥/铝/供热/蒸汽/外卖/餐饮/办公/居家）",
      "description": "原始描述片段",
      "amount": 数量（数字，仅数值）,
      "unit": "标准单位（kWh/km/L/m³/t/kg/MJ/人·km/小时/餐/份）",
      "region": "所在地区（默认 中国）",
      "period": "发生时间（默认 2026 年）",
      "industry": "所属行业（办公/生产/运输/建筑/餐饮/生活）",
      "boundary": "核算边界（如 范围二-外购电力 / 范围一-燃料燃烧 / 范围三-差旅）"
    }
  ],
  "suggestions": ["按减排优先级给出 1-3 条可执行建议"]
}

要求：
1. 提取描述中的全部排放活动，一条不落，每个活动生成一个 activity 对象。
2. 单位必须换算成标准单位：度/度电→kWh，公里→km，升→L，吨→t，公斤/千克→kg，立方米→m³。
3. 地区未指明时用"中国"，时间未指明时用"2026 年"。
4. 文本无法识别任何活动时，activities 返回空数组。
5. 只输出 JSON，不要输出任何解释文字。"""


class ActivityItem:
    """结构化活动项（Agent 内部使用的纯数据对象）。"""

    __slots__ = ("activity", "description", "amount", "unit", "region",
                 "period", "industry", "boundary", "confidence")

    def __init__(self, activity: str, amount: float, unit: str,
                 description: str = "", region: str = "中国",
                 period: str = "2026 年", industry: str = "",
                 boundary: str = "", confidence: float = 0.8) -> None:
        self.activity = activity
        self.description = description
        self.amount = amount
        self.unit = unit
        self.region = region or "中国"
        self.period = period or "2026 年"
        self.industry = industry
        self.boundary = boundary
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity": self.activity,
            "description": self.description,
            "amount": self.amount,
            "unit": self.unit,
            "region": self.region,
            "period": self.period,
            "industry": self.industry,
            "boundary": self.boundary,
            "confidence": self.confidence,
        }


def _normalize_unit(unit: str) -> str:
    u = (unit or "").strip().lower()
    return UNIT_ALIAS.get(unit.strip()) or UNIT_ALIAS.get(u, unit.strip() or "")


# ---------------------------------------------------------------------------
# LLM 解析
# ---------------------------------------------------------------------------
def _parse_with_llm(text: str) -> Optional[Dict[str, Any]]:
    result = chat_completion_json(SYSTEM_PROMPT, text, temperature=0.1)
    if result is None:
        return None
    data = result.get("data") or {}
    activities = data.get("activities")
    if not isinstance(activities, list):
        return None
    items: List[ActivityItem] = []
    for raw in activities:
        if not isinstance(raw, dict):
            continue
        try:
            amount = float(raw.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        items.append(ActivityItem(
            activity=str(raw.get("activity") or "").strip(),
            description=str(raw.get("description") or "").strip(),
            amount=amount,
            unit=_normalize_unit(str(raw.get("unit") or "")),
            region=str(raw.get("region") or "中国").strip(),
            period=str(raw.get("period") or "2026 年").strip(),
            industry=str(raw.get("industry") or "").strip(),
            boundary=str(raw.get("boundary") or "").strip(),
            confidence=0.9,
        ))
    suggestions = data.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []
    return {
        "items": items,
        "llm_suggestions": [str(s) for s in suggestions if str(s).strip()],
        "meta": result,
    }


# ---------------------------------------------------------------------------
# 规则降级解析（确定性，无大模型时可用）
# ---------------------------------------------------------------------------
def _parse_with_rules(text: str) -> List[ActivityItem]:
    items: List[ActivityItem] = []
    unit_rules: List[tuple] = [
        ("小时", "办公"), ("公里", "开车"), ("km", "开车"), ("千米", "开车"),
        ("度", "用电"), ("kwh", "用电"), ("升", "柴油"), ("l", "柴油"),
        ("吨", "钢铁"), ("t", "钢铁"), ("kg", "钢铁"), ("公斤", "钢铁"),
        ("立方米", "天然气"), ("m3", "天然气"), ("方", "天然气"),
    ]
    seen = set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)", text):
        num = float(m.group(1))
        tail = text[m.end():m.end() + 8]
        window = text[max(0, m.start() - 10):m.end() + 12]
        activity: Optional[str] = None
        unit = ""
        for kw, act in unit_rules:
            if tail.lower().startswith(kw.lower()) or kw.lower() in tail.lower():
                activity = act
                unit = _normalize_unit(kw)
                break
        if activity is None:
            for kw, act in KEYWORD_RULES:
                if kw in window:
                    activity = act
                    break
        if not activity:
            continue
        key = (activity, round(num, 3))
        if key in seen:
            continue
        seen.add(key)
        items.append(ActivityItem(
            activity=activity,
            description=window.strip(),
            amount=num,
            unit=unit or "km",
            region="中国",
            period="2026 年",
            boundary="",
            confidence=0.6,
        ))
    return items


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def parse_activities(text: str, form_items: Optional[list] = None) -> Dict[str, Any]:
    """解析入口。

    返回统一结构：
        {
          "items": [ActivityItem...],
          "llm_used": bool,
          "model": str | None,
          "prompt_version": str,
          "duration_ms": int,
          "llm_suggestions": [str],
          "fallback_reason": str | None,
        }
    """
    # 表单模式：直接使用结构化明细，无需 LLM
    if form_items:
        items = []
        for f in form_items:
            items.append(ActivityItem(
                activity=f.activity_type,
                description=f"表单录入",
                amount=f.amount,
                unit=_normalize_unit(f.unit) if f.unit else "",
                region="中国",
                period="2026 年",
                confidence=0.8,
            ))
        return {
            "items": items,
            "llm_used": False,
            "model": None,
            "prompt_version": PROMPT_VERSION,
            "duration_ms": 0,
            "llm_suggestions": [],
            "fallback_reason": "form",
        }

    if not text or not text.strip():
        return {
            "items": [], "llm_used": False, "model": None,
            "prompt_version": PROMPT_VERSION, "duration_ms": 0,
            "llm_suggestions": [], "fallback_reason": "empty_input",
        }

    # 1) 尝试 LLM
    llm = _parse_with_llm(text)
    if llm is not None and llm["items"]:
        llm["llm_used"] = True
        llm["prompt_version"] = PROMPT_VERSION
        llm["fallback_reason"] = None
        return llm

    # 2) 规则降级
    items = _parse_with_rules(text)
    return {
        "items": items,
        "llm_used": False,
        "model": None,
        "prompt_version": PROMPT_VERSION,
        "duration_ms": llm["meta"]["duration_ms"] if llm else 0,
        "llm_suggestions": [],
        "fallback_reason": "llm_unavailable_or_empty" if llm is not None else "llm_not_configured",
    }
