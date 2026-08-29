"""全球碳价数据源适配器。

- 默认数据源：本地 `data/carbon_prices.json`（演示数据）。
- 预留真实数据源：设置环境变量 `CARBON_PRICE_API_URL` 后，自动切换为请求
  外部 HTTP 接口（返回格式需与本地文件一致：顶层含 `markets` 数组）。
  接入真实行情只需改一个环境变量，前端与接口结构均不变。
- 远程数据源不可用时自动降级为本地演示数据，保证接口始终可用。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "carbon_prices.json"
REMOTE_URL = os.getenv("CARBON_PRICE_API_URL", "").rstrip("/")
REMOTE_TIMEOUT = 5.0

_LOCAL_LABEL = "演示数据（本地 JSON，价格水平参考公开市场区间）"


def _load_local() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        raise RuntimeError("碳价数据文件缺失")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _load_remote() -> Dict[str, Any]:
    resp = httpx.get(REMOTE_URL, timeout=REMOTE_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "markets" in data:
        return data
    if isinstance(data, list):
        return {"markets": data}
    raise ValueError("远程碳价数据格式不兼容（需含 markets 数组）")


def load_all() -> Dict[str, Any]:
    """返回统一结构：{source, source_label, updated_at, market_count, markets:[...]}"""
    if REMOTE_URL:
        try:
            data = _load_remote()
            data.setdefault("source", "remote")
            data.setdefault("source_label", "实时行情（外部平台）")
            data.setdefault("updated_at", "")
            return data
        except Exception as exc:  # 远程失败 -> 降级本地，保证可用
            data = _load_local()
            data["source"] = "local"
            data["source_label"] = f"演示数据（远程行情不可用，已降级：{exc}）"
            data["updated_at"] = data.get("updated_at", "")
            return data
    data = _load_local()
    data.setdefault("updated_at", "")
    return data


def list_markets() -> Dict[str, Any]:
    """市场概要（不含 series），供下拉列表与行情卡使用。"""
    data = load_all()
    keys = ("market_id", "name", "region", "ccy", "unit", "price", "change_pct")
    return {
        "source": data.get("source", "local"),
        "source_label": data.get("source_label", _LOCAL_LABEL),
        "updated_at": data.get("updated_at", ""),
        "market_count": len(data.get("markets", [])),
        "markets": [{k: m[k] for k in keys if k in m} for m in data.get("markets", [])],
    }


def get_market(market_id: str) -> Optional[Dict[str, Any]]:
    """单个市场完整行情（含 series 走势），不存在返回 None。"""
    for m in load_all().get("markets", []):
        if m.get("market_id") == market_id:
            return m
    return None
