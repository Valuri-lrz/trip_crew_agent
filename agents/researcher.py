"""Agent 2: 目的地深度研究"""
from crewai import Agent, Task
from config.llm_config import get_llm
from tools.search_tool import search_destination
from tools.weather_tool import get_weather_forecast


def create_researcher_agent() -> Agent:
    return Agent(
        role="目的地深度研究员",
        goal="""
基于用户画像，深度研究目的地信息。
不只推荐热门景点，要挖掘匹配隐性偏好的小众体验。
每个推荐说明"为什么匹配这个用户"。
标注体力消耗和天气依赖性。
""",
        backstory="""你是一位在当地生活了10年的文化人类学家。
你知道哪些地方是游客不会去的，哪些体验只有本地人才懂。""",
        llm=get_llm(temperature=0.7),  # ← 统一模型
        tools=[search_destination, get_weather_forecast],
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )


def create_research_task(destination: str, user_profiles: str, days: int = 3) -> Task:
    agent = create_researcher_agent()

    return Task(
        description=f"""
【目的地】{destination}
【天数】{days}天
【用户画像】
{user_profiles}

【任务】
1. 搜索匹配用户偏好的活动（含小众选项）
2. 查询天气
3. 为每个活动提供6维情感评分
4. 标注时段/天气依赖/社交属性/隐性偏好匹配

【输出】
{{
    "destination": "{destination}",
    "weather_summary": "...",
    "activities": [
        {{
            "name": "...",
            "location": "...",
            "description": "...",
            "best_time_slot": "上午",
            "weather_dependency": "outdoor",
            "social_type": "小群体",
            "emotion_score": {{
                "excitement": 0.7, "relaxation": 0.4,
                "novelty": 0.8, "social_fulfillment": 0.5,
                "aesthetic_pleasure": 0.9, "fatigue_cost": 0.6
            }},
            "matches_implicit_preference": "...",
            "social_multiplier": 0.2,
            "min_group_size": 1
        }}
    ]
}}
""",
        agent=agent,
        expected_output="目的地研究结果 JSON",
    )