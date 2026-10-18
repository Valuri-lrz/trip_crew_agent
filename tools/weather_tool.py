"""高德天气工具。

修复点：
- 加 timeout，避免请求挂死
- 校验高德 status/info，不再“假设天气良好”
- 城市名找不到时尝试“市/自治州”后缀
"""
from __future__ import annotations

import os

import requests
from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


def _get_adcode(city: str, key: str) -> tuple[str | None, str]:
    """Return (adcode, error).  error is '' on success."""
    candidates = [city]
    if not city.endswith(("市", "州", "县", "区")):
        candidates.extend([f"{city}市", f"{city}白族自治州"])

    last_info = "not_found"
    for address in candidates:
        response = requests.get(
            GEO_URL,
            params={"key": key, "address": address},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "1" and data.get("geocodes"):
            return data["geocodes"][0].get("adcode"), ""
        last_info = data.get("info", last_info)
        if last_info == "INVALID_USER_KEY":
            break
    return None, last_info


@tool("get_weather_forecast")
def get_weather_forecast(city: str, days: int = 3) -> str:
    """
    查询指定城市未来几天的天气预报。
    输入：城市名称（如"大理"），天数（默认3天）
    输出：天气预报信息；不可用时明确说明，不要假设天气良好。
    """
    api_key = os.getenv("AMAP_API_KEY", "").strip()
    if not api_key:
        return (
            f"[天气不可用] 未配置 AMAP_API_KEY。城市：{city}\n"
            "请明确写“天气需核实”，不要假设适合户外活动。"
        )

    try:
        adcode, geo_error = _get_adcode(city, api_key)
        if not adcode:
            if geo_error == "INVALID_USER_KEY":
                return "[天气不可用] AMAP_API_KEY 无效或已过期，请检查高德控制台。"
            return f"[天气不可用] 高德未找到城市“{city}”（{geo_error}），请写“天气需核实”。"

        response = requests.get(
            WEATHER_URL,
            params={"key": api_key, "city": adcode, "extensions": "all"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"[天气查询失败] {type(exc).__name__}: {exc}\n请写“天气需核实”。"

    if data.get("status") != "1":
        return f"[天气查询失败] 高德返回：{data.get('info', 'unknown')}\n请写“天气需核实”。"

    forecasts = data.get("forecasts") or []
    if not forecasts:
        return f"[天气不可用] 未获取到 {city} 的预报，请写“天气需核实”。"

    casts = forecasts[0].get("casts") or []
    if not casts:
        return f"[天气不可用] {city} 的预报为空，请写“天气需核实”。"

    lines = [f"📍 {city} 天气预报（高德）："]
    for cast in casts[: max(1, min(days, 7))]:
        lines.append(
            f"  {cast.get('date', '')} | {cast.get('dayweather', '')}/"
            f"{cast.get('nightweather', '')} | "
            f"{cast.get('nighttemp', '?')}~{cast.get('daytemp', '?')}°C | "
            f"风力 {cast.get('daypower', '?')} 级"
        )
    return "\n".join(lines)
