"""Single source of truth for model/API settings."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

MODEL_ALIASES = {
    "deepseek-v4.1-flash": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}


def model_name() -> str:
    raw = os.getenv("MODEL_NAME", "deepseek-flash").strip()
    return MODEL_ALIASES.get(raw, raw)


def base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


def api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，请检查 .env")
    return key


def provider_prefix() -> str:
    return os.getenv("LLM_PROVIDER_PREFIX", "openai").strip() or "openai"
