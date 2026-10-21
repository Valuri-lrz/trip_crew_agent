"""配置：全项目唯一读环境变量的地方。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    vision_model: str
    amap_key: str
    tavily_key: str
    db_path: Path
    demo_mode: bool
    day_budget_min: int
    think: bool
    max_items_per_day: int

    @property
    def llm_ready(self) -> bool:
        return bool(self.api_key) and not self.demo_mode

    @property
    def amap_ready(self) -> bool:
        # 占位符不算配好，否则每次都要白等一轮超时
        if not self.amap_key or self.demo_mode:
            return False
        return not self.amap_key.lower().startswith(('your-', 'amap-key'))


def load_settings() -> Settings:
    api_key = _env("DEEPSEEK_API_KEY")
    amap_key = _env("AMAP_KEY") or _env("AMAP_API_KEY")
    forced = _env("DEMO_MODE", "0") == "1"
    return Settings(
        api_key=api_key,
        base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=_env("MODEL_NAME", "deepseek-flash"),
        vision_model=_env("VISION_MODEL") or _env("MODEL_NAME", "deepseek-flash"),
        amap_key=amap_key,
        tavily_key=_env("TAVILY_API_KEY"),
        db_path=_path(_env("DB_PATH", "data/travel.db")),
        # 没有模型 key 就无法理解语言，直接进演示模式
        demo_mode=forced or not api_key,
        day_budget_min=int(_env("DAY_BUDGET_MIN", "480")),
        think=_env("THINK", "1") != "0",
        max_items_per_day=int(_env("MAX_ITEMS_PER_DAY", "3")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
