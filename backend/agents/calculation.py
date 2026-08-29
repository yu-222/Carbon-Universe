"""Calculation Service —— 执行确定性排放公式，绝不依赖 LLM 心算。

公式：emission = amount × factor
结果单位为 kgCO₂e；若因子已换算到活动单位，则直接相乘。

所有数值一律用 Decimal 兜底避免浮点误差，保留 6 位小数。
"""
from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict

getcontext().prec = 28

RESULT_UNIT = "kgCO₂e"


def calculate(amount: float, factor_value: float,
              activity_unit: str, factor_unit: str) -> Dict[str, Any]:
    """确定性计算。

    返回：
        {
          "emission": float,          # kgCO₂e
          "formula": str,             # 人类可读公式
          "result_unit": str,
          "amount": float,
          "factor_value": float,
          "activity_unit": str,
          "factor_unit": str,
        }
    """
    emission_decimal = Decimal(str(amount)) * Decimal(str(factor_value))
    emission = round(float(emission_decimal), 6)
    formula = (
        f"{amount} {activity_unit or '?'} × {factor_value} "
        f"kgCO₂e/{factor_unit or '?'} = {emission} {RESULT_UNIT}"
    )
    return {
        "emission": emission,
        "formula": formula,
        "result_unit": RESULT_UNIT,
        "amount": float(amount),
        "factor_value": float(factor_value),
        "activity_unit": activity_unit,
        "factor_unit": factor_unit,
    }
