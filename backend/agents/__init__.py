"""AI 碳核算 Agent 包。

首版实现"一次 LLM 调用完成解析与建议"，Agent 体现为明确的代码职责：
    Activity Parser → Factor Selector → Calculation Service → Verification
    → Recommendation → Ledger Writer（由 Orchestrator 编排）

LLM 未配置或调用失败时，自动降级到确定性规则，保证核算链路可用。
"""
from agents.orchestrator import run_pipeline

__all__ = ["run_pipeline"]
