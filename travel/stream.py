"""把一句话流式吐出来。

为什么要单独一层：CrewAI 的 kickoff 是阻塞的，拿不到 token。
所以结构化那部分（画像/点位/攻略）继续用 CrewAI，
只有"说出来"这一层改成直接流式调用——用户看到的是字一个个出来。
"""
from __future__ import annotations

from typing import Iterator

from travel.config import get_settings

SITUATION_STYLE = """你是个话不多但靠谱的旅行搭子。你不说"为您服务"，也不列 1234，
就像朋友发微信。你现在要把下面这段草稿说给用户听。"""


def _fallback(text: str, n: int = 4) -> Iterator[str]:
    for i in range(0, len(text), n):
        yield text[i:i + n]


def stream_reply(situation: str, draft: str) -> Iterator[str]:
    """优先真流式；任何失败都退回按块吐，保证前端不空着。"""
    s = get_settings()
    if not s.llm_ready or not draft.strip():
        yield from _fallback(draft)
        return

    try:
        from openai import OpenAI

        client = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=60)
        stream = client.chat.completions.create(
            model=s.model,
            messages=[
                {"role": "system", "content": SITUATION_STYLE},
                {"role": "user", "content":
                    f"现在的情况：{situation}\n\n草稿：{draft}\n\n"
                    "改写成你会说的话：口语，自然，长度随内容。"
                    "不许新增事实（天气/价格/评分/营业时间）。只输出这句话。"},
            ],
            temperature=0.7,
            max_tokens=1200,
            stream=True,
            extra_body={"thinking": {"type": "disabled"}},
        )
        got = False
        for chunk in stream:
            piece = chunk.choices[0].delta.content if chunk.choices else None
            if piece:
                got = True
                yield piece
        if not got:
            yield from _fallback(draft)
    except Exception:
        yield from _fallback(draft)
