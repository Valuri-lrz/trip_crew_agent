"""配图：从维基共享资源找实景照片，找不到就当场画一张占位图。

为什么用 Commons：免费、不用 key、图片有来源、中文地名也能搜到。
为什么一定要有兜底：网络不通时页面不能出现一排破图。
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from functools import lru_cache

UA = "travel-agent/0.1 (personal project; contact: local)"
API = "https://commons.wikimedia.org/w/api.php"


@lru_cache(maxsize=256)
def search(query: str, width: int = 480) -> tuple[str, ...]:
    """返回最多 3 张图的缩略图地址。失败返回空元组。"""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrnamespace": "6", "gsrsearch": query, "gsrlimit": "3",
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": str(width),
    }
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode("utf-8"))
        pages = (data.get("query") or {}).get("pages") or {}
        out = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            link = info.get("thumburl") or info.get("url")
            if link:
                out.append(link)
        return tuple(out)
    except Exception:
        return ()


def photo_for(name: str, city: str = "") -> str | None:
    """优先高德的点位实景图（国内可用），其次维基共享资源。"""
    try:
        from travel.live import search_places

        hits = search_places(f"{city}{name}".strip() or name, city, limit=1)
        if hits:
            shots = hits[0].get("photos") or []
            if shots:
                return shots[0]
            # 名字对不上时再放宽一次
            hits = search_places(name, city, limit=1)
            if hits and (hits[0].get("photos") or []):
                return hits[0]["photos"][0]
    except Exception:
        pass

    for q in (f"{city} {name}".strip(), name):
        got = search(q)
        if got:
            return got[0]
    return None


_PALETTE = [
    ("#c98b6b", "#a9542f"), ("#7d9a86", "#46695a"),
    ("#b9a07a", "#8a7248"), ("#8a93a8", "#4f5768"),
]


def placeholder(name: str) -> str:
    """占位图：按名字取一个稳定配色，写上地名。永远渲染得出来。"""
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    a, b = _PALETTE[h % len(_PALETTE)]
    safe = (name or "?").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320" viewBox="0 0 480 320">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>
<rect width="480" height="320" fill="url(#g)"/>
<circle cx="392" cy="74" r="46" fill="#ffffff" opacity="0.14"/>
<path d="M0 250 L120 190 L220 240 L330 180 L480 235 L480 320 L0 320 Z" fill="#000000" opacity="0.16"/>
<text x="28" y="288" font-size="26" fill="#ffffff" opacity="0.94"
 font-family="PingFang SC,Microsoft YaHei,sans-serif">{safe}</text>
</svg>"""
