"""天气查询工具"""
import os
import requests
from dotenv import load_dotenv
from crewai.tools import tool

load_dotenv()


@tool("get_weather_forecast")
def get_weather_forecast(city: str, days: int = 3) -> str:
    """
    查询指定城市未来几天的天气预报。
    输入：城市名称（如"大理"），天数（默认3天）
    输出：天气预报信息
    """
    amap_key = os.getenv("AMAP_API_KEY")

    if not amap_key:
        return (
            f"[天气工具未配置] 城市: {city}\n"
            "请设置 AMAP_API_KEY 环境变量。\n"
            "当前假设天气良好，适合户外活动。"
        )

    try:
        # 1. 城市编码查询
        geo_url = "https://restapi.amap.com/v3/geocode/geo"
        geo_resp = requests.get(geo_url, params={
            "key": amap_key,
            "address": city
        })
        geo_data = geo_resp.json()

        if geo_data.get("geocodes"):
            adcode = geo_data["geocodes"][0]["adcode"]
        else:
            return f"未找到城市: {city}"

        # 2. 天气查询
        weather_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        weather_resp = requests.get(weather_url, params={
            "key": amap_key,
            "city": adcode,
            "extensions": "all"  # 预报
        })
        weather_data = weather_resp.json()

        forecasts = weather_data.get("forecasts", [])
        if not forecasts:
            return f"未获取到 {city} 的天气数据"

        result = [f"📍 {city} 天气预报："]
        for cast in forecasts[0].get("casts", [])[:days]:
            result.append(
                f"  {cast['date']} | {cast['dayweather']} | "
                f"{cast['nighttemp']}~{cast['daytemp']}°C | "
                f"风力{cast['daypower']}级"
            )

        return "\n".join(result)

    except Exception as e:
        return f"天气查询出错: {str(e)}"