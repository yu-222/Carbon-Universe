"""LLM 客户端（OpenAI 兼容 Chat Completions）。

配置方式（环境变量或 backend/.env，优先级由高到低）：
    LLM_API_KEY   /  LLM_BASE_URL  /  LLM_MODEL
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL

- LLM_BASE_URL 示例：https://api.openai.com/v1、https://dashscope.aliyuncs.com/compatible-mode/v1
- LLM_MODEL 示例：gpt-4o-mini、deepseek-chat、qwen-plus、moonshot-v1-8k 等
- 未配置或调用失败时：chat_completion_json() 返回 None，上层 Agent 自动降级到确定性规则。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)
CHAT_URL = "/chat/completions"


def _load_dotenv() -> None:
    """轻量读取 backend/.env（存在且变量未设置时写入环境）。"""
    if not os.path.exists(_ENV_FILE):
        return
    try:
        with open(_ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except OSError:
        pass


def get_config() -> Optional[Dict[str, str]]:
    """返回 LLM 配置；未配置 API Key 时返回 None（调用方降级）。

    本地模型（Ollama / LM Studio 等 OpenAI 兼容端点，base_url 指向
    localhost/127.0.0.1）无需真实 API Key，留空即可启用。
    """
    _load_dotenv()
    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    is_local = any(host in base_url.lower() for host in ("localhost", "127.0.0.1", "0.0.0.0"))
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key and not is_local:
        return None
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    return {"api_key": api_key or "", "base_url": base_url, "model": model}


def chat_completion_json(
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 60.0,
) -> Optional[Dict[str, Any]]:
    """调用一次 Chat Completions 并解析 JSON 输出。

    返回（调用成功）：
        {
          "data": <dict>,            # 模型返回的 JSON 对象
          "model": str,              # 实际使用的模型名
          "duration_ms": int,        # 本次调用耗时
          "prompt_tokens": int, "completion_tokens": int,
          "status": "ok",
        }
    未配置 / 网络失败 / 解析失败时返回 None，由调用方降级。
    """
    cfg = get_config()
    if cfg is None or httpx is None:
        return None
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    started = time.perf_counter()
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    try:
        resp = httpx.post(
            cfg["base_url"] + CHAT_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        usage = body.get("usage", {})
        return {
            "data": data,
            "model": cfg["model"],
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "status": "ok",
        }
    except Exception:
        return None
