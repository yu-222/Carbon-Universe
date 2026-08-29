"""Factor Selector Agent —— 按地区、行业、年份和单位选择排放因子。

匹配策略（按优先级）：
    1. 活动匹配：因子 aliases 与活动名做包含/相等匹配，取匹配得分最高者
    2. 地区匹配：国家/省市区归一化后匹配 region_code；匹配不到时退回"全球"
    3. 年份匹配：取 <= 活动年份的最新因子版本；活动年份缺失时取最新
    4. 单位换算：因子单位与活动单位不一致时，按换算表折算（金额不变，因子按系数换算）

选择结果同时给出：因子 ID、数值、版本、来源、适用范围与匹配说明，
供 Ledger Writer 原样记录。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

FACTORS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "emission_factors.json",
)

# 地区/省市区 → 国家码（用于匹配因子表的 region_code）
REGION_TO_CODE = {
    "中国": "CN", "中国大陆": "CN", "北京": "CN", "上海": "CN", "广东": "CN",
    "深圳": "CN", "广州": "CN", "浙江": "CN", "江苏": "CN", "四川": "CN",
    "山东": "CN", "福建": "CN", "湖北": "CN", "湖南": "CN", "河南": "CN",
    "美国": "US", "美利坚": "US", "usa": "US", "united states": "US",
    "英国": "UK", "英格兰": "UK", "uk": "UK", "united kingdom": "UK",
    "德国": "DE", "germany": "DE",
    "法国": "FR", "france": "FR",
    "欧盟": "EU", "欧洲": "EU", "eu": "EU", "europe": "EU",
    "印度": "IN", "india": "IN",
    "日本": "JP", "japan": "JP",
    "澳大利亚": "AU", "australia": "AU",
    "巴西": "BR", "brazil": "BR",
    "全球": "WD", "世界": "WD", "国际": "WD", "默认": "WD", "world": "WD",
}

# 单位换算：把"活动单位"折算到"因子单位"时的系数
# factor_unit ← activity_unit: factor_per_factor_unit * CONV[factor_unit][activity_unit]
UNIT_CONV: Dict[str, Dict[str, float]] = {
    # 1 MWh = 1000 kWh
    "kWh": {"MWh": 1000.0, "kWh": 1.0},
    # 1 t = 1000 kg
    "t": {"kg": 0.001, "t": 1.0, "万t": 10000.0},
    "kg": {"t": 1000.0, "kg": 1.0},
    # 1 km = 1000 m
    "km": {"m": 0.001, "km": 1.0},
    # 1 GJ = 1000 MJ
    "MJ": {"GJ": 1000.0, "MJ": 1.0},
}

# 表单活动类型 → 因子库活动名
FORM_TYPE_MAP = {
    "用电": "用电", "出行": "开车", "餐饮": "餐饮", "办公": "办公",
    "电力": "用电", "开车": "开车", "飞机": "飞机", "天然气": "天然气",
    "柴油": "柴油", "汽油": "汽油", "钢铁": "钢铁", "水泥": "水泥",
    "铝": "铝", "供热": "供热", "蒸汽": "蒸汽", "地铁": "地铁", "公交": "公交",
    "外卖": "外卖", "居家": "居家", "电炉钢": "电炉钢",
}

_FACTORS_CACHE: Optional[List[Dict[str, Any]]] = None
_DOC_CACHE: Optional[Dict[str, Any]] = None


def load_document() -> Dict[str, Any]:
    """返回完整因子库文档（schema_version + factors），供 /api/carbon/factors 与审计。"""
    global _DOC_CACHE
    if _DOC_CACHE is None:
        with open(FACTORS_FILE, "r", encoding="utf-8") as f:
            _DOC_CACHE = json.load(f)
    return _DOC_CACHE


def load_factors() -> List[Dict[str, Any]]:
    global _FACTORS_CACHE
    if _FACTORS_CACHE is None:
        _FACTORS_CACHE = load_document()["factors"]
    return _FACTORS_CACHE


def _year_of(period: Optional[str]) -> Optional[int]:
    if not period:
        return None
    m = re.search(r"(20\d{2})", str(period))
    return int(m.group(1)) if m else None


def _activity_score(factor: Dict[str, Any], activity: str) -> int:
    """活动匹配得分：0 不匹配；1 别名包含；2 完全相等。"""
    act = (activity or "").strip().lower()
    if not act:
        return 0
    names = [str(factor.get("activity", "")).lower()] + [
        str(a).lower() for a in factor.get("aliases", [])
    ]
    if act in names:
        return 2
    for n in names:
        if n and (n in act or act in n):
            return 1
    return 0


def _region_code(region: Optional[str]) -> Optional[str]:
    if not region:
        return None
    r = region.strip()
    if r in REGION_TO_CODE:
        return REGION_TO_CODE[r]
    lower = r.lower()
    for k, v in REGION_TO_CODE.items():
        if k.lower() in lower or lower in k.lower():
            return v
    return None


def _unit_factor(factor_unit: str, activity_unit: str) -> Optional[float]:
    """返回把活动单位折算到因子单位时的倍数；无法换算返回 None。"""
    if not factor_unit or not activity_unit:
        return None
    fu, au = factor_unit.strip(), activity_unit.strip()
    if fu == au:
        return 1.0
    table = UNIT_CONV.get(fu)
    if table is None:
        return None
    return table.get(au)


def select(item: Any, factors: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """为单个活动项选择因子并换算单位。

    返回：
        {
          "factor": {...因子条目...},
          "factor_value": float,        # 换算到活动单位后的因子值（kgCO2e/活动单位）
          "factor_unit": str,           # 因子库原始单位
          "converted": bool,            # 是否发生单位换算
          "conv_note": str,             # 换算说明
          "year": int | None,           # 实际采用的因子年份
          "year_note": str,             # 年份匹配说明
        }
    无匹配返回 None。
    """
    factors = factors or load_factors()
    activity = FORM_TYPE_MAP.get(item.activity, item.activity)
    code = _region_code(item.region)

    candidates = []
    for f in factors:
        score = _activity_score(f, activity)
        if score == 0:
            continue
        # 地区匹配：code 相同 > 全球兜底 > 其他
        f_code = f.get("region_code")
        if code and f_code:
            region_score = 2 if f_code == code else (1 if f_code == "WD" else 0)
        else:
            region_score = 1 if f_code == "WD" else 0
        candidates.append((score + region_score, f))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score = candidates[0][0]
    pool = [f for s, f in candidates if s == best_score]

    # 年份：取 <= 活动年份的最新版本；无年份约束取最新
    year = _year_of(item.period)
    if year:
        usable = [f for f in pool if int(f.get("year", 0)) <= year]
        if usable:
            chosen = max(usable, key=lambda f: (int(f.get("year", 0)), f.get("id", "")))
        else:
            chosen = min(pool, key=lambda f: int(f.get("year", 0)))
    else:
        chosen = max(pool, key=lambda f: (int(f.get("year", 0)), f.get("id", "")))

    # 单位换算
    fu = str(chosen.get("unit", ""))
    au = item.unit or ""
    conv = _unit_factor(fu, au)
    factor_value = float(chosen["factor"])
    converted = False
    conv_note = ""
    if conv is not None and conv != 1.0:
        factor_value = round(factor_value * conv, 6)
        converted = True
        conv_note = f"因子原始单位 {fu} → 活动单位 {au}，按 {conv} 换算"
    elif conv is None:
        conv_note = f"因子单位 {fu} 与活动单位 {au or '未知'} 不一致，未换算"

    return {
        "factor": chosen,
        "factor_value": factor_value,
        "factor_unit": fu,
        "converted": converted,
        "conv_note": conv_note,
        "year": int(chosen.get("year", 0)),
        "year_note": (
            f"活动年份 {year}，采用 {chosen['year']} 版因子"
            if year else f"未指定年份，采用最新 {chosen['year']} 版因子"
        ),
    }
