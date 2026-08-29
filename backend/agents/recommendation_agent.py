"""Recommendation Agent —— 根据主要排放项给出可执行减排建议。

策略：
    1. 优先复用 LLM 单次调用产出的 suggestions；
    2. 未配置 LLM / 表单模式时，按排放占比排序，针对 Top 排放活动给出规则库建议。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 规则建议库：category/activity → 建议列表
RULE_BANK: Dict[str, List[str]] = {
    "电力": [
        "优先采购绿色电力，提升可再生能源电力占比，可显著降低范围二排放。",
        "对高耗能设备进行能效审计，用节能电机/变频器替代落后设备。",
        "在分时电价时段错峰用电，并将照明/空调升级为一级能效产品。",
    ],
    "开车": [
        "优先采用公共交通、拼车或骑行，可显著降低出行碳排放。",
        "将公务车辆电动化，并优化运输路线减少空驶里程。",
        "保持经济时速驾驶，避免急加速急刹车，可节省 10%~20% 油耗。",
    ],
    "飞机": [
        "优先选择高铁替代短途航班；中长途航班尽量直飞、减少中转。",
        "差旅政策中纳入碳预算，鼓励视频会议替代非必要出行。",
    ],
    "公交": [
        "持续引导员工使用公共交通出行，并将通勤补贴向低碳方式倾斜。",
    ],
    "地铁": [
        "推广地铁/轨道交通通勤，并把低碳出行纳入员工碳账户积分。",
    ],
    "天然气": [
        "开展锅炉/窑炉余热回收，提高燃料利用效率。",
        "评估生物质、绿氢等替代燃料的经济性与减排潜力。",
    ],
    "柴油": [
        "优化物流调度降低柴油消耗，并评估电动/氢能重卡替代方案。",
    ],
    "汽油": [
        "将汽油车更新为新能源车，并建设配套充电基础设施。",
    ],
    "钢铁": [
        "提高废钢比、发展电弧炉短流程炼钢，可显著降低吨钢排放。",
        "对高炉工序实施能效提升与余能回收，探索绿氢直接还原工艺。",
    ],
    "电炉钢": [
        "提升绿电使用比例，推动电炉钢全生命周期低碳化。",
    ],
    "水泥": [
        "提升熟料替代率（掺合料），并推进低碳胶凝材料研发应用。",
        "在水泥窑协同处置与富氧燃烧技术上加大投入。",
    ],
    "铝": [
        "电解铝优先使用绿电，并提高再生铝使用比例。",
    ],
    "供热": [
        "实施建筑围护结构保温改造，降低采暖热负荷。",
        "将燃煤锅炉替换为燃气/生物质，并推广集中供热与热泵。",
    ],
    "蒸汽": [
        "回收冷凝水与闪蒸汽，提高蒸汽系统综合能效。",
    ],
    "外卖": [
        "减少一次性餐具与过度包装，鼓励自备餐具与堂食。",
    ],
    "餐饮": [
        "减少食物浪费，适当增加植物性饮食占比，可有效降低碳足迹。",
    ],
    "办公": [
        "合理设置空调温度（夏季≥26℃、冬季≤20℃），下班关闭待机设备。",
        "推进无纸化办公与节能灯具改造，将节能纳入部门考核。",
    ],
    "居家": [
        "使用智能插座与节能家电，避免待机能耗。",
    ],
}

# 活动名 → 规则建议键
ACTIVITY_KEY: Dict[str, str] = {
    "用电": "电力", "开车": "开车", "飞机": "飞机", "公交": "公交", "地铁": "地铁",
    "天然气": "天然气", "柴油": "柴油", "汽油": "汽油", "钢铁": "钢铁",
    "电炉钢": "电炉钢", "水泥": "水泥", "铝": "铝", "供热": "供热", "蒸汽": "蒸汽",
    "外卖": "外卖", "餐饮": "餐饮", "办公": "办公", "居家": "居家",
}


def recommend(pipeline: Dict[str, Any]) -> List[str]:
    """生成建议。

    入参 pipeline 包含：
        items: List[ActivityItem]
        calcs: List[calculate 结果]
        llm_suggestions: List[str]
    返回建议列表（去重，最多 3 条）。
    """
    llm_suggestions = pipeline.get("llm_suggestions") or []
    if llm_suggestions:
        return [s for s in llm_suggestions if s.strip()][:3]

    items = pipeline.get("items", [])
    calcs = pipeline.get("calcs", [])
    # 计算每项占比
    total = sum(c["emission"] for c in calcs if c) or 0.0
    scored = []
    for idx, item in enumerate(items):
        calc = calcs[idx] if idx < len(calcs) else None
        if not calc:
            continue
        key = ACTIVITY_KEY.get(item.activity)
        tips = RULE_BANK.get(key) if key else None
        if not tips:
            continue
        share = calc["emission"] / total if total else 0.0
        scored.append((share, tips))

    scored.sort(key=lambda x: x[0], reverse=True)
    result: List[str] = []
    seen = set()
    for share, tips in scored:
        for t in tips:
            if t in seen:
                continue
            seen.add(t)
            result.append(t)
        if len(result) >= 3:
            break
    return result[:3]
