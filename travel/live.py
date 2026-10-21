"""外部数据：高德（天气 / 地理编码 / 路线 / 地点搜索）+ 联网搜索。

统一约定：拿不到就返回 None，绝不编造。
每一个 get_* 都是"边界上的归一化函数"——上层只认这里返回的形状。
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from travel.config import get_settings

_CACHE: dict[str, tuple[float, object]] = {}
AMAP = "https://restapi.amap.com/v3"


def _cached(key: str, ttl: int, fn):
    now = time.time()
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts < ttl:
            return val
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _amap(path: str, params: dict, ttl: int = 1800):
    s = get_settings()
    if not s.amap_ready:
        return None
    params = dict(params, key=s.amap_key)

    def call():
        try:
            url = f"{AMAP}/{path}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
            if str(data.get("status")) != "1":
                return None
            return data
        except Exception:
            return None

    return _cached(f"amap:{path}:{urllib.parse.urlencode(params)}", ttl, call)


def weather(adcode: str) -> list[dict] | None:
    """未来几天天气。返回 [{date, text, temp}]，拿不到返回 None。"""
    data = _amap("weather/weatherInfo", {"city": adcode, "extensions": "all"}, ttl=1800)
    if not data:
        return None
    casts = (data.get("forecasts") or [{}])[0].get("casts") or []
    return [{"date": c.get("date", ""), "text": f"{c.get('dayweather','')}",
             "temp": f"{c.get('nighttemp','')}~{c.get('daytemp','')}℃"} for c in casts]


def is_bad_weather(text: str) -> bool:
    return any(k in (text or "") for k in ("雨", "雪", "雷", "风", "雾"))


def geocode(name: str, city: str) -> tuple[float, float] | None:
    data = _amap("geocode/geo", {"address": name, "city": city})
    if not data:
        return None
    try:
        loc = data["geocodes"][0]["location"].split(",")
        return float(loc[0]), float(loc[1])
    except Exception:
        return None


def drive_minutes(o: tuple[float, float], d: tuple[float, float]) -> int | None:
    data = _amap("direction/driving", {
        "origin": f"{o[0]:.6f},{o[1]:.6f}",
        "destination": f"{d[0]:.6f},{d[1]:.6f}",
        "strategy": 0,
    })
    if not data:
        return None
    try:
        path = data["route"]["paths"][0]
        return max(1, round(int(path["duration"]) / 60))
    except Exception:
        return None


def travel_minutes(a: tuple[float, float] | None, b: tuple[float, float] | None) -> int:
    """两点通勤时间。有高德就用真实值，没有就按同城 20 分钟估。"""
    if a and b:
        real = drive_minutes(a, b)
        if real is not None:
            return real
    return 20


def search_places(keyword: str, city: str, limit: int = 5) -> list[dict] | None:
    """高德地点搜索：真实存在的店/景点。拿不到返回 None。"""
    data = _amap("place/text", {"keywords": keyword, "city": city,
                                "citylimit": "true", "offset": limit}, ttl=3600)
    if not data:
        return None
    out = []
    for p in (data.get("pois") or [])[:limit]:
        out.append({
            "name": p.get("name", ""),
            "type": p.get("type", ""),
            "address": p.get("address", ""),
            "location": p.get("location", ""),
            # 高德会带点位实景图，配图优先用它（国内可访问）
            "photos": [ph.get("url", "") for ph in (p.get("photos") or []) if ph.get("url")],
        })
    return out


def web_search(query: str) -> list[dict] | None:
    """联网搜索。没有 key 就返回 None，由上层标注"需核实"。"""
    key = get_settings().tavily_key
    if not key:
        return None
    try:
        body = json.dumps({"api_key": key, "query": query,
                           "max_results": 3, "search_depth": "basic"}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [{"title": x.get("title", ""), "url": x.get("url", ""),
                 "content": (x.get("content") or "")[:300]} for x in data.get("results", [])]
    except Exception:
        return None


def _first(v):
    """高德的 biz_ext 有时是 dict、有时是单元素 list，两种都兜住。"""
    if isinstance(v, list):
        return v[0] if v else ""
    return v if v is not None else ""


def place_facts(name: str, city: str) -> dict | None:
    """点位的"真事实"：评分、人均、营业时间、地址。拿不到返回 None。"""
    data = _amap("place/text", {
        "keywords": name, "city": city, "citylimit": "true",
        "extensions": "all", "offset": 1,
    }, ttl=86400)
    if not data:
        return None
    pois = data.get("pois") or []
    if not pois:
        return None
    p = pois[0]
    biz = p.get("biz_ext") or {}
    facts = {
        "name": p.get("name", name),
        "address": p.get("address", ""),
        "tel": _first(p.get("tel")),
        "rating": _first(biz.get("rating")) if isinstance(biz, dict) else "",
        "cost": _first(biz.get("cost")) if isinstance(biz, dict) else "",
        "open_time": _first(biz.get("open_time")) if isinstance(biz, dict) else "",
        "type": p.get("type", ""),
    }
    if not any(facts[k] for k in ("rating", "address", "open_time", "cost")):
        return None
    return facts
