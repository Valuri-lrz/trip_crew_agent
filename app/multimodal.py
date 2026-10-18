"""DeepSeek vision pre-analysis for user reference images.

One call per user (all their images in one message) keeps latency/cost low.
The result is plain text + JSON that is injected into the Profiler task, so the
text-only Crew remains the single orchestration path.
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Sequence

from openai import OpenAI
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.settings import api_key, base_url, model_name


class VisualProfile(BaseModel):
    summary: str = Field(description="图片整体传达的旅行氛围")
    mood: str = Field(default="", description="情绪基调，如 平静/热闹/浪漫/野性")
    implicit_needs: list[str] = Field(default_factory=list, description="图片暗示的隐性需求")
    evidence: list[str] = Field(default_factory=list, description="支撑判断的画面线索")
    confidence: float = Field(default=0.6, ge=0, le=1)


def _client() -> OpenAI:
    return OpenAI(api_key=api_key(), base_url=base_url(), timeout=60)


def _data_url(path: str, max_side: int = 1280) -> str:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _json_text(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def analyze_images(paths: Sequence[str], user_text: str = "") -> VisualProfile:
    """Analyze up to 3 local images for one traveler.

    Returns an empty VisualProfile if no images.  Raises on API/format errors;
    the caller decides whether to degrade to text-only.
    """
    paths = [p for p in paths if p and Path(p).is_file()][:3]
    if not paths:
        return VisualProfile(summary="未上传参考图片", confidence=0.0)

    prompt = f"""你在帮旅行规划系统做“多模态隐性偏好推理”。
用户文字：{user_text or "（无）"}

请只根据图片中可观察到的线索，推理这位用户可能喜欢的旅行氛围。
不要描述“图片里有什么”作为结论，要给出“这暗示了什么需求”。
不要编造图片中不存在的信息。

只输出 JSON，字段：
{{
  "summary": "一句话整体氛围",
  "mood": "平静/热闹/浪漫/野性/治愈/探索 等",
  "implicit_needs": ["隐性需求1", "隐性需求2"],
  "evidence": ["画面线索1", "画面线索2"],
  "confidence": 0.0-1.0
}}"""

    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": _data_url(path), "detail": "low"},
        })

    response = _client().chat.completions.create(
        model=model_name(),
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1200,
        extra_body={"thinking": {"type": "disabled"}},
    )
    raw = response.choices[0].message.content or ""
    return VisualProfile.model_validate(json.loads(_json_text(raw)))
