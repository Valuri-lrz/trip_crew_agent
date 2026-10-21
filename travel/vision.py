"""视觉：参考图 → 三层偏好线索。

一次调用看全部图片，返回标签、证据和三层判断。
没有 key 时返回 None，上层自动退回文字规则。
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from travel.config import get_settings

PROMPT = """你在帮旅行助手读一张参考图。用户可能只是随手存了一张喜欢的图。

用户原话：{text}

第一步：先认地方。能认出就写名字（如"挪威 罗弗敦群岛 雷讷"），认不出就按
"场景类型"描述（如"雪后的北欧渔村"），不要硬猜城市。

第二步：把画面拆成可判断的维度，不要说"很美""很安静"这种糊话：
- geo：地形。sea / mountain / lake / village / city / desert / forest
- weather：雪 / 雨 / 晴 / 雾 / 极夜 / 极昼
- light：蓝调 / 朝阳 / 逆光 / 夜间灯光 / 阴天
- human：无人 / 三两人 / 人群 / 集市
- activity：摄影 / 徒步 / 自驾 / 发呆 / 逛街 / 吃
- cost：低 / 中 / 高（从住宿形态、地貌偏远程度估）
- crowd：空 / 少 / 多

第三步：判断"这地方和常规国内游差多远"：
- far=true 表示这是境外 / 极地 / 需要长线交通的地方，国内库对不上
- far=false 表示国内能找到接近的

第四步：给 5 个标签，要具体（"雪后渔村""冷到发蓝""极夜""木屋暖灯"），
不要写"安静""治愈"这种放之四海皆准的词。

输出 JSON：
{{
  "place_guess": "认出来的地名，认不出写场景类型",
  "country": "国家/地区，猜不到写空",
  "scene": {{"geo": [], "weather": [], "light": [], "human": [],
             "activity": [], "cost": "", "crowd": ""}},
  "far": true/false,
  "tags": ["5 个具体标签"],
  "summary": "一句话：这张图在说一种什么体验",
  "evidence": ["画面里的具体证据，3 条以内"],
  "aesthetic": {{"quiet_lively": -1~1, "nature_urban": -1~1,
                 "minimal_ornate": -1~1, "warm_cool": -1~1, "classic_trendy": -1~1}},
  "emotion": {{"restore": 0~1, "novelty": 0~1, "control": 0~1,
               "belong": 0~1, "beauty": 0~1, "achieve": 0~1}},
  "social": {{"together": -1~1, "participate": -1~1, "crowd_tolerance": 0~1}},
  "confidence": 0~1
}}

字段含义：
  quiet_lively  负=安静 正=热闹        nature_urban  负=自然 正=城市
  minimal_ornate 负=极简 正=繁复       warm_cool     负=温暖 正=冷冽
  classic_trendy 负=老派 正=新潮
  restore 想放松 novelty 想新鲜 control 想被安排 belong 想有人陪
  beauty 想看好看 achieve 想有点挑战
  together 负=独处 正=结伴          crowd_tolerance 0=怕人多 1=喜欢人气"""


def _data_url(path: str, max_side: int = 1280) -> str:
    from PIL import Image, ImageOps

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def analyze(paths: list[str], text: str = "") -> dict | None:
    """返回 {"tags", "summary", "evidence", "aesthetic", "emotion", "social", "confidence"}。"""
    s = get_settings()
    files = [p for p in paths if p and Path(p).is_file()][:3]
    if not files or not s.llm_ready:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=60)
        content: list[dict] = [{"type": "text", "text": PROMPT.format(text=text or "（没有文字）")}]
        for f in files:
            content.append({"type": "image_url",
                            "image_url": {"url": _data_url(f), "detail": "high"}})
        resp = client.chat.completions.create(
            model=s.vision_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=800,
            extra_body={"thinking": {"type": "disabled"}},
        )
        raw = resp.choices[0].message.content or ""
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1] if start >= 0 else raw)
    except Exception:
        return None
