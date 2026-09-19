from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


def _secret_or_env(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        import streamlit as st

        secret_value = st.secrets.get(name, "")
        return str(secret_value) if secret_value else default
    except Exception:
        return default


@dataclass
class LLMSettings:
    provider: str = "演示模式"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.2
    timeout: int = 45

    @property
    def enabled(self) -> bool:
        return self.provider != "演示模式" and bool(self.api_key and self.base_url and self.model)


def default_settings(provider: str) -> LLMSettings:
    if provider == "DeepSeek":
        return LLMSettings(
            provider=provider,
            api_key=_secret_or_env("DEEPSEEK_API_KEY"),
            base_url=_secret_or_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            model=_secret_or_env("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    if provider == "通义千问":
        return LLMSettings(
            provider=provider,
            api_key=_secret_or_env("DASHSCOPE_API_KEY"),
            base_url=_secret_or_env(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            model=_secret_or_env("DASHSCOPE_MODEL", "qwen-plus"),
        )
    if provider == "自定义兼容接口":
        return LLMSettings(
            provider=provider,
            api_key=_secret_or_env("CUSTOM_API_KEY"),
            base_url=_secret_or_env("CUSTOM_BASE_URL"),
            model=_secret_or_env("CUSTOM_MODEL"),
        )
    return LLMSettings(provider="演示模式")


def chat_completion(settings: LLMSettings, system_prompt: str, user_prompt: str) -> str:
    if not settings.enabled:
        raise RuntimeError("LLM 未启用。")

    url = settings.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=settings.timeout)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def parse_json_object(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("模型返回内容不是 JSON。")
    return json.loads(match.group(0))
