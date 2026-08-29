"""生成全球碳市场模拟价格数据 -> data/carbon_prices.json

- 供黑客松演示使用：价格水平基于公开市场信息（2024-2026 主要碳市场价格区间）模拟，
  标注为"演示数据"。
- 该脚本为数据维护工具：接入真实行情后，可将外部数据按相同结构写入
  data/carbon_prices.json（或改走 price_source.py 的远程数据源），脚本保持幂等。

用法（在 backend 目录下执行）：
    python scripts/gen_carbon_prices.py
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

# market_id, 名称, 大区, 币种, 单位, 基准价(元/吨 或 对应币种)
MARKETS = [
    # ---- 中国 ----
    ("cn_cea",    "中国全国碳市场（CEA）",  "中国", "CNY", "元/吨",  96.5),
    ("cn_bj",     "北京碳排放权（BEA）",    "中国", "CNY", "元/吨", 105.8),
    ("cn_sh",     "上海碳排放权（SHEA）",   "中国", "CNY", "元/吨",  76.4),
    ("cn_gd",     "广东碳排放权（GDEA）",   "中国", "CNY", "元/吨",  64.2),
    ("cn_sz",     "深圳碳排放权（SZEA）",   "中国", "CNY", "元/吨",  61.5),
    ("cn_hb",     "湖北碳排放权（HBEA）",   "中国", "CNY", "元/吨",  43.1),
    ("cn_cq",     "重庆碳排放权（CQEA）",   "中国", "CNY", "元/吨",  46.7),
    ("cn_tj",     "天津碳排放权（TJEA）",   "中国", "CNY", "元/吨",  35.9),
    ("cn_fj",     "福建碳排放权（FJEA）",   "中国", "CNY", "元/吨",  28.6),
    # ---- 欧盟 / 欧洲 ----
    ("eu_ets",    "欧盟碳配额（EUA）",      "欧盟", "EUR", "欧元/吨", 68.5),
    ("uk_ets",    "英国碳排放权（UKA）",    "欧盟", "GBP", "英镑/吨", 42.0),
    # ---- 美洲 ----
    ("us_ca",     "美国加州配额（CCA）",    "美洲", "USD", "美元/吨", 39.8),
    # ---- 亚太 ----
    ("kr_kau",    "韩国碳排放权（KAU）",    "亚太", "KRW", "韩元/吨", 9550.0),
    ("nz_nzu",    "新西兰碳单位（NZU）",    "亚太", "NZD", "纽元/吨", 63.4),
]

POINTS = 30          # 每个市场近 30 个交易日收盘价
DAILY_VOL = 0.012    # 单日波动幅度（±1.2%）


def gen_series(base: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    pts = [base]
    for _ in range(1, POINTS):
        drift = rng.uniform(-DAILY_VOL, DAILY_VOL)
        pts.append(round(pts[-1] * (1 + drift), 2))
    # 缩放使终点精确等于当前价
    scale = base / pts[-1]
    pts = [round(p * scale, 2) for p in pts]
    pts[-1] = round(base, 2)
    return pts


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    out = data_dir / "carbon_prices.json"

    markets = []
    for idx, (mid, name, region, ccy, unit, base) in enumerate(MARKETS, start=1):
        series = gen_series(base, seed=idx * 1007)
        prev = series[-2]
        change_pct = round((series[-1] / prev - 1) * 100, 2)
        markets.append({
            "market_id": mid,
            "name": name,
            "region": region,
            "ccy": ccy,
            "unit": unit,
            "price": series[-1],
            "change_pct": change_pct,
            "high": round(max(series), 2),
            "low": round(min(series), 2),
            "source": "演示数据（本地 JSON，价格水平参考公开市场区间）",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "series": series,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_count": len(markets),
        "markets": markets,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK -> {out}  ({len(markets)} markets, {POINTS} points each)")


if __name__ == "__main__":
    main()
