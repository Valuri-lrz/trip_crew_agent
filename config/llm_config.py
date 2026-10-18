"""DeepSeek LLM 统一配置 - 全部使用多模态模型"""
import os
from dotenv import load_dotenv
from crewai import LLM

load_dotenv()

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4.1-flash")


def get_llm(temperature: float = 0.7, max_tokens: int = 4096) -> LLM:
    """
    统一模型入口

    DeepSeek-V4.1-Flash：
    - 支持图片输入（多模态）
    - 所有Agent统一使用此模型
    """
    return LLM(
        model=f"deepseek/{MODEL_NAME}",
        base_url=DEEPSEEK_BASE_URL,
        api_key=DEEPSEEK_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
    )