"""联网攻略 → 结构化事实。

为什么不能"直接总结成一段话"：
攻略互相矛盾（2022 说 20 元，2024 说 50 元），直接总结会抹平矛盾，
输出一段读起来很确定、其实谁也不知道的文字。

所以这里的规矩：
1. 每条事实必须能指回第几条来源
2. 同一字段出现不同值 → 不选边，写进 conflicts
3. 摘要里没有的，一个字都不许补
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GuideFact(BaseModel):
    field: str = Field(default="", description="门票 / 开放时间 / 怎么去 / 排队 / 适合谁 / 注意")
    value: str = ""
    source: int = Field(default=-1, description="来自第几条摘要，从 0 开始")
    year_hint: str = Field(default="", description="这条里出现的年份，没有就空")


class GuideBundle(BaseModel):
    facts: list[GuideFact] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


def summarize(name: str, city: str, snippets: list[dict]) -> GuideBundle | None:
    """把搜索摘要抽成事实 + 冲突。失败返回 None。"""
    from travel import agents

    if not snippets:
        return None
    try:
        return agents.run_guide_summary(name, city, snippets)
    except Exception:
        return None


def collect(name: str, city: str) -> tuple[GuideBundle | None, str]:
    """先去网上找，再抽。返回 (结果, 状态说明)。"""
    from travel import live

    hits = live.web_search(f"{city} {name} 门票 开放时间 攻略")
    if not hits:
        return None, "没有搜索 key，查不了网上的攻略"
    return summarize(name, city, hits), f"查到 {len(hits)} 条"
